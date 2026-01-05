from datetime import datetime, timedelta
import os

from django.conf import settings
from django.core.cache import caches
from django.db import connections
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response

from apps.affiliates.models import AffiliateLink, ClickTracking
from apps.ai_services.models import ProductRecommendation
from apps.analytics.models import FraudDetectionLog
from apps.analytics.serializers import FraudDetectionLogSerializer
from apps.authentication.models import User
from apps.authentication.permissions import IsAdmin, IsMarketer, IsSeller
from apps.commissions.models import Commission
from apps.orders.models import Order
from apps.products.models import Product


class MarketerDashboardView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsMarketer]

    def get(self, request, *args, **kwargs):
        user = request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        interval = request.query_params.get("interval", "monthly")
        if interval not in ("daily", "weekly", "monthly"):
            interval = "monthly"

        total_earned = (
            Commission.objects.filter(
                marketer=user,
                status__in=["approved", "paid"],
            ).aggregate(total_amount=Sum("net_commission"))
        )["total_amount"] or 0

        clicks_this_month = ClickTracking.objects.filter(
            link__marketer=user,
            clicked_at__gte=start_of_month,
        ).count()

        conversions_this_month = Order.objects.filter(
            marketer=user,
            created_at__gte=start_of_month,
            status__in=["processing", "shipped", "delivered"],
        ).count()

        pending_payout = (
            Commission.objects.filter(
                marketer=user,
                status__in=["earned", "held", "approved"],
            ).aggregate(total_amount=Sum("net_commission"))
        )["total_amount"] or 0

        recent_commissions = Commission.objects.filter(
            marketer=user,
        ).order_by("-created_at")[:10]

        recent_commission_data = [
            {
                "id": str(c.id),
                "order_id": str(c.order_id),
                "product_id": str(c.product_id) if c.product_id else None,
                "commission_amount": float(c.commission_amount),
                "net_commission": float(c.net_commission or 0),
                "status": c.status,
                "created_at": c.created_at,
            }
            for c in recent_commissions
        ]

        recommended_products = ProductRecommendation.objects.filter(
            marketer=user,
        ).order_by("-recommendation_score")[:10]

        recommended_products_data = [
            {
                "id": r.id,
                "product_id": r.product_id,
                "recommendation_score": float(r.recommendation_score),
                "recommendation_reason": r.recommendation_reason,
                "match_factors": r.match_factors,
            }
            for r in recommended_products
        ]

        # Earnings and clicks time series
        if interval == "daily":
            start_date = now - timedelta(days=29)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            step = timedelta(days=1)
        elif interval == "weekly":
            start_date = now - timedelta(weeks=11)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            step = timedelta(weeks=1)
        else:  # monthly
            # 11 months ago, start of that month
            year = now.year
            month = now.month - 11
            while month <= 0:
                year -= 1
                month += 12
            start_date = datetime(year, month, 1, tzinfo=now.tzinfo)
            step = "monthly"

        earnings_points: list[dict] = []
        clicks_points: list[dict] = []

        if interval in ("daily", "weekly"):
            # Build buckets
            current = start_date
            buckets: list[tuple[datetime, str, str]] = []
            while current <= now:
                if interval == "daily":
                    key = current.date().isoformat()
                    label = current.strftime("%d %b")
                else:  # weekly
                    iso_year, iso_week, _ = current.isocalendar()
                    key = f"{iso_year}-W{iso_week:02d}"
                    label = f"W{iso_week}"
                buckets.append((current, key, label))
                current = current + step  # type: ignore[operator]

            earnings_map = {key: 0.0 for _, key, _ in buckets}
            clicks_map = {key: 0 for _, key, _ in buckets}

            commissions = Commission.objects.filter(
                marketer=user,
                status__in=["approved", "paid"],
                created_at__gte=start_date,
            )
            for c in commissions:
                dt = c.created_at
                if interval == "daily":
                    key = dt.date().isoformat()
                else:
                    iso_year, iso_week, _ = dt.isocalendar()
                    key = f"{iso_year}-W{iso_week:02d}"
                if key in earnings_map:
                    earnings_map[key] += float(c.net_commission or 0)

            clicks = ClickTracking.objects.filter(
                link__marketer=user,
                clicked_at__gte=start_date,
            )
            for clk in clicks:
                dt = clk.clicked_at
                if interval == "daily":
                    key = dt.date().isoformat()
                else:
                    iso_year, iso_week, _ = dt.isocalendar()
                    key = f"{iso_year}-W{iso_week:02d}"
                if key in clicks_map:
                    clicks_map[key] += 1

            for _, key, label in buckets:
                earnings_points.append({"period": key, "label": label, "amount": round(earnings_map[key], 2)})
                clicks_points.append({"period": key, "label": label, "clicks": clicks_map[key]})

        else:
            # Monthly buckets: last 12 months
            buckets: list[tuple[int, int, str, str]] = []
            year = start_date.year
            month = start_date.month
            for _ in range(12):
                key = f"{year}-{month:02d}"
                dt = datetime(year, month, 1, tzinfo=now.tzinfo)
                label = dt.strftime("%b %Y")
                buckets.append((year, month, key, label))
                month += 1
                if month > 12:
                    month = 1
                    year += 1

            earnings_map = {key: 0.0 for _, _, key, _ in buckets}
            clicks_map = {key: 0 for _, _, key, _ in buckets}

            commissions = Commission.objects.filter(
                marketer=user,
                status__in=["approved", "paid"],
                created_at__gte=start_date,
            )
            for c in commissions:
                dt = c.created_at
                key = f"{dt.year}-{dt.month:02d}"
                if key in earnings_map:
                    earnings_map[key] += float(c.net_commission or 0)

            clicks = ClickTracking.objects.filter(
                link__marketer=user,
                clicked_at__gte=start_date,
            )
            for clk in clicks:
                dt = clk.clicked_at
                key = f"{dt.year}-{dt.month:02d}"
                if key in clicks_map:
                    clicks_map[key] += 1

            for _, _, key, label in buckets:
                earnings_points.append({"period": key, "label": label, "amount": round(earnings_map[key], 2)})
                clicks_points.append({"period": key, "label": label, "clicks": clicks_map[key]})

        # Best selling products and commission per product
        marketer_orders = Order.objects.filter(
            marketer=user,
            status__in=["processing", "shipped", "delivered"],
        )

        best_products_qs = (
            marketer_orders.values("product_id", "product__name")
            .annotate(total_sales=Count("id"), total_revenue=Sum("total_amount"))
            .order_by("-total_sales")[:10]
        )

        commissions_by_product = (
            Commission.objects.filter(marketer=user)
            .values("product_id")
            .annotate(total_commission=Sum("net_commission"))
        )
        commission_map = {
            row["product_id"]: float(row["total_commission"] or 0) for row in commissions_by_product
        }

        best_selling_products = [
            {
                "product_id": row["product_id"],
                "product_name": row["product__name"],
                "total_sales": row["total_sales"],
                "total_revenue": float(row["total_revenue"] or 0),
                "total_commission": commission_map.get(row["product_id"], 0.0),
            }
            for row in best_products_qs
        ]

        commission_per_product = sorted(
            best_selling_products,
            key=lambda x: x["total_commission"],
            reverse=True,
        )

        data = {
            "metrics": {
                "totalEarned": float(total_earned),
                "clicksThisMonth": clicks_this_month,
                "conversionsThisMonth": conversions_this_month,
                "pendingPayout": float(pending_payout),
            },
            "earningsChart": {
                "interval": interval,
                "points": earnings_points,
            },
            "clicksChart": {
                "interval": interval,
                "points": clicks_points,
            },
            "bestSellingProducts": best_selling_products,
            "commissionPerProduct": commission_per_product,
            "recentCommissions": recent_commission_data,
            "recommendedProducts": recommended_products_data,
            "isLoading": False,
        }

        return Response(data, status=status.HTTP_200_OK)


