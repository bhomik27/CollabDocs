"""Tiny helpers shared by Person C's serializers."""


def brief_user(user):
    """Return a small, safe representation of a user for API output (or None if user is gone)."""
    if user is None:
        return None
    return {"id": user.pk, "username": user.get_username()}
