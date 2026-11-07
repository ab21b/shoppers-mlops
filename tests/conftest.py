import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shoppers.service.app import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # with -> отрабатывает lifespan, модель загружена
        yield c


@pytest.fixture()
def good_row() -> dict:
    return json.loads((ROOT / "good.json").read_text())
