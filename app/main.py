from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen

import bcrypt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from app.db import connection, init_db

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("arc_fitness")

APP_ENV = os.getenv("APP_ENV", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "local-development-key-change-this")
SESSION_COOKIE = "arc_session"
SESSION_DAYS = 14

app = FastAPI(
    title="ARC.FITNESS API",
    version="1.0.0",
    description="API веб-приложения фитнес-клуба ARC.FITNESS",
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

PAGE_FILES = {
    "about": "about.html",
    "trainers": "trainers.html",
    "schedule": "schedule.html",
    "memberships": "memberships.html",
    "promotions": "promotions.html",
    "news": "news.html",
    "login": "login.html",
    "register": "register.html",
    "verify": "verify.html",
    "account": "account.html",
    "admin": "admin.html",
    "privacy": "privacy.html",
}


# ---------- Models: every incoming API payload is validated by Pydantic ----------
class RegisterInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=72)


class VerifyInput(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class LoginInput(BaseModel):
    identifier: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)


class CallbackInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=5, max_length=32)
    comment: str = Field(default="", max_length=1000)


class ProfileInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    current_password: str | None = Field(default=None, max_length=72)
    new_password: str | None = Field(default=None, min_length=8, max_length=72)


class BookingInput(BaseModel):
    class_id: int = Field(gt=0)


class MembershipRequestInput(BaseModel):
    plan_key: str = Field(min_length=2, max_length=32)


class ClassCreateInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=60)
    day_of_week: int = Field(ge=0, le=6)
    starts_at: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int = Field(ge=10, le=240)
    room: str = Field(min_length=1, max_length=80)
    trainer_id: int | None = Field(default=None, gt=0)
    capacity: int = Field(ge=1, le=300)


class AdminClassUpdateInput(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, min_length=2, max_length=60)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    starts_at: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_minutes: int | None = Field(default=None, ge=10, le=240)
    room: str | None = Field(default=None, min_length=1, max_length=80)
    trainer_id: int | None = Field(default=None, gt=0)
    capacity: int | None = Field(default=None, ge=1, le=300)


class NewsCreateInput(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    category: str = Field(min_length=2, max_length=60)
    excerpt: str = Field(min_length=3, max_length=500)
    body: str = Field(min_length=3, max_length=6000)
    image_path: str = Field(default="/static/images/news-placeholder.jpg", max_length=300)


class AdminRequestStatusInput(BaseModel):
    status: str = Field(min_length=3, max_length=20)


class ClientMembershipInput(BaseModel):
    plan_key: str = Field(min_length=2, max_length=32)


class AdminBookingUpdateInput(BaseModel):
    class_id: int | None = Field(default=None, gt=0)
    status: Literal["active", "cancelled"] | None = None


# ---------- Common helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_text(value: str) -> str:
    return hashlib.sha256((SECRET_KEY + value).encode("utf-8")).hexdigest()


def password_matches(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def send_email_code(email: str, full_name: str, code: str) -> bool:
    host = os.getenv("SMTP_HOST", "smtp.yandex.ru")
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", username)

    if not username or not password or not sender:
        if APP_ENV == "development":
            logger.info("Development verification code for %s: %s", email, code)
            return False
        raise HTTPException(status_code=503, detail="Email-верификация временно недоступна. Попробуйте позднее.")

    message = EmailMessage()
    message["Subject"] = "Код подтверждения ARC.FITNESS"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Здравствуйте, {full_name}!\n\nВаш код подтверждения ARC.FITNESS: {code}\n"
        "Код действует 10 минут. Если вы не регистрировались на сайте, проигнорируйте это письмо."
    )
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=10) as server:
                server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(username, password)
                server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.exception("SMTP send failed: %s", exc)
        if APP_ENV == "development":
            return False
        raise HTTPException(status_code=503, detail="Не удалось отправить код подтверждения. Проверьте почту позднее.")


def send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.info("Telegram is not configured; notification skipped.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = URLRequest(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=8) as response:
            return 200 <= response.status < 300
    except Exception as exc:  # notification failure must not lose a saved request
        logger.warning("Telegram notification failed: %s", exc)
        return False


def current_user_from_request(conn, request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """SELECT u.id, u.email, u.phone, u.full_name, u.role, u.is_verified
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = %s AND s.expires_at > NOW() AND u.is_verified = TRUE""",
            (hash_text(token),),
        )
        return cur.fetchone()


def require_user(conn, request: Request):
    user = current_user_from_request(conn, request)
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт, чтобы продолжить.")
    return user


def require_admin(conn, request: Request):
    user = require_user(conn, request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Недостаточно прав для доступа к этому разделу.")
    return user


def public_user(user) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "phone": user["phone"],
        "full_name": user["full_name"],
        "role": user["role"],
        "is_verified": user["is_verified"],
    }


def day_name(day: int) -> str:
    return ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][day]


def class_to_public(row: dict) -> dict:
    starts = row["starts_at"]
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "is_group": str(row["category"]).strip().lower() not in {"персональная", "персональная тренировка", "индивидуальная"},
        "day_of_week": row["day_of_week"],
        "day_label": day_name(row["day_of_week"]),
        "starts_at": starts.strftime("%H:%M") if hasattr(starts, "strftime") else str(starts)[:5],
        "duration_minutes": row["duration_minutes"],
        "room": row["room"],
        "trainer_id": row.get("trainer_id"),
        "trainer_name": row.get("trainer_name") or "Тренер клуба",
        "capacity": row["capacity"],
        "booked_count": row["booked_count"],
        "available": max(0, row["capacity"] - row["booked_count"]),
    }


@app.on_event("startup")
def startup() -> None:
    try:
        init_db()
        logger.info("ARC.FITNESS database initialized.")
    except Exception as exc:
        # The informational pages still open during first setup; API endpoints explain DB errors.
        logger.warning("Database initialization skipped: %s", exc)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if APP_ENV == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ---------- Health ----------
