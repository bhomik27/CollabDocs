import logging

from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

logger = logging.getLogger("documents")

# Codes for Django exceptions (Http404, PermissionDenied) that DRF converts.
STATUS_CODES = {404: "not_found", 403: "permission_denied"}


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


class VersionConflict(Conflict):
    default_detail = "Another change to this document was saved at the same time. Reload and try again."
    default_code = "version_conflict"


def api_exception_handler(exc, context):
    """
    DRF's handler, plus:
      * IntegrityError -> 409 (transaction rolled back)
      * anything else unhandled -> generic 500 JSON with no internals exposed
    """
    if isinstance(exc, IntegrityError):
        set_rollback()
        logger.warning("Integrity error in %s: %s", context.get("view").__class__.__name__, exc)
        return Response({"detail": Conflict.default_detail, "code": Conflict.default_code}, status=status.HTTP_409_CONFLICT)

    response = exception_handler(exc, context)
    if response is not None:
        # Add a machine-readable code next to "detail" (e.g. not_found, permission_denied).
        if isinstance(response.data, dict) and "detail" in response.data:
            code = getattr(getattr(exc, "detail", None), "code", None) or getattr(exc, "default_code", None)
            response.data.setdefault("code", code or STATUS_CODES.get(response.status_code, "error"))
        return response

    set_rollback()
    logger.exception("Unhandled error in %s", context.get("view").__class__.__name__)
    return Response(
        {"detail": "An unexpected error occurred.", "code": "server_error"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
