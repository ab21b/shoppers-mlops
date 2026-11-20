from types import SimpleNamespace

import mlflow
import mlflow.artifacts
import mlflow.sklearn
import pytest

from shoppers.config import settings
from shoppers.model_store import load_model


def test_without_model_name_loads_file(monkeypatch):
    monkeypatch.setattr(settings, "model_name", None)
    pipeline, meta, version = load_model()
    assert hasattr(pipeline, "predict_proba")
    assert version == meta["model_version"] == "1.0.0"


def _fake_registry(monkeypatch, alias_error=None):
    calls = {}

    class FakeClient:
        def get_model_version_by_alias(self, name, alias):
            calls["alias"] = (name, alias)
            if alias_error:
                raise alias_error
            return SimpleNamespace(version="7", run_id="run-abc")

    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda uri: calls.__setitem__("uri", uri))
    monkeypatch.setattr(mlflow, "MlflowClient", FakeClient)
    monkeypatch.setattr(mlflow.sklearn, "load_model", lambda uri: calls.__setitem__("model_uri", uri) or "PIPELINE")
    monkeypatch.setattr(mlflow.artifacts, "load_dict", lambda uri: calls.__setitem__("meta_uri", uri) or {"threshold": 0.4})
    monkeypatch.setattr(settings, "model_name", "shoppers-rf")
    monkeypatch.setattr(settings, "model_alias", "champion")
    monkeypatch.setattr(settings, "mlflow_tracking_uri", "http://mlflow.test:5000")
    return calls


def test_registry_resolves_alias_to_version(monkeypatch):
    calls = _fake_registry(monkeypatch)
    pipeline, meta, version = load_model()
    assert calls["uri"] == "http://mlflow.test:5000"
    assert calls["alias"] == ("shoppers-rf", "champion")          # спрашиваем алиас а не номер версии
    assert calls["model_uri"] == "models:/shoppers-rf/7"          # грузим версию на которую он указывает
    assert calls["meta_uri"] == "runs:/run-abc/metadata.json"     # паспорт берем из того же прогона
    assert (pipeline, meta, version) == ("PIPELINE", {"threshold": 0.4}, "shoppers-rf-v7")


def test_missing_alias_fails_startup(monkeypatch):
    _fake_registry(monkeypatch, alias_error=RuntimeError("alias champion not found"))
    with pytest.raises(RuntimeError, match="not found"):
        load_model()