@app.get("/api/health")
def health():
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        logger.warning("Health check failed: %s", exc)
        raise HTTPException(status_code=503, detail="База данных недоступна. Проверьте DATABASE_URL и подключение PostgreSQL.")


# ---------- Public content API ----------
@app.get("/api/trainers")
def trainers_list():
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id, name, speciality, experience_years, bio, photo_path
                           FROM trainers WHERE is_active = TRUE ORDER BY id""")
            return {"items": cur.fetchall()}
    except Exception as exc:
        logger.warning("trainers_list failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить список тренеров.")


@app.get("/api/weekly-schedule")
def weekly_schedule(day: int | None = None):
    if day is not None and not 0 <= day <= 6:
        raise HTTPException(status_code=400, detail="День недели должен быть в диапазоне от 0 до 6.")
    try:
        with connection() as conn, conn.cursor() as cur:
            query = """SELECT c.id, c.title, c.category, c.day_of_week, c.starts_at, c.duration_minutes,
                              c.room, c.trainer_id, c.capacity, c.booked_count, t.name AS trainer_name
                       FROM classes c LEFT JOIN trainers t ON t.id = c.trainer_id
                       WHERE c.is_active = TRUE"""
            params: tuple = ()
            if day is not None:
                query += " AND c.day_of_week = %s"
                params = (day,)
            query += " ORDER BY c.day_of_week, c.starts_at"
            cur.execute(query, params)
            return {"items": [class_to_public(row) for row in cur.fetchall()]}
    except Exception as exc:
        logger.warning("weekly_schedule failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить расписание.")


@app.get("/api/memberships")
def memberships_list():
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT plan_key, title, price, duration_days, features, description
                           FROM membership_plans WHERE is_active = TRUE ORDER BY price""")
            return {"items": cur.fetchall()}
    except Exception as exc:
        logger.warning("memberships_list failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить абонементы.")


@app.get("/api/promotions")
def promotions_list():
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id, title, subtitle, description, discount_percent, ends_at
                           FROM promotions WHERE is_active = TRUE AND ends_at > NOW() ORDER BY ends_at""")
            return {"items": cur.fetchall()}
    except Exception as exc:
        logger.warning("promotions_list failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить акции.")


@app.get("/api/news")
def news_list(category: str | None = None):
    try:
        with connection() as conn, conn.cursor() as cur:
            if category and category != "Все":
                cur.execute("""SELECT id, title, category, excerpt, body, image_path, published_at
                               FROM news WHERE is_published = TRUE AND category = %s ORDER BY published_at DESC""", (category,))
            else:
                cur.execute("""SELECT id, title, category, excerpt, body, image_path, published_at
                               FROM news WHERE is_published = TRUE ORDER BY published_at DESC""")
            return {"items": cur.fetchall()}
    except Exception as exc:
        logger.warning("news_list failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить новости.")


@app.post("/api/callback", status_code=201)
def create_callback(payload: CallbackInput, request: Request):
    try:
        clean_name = payload.name.strip()
        clean_phone = payload.phone.strip()
        clean_comment = payload.comment.strip()
        if not clean_name or not clean_phone:
            raise HTTPException(status_code=422, detail="Заполните имя и номер телефона.")
        with connection() as conn, conn.cursor() as cur:
            linked_user = current_user_from_request(conn, request)
            cur.execute(
                "INSERT INTO callback_requests (user_id, name, phone, comment) VALUES (%s, %s, %s, %s) RETURNING id, created_at",
                (linked_user["id"] if linked_user else None, clean_name, clean_phone, clean_comment),
            )
            created = cur.fetchone()
        send_telegram(
            "📩 Новая заявка ARC.FITNESS\n"
            f"Имя: {clean_name}\nТелефон: {clean_phone}\nКомментарий: {clean_comment or '—'}\nID: {created['id']}"
        )
        return {"ok": True, "message": "Заявка отправлена. Администратор свяжется с вами.", "id": created["id"]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("create_callback failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось сохранить заявку. Попробуйте позже.")


# ---------- Authentication ----------
@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterInput, request: Request):
    email = str(payload.email).lower().strip()
    full_name = payload.full_name.strip()
    phone = payload.phone.strip() if payload.phone else None
    if phone == "":
        phone = None
    if not full_name:
        raise HTTPException(status_code=422, detail="Введите имя.")
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, is_verified FROM users WHERE email = %s", (email,))
            existing = cur.fetchone()
            if existing and existing["is_verified"]:
                raise HTTPException(status_code=409, detail="Аккаунт с таким email уже существует.")
            if phone:
                cur.execute("SELECT id FROM users WHERE phone = %s AND email <> %s", (phone, email))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Этот номер телефона уже используется.")
            pwd_hash = bcrypt.hashpw(payload.password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")
            if existing:
                user_id = existing["id"]
                cur.execute(
                    "UPDATE users SET full_name=%s, phone=%s, password_hash=%s, updated_at=NOW() WHERE id=%s",
                    (full_name, phone, pwd_hash, user_id),
                )
            else:
                cur.execute(
                    "INSERT INTO users (email, phone, full_name, password_hash) VALUES (%s, %s, %s, %s) RETURNING id",
                    (email, phone, full_name, pwd_hash),
                )
                user_id = cur.fetchone()["id"]
            code = f"{secrets.randbelow(1_000_000):06d}"
            cur.execute("DELETE FROM verification_codes WHERE user_id=%s", (user_id,))
            cur.execute(
                "INSERT INTO verification_codes (user_id, code_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, hash_text(code), now_utc() + timedelta(minutes=10)),
            )
        email_sent = send_email_code(email, full_name, code)
        result = {"ok": True, "message": "Если адрес указан верно, проверьте почту для подтверждения аккаунта.", "email": email}
        if not email_sent and APP_ENV != "development":
            raise HTTPException(status_code=503, detail="Не удалось отправить письмо с кодом подтверждения. Попробуйте позднее.")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("register failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось создать аккаунт. Проверьте данные и подключение к базе.")


@app.post("/api/auth/verify")
def verify_email(payload: VerifyInput, response: Response):
    email = str(payload.email).lower().strip()
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, is_verified FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Аккаунт не найден. Зарегистрируйтесь заново.")
            if user["is_verified"]:
                raise HTTPException(status_code=409, detail="Email уже подтверждён. Войдите в аккаунт.")
            cur.execute(
                """SELECT id, code_hash, expires_at FROM verification_codes
                   WHERE user_id=%s ORDER BY created_at DESC LIMIT 1""",
                (user["id"],),
            )
            code_row = cur.fetchone()
            if not code_row or code_row["expires_at"] <= now_utc() or code_row["code_hash"] != hash_text(payload.code):
                raise HTTPException(status_code=400, detail="Код неверный или срок его действия истёк.")
            cur.execute("UPDATE users SET is_verified=TRUE, updated_at=NOW() WHERE id=%s", (user["id"],))
            cur.execute("DELETE FROM verification_codes WHERE user_id=%s", (user["id"],))
            token = secrets.token_urlsafe(40)
            cur.execute(
                "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user["id"], hash_text(token), now_utc() + timedelta(days=SESSION_DAYS)),
            )
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, secure=APP_ENV == "production",
            samesite="lax", max_age=SESSION_DAYS * 24 * 60 * 60, path="/",
        )
        return {"ok": True, "message": "Email подтверждён. Добро пожаловать в ARC.FITNESS!"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("verify_email failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось подтвердить email. Попробуйте позже.")


@app.post("/api/auth/login")
def login(payload: LoginInput, response: Response):
    identifier = payload.identifier.strip()
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT id, email, phone, full_name, password_hash, role, is_verified
                   FROM users WHERE LOWER(email)=LOWER(%s) OR phone=%s LIMIT 1""",
                (identifier, identifier),
            )
            user = cur.fetchone()
            if not user or not password_matches(payload.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Неверный email/телефон или пароль.")
            if not user["is_verified"]:
                raise HTTPException(status_code=403, detail="Сначала подтвердите email. Код отправлен при регистрации.")
            token = secrets.token_urlsafe(40)
            cur.execute(
                "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user["id"], hash_text(token), now_utc() + timedelta(days=SESSION_DAYS)),
            )
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, secure=APP_ENV == "production",
            samesite="lax", max_age=SESSION_DAYS * 24 * 60 * 60, path="/",
        )
        return {"ok": True, "message": "Вход выполнен.", "user": public_user(user)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("login failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось выполнить вход. Попробуйте позже.")


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            with connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE token_hash=%s", (hash_text(token),))
        except Exception as exc:
            logger.warning("logout cleanup failed: %s", exc)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=APP_ENV == "production")
    return {"ok": True, "message": "Вы вышли из аккаунта."}


