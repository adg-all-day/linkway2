from __future__ import annotations

from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class RateLimitMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # For now we rely on DRF's throttling; hook Redis-based rate limiting here if needed.
        response = self.get_response(request)
        return response


class ActivityLogMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        try:
            from apps.analytics.models import ActivityLog

            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                ActivityLog.objects.create(
                    user=user,
                    action=request.path,
                    entity_type=getattr(request.resolver_match, "view_name", None)
                    if getattr(request, "resolver_match", None)
                    else None,
                    entity_id=None,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    metadata={
                        "method": request.method,
                        "status_code": response.status_code,
                    },
                )
        except Exception:
            # Do not let logging failures break the request cycle.
            pass
        return response

