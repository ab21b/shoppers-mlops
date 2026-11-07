"""Сюжет 3. Детерминизм: один вход дважды -> один и тот же ответ."""

import joblib
import pandas as pd

from shoppers.config import settings


def test_same_input_same_score(client, good_row):
    s1 = client.post("/v1/predict", json=good_row).json()["score"]
    s2 = client.post("/v1/predict", json=good_row).json()["score"]
    assert s1 == s2


def test_same_score_after_reloading_bundle(client, good_row):
    """Артефакт на диске даёт тот же скор, что и модель в памяти сервиса."""
    bundle = joblib.load(settings.model_path)
    frame = pd.DataFrame([good_row])[bundle["metadata"]["features"]]
    frame["Weekend"] = frame["Weekend"].astype(int)
    direct = float(bundle["pipeline"].predict_proba(frame)[0, 1])
    served = client.post("/v1/predict", json=good_row).json()["score"]
    assert abs(direct - served) < 1e-12


def test_pipeline_survives_unseen_category_and_nan(client):
    """Препроцессинг внутри Pipeline: незнакомая категория и пропуск не роняют инференс."""
    pipe = client.app.state.pipeline
    feats = client.app.state.meta["features"]
    row = {f: 0 for f in feats}
    row.update({"Month": "Jan", "VisitorType": "Robot", "OperatingSystems": 99, "PageValues": float("nan")})
    p = pipe.predict_proba(pd.DataFrame([row])[feats])[0, 1]
    assert 0.0 <= p <= 1.0
