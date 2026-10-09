import time

from core.context import reset_request, set_request


class AuditContextMiddleware:
    """Publishes the current request so audit signal handlers can record the acting user.

    The user is read lazily at signal time (see core/context.py), so this works for DRF token
    authentication, which happens inside the view, after middleware has run.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_request(request)
        try:
            return self.get_response(request)
        finally:
            reset_request(token)


class RequestLoggingMiddleware:
    """Prints: METHOD  /path  status  time_in_ms for every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000
        print(
            f"[REQUEST] {request.method} {request.path} "
            f"-> {response.status_code} ({duration_ms:.2f} ms)"
        )
        return response
