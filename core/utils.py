"""Tiny helpers shared across apps."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError


def brief_user(user):
    """Return a small, safe representation of a user for API output (or None if user is gone)."""
    if user is None:
        return None
    return {"id": user.pk, "username": user.get_username()}


def parse_query_value(model, field_name, param, raw):
    """Convert a query-string value with the model field's own parser (UUID, datetime, ...).

    Malformed input becomes a 400 naming the parameter instead of an unhandled 500 at query time.
    """
    field = model._meta.pk if field_name == "pk" else model._meta.get_field(field_name)
    try:
        return field.to_python(raw)
    except DjangoValidationError:
        raise ValidationError({param: f"'{raw}' is not a valid value."})
