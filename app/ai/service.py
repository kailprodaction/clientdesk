"""Обёртка над Claude API. Два сценария из спеки: status report и feedback summary.
Если ANTHROPIC_API_KEY не задан — детерминированный офлайн-фолбэк, чтобы фича работала локально."""
from datetime import datetime, timedelta

from flask import current_app

from ..models import Comment, Task


def _client():
    key = current_app.config.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic

        return anthropic.Anthropic(api_key=key)
    except Exception:
        return None


def _call_claude(system, user_prompt, max_tokens=1200):
    client = _client()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=current_app.config["CLAUDE_MODEL"],
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text").strip()
    except Exception as exc:  # graceful degradation
        current_app.logger.warning("Claude call failed: %s", exc)
        return None


# --------------------------- status report ---------------------------

def _gather_status_context(project):
    week_ago = datetime.utcnow() - timedelta(days=7)
    done = [
        t for t in project.tasks
        if t.status == "done" and (t.done_at is None or t.done_at >= week_ago)
    ]
    in_progress = [t for t in project.tasks if t.status in ("in_progress", "review")]
    upcoming = [t for t in project.tasks if t.status == "todo"]
    return done, in_progress, upcoming


def generate_status_report(project):
    """Возвращает (content, generated_by)."""
    done, in_progress, upcoming = _gather_status_context(project)

    def _titles(items):
        return "\n".join(f"- {t.title}" for t in items) or "- (нет)"

    facts = (
        f"Проект: {project.name}\n"
        f"Клиент: {project.client_name or '—'}\n"
        f"Дедлайн: {project.deadline or '—'}\n\n"
        f"Завершено за неделю:\n{_titles(done)}\n\n"
        f"В работе / на ревью:\n{_titles(in_progress)}\n\n"
        f"Запланировано:\n{_titles(upcoming)}\n"
    )

    system = (
        "Ты ассистент фрилансера. Пишешь клиенту статус-письмо о ходе проекта: "
        "дружелюбный, но профессиональный тон, без технического жаргона, 3–5 абзацев. "
        "Структура: что сделано, что в работе, что ожидается от клиента. Отвечай на русском."
    )
    out = _call_claude(system, facts)
    if out:
        return out, "ai"

    # офлайн-фолбэк
    lines = [
        f"Здравствуйте! Коротко о статусе проекта «{project.name}».",
        "",
        "За прошедшую неделю мы завершили:",
        _titles(done),
        "",
        "Сейчас в работе:",
        _titles(in_progress),
        "",
        "Дальше в планах:",
        _titles(upcoming),
        "",
        "Если по чему-то нужна ваша обратная связь — оставьте комментарии в портале, "
        "и мы учтём их на следующей итерации. Спасибо!",
    ]
    return "\n".join(lines), "fallback"


# --------------------------- feedback summary ---------------------------

def summarize_feedback(project):
    """Группирует клиентские комментарии в actionable-чеклист. Возвращает (content, generated_by)."""
    comments = [
        c for c in project.comments
        if c.author_type == "client" and not c.resolved
    ]
    if not comments:
        return "Открытых комментариев клиента нет.", "fallback"

    joined = "\n".join(
        f"- [{c.file.filename if c.file else 'общий'}] {c.body}" for c in comments
    )
    system = (
        "Ты помогаешь фрилансеру разобрать обратную связь клиента. "
        "Сгруппируй комментарии по темам и вытащи actionable-пункты в виде чек-листа "
        "с приоритетом (высокий/средний/низкий). Отвечай на русском, кратко."
    )
    out = _call_claude(system, f"Комментарии клиента:\n{joined}")
    if out:
        return out, "ai"

    return "Открытые комментарии клиента (сгруппируйте вручную):\n" + joined, "fallback"
