"""
Per-request context so code that has no `request` argument (Django signals!) can still
find out WHO is making the change.

How it works
------------
* The middleware calls `set_request(request)` when a request starts and
  `reset_request(token)` when it ends.
* A signal handler calls `current_user()`.
* We store the Django HttpRequest (not the user) because DRF authenticates INSIDE the view,
  after middleware has run. When DRF authenticates it copies the user onto the underlying
  HttpRequest (`request.user = ...`), so reading `request.user` lazily, at signal time,
  returns the real user. Reading it in the middleware itself would give AnonymousUser.

ContextVar (not a plain global / threading.local) keeps requests isolated even under
async servers.
"""
from contextvars import ContextVar

_current_request = ContextVar("collabdocs_current_request", default=None)


def set_request(request):
    """Remember `request` for the current context. Returns a token for `reset_request`."""
    return _current_request.set(request)


def reset_request(token):
    """Forget the request set by `set_request` (call in a `finally` block)."""
    _current_request.reset(token)


def current_user():
    """Return the authenticated user making the current request, or None.

    None means "no request in progress" (shell, management command, tests that use the ORM
    directly) or "request not authenticated".
    """
    request = _current_request.get()
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None
