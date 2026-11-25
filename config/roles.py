from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

ALL_ROLES = {"Salesman", "Admin", "Production", "Auditor", "Owner"}


def user_roles(user):
    if user.is_superuser:
        return set(ALL_ROLES)
    return set(user.groups.values_list("name", flat=True))


def role_required(*roles):
    """Allow only users whose group is one of `roles`. Others get a 403 page."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if user_roles(request.user) & set(roles):
                return view(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator