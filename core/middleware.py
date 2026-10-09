"""
Middleware that publishes the current request to `core.context`.

MERGE NOTE: Person A owns the project's request-logging middleware. Do not run two
middlewares. On merge, add the three marked lines from this file into A's middleware
(see INTEGRATION.md) and delete this file + its entry in settings.MIDDLEWARE.
"""
from .context import reset_request, set_request


class RequestContextMiddleware:
    """Make the request available to signal handlers via `core.context.current_user()`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_request(request)          # <-- line 1 to copy into A's middleware
        try:
            return self.get_response(request)
        finally:
            reset_request(token)              # <-- line 2 to copy into A's middleware
