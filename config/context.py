from .roles import user_roles


def roles(request):
    if request.user.is_authenticated:
        return {"roles": user_roles(request.user)}
    return {"roles": set()}