from __future__ import annotations

import os
from datetime import timedelta
import base64
from io import BytesIO
from typing import Any, Dict

from django.db import transaction
from django.utils import timezone
from openai import OpenAI, PermissionDeniedError

from apps.authentication.models import User
from apps.products.models import Product, ProductCategory

from .models import AIContentLog


def _get_client() -> OpenAI:
    # Relies on OPENAI_API_KEY env var configured globally.
    return OpenAI()


def generate_marketing_content(
    marketer: User,
    product_id: str,
    content_type: str,
    platform: str,
    tone: str = "professional",
    marketer_notes: str = "",
    affiliate_link: str | None = None,
) -> Dict[str, Any]:
    now = timezone.now()
    one_hour_ago = now - timedelta(hours=1)

    recent_generations = AIContentLog.objects.filter(
        user=marketer,
        created_at__gt=one_hour_ago,
    ).count()
    if recent_generations >= 30:
        raise ValueError("Maximum 30 content generations per hour")

    product = Product.objects.select_related("category").get(id=product_id)
    category: ProductCategory | None = product.category

    prompt = build_content_prompt(
        content_type=content_type,
        platform=platform,
        tone=tone,
        product=product,
        category_name=category.name if category else "",
        marketer_niche=marketer.niche_categories or [],
        marketer_notes=marketer_notes or "",
    )

    system_prompt = get_system_prompt(content_type=content_type, platform=platform)

    client = _get_client()

    try:
        start_time = timezone.now()
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=500,
        )
        duration_ms = int((timezone.now() - start_time).total_seconds() * 1000)
        message = response.choices[0].message
        generated_content = message.content if isinstance(message.content, str) else "".join(
            part.text for part in message.content  # type: ignore[attr-defined]
        )
        tokens_used = getattr(response, "usage", None)
        if tokens_used is not None:
            total_tokens = response.usage.total_tokens  # type: ignore[attr-defined]
        else:
            total_tokens = 0
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to generate content: {exc}") from exc

    processed_content = post_process_content(
        content=generated_content,
        platform=platform,
        content_type=content_type,
        affiliate_link=affiliate_link,
    )

    with transaction.atomic():
        log = AIContentLog.objects.create(
            user=marketer,
            product=product,
            content_type=content_type,
            prompt=prompt,
            generated_content=processed_content,
            platform=platform,
            tone=tone,
            tokens_used=total_tokens,
            generation_time_ms=duration_ms,
        )

    return {
        "content": processed_content,
        "log_id": log.id,
        "tokens_used": total_tokens,
        "character_count": len(processed_content),
    }


def generate_marketing_image(
    marketer: User,
    product_id: str,
    style: str,
    tone: str = "bold",
    marketer_notes: str = "",
    use_product_image: bool = True,
) -> Dict[str, Any]:
    """
    Generate an AI image prompt/poster for a product.

    Returns a hosted image URL from OpenAI plus basic logging information.
    """
    product = Product.objects.select_related("category").get(id=product_id)
    category: ProductCategory | None = product.category

    style_human_readable = {
        "social_square": "square social media post (Instagram feed)",
        "story_vertical": "vertical story format (WhatsApp / Instagram story)",
        "flyer_poster": "online flyer/poster you can share or print",
    }.get(style, "square social media post")

    marketer_notes_section = f"\nExtra creative direction from marketer: {marketer_notes}" if marketer_notes else ""

    prompt = (
        f"Create a {style_human_readable} promoting the following product for a Nigerian audience.\n\n"
        f"Product name: {product.name}\n"
        f"Category: {category.name if category else 'General'}\n"
        f"Price: ₦{product.price:,.2f}\n"
        f"Description: {product.description}\n"
        f"{marketer_notes_section}\n\n"
        "Design requirements:\n"
        f"- Overall tone: {tone}\n"
        "- Clean, modern design suitable for social media.\n"
        "- Make the product the hero/center of attention.\n"
        "- Use colours that will look good on phones.\n"
        "- Reserve some empty space where text like headline, price and call-to-action can be placed.\n"
        "- No tiny text inside the image; focus on visuals.\n"
    )

    client = _get_client()

    # Try to use the existing product image as a base for editing.
    base_image_bytes: bytes | None = None
    if use_product_image:
        try:
            if product.images:
                first_image = product.images[0]
                if isinstance(first_image, str) and first_image.startswith("data:image"):
                    # data URL: data:image/<type>;base64,<data>
                    _, b64_data = first_image.split(",", 1)
                    base_image_bytes = base64.b64decode(b64_data)
        except Exception:
            base_image_bytes = None

    try:
        if base_image_bytes:
            # Use image edit: keep the real product image, let the model stylise it.
            image_file = BytesIO(base_image_bytes)
            image_file.name = "product.png"  # type: ignore[attr-defined]
            response = client.images.edit(
                model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                image=image_file,
                prompt=prompt,
                size="1024x1024" if style != "story_vertical" else "1024x1792",
                n=1,
            )
        else:
            # Fallback: pure generation from text prompt.
            response = client.images.generate(
                model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                prompt=prompt,
                size="1024x1024" if style != "story_vertical" else "1024x1792",
                n=1,
            )

        image_b64 = getattr(response.data[0], "b64_json", None)  # type: ignore[assignment]
        if not image_b64:
            raise RuntimeError("Image generation did not return image data")
        # Return a data URL that the frontend <img> tag can render directly.
        image_url = f"data:image/png;base64,{image_b64}"
    except PermissionDeniedError as exc:
        raise RuntimeError("Image generation is not available for this project.") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to generate image: {exc}") from exc

    # Log in the same table so admin can see usage history.
    with transaction.atomic():
        log = AIContentLog.objects.create(
            user=marketer,
            product=product,
            content_type=f"image_{style}",
            prompt=prompt,
            generated_content=image_url or "",
            platform="image",
            tone=tone,
            tokens_used=None,
            generation_time_ms=None,
        )

    return {
        "image_url": image_url,
        "log_id": log.id,
    }


def build_content_prompt(
    content_type: str,
    platform: str,
    tone: str,
    product: Product,
    category_name: str,
    marketer_niche: list[str],
    marketer_notes: str,
) -> str:
    base_context = (
        f"Product Name: {product.name}\n"
        f"Category: {category_name}\n"
        f"Price: ₦{product.price:,.2f}\n"
        f"Description: {product.description}\n"
    )
    niche_str = ", ".join(marketer_niche) if marketer_niche else "general audience"
    notes_section = ""
    if marketer_notes:
        notes_section = f"\n\nAdditional notes and angle from marketer:\n{marketer_notes}\n"

    base_context = base_context + notes_section

    if content_type == "instagram_caption":
        return f"""
{base_context}

Create an engaging Instagram caption for this product.

Requirements:
- Maximum 2,200 characters
- Tone: {tone}
- Include 5-10 relevant hashtags
- Add emoji for visual appeal
- Include a call-to-action
- Mention that this is an affiliate link
- Target audience interested in {niche_str}

Format:
[Main caption text]

[Call-to-action with link placeholder: {{AFFILIATE_LINK}}]

[Hashtags]
"""
    if content_type == "twitter_post":
        return f"""
{base_context}

Create a compelling Twitter/X post for this product.

Requirements:
- Maximum 280 characters (including link placeholder)
- Tone: {tone}
- Include 2-3 relevant hashtags
- Add a clear call-to-action
- Use {{AFFILIATE_LINK}} as link placeholder
"""
    if content_type == "facebook_post":
        return f"""
{base_context}

Write a Facebook post promoting this product.

Requirements:
- 80-150 words
- Tone: {tone}
- Friendly and conversational
- Include a short story or benefit
- Include {{AFFILIATE_LINK}} naturally
"""
    if content_type == "blog_introduction":
        return f"""
{base_context}

Write an engaging blog post introduction (first 2-3 paragraphs) reviewing this product.

Requirements:
- 150-250 words
- Tone: {tone}
- Hook the reader in the first sentence
- Naturally introduce the product
- Mention you're an affiliate partner
- Target audience: {niche_str} enthusiasts
"""
    if content_type == "product_review":
        return f"""
{base_context}

Write a balanced product review highlighting both strengths and potential considerations.

Requirements:
- 200-300 words
- Tone: {tone}
- Be honest but persuasive
- Include practical use cases
- Include a soft call-to-action with {{AFFILIATE_LINK}}
"""
    if content_type == "email_pitch":
        return f"""
{base_context}

Write an email pitch promoting this product to potential customers.

Requirements:
- 150-250 words
- Tone: {tone}
- Clear subject line suggestion
- Short intro, benefits, social proof, and call-to-action
- Include {{AFFILIATE_LINK}} where appropriate
"""
    if content_type == "poster":
        return f"""
{base_context}

You are designing a high-converting poster or social media flyer for this product.
Assume the real product photo will be used as the main visual in the centre of the design.

Requirements:
- Tone: {tone}
- Nigerian audience (use simple, clear language)
- Optimised for online sharing (Instagram, WhatsApp status, Twitter/X, Facebook)
- Strong headline that can sit on top of the product image
- Short supporting line that explains the key benefit
- 3-5 bullet points of benefits or offers
- Clear call-to-action that can sit near the bottom
- Optional small line for terms/conditions if needed

Output format (plain text):
HEADLINE:
<short punchy headline>

SUBHEADLINE:
<1 short supporting sentence>

BENEFITS:
- <benefit 1>
- <benefit 2>
- <benefit 3>
- <benefit 4 (optional)>

CALL TO ACTION:
<clear call to action, you may include {{AFFILIATE_LINK}} as placeholder>

FOOTER NOTE (optional):
<very short line for terms, locations, or time-bound offer if relevant>
"""

    return f"{base_context}\n\nCreate concise marketing copy. Tone: {tone}. Include {{AFFILIATE_LINK}}."


def get_system_prompt(content_type: str, platform: str) -> str:
    return (
        "You are an expert Nigerian digital marketer writing high-converting content. "
        "Write in clear, natural language suitable for the specified platform. "
        "Do not invent product details beyond what is provided."
    )


def post_process_content(
    content: str,
    platform: str,  # noqa: ARG001
    content_type: str,  # noqa: ARG001
    affiliate_link: str | None = None,
) -> str:
    """
    Final tweak to generated text before returning it to the client.

    - Always trims whitespace.
    - If an affiliate link is provided, replaces the {{AFFILIATE_LINK}} placeholder
      with the real URL.
    - If no link is available, removes the placeholder so the text is still usable.
    """
    text = content.strip()
    placeholder = "{{AFFILIATE_LINK}}"
    if placeholder in text:
        if affiliate_link:
            text = text.replace(placeholder, affiliate_link.strip())
        else:
            text = text.replace(placeholder, "").strip()
    return text