class SellerDashboardView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsSeller]

    def get(self, request, *args, **kwargs):
        user = request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        interval = request.query_params.get("interval", "monthly")
        if interval not in ("daily", "weekly", "monthly"):
            interval = "monthly"

        seller_orders = Order.objects.filter(seller=user)

        total_revenue = (
            seller_orders.filter(
                status__in=["processing", "shipped", "delivered"],
            ).aggregate(total_amount=Sum("total_amount"))
        )["total_amount"] or 0

        orders_this_month = seller_orders.filter(created_at__gte=start_of_month).count()

        products_count = Product.objects.filter(seller=user, is_active=True).count()

        clicks_this_month = ClickTracking.objects.filter(
            link__product__seller=user,
            clicked_at__gte=start_of_month,
        ).count()

        top_products_qs = (
            seller_orders.filter(
                status__in=["processing", "shipped", "delivered"],
            )
            .values("product_id", "product__name")
            .annotate(order_count=Count("id"), revenue=Sum("total_amount"))
            .order_by("-order_count")[:10]
        )

        top_products = [
            {
                "product_id": row["product_id"],
                "product_name": row["product__name"],
                "order_count": row["order_count"],
                "revenue": float(row["revenue"] or 0),
            }
            for row in top_products_qs
        ]

        orders_by_marketer_qs = (
            seller_orders.filter(
                marketer__isnull=False,
                status__in=["processing", "shipped", "delivered"],
            )
            .values("marketer_id", "marketer__full_name", "marketer__email")
            .annotate(order_count=Count("id"), revenue=Sum("total_amount"))
        )

        top_marketers_qs = orders_by_marketer_qs.order_by("-revenue")[:10]

        top_marketers = [
            {
                "marketer_id": row["marketer_id"],
                "marketer_name": row["marketer__full_name"],
                "marketer_email": row["marketer__email"],
                "order_count": row["order_count"],
                "revenue": float(row["revenue"] or 0),
            }
            for row in top_marketers_qs
        ]

        orders_by_marketer_map = {
            row["marketer_id"]: {
                "order_count": row["order_count"],
                "revenue": float(row["revenue"] or 0),
            }
            for row in orders_by_marketer_qs
        }

        links_qs = (
            AffiliateLink.objects.filter(
                product__seller=user,
                is_active=True,
            )
            .values("marketer_id", "marketer__full_name", "marketer__email")
            .annotate(
                link_count=Count("id"),
                total_clicks=Sum("click_count"),
            )
        )

        marketers_with_links: list[dict] = []
        seen_marketer_ids: set[str] = set()

        for row in links_qs:
            marketer_id = row["marketer_id"]
            orders_info = orders_by_marketer_map.get(
                marketer_id,
                {"order_count": 0, "revenue": 0.0},
            )
            marketers_with_links.append(
                {
                    "marketer_id": marketer_id,
                    "marketer_name": row["marketer__full_name"],
                    "marketer_email": row["marketer__email"],
                    "link_count": row["link_count"],
                    "click_count": int(row["total_clicks"] or 0),
                    "order_count": orders_info["order_count"],
                    "revenue": orders_info["revenue"],
                }
            )
            seen_marketer_ids.add(marketer_id)

        for row in orders_by_marketer_qs:
            marketer_id = row["marketer_id"]
            if marketer_id in seen_marketer_ids:
                continue
            marketers_with_links.append(
                {
                    "marketer_id": marketer_id,
                    "marketer_name": row["marketer__full_name"],
                    "marketer_email": row["marketer__email"],
                    "link_count": 0,
                    "click_count": 0,
                    "order_count": row["order_count"],
                    "revenue": float(row["revenue"] or 0),
                }
            )

        # Earnings and clicks time series for seller
        if interval == "daily":
            start_date = now - timedelta(days=29)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            step = timedelta(days=1)
        elif interval == "weekly":
            start_date = now - timedelta(weeks=11)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            step = timedelta(weeks=1)
        else:
            # 11 months ago, start of that month
            year = now.year
            month = now.month - 11
            while month <= 0:
                year -= 1
                month += 12
            start_date = datetime(year, month, 1, tzinfo=now.tzinfo)
            step = "monthly"

        earnings_points: list[dict] = []
        clicks_points: list[dict] = []

        if interval in ("daily", "weekly"):
            current = start_date
            buckets: list[tuple[datetime, str, str]] = []
            while current <= now:
                if interval == "daily":
                    key = current.date().isoformat()
                    label = current.strftime("%d %b")
                else:
                    iso_year, iso_week, _ = current.isocalendar()
                    key = f"{iso_year}-W{iso_week:02d}"
                    label = f"W{iso_week}"
                buckets.append((current, key, label))
                current = current + step  # type: ignore[operator]

            earnings_map = {key: 0.0 for _, key, _ in buckets}
            clicks_map = {key: 0 for _, key, _ in buckets}

            orders_for_chart = seller_orders.filter(
                status__in=["processing", "shipped", "delivered"],
                created_at__gte=start_date,
            )
            for order in orders_for_chart:
                dt = order.created_at
                if interval == "daily":
                    key = dt.date().isoformat()
                else:
                    iso_year, iso_week, _ = dt.isocalendar()
                    key = f"{iso_year}-W{iso_week:02d}"
                if key in earnings_map:
                    earnings_map[key] += float(order.total_amount or 0)

            clicks_qs = ClickTracking.objects.filter(
                link__product__seller=user,
                clicked_at__gte=start_date,
            )
            for clk in clicks_qs:
                dt = clk.clicked_at
                if interval == "daily":
                    key = dt.date().isoformat()
                else:
                    iso_year, iso_week, _ = dt.isocalendar()
                    key = f"{iso_year}-W{iso_week:02d}"
                if key in clicks_map:
                    clicks_map[key] += 1

            for _, key, label in buckets:
                earnings_points.append({"period": key, "label": label, "amount": round(earnings_map[key], 2)})
                clicks_points.append({"period": key, "label": label, "clicks": clicks_map[key]})

        else:
            # Monthly buckets: last 12 months
            buckets: list[tuple[int, int, str, str]] = []
            year = start_date.year
            month = start_date.month
            for _ in range(12):
                key = f"{year}-{month:02d}"
                dt = datetime(year, month, 1, tzinfo=now.tzinfo)
                label = dt.strftime("%b %Y")
                buckets.append((year, month, key, label))
                month += 1
                if month > 12:
                    month = 1
                    year += 1

            earnings_map = {key: 0.0 for _, _, key, _ in buckets}
            clicks_map = {key: 0 for _, _, key, _ in buckets}

            orders_for_chart = seller_orders.filter(
                status__in=["processing", "shipped", "delivered"],
                created_at__gte=start_date,
            )
            for order in orders_for_chart:
                dt = order.created_at
                key = f"{dt.year}-{dt.month:02d}"
                if key in earnings_map:
                    earnings_map[key] += float(order.total_amount or 0)

            clicks_qs = ClickTracking.objects.filter(
                link__product__seller=user,
                clicked_at__gte=start_date,
            )
            for clk in clicks_qs:
                dt = clk.clicked_at
                key = f"{dt.year}-{dt.month:02d}"
                if key in clicks_map:
                    clicks_map[key] += 1

            for _, _, key, label in buckets:
                earnings_points.append({"period": key, "label": label, "amount": round(earnings_map[key], 2)})
                clicks_points.append({"period": key, "label": label, "clicks": clicks_map[key]})

        best_selling_products = top_products

        data = {
            "metrics": {
                "totalRevenue": float(total_revenue),
                "ordersThisMonth": orders_this_month,
                "productsCount": products_count,
                "clicksOnLinksThisMonth": clicks_this_month,
            },
            "topProducts": top_products,
            "bestSellingProducts": best_selling_products,
            "marketersWithLinks": marketers_with_links,
            "earningsChart": {
                "interval": interval,
                "points": earnings_points,
            },
            "clicksChart": {
                "interval": interval,
                "points": clicks_points,
            },
            "topMarketers": top_marketers,
            "isLoading": False,
        }

        return Response(data, status=status.HTTP_200_OK)


