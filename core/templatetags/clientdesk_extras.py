from django import template

register = template.Library()

_TASK_LABELS = {"todo": "Todo", "in_progress": "In Progress", "review": "Review", "done": "Done"}


@register.filter
def get_item(mapping, key):
    """Доступ к значению словаря по ключу-переменной в шаблоне."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def task_label(status):
    return _TASK_LABELS.get(status, status)
