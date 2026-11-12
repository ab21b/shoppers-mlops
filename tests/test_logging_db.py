import os
import time

import pytest

from shoppers import db
from shoppers.config import settings


@pytest.fixture()
def captured(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "save_prediction", lambda *a, **k: calls.append(a))
    return calls


def test_success_is_logged_with_status_200(client, good_row, captured):
    r = client.post("/v1/predict", json=good_row)
    assert r.status_code == 200
    (call,) = captured
    request_id, features, version, score, purchase, latency_ms, status = call
    assert request_id == r.json()["request_id"] and features == good_row
    assert status == 200 and score == r.json()["score"]


def test_validation_error_is_logged_with_status_422(client, good_row, captured):
    r = client.post("/v1/predict", json={**good_row, "PageValues": -1})
    assert r.status_code == 422
    (call,) = captured
    assert call[-1] == 422 and call[3] is None  # кода ответа 422, предсказания нет


def test_service_works_without_database_url(client, good_row, monkeypatch):
    monkeypatch.setattr(settings, "database_url", None)
    assert client.post("/v1/predict", json=good_row).status_code == 200


def test_unreachable_db_does_not_break_predict(client, good_row, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@127.0.0.1:1/none")
    assert client.post("/v1/predict", json=good_row).status_code == 200


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="нужен DATABASE_URL")
def test_row_lands_in_postgres(client, good_row):
    import psycopg

    r = client.post("/v1/predict", json=good_row).json()
    time.sleep(0.5)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute("SELECT status_code, features->>'Month' FROM predictions WHERE request_id = %s",
                           (r["request_id"],)).fetchone() 
    assert row == (200, "Nov")


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="нужен DATABASE_URL")
def test_validation_error_is_persisted_with_status_422(client, good_row):
    import psycopg

    response = client.post("/v1/predict", json={**good_row, "PageValues": -1})
    assert response.status_code == 422
    request_id = response.json()["request_id"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT status_code, score FROM predictions WHERE request_id = %s",
            (request_id,),
        ).fetchone()
    assert row == (422, None)


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="нужен DATABASE_URL")
def test_malformed_json_is_persisted_with_status_422(client):
    import psycopg

    response = client.post(
        "/v1/predict",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    request_id = response.json()["request_id"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT status_code FROM predictions WHERE request_id = %s",
            (request_id,),
        ).fetchone()
    assert row == (422,)
