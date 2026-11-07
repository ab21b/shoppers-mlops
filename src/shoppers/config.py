from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # путь внутри репозитория/образа; в проде веса лежали бы в registry (mlflow/dvc), а не в git
    model_path: str = "artifact/model.joblib"
    database_url: str | None = None  # нет адреса -> сервис работает, но не логирует
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
