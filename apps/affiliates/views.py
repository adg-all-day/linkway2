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
from apps.products.models import Product

from .models import AffiliateLink, ClickTracking
from .serializers import AffiliateLinkSerializer, GenerateAffiliateLinkSerializer
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
