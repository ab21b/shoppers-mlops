import uuid

import pandas as pd

from shoppers.schemas import Features
from tests.conftest import ROOT


def test_predict_smoke(client, good_row):
    r = client.post("/v1/predict", json=good_row)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["score"], float) and 0.0 <= body["score"] <= 1.0
    assert isinstance(body["purchase"], bool)
    assert body["model_version"] == "1.0.0"
    assert isinstance(body["latency_ms"], float) and body["latency_ms"] >= 0
    uuid.UUID(body["request_id"]) 


def test_purchase_follows_threshold(client, good_row):
    body = client.post("/v1/predict", json=good_row).json()
    assert body["purchase"] == (body["score"] >= client.app.state.threshold)


def test_model_separates_obvious_cases(client, good_row):
    low = client.post("/v1/predict", json={**good_row, "PageValues": 0.0}).json()["score"]
    high = client.post("/v1/predict", json={**good_row, "PageValues": 60.0}).json()["score"]
    assert high > low


def test_every_dataset_row_passes_contract():
    df = pd.read_csv(ROOT / "tests" / "fixtures" / "sessions_sample.csv").drop(columns="Revenue")
    for row in df.to_dict("records"):
        Features.model_validate(row)


def test_health_and_ready(client):
    h = client.get("/health")
    assert h.status_code == 200 and h.json()["status"] == "ok"
    assert h.json()["prediction_threshold"] == client.app.state.threshold
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
