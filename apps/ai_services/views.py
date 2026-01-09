import logging

from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.authentication.permissions import IsMarketer
from apps.affiliates.models import AffiliateLink

from .product_matcher import generate_product_recommendations
from .serializers import (
    GenerateContentSerializer,
    GenerateImageSerializer,
    ProductRecommendationSerializer,
)
from .services import generate_marketing_content, generate_marketing_image

logger = logging.getLogger(__name__)


class GenerateContentView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsMarketer]

    def post(self, request, *args, **kwargs):
        serializer = GenerateContentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        affiliate = (
            AffiliateLink.objects.filter(
                marketer=request.user,
                product_id=data["product_id"],
                is_active=True,
            )
            .order_by("-created_at")
            .first()
        )
        affiliate_url = affiliate.full_url if affiliate else None

        try:
            result = generate_marketing_content(
                marketer=request.user,
                product_id=str(data["product_id"]),
                content_type=data["content_type"],
                platform=data["platform"],
                tone=data.get("tone", "professional"),
                marketer_notes=data.get("marketer_notes", ""),
                affiliate_link=affiliate_url,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


class GenerateRecommendationsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsMarketer]

    def post(self, request, *args, **kwargs):
        limit = request.data.get("limit", 10)
        try:
            limit_int = int(limit)
        except (TypeError, ValueError):
            limit_int = 10
        recommendations = generate_product_recommendations(marketer=request.user, limit=limit_int)
        serializer = ProductRecommendationSerializer(recommendations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GenerateImageView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsMarketer]

    def post(self, request, *args, **kwargs):
        serializer = GenerateImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result = generate_marketing_image(
                marketer=request.user,
                product_id=str(data["product_id"]),
                style=data["style"],
                tone=data.get("tone", "bold"),
                marketer_notes=data.get("marketer_notes", ""),
                use_product_image=data.get("use_product_image", True),
            )
        except Exception:  # noqa: BLE001
            # Log full details for debugging, but keep response generic for users.
            logger.exception("AI image generation failed")
            return Response(
                {"detail": "Service temporarily unavailable, we're working on it."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result, status=status.HTTP_200_OK)
