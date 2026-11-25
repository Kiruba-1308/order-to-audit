from django.shortcuts import render

from config.roles import role_required

from .models import AuditLog


@role_required("Auditor", "Admin", "Owner")
def audit_log(request):
    logs = AuditLog.objects.select_related("user")[:300]
    return render(request, "audit_log.html", {"logs": logs})