import time


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
