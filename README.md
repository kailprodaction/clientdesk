# ClientDesk (локальный MVP)

AI-портал для фрилансеров и небольших агентств: проекты, файлы, **точечные комментарии
на макете**, Kanban-задачи, клиентский view по magic-link и **AI-статус-отчёты через Claude**.

Это работающий локальный MVP по спецификации из `project_clientdesk.md`. Продакшн-стек из спеки
(Supabase, Cloud Run, Stripe, Resend, Sentry) заменён на локальные аналоги, чтобы приложение
запускалось одной командой без внешних аккаунтов:

| В спецификации          | В этом MVP                                   |
|-------------------------|----------------------------------------------|
| Supabase Postgres + RLS | SQLite + изоляция workspace на уровне запросов |
| Supabase Auth           | Сессии Flask + хэш пароля (Werkzeug)          |
| Supabase Storage        | Локальная папка `uploads/`                    |
| Supabase Realtime       | Лёгкий polling комментариев на фронте          |
| Cloud Tasks / Scheduler | Синхронная генерация отчётов                    |
| Stripe / Resend / Sentry| Не подключены (заглушки)                        |
| **Claude API**          | **Реальный вызов**, если задан `ANTHROPIC_API_KEY`; иначе офлайн-фолбэк |

## Запуск

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # опционально: впишите ANTHROPIC_API_KEY
python run.py
```

Откройте http://127.0.0.1:5000 → зарегистрируйтесь → создайте проект.

## Как попробовать все фичи

1. **Проект** — создайте, укажите клиента и дедлайн.
2. **Файл** — загрузите изображение (PNG/JPG) на странице проекта.
3. **Точечные комментарии** — откройте файл, кликните по макету → оставьте пин с тредом.
   Координаты хранятся в процентах, поэтому пины корректны на любом экране.
4. **Kanban** — добавьте задачи и перетаскивайте карточки между колонками (drag-and-drop).
5. **Клиентский доступ** — создайте magic-link, откройте его в приватном окне: клиент видит
   прогресс и может комментировать без регистрации.
6. **AI-статус-отчёт** — «AI: статус-отчёт» собирает закрытые/текущие задачи в письмо клиенту.
   Отредактируйте и «Отправить» → отчёт появится в клиентском портале.
7. **AI: разобрать фидбек** — группирует открытые комментарии клиента в actionable-чеклист.

Без `ANTHROPIC_API_KEY` пункты 6–7 работают в детерминированном офлайн-режиме.

## Структура

```
app/
├── __init__.py     # фабрика приложения, регистрация блюпринтов
├── config.py       # конфиг через env
├── extensions.py   # SQLAlchemy
├── models.py       # workspaces, users, projects, files, comments, tasks, links, reports
├── security.py     # login_required, CSRF
├── auth/           # регистрация / вход
├── projects/       # проекты, файлы, задачи, клиентские ссылки
├── comments/       # JSON API точечных комментариев (member + client)
├── ai/             # Claude: статус-отчёт и summary фидбека
├── client/         # клиентский портал по magic-link
└── templates/      # Jinja2 + Tailwind (CDN) + Alpine.js (CDN)
```
