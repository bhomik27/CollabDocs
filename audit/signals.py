"""
Signal handlers that write AuditLog rows. They are connected per-model by audit.registry.register().

Flow for an update:  pre_save  -> remember the row's old field values on the instance
                     post_save -> diff old vs new, write one AuditLog row
Create:  post_save(created=True) -> one row with the new values.
Delete:  post_delete -> one row with the final values.

The handlers run INSIDE the same database transaction as the change (signals fire during
save()/delete()), so if the view's transaction.atomic() rolls back, the audit row rolls back too:
the log never records something that did not happen.

Caveats (also in BUILD_GUIDE.md): QuerySet.update(), bulk_create() and queryset.delete() skip
save()/signals for update/bulk_create, so views must call instance.save()/instance.delete().
"""
from django.core.exceptions import ObjectDoesNotExist

from core.context import current_user

from .models import AuditLog
from .registry import get_entry


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
    AuditLog.objects.create(
        workspace_id=workspace_id,
        actor=current_user(),
        action=action,
        target_type=target_type,
        target_id=instance.pk,
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


def write_delete_entry(sender, instance, **kwargs):
    """post_delete: write a delete entry holding the object's last known values."""
    _write(sender, instance, AuditLog.Action.DELETE, _snapshot(instance))