class AdminDashboardView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request, *args, **kwargs):
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total_users = User.objects.count()
        sellers_count = User.objects.filter(role="seller").count()
        marketers_count = User.objects.filter(role="marketer").count()

        total_orders = Order.objects.count()
        paid_gmv = (
            Order.objects.filter(payment_status="paid").aggregate(total_amount=Sum("total_amount"))
        )["total_amount"] or 0

        orders_this_month = Order.objects.filter(created_at__gte=start_of_month).count()

        active_products = Product.objects.filter(is_active=True).count()

        pending_commissions = (
            Commission.objects.filter(status__in=["earned", "held", "approved"]).aggregate(
                total_amount=Sum("net_commission")
            )
        )["total_amount"] or 0

        from apps.commissions.models import Payout

        pending_payouts_amount = (
            Payout.objects.filter(status__in=["pending", "processing"]).aggregate(
                total_amount=Sum("total_amount")
            )
        )["total_amount"] or 0

        data = {
            "metrics": {
                "totalUsers": total_users,
                "sellersCount": sellers_count,
                "marketersCount": marketers_count,
                "totalOrders": total_orders,
                "ordersThisMonth": orders_this_month,
                "paidGMV": float(paid_gmv),
                "activeProducts": active_products,
                "pendingCommissions": float(pending_commissions),
                "pendingPayoutsAmount": float(pending_payouts_amount),
            },
            "isLoading": False,
        }

        return Response(data, status=status.HTTP_200_OK)


