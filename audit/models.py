from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only trail of who changed what and when."""
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_label = models.CharField(max_length=80, blank=True)
    detail = models.TextField(blank=True)

    class Meta:
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Audit log entries cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log entries cannot be deleted.")

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.object_label}"