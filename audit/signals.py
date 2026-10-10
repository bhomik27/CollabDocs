"""
Signal handlers that write AuditLog rows. They are connected per-model by audit.registry.register().

Flow for an update:  pre_save  -> remember the row's old field values on the instance
                     post_save -> diff old vs new, write one AuditLog row
Create:  post_save(created=True) -> one row with the new values.
Delete:  pre_delete -> capture the final values; post_delete -> one row with them.

The handlers run INSIDE the same database transaction as the change (signals fire during
save()/delete()), so if the view's transaction.atomic() rolls back, the audit row rolls back too:
the log never records something that did not happen.

Caveats: QuerySet.update(), bulk_create() and queryset.delete() skip save()/signals for
update/bulk_create, so views must call instance.save()/instance.delete().

Deleting a user cascades (Workspace.owner) into audited rows. The entries written during that
cascade must not point at the user being deleted: Django computed its SET_NULL updates before
those rows existed, so the deferred FK check would fail at commit. `forget_deleted_actor`
records the pk on pre_delete and `_write` stores actor = None for it.
"""
from contextvars import ContextVar

from django.core.exceptions import ObjectDoesNotExist

from core.context import current_user

from .models import AuditLog
from .registry import get_entry

_deleting_user_pks = ContextVar("audit_deleting_user_pks", default=frozenset())


def _snapshot(instance):
    """Dict of the instance's editable concrete field values (FKs as ids, no M2M, no auto timestamps)."""
    data = {}
    for field in instance._meta.concrete_fields:
        if field.primary_key or getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            continue
        data[field.attname] = getattr(instance, field.attname)
    return data


def _write(sender, instance, action, changes):
    """Create one AuditLog row for `instance` using the registered workspace resolver."""
    resolver, target_type = get_entry(sender)
    try:
        workspace_id = resolver(instance)
    except ObjectDoesNotExist:  # parent already gone (e.g. mid-cascade): keep the entry, workspace unknown
        workspace_id = None
    actor = current_user()
    if actor is not None and actor.pk in _deleting_user_pks.get():
        actor = None
    AuditLog.objects.create(
        workspace_id=workspace_id,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(instance.pk),
        changes=changes,
    )


def snapshot_before_save(sender, instance, **kwargs):
    """pre_save: on UPDATE, load the old row and stash its values on the instance (1 extra query)."""
    instance._audit_old = None
    if kwargs.get("raw") or instance._state.adding:
        return
    old = sender._default_manager.filter(pk=instance.pk).first()
    if old is not None:
        instance._audit_old = _snapshot(old)


def write_save_entry(sender, instance, created, **kwargs):
    """post_save: write a create entry, or an update entry listing only fields that changed."""
    if kwargs.get("raw"):  # loaddata/fixtures: not a user action
        return
    new = _snapshot(instance)
    if created:
        _write(sender, instance, AuditLog.Action.CREATE, new)
        return
    old = getattr(instance, "_audit_old", None) or {}
    changes = {name: {"from": old.get(name), "to": value} for name, value in new.items() if old.get(name) != value}
    if changes:  # a save() that changed nothing is not worth a log row
        _write(sender, instance, AuditLog.Action.UPDATE, changes)


def snapshot_before_delete(sender, instance, **kwargs):
    """pre_delete: capture the final values while the row still exists.

    The instance may have deferred fields (e.g. a view that loaded it with .only()); reading
    them after the delete would hit a row that no longer exists, so load them all now in one query.
    """
    deferred = instance.get_deferred_fields()
    if deferred:
        instance.refresh_from_db(fields=list(deferred))
    instance._audit_final = _snapshot(instance)


def write_delete_entry(sender, instance, **kwargs):
    """post_delete: write a delete entry holding the object's last known values."""
    final = getattr(instance, "_audit_final", None)
    _write(sender, instance, AuditLog.Action.DELETE, final if final is not None else _snapshot(instance))


def forget_deleted_actor(sender, instance, **kwargs):
    """pre_delete on the user model: audit rows written during this deletion get actor = None."""
    _deleting_user_pks.set(_deleting_user_pks.get() | {instance.pk})


def remember_actor_again(sender, instance, **kwargs):
    """post_delete on the user model: the deletion is done, stop special-casing this pk."""
    _deleting_user_pks.set(_deleting_user_pks.get() - {instance.pk})
