"""Обёртка над Claude API: статус-отчёт и разбор фидбека (сценарии из спеки).
Без ANTHROPIC_API_KEY работает детерминированный офлайн-фолбэк."""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _call_claude(system, prompt, max_tokens=1200):
    key = settings.ANTHROPIC_API_KEY
    if not key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as exc:  # graceful degradation
        logger.warning("Claude call failed: %s", exc)
        return None


def generate_status_report(project):
    """Возвращает (content, source)."""
    week_ago = timezone.now() - timedelta(days=7)
    tasks = list(project.tasks.all())
    done = [t for t in tasks if t.status == "done" and (t.done_at is None or t.done_at >= week_ago)]
    in_progress = [t for t in tasks if t.status in ("in_progress", "review")]
    upcoming = [t for t in tasks if t.status == "todo"]

    def titles(items):
        return "\n".join(f"- {t.title}" for t in items) or "- (нет)"

    facts = (
        f"Проект: {project.name}\nКлиент: {project.client_name or '—'}\n"
        f"Дедлайн: {project.deadline or '—'}\n\n"
        f"Завершено за неделю:\n{titles(done)}\n\n"
        f"В работе / на ревью:\n{titles(in_progress)}\n\n"
        f"Запланировано:\n{titles(upcoming)}\n"
    )
    system = (
        "Ты ассистент фрилансера. Пишешь клиенту статус-письмо: дружелюбный, но "
        "профессиональный тон, без технического жаргона, 3–5 абзацев. Структура: что "
        "сделано, что в работе, что ожидается от клиента. Отвечай на русском."
    )
    out = _call_claude(system, facts)
    if out:
        return out, "ai"

    lines = [
        f"Здравствуйте! Коротко о статусе проекта «{project.name}».", "",
        "За прошедшую неделю мы завершили:", titles(done), "",
        "Сейчас в работе:", titles(in_progress), "",
        "Дальше в планах:", titles(upcoming), "",
        "Если по чему-то нужна ваша обратная связь — оставьте комментарии в портале, "
        "и мы учтём их на следующей итерации. Спасибо!",
    ]
    return "\n".join(lines), "fallback"


def summarize_feedback(project):
    """Группирует открытые клиентские комментарии в actionable-чеклист. Возвращает (content, source)."""
    comments = [c for c in project.comments.all() if c.author_type == "client" and not c.resolved]
    if not comments:
        return "Открытых комментариев клиента нет.", "fallback"

    joined = "\n".join(
        f"- [{c.file.filename if c.file else 'общий'}] {c.body}" for c in comments
    )
    system = (
        "Ты помогаешь фрилансеру разобрать обратную связь клиента. Сгруппируй комментарии "
        "по темам и вытащи actionable-пункты в виде чек-листа с приоритетом "
        "(высокий/средний/низкий). Отвечай на русском, кратко."
    )
    out = _call_claude(system, f"Комментарии клиента:\n{joined}")
    if out:
        return out, "ai"
    return "Открытые комментарии клиента (сгруппируйте вручную):\n" + joined, "fallback"
