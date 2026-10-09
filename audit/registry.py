"""
The audit registry: which models are audited, and how to find each instance's workspace.

Any app (A, B or C) turns on auditing for a model with ONE call, normally in its AppConfig.ready():

    from audit.registry import register
    register(Document, lambda doc: doc.workspace_id)

`register` connects the three Django signals (pre_save, post_save, post_delete) for that model
only, so un-registered models cost nothing.
"""
from django.db.models.signals import post_delete, post_save, pre_save

_REGISTRY = {}  # model class -> (workspace_resolver, target_type)


def register(model, workspace_resolver, target_type=None):
    """Audit `model`.

    workspace_resolver: callable(instance) -> workspace id (or None). Called at signal time.
    target_type: label stored in the log (default: the lower-case model name).
    Safe to call twice for the same model (dispatch_uid de-duplicates).
    """
    from . import signals  # imported here to avoid a circular import at module load

    _REGISTRY[model] = (workspace_resolver, target_type or model._meta.model_name)
    uid = f"audit-{model._meta.label_lower}"
    pre_save.connect(signals.snapshot_before_save, sender=model, dispatch_uid=f"{uid}-pre")
    post_save.connect(signals.write_save_entry, sender=model, dispatch_uid=f"{uid}-post")
    post_delete.connect(signals.write_delete_entry, sender=model, dispatch_uid=f"{uid}-del")


def get_entry(model):
    """Return (workspace_resolver, target_type) for a registered model."""
    return _REGISTRY[model]


def registered_models():
    """List of audited model classes (handy for debugging / tests)."""
    return list(_REGISTRY)
