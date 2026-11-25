from .models import AuditLog


def log(user, action, obj=None, detail=""):
    """Record one audit entry. `user` may be None (system or tests)."""
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    return AuditLog.objects.create(
        user=user, action=action,
        object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=getattr(obj, "pk", None),
        object_label=str(obj)[:80] if obj is not None else "",
        detail=detail)