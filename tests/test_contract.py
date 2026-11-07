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
        ("PageValues", -5),                
        ("BounceRates", 1.5),            
        ("ExitRates", "abc"),             
        ("Month", "Jan"),                  # такой месяц не представлен в датасете
        ("VisitorType", "Robot"),         
        ("Browser", 0),                   
        ("Weekend", "maybe"),              
        ("Administrative", 2.5),          
    ],
)  
def test_garbage_value_is_422(client, good_row, field, bad):
    assert post(client, {**good_row, field: bad}).status_code == 422


def test_non_json_body_is_422(client):
    r = client.post("/v1/predict", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_schema_matches_model_passport(client):
    meta_features = client.app.state.meta["features"]
    assert list(Features.model_fields) == meta_features