@app.get("/api/auth/me")
def auth_me(request: Request):
    try:
        with connection() as conn:
            user = current_user_from_request(conn, request)
            if not user:
                raise HTTPException(status_code=401, detail="Необходимо войти в аккаунт.")
            return {"user": public_user(user)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("auth_me failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось проверить сессию.")


@app.patch("/api/profile")
def update_profile(payload: ProfileInput, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            user = require_user(conn, request)
            phone = payload.phone.strip() if payload.phone else None
            if phone == "":
                phone = None
            if payload.new_password:
                if not payload.current_password:
                    raise HTTPException(status_code=422, detail="Для смены пароля укажите текущий пароль.")
                cur.execute("SELECT password_hash FROM users WHERE id=%s", (user["id"],))
                password_row = cur.fetchone()
                if not password_matches(payload.current_password, password_row["password_hash"]):
                    raise HTTPException(status_code=400, detail="Текущий пароль введён неверно.")
                new_hash = bcrypt.hashpw(payload.new_password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")
                cur.execute(
                    "UPDATE users SET full_name=%s, phone=%s, password_hash=%s, updated_at=NOW() WHERE id=%s",
                    (payload.full_name.strip(), phone, new_hash, user["id"]),
                )
                # Revoke other sessions; the current one remains valid.
                token = request.cookies.get(SESSION_COOKIE)
                cur.execute("DELETE FROM sessions WHERE user_id=%s AND token_hash<>%s", (user["id"], hash_text(token or "")))
            else:
                cur.execute(
                    "UPDATE users SET full_name=%s, phone=%s, updated_at=NOW() WHERE id=%s",
                    (payload.full_name.strip(), phone, user["id"]),
                )
            cur.execute("SELECT id, email, phone, full_name, role, is_verified FROM users WHERE id=%s", (user["id"],))
            updated = cur.fetchone()
        return {"ok": True, "message": "Профиль сохранён.", "user": public_user(updated)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("update_profile failed: %s", exc)
        if "unique constraint" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Этот номер телефона уже используется.")
        raise HTTPException(status_code=503, detail="Не удалось сохранить профиль.")


# ---------- Booking and membership requests ----------
@app.post("/api/bookings", status_code=201)
def create_booking(payload: BookingInput, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            user = require_user(conn, request)
            cur.execute("SELECT id, title, category, capacity FROM classes WHERE id=%s AND is_active=TRUE FOR UPDATE", (payload.class_id,))
            training = cur.fetchone()
            if not training:
                raise HTTPException(status_code=404, detail="Занятие не найдено или больше недоступно.")
            if str(training["category"]).strip().lower() in {"персональная", "персональная тренировка", "индивидуальная"}:
                raise HTTPException(status_code=400, detail="Онлайн-запись доступна только на групповые занятия. Для персональной тренировки оставьте заявку на обратный звонок.")
            cur.execute("SELECT id FROM bookings WHERE user_id=%s AND class_id=%s AND status='active'", (user["id"], payload.class_id))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Вы уже записаны на это занятие.")
            cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (payload.class_id,))
            active_count = cur.fetchone()["count"]
            if active_count >= training["capacity"]:
                cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (active_count, payload.class_id))
                raise HTTPException(status_code=409, detail="Свободных мест больше нет.")
            code = f"ARC-{secrets.randbelow(90000) + 10000}"
            cur.execute(
                "INSERT INTO bookings (user_id, class_id, booking_code) VALUES (%s, %s, %s) RETURNING id, booking_code, created_at",
                (user["id"], payload.class_id, code),
            )
            booking = cur.fetchone()
            cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (active_count + 1, payload.class_id))
        send_telegram(f"🏋️ Новая запись ARC.FITNESS\nПользователь: {user['full_name']}\nЗанятие: {training['title']}\nНомер: {code}")
        return {"ok": True, "message": "Вы записаны на тренировку.", "booking": booking}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("create_booking failed: %s", exc)
        if "uq_active_booking_user_class" in str(exc):
            raise HTTPException(status_code=409, detail="Вы уже записаны на это занятие.")
        raise HTTPException(status_code=503, detail="Не удалось оформить запись.")


@app.get("/api/bookings")
def my_bookings(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            user = require_user(conn, request)
            cur.execute(
                """SELECT b.id, b.booking_code, b.status, b.created_at,
                          c.title, c.category, c.day_of_week, c.starts_at, c.room,
                          t.name AS trainer_name
                   FROM bookings b JOIN classes c ON c.id=b.class_id
                   LEFT JOIN trainers t ON t.id=c.trainer_id
                   WHERE b.user_id=%s ORDER BY b.created_at DESC LIMIT 100""",
                (user["id"],),
            )
            return {"items": cur.fetchall()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("my_bookings failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить записи.")


@app.delete("/api/bookings/{booking_id}")
def cancel_booking(booking_id: int, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            user = require_user(conn, request)
            # Use the same lock order as booking creation: class first, then booking.
            cur.execute(
                "SELECT class_id FROM bookings WHERE id=%s AND user_id=%s AND status='active'",
                (booking_id, user["id"]),
            )
            preview = cur.fetchone()
            if not preview:
                raise HTTPException(status_code=404, detail="Активная запись не найдена.")
            cur.execute("SELECT id FROM classes WHERE id=%s FOR UPDATE", (preview["class_id"],))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Занятие больше не найдено.")
            cur.execute(
                "SELECT id, class_id FROM bookings WHERE id=%s AND user_id=%s AND status='active' FOR UPDATE",
                (booking_id, user["id"]),
            )
            booking = cur.fetchone()
            if not booking:
                raise HTTPException(status_code=409, detail="Запись уже была изменена. Обновите страницу.")
            if booking["class_id"] != preview["class_id"]:
                raise HTTPException(status_code=409, detail="Запись была перенесена. Обновите страницу и повторите действие.")
            cur.execute("UPDATE bookings SET status='cancelled' WHERE id=%s", (booking_id,))
            cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (booking["class_id"],))
            remaining = cur.fetchone()["count"]
            cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (remaining, booking["class_id"]))
        return {"ok": True, "message": "Запись отменена, место освобождено."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("cancel_booking failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось отменить запись.")


@app.get("/api/membership-requests/mine")
def my_membership_requests(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            user = require_user(conn, request)
            cur.execute("UPDATE client_memberships SET status='expired' WHERE user_id=%s AND status='active' AND ends_at <= NOW()", (user["id"],))
            cur.execute(
                """SELECT mr.id, mr.status, mr.created_at, mp.title AS plan_title, mp.price, mp.duration_days
                   FROM membership_requests mr JOIN membership_plans mp ON mp.id=mr.plan_id
                   WHERE mr.user_id=%s ORDER BY mr.created_at DESC LIMIT 50""",
                (user["id"],),
            )
            requests = cur.fetchall()
            cur.execute(
                """SELECT cm.id, cm.starts_at, cm.ends_at, mp.title AS plan_title, mp.price,
                          mp.duration_days, mp.features
                   FROM client_memberships cm JOIN membership_plans mp ON mp.id=cm.plan_id
                   WHERE cm.user_id=%s AND cm.status='active' AND cm.ends_at > NOW()
                   ORDER BY cm.ends_at DESC LIMIT 1""",
                (user["id"],),
            )
            active_membership = cur.fetchone()
            return {"items": requests, "active_membership": active_membership}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("my_membership_requests failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить сведения об абонементах.")


@app.post("/api/membership-requests", status_code=201)
def request_membership(payload: MembershipRequestInput, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            user = require_user(conn, request)
            cur.execute("SELECT id, title, price FROM membership_plans WHERE plan_key=%s AND is_active=TRUE", (payload.plan_key,))
            plan = cur.fetchone()
            if not plan:
                raise HTTPException(status_code=404, detail="Тариф не найден.")
            cur.execute(
                "INSERT INTO membership_requests (user_id, plan_id) VALUES (%s, %s) RETURNING id",
                (user["id"], plan["id"]),
            )
            request_id = cur.fetchone()["id"]
        send_telegram(f"💳 Заявка на абонемент ARC.FITNESS\nПользователь: {user['full_name']}\nТариф: {plan['title']}\nЦена на сайте: {plan['price']} ₽\nЗаявка №{request_id}")
        return {"ok": True, "message": "Заявка на оформление отправлена. Администратор свяжется с вами.", "id": request_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("request_membership failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось оформить заявку на абонемент.")


# ---------- Admin API: all endpoints check role on the server ----------
@app.get("/api/admin/overview")
def admin_overview(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute("SELECT COUNT(*) AS count FROM users WHERE role='user'")
            users_count = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE status='active'")
            bookings_count = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) AS count FROM callback_requests WHERE status='new'")
            callbacks_count = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) AS count FROM membership_requests WHERE status='new'")
            memberships_count = cur.fetchone()["count"]
        return {"users": users_count, "active_bookings": bookings_count, "new_callbacks": callbacks_count, "new_membership_requests": memberships_count}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_overview failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить сводку.")


@app.get("/api/admin/callbacks")
def admin_callbacks(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute("SELECT id, name, phone, comment, status, created_at FROM callback_requests ORDER BY created_at DESC LIMIT 200")
            return {"items": cur.fetchall()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_callbacks failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить обращения.")


@app.patch("/api/admin/callbacks/{callback_id}/processed")
def process_callback(callback_id: int, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute("UPDATE callback_requests SET status='processed' WHERE id=%s RETURNING id", (callback_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Обращение не найдено.")
        return {"ok": True, "message": "Обращение отмечено обработанным."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("process_callback failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось обновить обращение.")


@app.get("/api/admin/bookings")
def admin_bookings(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(
                """SELECT b.id, b.user_id, b.class_id, b.booking_code, b.status, b.created_at,
                          u.full_name, u.email, u.phone, c.title AS class_title, c.category,
                          c.day_of_week, c.starts_at, c.room, c.duration_minutes
                   FROM bookings b JOIN users u ON u.id=b.user_id JOIN classes c ON c.id=b.class_id
                   ORDER BY b.created_at DESC LIMIT 300"""
            )
            return {"items": cur.fetchall()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_bookings failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить записи.")


@app.get("/api/admin/membership-requests")
def admin_membership_requests(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(
                """SELECT mr.id, mr.status, mr.created_at, u.full_name, u.email, u.phone,
                          mp.title AS plan_title, mp.price
                   FROM membership_requests mr JOIN users u ON u.id=mr.user_id
                   JOIN membership_plans mp ON mp.id=mr.plan_id
                   ORDER BY mr.created_at DESC LIMIT 300"""
            )
            return {"items": cur.fetchall()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_membership_requests failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить заявки на абонементы.")


@app.get("/api/admin/requests")
def admin_all_requests(request: Request):
    """Единый список заявок: обратный звонок, абонемент и запись на групповое занятие."""
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            items = []
            cur.execute("""SELECT cr.id, cr.user_id, cr.name, cr.phone, cr.comment, cr.status, cr.created_at,
                              u.email AS user_email
                       FROM callback_requests cr LEFT JOIN users u ON u.id=cr.user_id
                       ORDER BY cr.created_at DESC LIMIT 300""")
            for row in cur.fetchall():
                items.append({
                    "type": "callback", "type_label": "Обратный звонок", "id": row["id"],
                    "user_id": row["user_id"], "created_at": row["created_at"], "status": row["status"],
                    "client_name": row["name"], "phone": row["phone"], "email": row["user_email"],
                    "title": "Заявка на обратный звонок", "details": row["comment"] or "Комментарий не указан",
                    "comment": row["comment"] or "",
                })
            cur.execute(
                """SELECT mr.id, mr.status, mr.created_at, u.id AS user_id, u.full_name, u.email, u.phone,
                          mp.plan_key, mp.title AS plan_title, mp.price, mp.duration_days
                   FROM membership_requests mr JOIN users u ON u.id=mr.user_id
                   JOIN membership_plans mp ON mp.id=mr.plan_id
                   ORDER BY mr.created_at DESC LIMIT 300"""
            )
            for row in cur.fetchall():
                items.append({
                    "type": "membership", "type_label": "Заявка на абонемент", "id": row["id"],
                    "user_id": row["user_id"], "created_at": row["created_at"], "status": row["status"],
                    "client_name": row["full_name"], "phone": row["phone"], "email": row["email"],
                    "title": row["plan_title"], "details": f"Тариф: {row['plan_title']} · {row['price']} ₽ · {row['duration_days']} дней",
                    "plan_key": row["plan_key"], "plan_title": row["plan_title"], "price": row["price"],
                })
            cur.execute(
                """SELECT b.id, b.booking_code, b.status, b.created_at, b.class_id, u.id AS user_id,
                          u.full_name, u.email, u.phone, c.title AS class_title, c.category,
                          c.day_of_week, c.starts_at, c.duration_minutes, c.room, t.name AS trainer_name
                   FROM bookings b JOIN users u ON u.id=b.user_id JOIN classes c ON c.id=b.class_id
                   LEFT JOIN trainers t ON t.id=c.trainer_id
                   ORDER BY b.created_at DESC LIMIT 300"""
            )
            for row in cur.fetchall():
                start = row["starts_at"].strftime("%H:%M") if hasattr(row["starts_at"], "strftime") else str(row["starts_at"])[:5]
                details = f"{row['class_title']} · {day_name(row['day_of_week'])}, {start} · {row['room']} · {row['booking_code']}"
                items.append({
                    "type": "booking", "type_label": "Запись на тренировку", "id": row["id"],
                    "user_id": row["user_id"], "created_at": row["created_at"], "status": row["status"],
                    "client_name": row["full_name"], "phone": row["phone"], "email": row["email"],
                    "title": row["class_title"], "details": details, "class_id": row["class_id"],
                    "class_title": row["class_title"], "day_of_week": row["day_of_week"],
                    "starts_at": start, "room": row["room"], "booking_code": row["booking_code"],
                })
        items.sort(key=lambda item: item["created_at"].timestamp() if item.get("created_at") else 0, reverse=True)
        return {"items": items[:500]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_all_requests failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить список заявок.")


@app.patch("/api/admin/requests/{request_type}/{request_id}")
def admin_update_request_status(request_type: str, request_id: int, payload: AdminRequestStatusInput, request: Request):
    allowed = {
        "callback": {"new", "processed", "closed"},
        "membership": {"new", "processed", "cancelled"},
    }
    if request_type not in allowed:
        raise HTTPException(status_code=400, detail="Для этого типа заявки используйте управление записями на тренировки.")
    if payload.status not in allowed[request_type]:
        raise HTTPException(status_code=422, detail="Недопустимый статус заявки.")
    table = "callback_requests" if request_type == "callback" else "membership_requests"
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(f"UPDATE {table} SET status=%s WHERE id=%s RETURNING id", (payload.status, request_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Заявка не найдена.")
        return {"ok": True, "message": "Статус заявки обновлён."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_update_request_status failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось изменить статус заявки.")


@app.get("/api/admin/clients")
def admin_clients(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(
                """SELECT u.id, u.full_name, u.email, u.phone, u.is_verified, u.created_at,
                          cm.id AS membership_id, mp.title AS membership_title, cm.ends_at AS membership_ends_at
                   FROM users u
                   LEFT JOIN LATERAL (
                       SELECT cm0.* FROM client_memberships cm0
                       WHERE cm0.user_id=u.id AND cm0.status='active' AND cm0.ends_at > NOW()
                       ORDER BY cm0.ends_at DESC LIMIT 1
                   ) cm ON TRUE
                   LEFT JOIN membership_plans mp ON mp.id=cm.plan_id
                   WHERE u.role='user' ORDER BY u.created_at DESC LIMIT 1000"""
            )
            return {"items": cur.fetchall()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_clients failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить клиентов.")


@app.get("/api/admin/clients/{user_id}")
def admin_client_detail(user_id: int, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute("SELECT id, full_name, email, phone, is_verified, created_at FROM users WHERE id=%s AND role='user'", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Клиент не найден.")
            cur.execute("UPDATE client_memberships SET status='expired' WHERE user_id=%s AND status='active' AND ends_at <= NOW()", (user_id,))
            cur.execute(
                """SELECT cm.id, cm.status, cm.starts_at, cm.ends_at, cm.created_at, mp.plan_key,
                          mp.title AS plan_title, mp.price, mp.duration_days, mp.features
                   FROM client_memberships cm JOIN membership_plans mp ON mp.id=cm.plan_id
                   WHERE cm.user_id=%s ORDER BY cm.created_at DESC LIMIT 30""", (user_id,)
            )
            memberships = cur.fetchall()
            cur.execute(
                """SELECT mr.id, mr.status, mr.created_at, mp.title AS plan_title, mp.price
                   FROM membership_requests mr JOIN membership_plans mp ON mp.id=mr.plan_id
                   WHERE mr.user_id=%s ORDER BY mr.created_at DESC LIMIT 30""", (user_id,)
            )
            membership_requests = cur.fetchall()
            cur.execute(
                """SELECT b.id, b.booking_code, b.status, b.created_at, b.class_id,
                          c.title AS class_title, c.category, c.day_of_week, c.starts_at, c.room
                   FROM bookings b JOIN classes c ON c.id=b.class_id
                   WHERE b.user_id=%s ORDER BY b.created_at DESC LIMIT 50""", (user_id,)
            )
            bookings = cur.fetchall()
            cur.execute("SELECT plan_key, title, price, duration_days FROM membership_plans WHERE is_active=TRUE ORDER BY price")
            plans = cur.fetchall()
        return {"user": user, "memberships": memberships, "membership_requests": membership_requests, "bookings": bookings, "plans": plans}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_client_detail failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить информацию о клиенте.")


@app.post("/api/admin/clients/{user_id}/membership", status_code=201)
def admin_assign_membership(user_id: int, payload: ClientMembershipInput, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            admin = require_admin(conn, request)
            cur.execute("SELECT id FROM users WHERE id=%s AND role='user' FOR UPDATE", (user_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Клиент не найден.")
            cur.execute("UPDATE client_memberships SET status='expired' WHERE user_id=%s AND status='active' AND ends_at <= NOW()", (user_id,))
            cur.execute("SELECT id FROM client_memberships WHERE user_id=%s AND status='active' AND ends_at > NOW() FOR UPDATE", (user_id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="У клиента уже есть активный абонемент. Сначала отвяжите его.")
            cur.execute("SELECT id, title, price, duration_days FROM membership_plans WHERE plan_key=%s AND is_active=TRUE", (payload.plan_key,))
            plan = cur.fetchone()
            if not plan:
                raise HTTPException(status_code=404, detail="Выбранный тариф не найден.")
            cur.execute(
                """INSERT INTO client_memberships (user_id, plan_id, assigned_by, starts_at, ends_at, status)
                   VALUES (%s, %s, %s, NOW(), NOW() + (%s * INTERVAL '1 day'), 'active')
                   RETURNING id, starts_at, ends_at""",
                (user_id, plan["id"], admin["id"], plan["duration_days"]),
            )
            assigned = cur.fetchone()
            cur.execute("UPDATE membership_requests SET status='processed' WHERE user_id=%s AND status='new'", (user_id,))
        return {"ok": True, "message": f"Абонемент «{plan['title']}» привязан к клиенту.", "membership": {**assigned, "plan_title": plan["title"], "price": plan["price"]}}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_assign_membership failed: %s", exc)
        if "uq_one_active_membership_per_user" in str(exc):
            raise HTTPException(status_code=409, detail="У клиента уже есть активный абонемент.")
        raise HTTPException(status_code=503, detail="Не удалось привязать абонемент.")


@app.delete("/api/admin/clients/{user_id}/membership")
def admin_revoke_membership(user_id: int, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(
                """UPDATE client_memberships SET status='revoked', revoked_at=NOW()
                   WHERE user_id=%s AND status='active' AND ends_at > NOW() RETURNING id""", (user_id,)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="У клиента нет активного абонемента.")
        return {"ok": True, "message": "Абонемент отвязан от клиента."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_revoke_membership failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось отвязать абонемент.")


@app.get("/api/admin/classes")
def admin_group_classes(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(
                """SELECT c.id, c.title, c.category, c.day_of_week, c.starts_at, c.duration_minutes,
                          c.room, c.trainer_id, c.capacity, c.booked_count, t.name AS trainer_name
                   FROM classes c LEFT JOIN trainers t ON t.id=c.trainer_id
                   WHERE c.is_active=TRUE AND LOWER(c.category) NOT IN ('персональная', 'персональная тренировка', 'индивидуальная')
                   ORDER BY c.day_of_week, c.starts_at"""
            )
            items=[]
            for row in cur.fetchall():
                row=dict(row)
                start=row["starts_at"].strftime("%H:%M") if hasattr(row["starts_at"], "strftime") else str(row["starts_at"])[:5]
                items.append({**row, "starts_at":start, "day_label":day_name(row["day_of_week"]), "available":max(0, row["capacity"]-row["booked_count"])})
            return {"items":items}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_group_classes failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить групповые занятия.")


@app.patch("/api/admin/bookings/{booking_id}")
def admin_update_booking(booking_id: int, payload: AdminBookingUpdateInput, request: Request):
    if payload.class_id is None and payload.status is None:
        raise HTTPException(status_code=422, detail="Укажите новую тренировку или статус записи.")
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            # Read without locking first so we can acquire class locks in a stable order.
            cur.execute("SELECT id, user_id, class_id, status FROM bookings WHERE id=%s", (booking_id,))
            preview = cur.fetchone()
            if not preview:
                raise HTTPException(status_code=404, detail="Запись не найдена.")

            target_class_id = payload.class_id if payload.class_id is not None else preview["class_id"]
            lock_ids = sorted({preview["class_id"], target_class_id})
            cur.execute("SELECT id, title, category, capacity, is_active FROM classes WHERE id = ANY(%s) ORDER BY id FOR UPDATE", (lock_ids,))
            class_rows = {row["id"]: row for row in cur.fetchall()}
            cur.execute("SELECT id, user_id, class_id, status FROM bookings WHERE id=%s FOR UPDATE", (booking_id,))
            booking = cur.fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Запись не найдена.")
            if booking["class_id"] != preview["class_id"]:
                raise HTTPException(status_code=409, detail="Запись одновременно изменили. Обновите данные и повторите действие.")

            if payload.status == "cancelled":
                if booking["status"] == "cancelled":
                    return {"ok": True, "message": "Эта запись уже отменена."}
                cur.execute("UPDATE bookings SET status='cancelled' WHERE id=%s", (booking_id,))
                cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (booking["class_id"],))
                remaining = cur.fetchone()["count"]
                cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (remaining, booking["class_id"]))
                return {"ok": True, "message": "Запись отменена, место освобождено."}

            if payload.status == "active" and booking["status"] == "cancelled":
                raise HTTPException(status_code=409, detail="Отменённую запись нельзя восстановить. Создайте новую запись клиента.")

            if payload.class_id is not None and payload.class_id != booking["class_id"]:
                if booking["status"] != "active":
                    raise HTTPException(status_code=409, detail="Нельзя перенести уже отменённую запись.")
                old_class = class_rows.get(booking["class_id"])
                new_class = class_rows.get(payload.class_id)
                if not old_class or not new_class or not old_class["is_active"] or not new_class["is_active"]:
                    raise HTTPException(status_code=404, detail="Исходное или новое занятие не найдено.")
                if str(new_class["category"]).strip().lower() in {"персональная", "персональная тренировка", "индивидуальная"}:
                    raise HTTPException(status_code=400, detail="Перенос доступен только на групповое занятие.")
                cur.execute("SELECT id FROM bookings WHERE user_id=%s AND class_id=%s AND status='active' AND id<>%s", (booking["user_id"], payload.class_id, booking_id))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="У клиента уже есть активная запись на это занятие.")
                cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (payload.class_id,))
                target_count = cur.fetchone()["count"]
                if target_count >= new_class["capacity"]:
                    cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (target_count, payload.class_id))
                    raise HTTPException(status_code=409, detail="В выбранной группе нет свободных мест.")
                cur.execute("UPDATE bookings SET class_id=%s WHERE id=%s", (payload.class_id, booking_id))
                cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (booking["class_id"],))
                old_count = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (payload.class_id,))
                new_count = cur.fetchone()["count"]
                cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (old_count, booking["class_id"]))
                cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (new_count, payload.class_id))
        return {"ok": True, "message": "Запись на тренировку обновлена."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_update_booking failed: %s", exc)
        if "uq_active_booking_user_class" in str(exc):
            raise HTTPException(status_code=409, detail="У клиента уже есть запись на выбранное занятие.")
        raise HTTPException(status_code=503, detail="Не удалось изменить запись на тренировку.")


@app.post("/api/admin/classes", status_code=201)
def admin_create_class(payload: ClassCreateInput, request: Request):
    if payload.category.strip().lower() in {"персональная", "персональная тренировка", "индивидуальная"}:
        raise HTTPException(status_code=422, detail="Онлайн-расписание предназначено для групповых занятий.")
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            if payload.trainer_id is not None:
                cur.execute("SELECT id FROM trainers WHERE id=%s AND is_active=TRUE", (payload.trainer_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Выбранный тренер не найден.")
            cur.execute(
                """INSERT INTO classes (title, category, day_of_week, starts_at, duration_minutes, room, trainer_id, capacity)
                   VALUES (%s, %s, %s, %s::time, %s, %s, %s, %s) RETURNING id""",
                (payload.title.strip(), payload.category.strip(), payload.day_of_week, payload.starts_at,
                 payload.duration_minutes, payload.room.strip(), payload.trainer_id, payload.capacity),
            )
            class_id = cur.fetchone()["id"]
        return {"ok": True, "id": class_id, "message": "Занятие добавлено в расписание."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_create_class failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось добавить занятие.")


@app.patch("/api/admin/classes/{class_id}")
def admin_update_class(class_id: int, payload: AdminClassUpdateInput, request: Request):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Нет изменений для сохранения.")
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(
                """SELECT id, title, category, day_of_week, starts_at, duration_minutes, room,
                          trainer_id, capacity, booked_count, is_active
                   FROM classes WHERE id=%s FOR UPDATE""",
                (class_id,),
            )
            current = cur.fetchone()
            if not current or not current["is_active"]:
                raise HTTPException(status_code=404, detail="Занятие не найдено или уже скрыто.")
            if str(current["category"]).strip().lower() in {"персональная", "персональная тренировка", "индивидуальная"}:
                raise HTTPException(status_code=400, detail="В панели доступны групповые занятия.")

            fields = {
                "title": current["title"],
                "category": current["category"],
                "day_of_week": current["day_of_week"],
                "starts_at": current["starts_at"].strftime("%H:%M") if hasattr(current["starts_at"], "strftime") else str(current["starts_at"])[:5],
                "duration_minutes": current["duration_minutes"],
                "room": current["room"],
                "trainer_id": current["trainer_id"],
                "capacity": current["capacity"],
            }
            fields.update(updates)
            required_fields = ("title", "category", "day_of_week", "starts_at", "duration_minutes", "room", "capacity")
            if any(fields.get(key) is None for key in required_fields):
                raise HTTPException(status_code=422, detail="Заполните все поля занятия.")
            fields["title"] = fields["title"].strip()
            fields["category"] = fields["category"].strip()
            fields["room"] = fields["room"].strip()
            if not fields["title"] or not fields["room"]:
                raise HTTPException(status_code=422, detail="Название занятия и зал обязательны.")
            if fields["category"].lower() in {"персональная", "персональная тренировка", "индивидуальная"}:
                raise HTTPException(status_code=422, detail="Категория должна быть групповой тренировкой.")
            cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (class_id,))
            actual_bookings = cur.fetchone()["count"]
            cur.execute("UPDATE classes SET booked_count=%s WHERE id=%s", (actual_bookings, class_id))
            if int(fields["capacity"]) < int(actual_bookings):
                raise HTTPException(status_code=409, detail=f"В группе уже {actual_bookings} активных записей. Вместимость нельзя уменьшить ниже этого количества.")
            if fields["trainer_id"] is not None:
                cur.execute("SELECT id FROM trainers WHERE id=%s AND is_active=TRUE", (fields["trainer_id"],))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Выбранный тренер не найден.")
            cur.execute(
                """UPDATE classes
                   SET title=%s, category=%s, day_of_week=%s, starts_at=%s::time,
                       duration_minutes=%s, room=%s, trainer_id=%s, capacity=%s
                   WHERE id=%s RETURNING id""",
                (fields["title"], fields["category"], fields["day_of_week"], fields["starts_at"],
                 fields["duration_minutes"], fields["room"], fields["trainer_id"], fields["capacity"], class_id),
            )
        return {"ok": True, "message": "Расписание обновлено."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_update_class failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось обновить занятие.")


@app.delete("/api/admin/classes/{class_id}")
def admin_delete_class(class_id: int, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute("SELECT id FROM classes WHERE id=%s AND is_active=TRUE FOR UPDATE", (class_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Занятие не найдено.")
            cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE class_id=%s AND status='active'", (class_id,))
            active_count = cur.fetchone()["count"]
            if active_count:
                raise HTTPException(status_code=409, detail=f"На занятие уже записаны клиенты ({active_count}). Сначала перенесите или отмените эти записи.")
            cur.execute("UPDATE classes SET is_active=FALSE WHERE id=%s", (class_id,))
        return {"ok": True, "message": "Занятие скрыто из расписания."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_delete_class failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось скрыть занятие.")


@app.get("/api/admin/news")
def admin_news(request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute("SELECT id, title, category, excerpt, body, image_path, published_at, is_published FROM news ORDER BY published_at DESC")
            return {"items": cur.fetchall()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_news failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось загрузить новости для управления.")


@app.post("/api/admin/news", status_code=201)
def admin_create_news(payload: NewsCreateInput, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute(
                """INSERT INTO news (title, category, excerpt, body, image_path, published_at, is_published)
                   VALUES (%s, %s, %s, %s, %s, NOW(), TRUE) RETURNING id""",
                (payload.title.strip(), payload.category.strip(), payload.excerpt.strip(), payload.body.strip(), payload.image_path.strip()),
            )
            news_id = cur.fetchone()["id"]
        return {"ok": True, "id": news_id, "message": "Новость опубликована."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_create_news failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось опубликовать новость.")


@app.delete("/api/admin/news/{news_id}")
def admin_delete_news(news_id: int, request: Request):
    try:
        with connection() as conn, conn.cursor() as cur:
            require_admin(conn, request)
            cur.execute("UPDATE news SET is_published=FALSE WHERE id=%s RETURNING id", (news_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Новость не найдена.")
        return {"ok": True, "message": "Новость снята с публикации."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("admin_delete_news failed: %s", exc)
        raise HTTPException(status_code=503, detail="Не удалось снять новость с публикации.")


# ---------- HTML pages ----------
@app.get("/", response_class=HTMLResponse)
def home_page():
    return FileResponse(ROOT / "pages" / "index.html")


@app.get("/{page_name}", response_class=HTMLResponse)
def html_page(page_name: str, request: Request):
    if page_name.endswith(".html"):
        page_name = page_name[:-5]
    if page_name in {"index", "home"}:
        return FileResponse(ROOT / "pages" / "index.html")
    if page_name == "admin":
        try:
            with connection() as conn:
                current = current_user_from_request(conn, request)
                if not current:
                    return RedirectResponse(url="/login?next=/admin", status_code=303)
                if current["role"] != "admin":
                    return RedirectResponse(url="/account", status_code=303)
        except Exception as exc:
            logger.warning("Admin page access check failed: %s", exc)
            return RedirectResponse(url="/login?next=/admin", status_code=303)
    file_name = PAGE_FILES.get(page_name)
    if not file_name:
        raise HTTPException(status_code=404, detail="Страница не найдена.")
    return FileResponse(ROOT / "pages" / file_name)
