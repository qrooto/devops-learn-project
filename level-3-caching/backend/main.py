"""
Bulletin Board API v2 — Кэширование через Redis
Что добавлено к уровню 2:
  - Redis-кэш для GET /api/ads с TTL 30 секунд
  - Инвалидация кэша при POST/DELETE (данные изменились — кэш устарел)
  - /api/cache-stats: видим hits vs misses в реальном времени

Зачем кэш?
  GET /api/ads при каждом запросе делает JOIN к БД + сортировку.
  При 100 RPS это 100 запросов в секунду к PostgreSQL.
  С кэшем: первый запрос идёт в БД, следующие 30 секунд — из Redis (~0.1ms vs ~5ms).
"""
import os
import time
import json
import socket
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import redis

from auth import hash_password, verify_password, create_access_token, get_current_user, require_user

app = FastAPI(title="Bulletin Board API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
CACHE_TTL = 30  # секунд — как долго список объявлений живёт в кэше
INSTANCE_ID = socket.gethostname()

cache = redis.from_url(REDIS_URL, decode_responses=True)


def get_engine():
    for attempt in range(10):
        try:
            engine = create_engine(
                DATABASE_URL,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception as e:
            print(f"DB not ready ({attempt + 1}/10): {e}")
            time.sleep(2)
    raise RuntimeError("Cannot connect to database after 10 attempts")


engine = get_engine()


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AdCreate(BaseModel):
    title: str
    description: str
    price: int


# ── Auth ───────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register", status_code=201)
def register(body: RegisterRequest):
    with engine.connect() as conn:
        if conn.execute(
            text("SELECT id FROM users WHERE username = :u OR email = :e"),
            {"u": body.username, "e": body.email},
        ).fetchone():
            raise HTTPException(409, "Username or email already taken")
        row = conn.execute(
            text("INSERT INTO users (username, email, password_hash) VALUES (:u, :e, :p) RETURNING id"),
            {"u": body.username, "e": body.email, "p": hash_password(body.password)},
        ).fetchone()
        conn.commit()
    return {"access_token": create_access_token(row[0], body.username), "token_type": "bearer"}


@app.post("/api/auth/login")
def login(body: LoginRequest):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, password_hash FROM users WHERE username = :u"),
            {"u": body.username},
        ).fetchone()
    if not row or not verify_password(body.password, row[1]):
        raise HTTPException(401, "Wrong username or password")
    return {"access_token": create_access_token(row[0], body.username), "token_type": "bearer"}


@app.get("/api/auth/me")
def me(user: dict = Depends(require_user)):
    return user


# ── System ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "instance": INSTANCE_ID}


@app.get("/api/cache-stats")
def cache_stats():
    """
    Статистика кэша Redis. Ключевые метрики:
    - hits: сколько раз данные были взяты из кэша (быстро, ~0.1ms)
    - misses: сколько раз кэш был пуст и мы пошли в БД (~5ms)
    - hit_rate: процент кэш-хитов — чем выше, тем лучше
    """
    info = cache.info("stats")
    hits = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    return {
        "hits": hits,
        "misses": misses,
        "hit_rate_percent": round(hits / max(hits + misses, 1) * 100, 1),
        "cache_ttl_seconds": CACHE_TTL,
    }


# ── Ads ────────────────────────────────────────────────────────────────────────

@app.get("/api/ads")
def list_ads():
    cached = cache.get("ads:list")
    if cached:
        # Cache HIT — данные из Redis, PostgreSQL не трогаем
        return json.loads(cached)

    # Cache MISS — идём в БД, кладём результат в Redis на CACHE_TTL секунд
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT a.id, a.title, a.description, a.price,
                   COALESCE(u.username, 'anonymous') AS author, a.created_at
            FROM ads a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.created_at DESC
        """)).fetchall()

    result = [
        {"id": r[0], "title": r[1], "description": r[2],
         "price": r[3], "author": r[4], "created_at": str(r[5])}
        for r in rows
    ]
    cache.setex("ads:list", CACHE_TTL, json.dumps(result))
    return result


@app.post("/api/ads", status_code=201)
def create_ad(ad: AdCreate, user: dict = Depends(require_user)):
    with engine.connect() as conn:
        row = conn.execute(
            text("INSERT INTO ads (title, description, price, user_id) VALUES (:t, :d, :p, :uid) RETURNING id"),
            {"t": ad.title, "d": ad.description, "p": ad.price, "uid": user["id"]},
        ).fetchone()
        conn.commit()
    # Инвалидируем кэш — новое объявление должно появиться немедленно
    cache.delete("ads:list")
    return {"id": row[0], "title": ad.title, "description": ad.description,
            "price": ad.price, "author": user["username"]}


@app.get("/api/ads/{ad_id}")
def get_ad(ad_id: int):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT a.id, a.title, a.description, a.price,
                   COALESCE(u.username, 'anonymous') AS author, a.created_at
            FROM ads a LEFT JOIN users u ON a.user_id = u.id WHERE a.id = :id
        """), {"id": ad_id}).fetchone()
    if not row:
        raise HTTPException(404, "Ad not found")
    return {"id": row[0], "title": row[1], "description": row[2],
            "price": row[3], "author": row[4], "created_at": str(row[5])}


@app.delete("/api/ads/{ad_id}", status_code=204)
def delete_ad(ad_id: int, user: dict = Depends(require_user)):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT user_id FROM ads WHERE id = :id"), {"id": ad_id}).fetchone()
        if not row:
            raise HTTPException(404, "Ad not found")
        if row[0] != user["id"]:
            raise HTTPException(403, "You can only delete your own ads")
        conn.execute(text("DELETE FROM ads WHERE id = :id"), {"id": ad_id})
        conn.commit()
    cache.delete("ads:list")
