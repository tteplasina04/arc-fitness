from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parent.parent


def get_connection():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL не задан. Скопируйте .env.example в .env и настройте PostgreSQL.")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor, connect_timeout=8)


@contextmanager
def connection() -> Iterator:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    schema_path = ROOT / "app" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
            seed_data(cur)
            seed_admin(cur)
            cur.execute(
                """UPDATE classes c
                   SET booked_count = (
                       SELECT COUNT(*) FROM bookings b
                       WHERE b.class_id = c.id AND b.status = 'active'
                   )"""
            )
            cur.execute("UPDATE client_memberships SET status='expired' WHERE status='active' AND ends_at <= NOW()")


def seed_data(cur) -> None:
    cur.execute("SELECT COUNT(*) AS count FROM membership_plans")
    if cur.fetchone()["count"] == 0:
        plans = [
            ("basic", "Базовый", 2490, 30, "Доступ в тренажёрный зал; Свободный тренировочный план; Поддержка администратора", "Для самостоятельных тренировок"),
            ("plus", "Плюс", 3990, 30, "Доступ в тренажёрный зал; Групповые программы; Поддержка команды клуба", "Больше возможностей для регулярных занятий"),
            ("premium", "Премиум", 6990, 30, "Доступ в тренажёрный зал; Групповые программы; Вводная персональная тренировка", "Максимальная поддержка на старте"),
        ]
        for key, title, price, duration, features, description in plans:
            cur.execute(
                """INSERT INTO membership_plans (plan_key, title, price, duration_days, features, description)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (plan_key) DO NOTHING""",
                (key, title, price, duration, features, description),
            )

    cur.execute("SELECT COUNT(*) AS count FROM trainers")
    if cur.fetchone()["count"] == 0:
        trainers = [
            ("Алексей Морозов", "Силовой тренинг", 7, "Помогает выстроить технику и последовательный план тренировок.", "/static/images/trainer-01.jpg"),
            ("Мария Соколова", "Функциональный тренинг", 5, "Сочетает работу над выносливостью, координацией и мобильностью.", "/static/images/trainer-02.jpg"),
            ("Денис Волков", "Персональные тренировки", 9, "Подбирает программу с учётом опыта и целей клиента.", "/static/images/trainer-03.jpg"),
        ]
        for trainer in trainers:
            cur.execute(
                "INSERT INTO trainers (name, speciality, experience_years, bio, photo_path) VALUES (%s, %s, %s, %s, %s)",
                trainer,
            )

    cur.execute("SELECT COUNT(*) AS count FROM classes")
    if cur.fetchone()["count"] == 0:
        cur.execute("SELECT id, name FROM trainers ORDER BY id")
        trainer_rows = cur.fetchall()
        trainer_by_name = {row["name"]: row["id"] for row in trainer_rows}
        weekly = [
            ("Силовая база", "Силовая", 0, "08:00", 55, "Зал A", "Алексей Морозов", 14),
            ("Мобильность", "Функциональная", 0, "18:30", 45, "Зал B", "Мария Соколова", 16),
            ("Круговая тренировка", "Функциональная", 1, "19:00", 50, "Зал B", "Мария Соколова", 14),
            ("Работа со штангой", "Силовая", 2, "08:30", 60, "Зал A", "Алексей Морозов", 12),
            ("Персональный старт", "Персональная", 2, "17:30", 45, "Зал A", "Денис Волков", 1),
            ("Функциональный микс", "Функциональная", 3, "18:00", 50, "Зал B", "Мария Соколова", 16),
            ("Силовая база", "Силовая", 4, "09:00", 55, "Зал A", "Алексей Морозов", 14),
            ("Выносливость", "Кардио", 4, "19:15", 40, "Кардио-зона", "Денис Волков", 14),
            ("Техника и контроль", "Персональная", 5, "11:00", 45, "Зал A", "Денис Волков", 1),
            ("Мобильность", "Функциональная", 6, "12:00", 45, "Зал B", "Мария Соколова", 16),
        ]
        for title, category, day, start, duration, room, trainer, capacity in weekly:
            cur.execute(
                """INSERT INTO classes (title, category, day_of_week, starts_at, duration_minutes, room, trainer_id, capacity)
                   VALUES (%s, %s, %s, %s::time, %s, %s, %s, %s)""",
                (title, category, day, start, duration, room, trainer_by_name.get(trainer), capacity),
            )

    cur.execute("SELECT COUNT(*) AS count FROM news")
    if cur.fetchone()["count"] == 0:
        news_items = [
            ("Новая зона функционального тренинга", "Обновления", "В клубе готовится пространство для динамичных тренировок.", "Расширяем пространство для движения: следите за новостями клуба и расписанием запусков.", "/static/images/news-01.jpg"),
            ("Открытая тренировка выходного дня", "События", "Познакомьтесь с форматом групповых занятий.", "Приглашаем участников клуба на открытую тренировку. Подробности и время уточняйте у администратора.", "/static/images/news-02.jpg"),
            ("Истории постоянных участников", "Достижения", "Рассказываем о дисциплине и регулярности.", "Мы верим в системный подход: небольшие последовательные шаги помогают сохранять привычку заниматься.", "/static/images/news-03.jpg"),
        ]
        for item in news_items:
            cur.execute(
                "INSERT INTO news (title, category, excerpt, body, image_path, published_at) VALUES (%s, %s, %s, %s, %s, NOW())",
                item,
            )

    cur.execute("SELECT COUNT(*) AS count FROM promotions")
    if cur.fetchone()["count"] == 0:
        promotions = [
            ("Первый шаг", "Скидка на первый месяц", "Начните знакомство с клубом с вводного предложения.", 15, "2026-12-31 23:59:59+03"),
            ("Вместе проще", "Приходите вдвоём", "Уточните у администратора условия совместного оформления.", 10, "2026-12-15 23:59:59+03"),
        ]
        for title, subtitle, description, discount, ends_at in promotions:
            cur.execute(
                "INSERT INTO promotions (title, subtitle, description, discount_percent, ends_at, is_active) VALUES (%s, %s, %s, %s, %s::timestamptz, TRUE)",
                (title, subtitle, description, discount, ends_at),
            )


def seed_admin(cur) -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if not admin_email or not admin_password:
        return
    cur.execute("SELECT id FROM users WHERE email = %s", (admin_email,))
    existing = cur.fetchone()
    if existing:
        cur.execute("UPDATE users SET role = 'admin', is_verified = TRUE WHERE id = %s", (existing["id"],))
        return
    password_bytes = admin_password.encode("utf-8")[:72]
    password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")
    cur.execute(
        """INSERT INTO users (email, full_name, password_hash, is_verified, role)
           VALUES (%s, %s, %s, TRUE, 'admin')""",
        (admin_email, "Администратор ARC.FITNESS", password_hash),
    )
