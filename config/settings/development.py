from .base import *  # noqa

DEBUG = True

# Use local memory cache in development to avoid requiring Redis.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
