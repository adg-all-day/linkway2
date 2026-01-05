from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List

from django.db.models import Count, Sum
from django.utils import timezone

from apps.affiliates.models import AffiliateLink
from apps.authentication.models import User
from apps.orders.models import Order
from apps.products.models import Product

from .models import ProductRecommendation


def extract_keywords(text: str) -> List[str]:
    tokens = re.split(r"[\\s,;/]+", text.lower())
    return [t for t in tokens if t]


def calculate_niche_match(marketer_niche: List[str], product_category: str) -> float:
    marketer_text = ", ".join(marketer_niche)
    marketer_keywords = set(extract_keywords(marketer_text))
    product_keywords = set(extract_keywords(product_category))

    if not marketer_keywords or not product_keywords:
        return 0.0

    intersection = marketer_keywords & product_keywords
    union = marketer_keywords | product_keywords

    if not union:
        return 0.0

    score = len(intersection) / len(union)

    if product_category.lower() in [n.lower() for n in marketer_niche]:
        score = min(score + 0.3, 1.0)

    return float(score)


def find_similar_marketers(marketer: User, limit: int = 20) -> List[str]:
    target_niche = marketer.niche_categories or []
    target_audience = marketer.audience_size or 0

    others = (
        User.objects.filter(role="marketer", is_active=True)
        .exclude(id=marketer.id)
        .only("id", "niche_categories", "audience_size")
    )

    similarities: List[Dict[str, float]] = []

    for other in others:
        niche_similarity = calculate_niche_match(
            marketer_niche=target_niche,
            product_category=", ".join(other.niche_categories or []),
        )

        if target_audience and other.audience_size:
            audience_ratio = min(
                target_audience / other.audience_size,
                other.audience_size / target_audience,
            )
        else:
            audience_ratio = 0.5

        combined = (niche_similarity * 0.7) + (audience_ratio * 0.3)

        similarities.append({"id": str(other.id), "similarity": combined})

    similarities.sort(key=lambda x: x["similarity"], reverse=True)
    return [s["id"] for s in similarities[:limit]]


def calculate_performance_scores(similar_marketers: List[str]) -> Dict[str, float]:
    if not similar_marketers:
        return {}

    conversions = (
        Order.objects.filter(
            marketer_id__in=similar_marketers,
            status__in=["processing", "shipped", "delivered"],
        )
        .values("product_id")
        .annotate(conversion_count=Count("id"))
    )
    clicks = (
        AffiliateLink.objects.filter(marketer_id__in=similar_marketers)
        .values("product_id")
        .annotate(total_clicks=Sum("click_count"))
    )

    conv_map = {row["product_id"]: row["conversion_count"] for row in conversions}
    click_map = {row["product_id"]: row["total_clicks"] for row in clicks}

    scores: Dict[str, float] = {}

    for product_id, total_clicks in click_map.items():
        conversions_for_product = conv_map.get(product_id, 0)
        if total_clicks == 0:
            score = 0.3
        else:
            conversion_rate = conversions_for_product / total_clicks
            score = min(conversion_rate / 0.05, 1.0)
        scores[str(product_id)] = float(score)

    return scores


def generate_reasoning(match_factors: Dict[str, float], product: Product) -> str:
    reasons: List[str] = []

    if match_factors.get("niche_match", 0.0) > 0.7:
        if product.category:
            reasons.append(f"Strong fit for your {product.category.name} niche")
        else:
            reasons.append("Strong fit for your audience niche")

    if match_factors.get("performance_history", 0.0) > 0.6:
        reasons.append("Similar marketers are converting well with this product")

    if match_factors.get("commission_potential", 0.0) > 0.7:
        reasons.append("High earning potential per sale")

    if match_factors.get("popularity", 0.0) > 0.7 and product.total_sales:
        reasons.append(f"Trending product with {product.total_sales} sales")

    if not reasons:
        reasons.append("Could be a good match for your audience")

    return ". ".join(reasons) + "."


def generate_product_recommendations(marketer: User, limit: int = 10) -> List[ProductRecommendation]:
    limit = max(1, min(limit, 50))
    marketer_niche = marketer.niche_categories or []

    products = Product.objects.filter(is_active=True)
    if not products.exists():
        return []

    similar_marketer_ids = find_similar_marketers(marketer, limit=20)
    performance_scores = calculate_performance_scores(similar_marketer_ids)

    max_potential = Decimal("0")
    max_sales = 0
    product_data: List[Dict[str, object]] = []

    for product in products.select_related("category"):
        niche_match = calculate_niche_match(
            marketer_niche=marketer_niche,
            product_category=product.category.name if product.category else "",
        )

        perf_score = performance_scores.get(str(product.id), 0.3)

        if product.commission_type == "percentage":
            potential = (product.price * product.commission_rate) / Decimal("100")
        else:
            potential = product.fixed_commission_amount or Decimal("0")

        max_potential = max(max_potential, potential)
        max_sales = max(max_sales, product.total_sales or 0)

        product_data.append(
            {
                "product": product,
                "niche_match": float(niche_match),
                "performance_history": float(perf_score),
                "raw_potential": potential,
                "total_sales": product.total_sales or 0,
            }
        )

    recommendations: List[Dict[str, object]] = []

    for item in product_data:
        product = item["product"]
        niche_match = item["niche_match"]
        perf_score = item["performance_history"]
        raw_potential: Decimal = item["raw_potential"]  # type: ignore[assignment]
        total_sales: int = item["total_sales"]  # type: ignore[assignment]

        if max_potential > 0:
            commission_potential = float(raw_potential / max_potential)
        else:
            commission_potential = 0.5

        if max_sales > 0:
            popularity = float(total_sales / max_sales)
        else:
            popularity = 0.5

        score = (
            (niche_match * 0.4)
            + (perf_score * 0.3)
            + (commission_potential * 0.2)
            + (popularity * 0.1)
        )

        match_factors = {
            "niche_match": round(niche_match, 3),
            "performance_history": round(perf_score, 3),
            "commission_potential": round(commission_potential, 3),
            "popularity": round(popularity, 3),
        }

        reasoning = generate_reasoning(match_factors, product)

        recommendations.append(
            {
                "product": product,
                "score": float(score),
                "match_factors": match_factors,
                "reasoning": reasoning,
            }
        )

    recommendations.sort(key=lambda x: x["score"], reverse=True)

    now = timezone.now()
    ProductRecommendation.objects.filter(marketer=marketer).delete()

    created: List[ProductRecommendation] = []
    for rec in recommendations[:limit]:
        created.append(
            ProductRecommendation.objects.create(
                marketer=marketer,
                product=rec["product"],
                recommendation_score=Decimal(str(rec["score"])),
                recommendation_reason=rec["reasoning"],
                match_factors=rec["match_factors"],
                expires_at=now + timedelta(days=7),
            )
        )

    return created

