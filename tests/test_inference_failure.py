"""Сбой модели при инференсе: ответ 500, request_id в ответе и строка в журнале без выдуманного score."""

import os
import time
import uuid

import pytest

from shoppers import db


class BrokenPipeline:
    """Подмена модели: predict_proba всегда падает."""

    def predict_proba(self, X):
        raise RuntimeError("boom: модель сломалась")


@pytest.fixture()
def broken_model(client):
    """Подменяем модель вручную и возвращаем настоящую: monkeypatch на app.state не восстанавливает атрибут."""
    real = client.app.state.pipeline
    client.app.state.pipeline = BrokenPipeline()
    yield
    client.app.state.pipeline = real


def test_inference_failure_returns_500_and_is_logged(client, good_row, broken_model, monkeypatch):
    calls = []
    monkeypatch.setattr(db, "save_prediction", lambda *a, **k: calls.append(a))

    r = client.post("/v1/predict", json=good_row)

    assert r.status_code == 500
    body = r.json()
    uuid.UUID(body["request_id"])                
    assert "score" not in body and "purchase" not in body
    assert "boom" not in r.text           

    (call,) = calls            
    request_id, features, version, score, purchase, latency_ms, status_code = call
    assert request_id == body["request_id"]  
    assert features == good_row
    assert status_code == 500
    assert score is None and purchase is None     
    assert latency_ms >= 0


def test_service_stays_alive_after_inference_failure(client, good_row, broken_model):
    assert client.post("/v1/predict", json=good_row).status_code == 500
    assert client.post("/v1/predict", json=good_row).status_code == 500  
    assert client.get("/health").status_code == 200


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="нужен DATABASE_URL")
def test_inference_failure_row_in_postgres(client, good_row, broken_model):
    import psycopg

    r = client.post("/v1/predict", json=good_row)
    assert r.status_code == 500
    request_id = r.json()["request_id"]

    deadline, row = time.time() + 5, None       
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        while row is None and time.time() < deadline:
            row = conn.execute(
                "SELECT status_code, score, purchase, features->>'Month' FROM predictions WHERE request_id = %s",
                (request_id,),
            ).fetchone()
            time.sleep(0.2)
    assert row == (500, None, None, good_row["Month"])  
