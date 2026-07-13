"""Context processor: делает workspace текущего пользователя доступным в шаблонах."""


def workspace(request):
    ws = None
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        profile = getattr(user, "profile", None)
        ws = profile.workspace if profile else None
    return {"workspace": ws}
