"""Сюжет 1. Контракт: мусор и лишние поля -> 422, а не 500 и не «молчаливый» ответ."""

import pytest

from shoppers.schemas import Features


def post(client, body):
    return client.post("/v1/predict", json=body)


def test_extra_field_is_422(client, good_row):
    assert post(client, {**good_row, "hacker_field": 1}).status_code == 422


def test_missing_field_is_422(client, good_row):
    row = dict(good_row)
    del row["PageValues"]
    assert post(client, row).status_code == 422


@pytest.mark.parametrize(
    "field, bad",
    [
        ("PageValues", -5),                # отрицательное
        ("BounceRates", 1.5),              # доля > 1
        ("ExitRates", "abc"),              # не число
        ("Month", "Jan"),                  # такого месяца нет в обучающих данных
        ("VisitorType", "Robot"),          # неизвестная категория
        ("Browser", 0),                    # коды начинаются с 1
        ("Weekend", "maybe"),              # не bool
        ("Administrative", 2.5),           # дробное там, где счётчик
    ],
)  # fmt: skip
def test_garbage_value_is_422(client, good_row, field, bad):
    assert post(client, {**good_row, field: bad}).status_code == 422


def test_non_json_body_is_422(client):
    r = client.post("/v1/predict", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_schema_matches_model_passport(client):
    """Схема запроса и список фичей в паспорте модели не должны разъехаться."""
    meta_features = client.app.state.meta["features"]
    assert list(Features.model_fields) == meta_features
