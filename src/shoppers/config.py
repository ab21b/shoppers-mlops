from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_path: str = "artifact/model.joblib"
    # если MODEL_NAME задан, модель берется из реестра MLflow по алиасу, иначе из файла model_path
    model_name: str | None = None
    model_alias: str = "champion"
    mlflow_tracking_uri: str = "http://127.0.0.1:5000"
    database_url: str | None = None
    log_level: str = "INFO"
    prediction_threshold: float | None = None  # переопределяет порог из metadata; в k8s по умолчанию не задан

    model_config = {"env_file": ".env", "extra": "ignore", "protected_namespaces": ()}


settings = Settings()