class SystemConfigView(views.APIView):
    """
    Read-only snapshot of key system configuration and integration status for admins.
    """

    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request, *args, **kwargs):
        # Database health
        db_ok = False
        db_error: str | None = None
        try:
            default_conn = connections["default"]
            with default_conn.cursor() as cursor:
                cursor.execute("SELECT 1;")
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            db_ok = False
            db_error = str(exc)

        # Cache health
        cache_ok = False
        cache_backend = settings.CACHES["default"]["BACKEND"]
        try:
            default_cache = caches["default"]
            default_cache.set("linkway_health_check", "ok", 5)
            cache_ok = default_cache.get("linkway_health_check") == "ok"
        except Exception:  # noqa: BLE001
            cache_ok = False

        openai_configured = bool(os.getenv("OPENAI_API_KEY"))
        paystack_public = bool(os.getenv("PAYSTACK_PUBLIC_KEY"))
        paystack_secret = bool(os.getenv("PAYSTACK_SECRET_KEY"))

        data = {
            "environment": {
                "debug": settings.DEBUG,
                "timezone": settings.TIME_ZONE,
            },
            "database": {
                "engine": settings.DATABASES["default"]["ENGINE"],
                "name": settings.DATABASES["default"]["NAME"],
                "healthy": db_ok,
                "error": db_error,
            },
            "cache": {
                "backend": cache_backend,
                "healthy": cache_ok,
            },
            "celery": {
                "broker_url": settings.CELERY_BROKER_URL,
                "result_backend": settings.CELERY_RESULT_BACKEND,
            },
            "integrations": {
                "openai": {
                    "configured": openai_configured,
                },
                "paystack": {
                    "public_key_set": paystack_public,
                    "secret_key_set": paystack_secret,
                },
            },
            "links": {
                "public_base_url": os.getenv("LINKWAY_PUBLIC_BASE_URL", ""),
                "frontend_base_url": os.getenv("FRONTEND_BASE_URL", ""),
            },
        }

        return Response(data, status=status.HTTP_200_OK)


class FraudLogListView(generics.ListAPIView):
    """
    Admin-only list of fraud detection logs for the Fraud Monitoring page.
    """

    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    serializer_class = FraudDetectionLogSerializer
    queryset = FraudDetectionLog.objects.all().order_by("-detected_at")
