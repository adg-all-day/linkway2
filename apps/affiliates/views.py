import os

from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.analytics.services import detect_fraud
from apps.authentication.models import User
from apps.products.models import Product

from .models import AffiliateLink, Catalogue, ClickTracking
from .serializers import AffiliateLinkSerializer, CatalogueSerializer, GenerateAffiliateLinkSerializer
from .services import create_or_update_attribution


class IsMarketer(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "marketer")


class AffiliateLinkViewSet(viewsets.ModelViewSet):
    queryset = AffiliateLink.objects.select_related("product", "marketer").all()
    serializer_class = AffiliateLinkSerializer
    permission_classes = [IsMarketer]

    def get_queryset(self):
        return self.queryset.filter(marketer=self.request.user)

    @action(detail=False, methods=["post"], url_path="generate")
    def generate_link(self, request: Request) -> Response:
        serializer = GenerateAffiliateLinkSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        link = serializer.save()
        return Response(AffiliateLinkSerializer(link).data, status=status.HTTP_201_CREATED)


class CatalogueViewSet(viewsets.ModelViewSet):
    """
    Marketer-only CRUD for package catalogues plus public read-only
    endpoints used by the shareable store pages.
    """

    queryset = Catalogue.objects.select_related("marketer").prefetch_related("links__product")
    serializer_class = CatalogueSerializer
    permission_classes = [IsMarketer]

    def get_queryset(self):
        if self.action in {"retrieve_public", "main"}:
            return self.queryset.filter(is_active=True)
        return self.queryset.filter(marketer=self.request.user, is_active=True)

    def perform_destroy(self, instance: Catalogue):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["get"], permission_classes=[permissions.AllowAny], url_path="public")
    def retrieve_public(self, request: Request, pk: str | None = None) -> Response:
        """
        Public read-only endpoint returning the products in a package catalogue.
        """
        catalogue = self.get_object()
        items = []
        for link in catalogue.links.select_related("product").filter(
            is_active=True,
            product__is_active=True,
        ):
            product = link.product
            first_image = None
            if isinstance(product.images, list) and product.images:
                first_image = product.images[0]
            items.append(
                {
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "price": str(product.price),
                    "description": product.short_description or product.description,
                    "image": first_image,
                    "affiliate_url": link.full_url,
                }
            )

        return Response(
            {
                "id": str(catalogue.id),
                "slug": catalogue.slug,
                "name": catalogue.name,
                "marketer": {
                    "id": str(catalogue.marketer.id),
                    "name": catalogue.marketer.full_name,
                },
                "items": items,
            }
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.AllowAny],
        url_path=r"main/(?P<marketer_id>[^/.]+)",
    )
    def main(self, request: Request, marketer_id: str | None = None) -> Response:
        """
        Public main catalogue: all active products this marketer is promoting.
        """
        marketer = get_object_or_404(User, id=marketer_id, role="marketer", is_active=True)
        links = (
            AffiliateLink.objects.select_related("product")
            .filter(marketer=marketer, is_active=True, product__is_active=True)
            .order_by("-created_at")
        )

        items = []
        for link in links:
            product = link.product
            first_image = None
            if isinstance(product.images, list) and product.images:
                first_image = product.images[0]
            items.append(
                {
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "price": str(product.price),
                    "description": product.short_description or product.description,
                    "image": first_image,
                    "affiliate_url": link.full_url,
                }
            )

        return Response(
            {
                "id": None,
                "slug": None,
                "name": "Main catalogue",
                "marketer": {
                    "id": str(marketer.id),
                    "name": marketer.full_name,
                },
                "items": items,
            }
        )


FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")


def _product_url(slug: str) -> str:
    if FRONTEND_BASE_URL:
        return f"{FRONTEND_BASE_URL.rstrip('/')}/products/{slug}"
    return f"/products/{slug}"


def handle_affiliate_click(request: HttpRequest, product_slug: str) -> HttpResponse:
    ref = request.GET.get("ref")
    if not ref:
        product = get_object_or_404(Product, slug=product_slug)
        return redirect(_product_url(product.slug))

    try:
        link = AffiliateLink.objects.select_related("product").get(unique_slug=ref, is_active=True)
    except AffiliateLink.DoesNotExist:
        product = get_object_or_404(Product, slug=product_slug)
        return redirect(_product_url(product.slug))

    if link.expires_at and link.expires_at < timezone.now():
        return redirect(_product_url(link.product.slug))

    ip_address = request.META.get("REMOTE_ADDR", "")
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    referrer = request.META.get("HTTP_REFERER", "")

    cookie_id = request.COOKIES.get("linkway_attr")
    if not cookie_id:
        if not request.session.session_key:
            request.session.create()
        cookie_id = request.session.session_key

    session_id = request.session.session_key

    attribution = create_or_update_attribution(cookie_id=cookie_id, affiliate_link=link, session_id=session_id)

    click = ClickTracking.objects.create(
        link=link,
        ip_address=ip_address or "0.0.0.0",
        user_agent=user_agent,
        referrer_url=referrer,
        landing_page_url=request.build_absolute_uri(),
        session_id=session_id,
        cookie_id=cookie_id,
    )

    detect_fraud("click", str(click.id))

    AffiliateLink.objects.filter(pk=link.pk).update(
        click_count=models.F("click_count") + 1, last_clicked_at=timezone.now()
    )

    response = redirect(_product_url(link.product.slug))
    max_age = 30 * 24 * 60 * 60
    response.set_cookie(
        "linkway_attr",
        cookie_id,
        max_age=max_age,
        httponly=True,
        secure=False,
        samesite="Lax",
    )
    return response
