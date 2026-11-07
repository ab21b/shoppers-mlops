from __future__ import annotations

import logging

import psycopg
from psycopg.types.json import Json

from shoppers.config import settings

log = logging.getLogger("shoppers.db")

DDL = """
CREATE TABLE IF NOT EXISTS predictions (
    request_id    uuid PRIMARY KEY,
    ts            timestamptz NOT NULL DEFAULT now(),
    model_version text        NOT NULL,
    features      jsonb       NOT NULL,
    score         double precision,          -- NULL, если предсказания не было (422/500)
    purchase      boolean,                   -- итоговый класс по порогу
    latency_ms    real,
    status_code   integer     NOT NULL       
)
"""

_table_ready = False


def enabled() -> bool:
    return bool(settings.database_url)


def _ensure_table(conn: psycopg.Connection) -> None:
    global _table_ready
    if _table_ready:
        return
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(7001)") 
        conn.execute(DDL)
    _table_ready = True


def init() -> None:
    """Вызывается в lifespan. Ошибка БД не должна ронять сервис: логируем и работаем дальше."""
    if not enabled():
        log.info("DATABASE_URL не задан: логирование в Postgres выключено")
        return
    try:
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            _ensure_table(conn)
        log.info("таблица predictions готова")
    except Exception:
        log.exception("не удалось подготовить таблицу predictions; повторим при первой записи")


def save_prediction(
    request_id: str,
    features: dict,
    model_version: str,
    score: float | None,
    purchase: bool | None,
    latency_ms: float,
    status_code: int,
) -> None:
    if not enabled():
        return
    try:
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO predictions (request_id, model_version, features, score, purchase, latency_ms, status_code) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (request_id, model_version, Json(features), score, purchase, latency_ms, status_code),
            )
    except Exception:
        # запись в лог не должна превращать успешный предикт в ошибку
        log.exception("не удалось записать запрос %s в Postgres", request_id)
