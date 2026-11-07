import logging
import time
import uuid
from contextlib import asynccontextmanager

import joblib
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from shoppers import db
from shoppers.config import settings
from shoppers.schemas import Features, Prediction

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("shoppers.service")

PREDICT_PATH = "/v1/predict"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # модель грузится ОДИН раз при старте, не на каждый запрос
    bundle = joblib.load(settings.model_path)
    app.state.pipeline = bundle["pipeline"]
    app.state.meta = bundle["metadata"]
    app.state.version = bundle["metadata"]["model_version"]
    db.init()
    yield
    app.state.pipeline = None


app = FastAPI(title="shoppers-service", version="1.0", lifespan=lifespan,
              description="Вероятность покупки в интернет-магазине (Random Forest, online shoppers intention)")  # fmt: skip


@app.get("/health")
def health():
    """Liveness: процесс жив. Модель не проверяем: перезапуск пода тут не поможет."""
    return {"status": "ok", "model_version": getattr(app.state, "version", "unknown")}


@app.get("/ready")
def ready():
    """Readiness: модель загружена, можно слать трафик."""
    if getattr(app.state, "pipeline", None) is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready", "model_version": app.state.version}


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    """422 тоже логируем: в таблице видно и мусорные запросы с кодом ответа."""
    request_id = str(uuid.uuid4())
    body = jsonable_encoder({"detail": exc.errors(), "request_id": request_id})
    bg = None
    if request.url.path == PREDICT_PATH:
        raw = exc.body if isinstance(exc.body, dict) else {"_raw": str(exc.body)[:2000]}
        bg = BackgroundTask(db.save_prediction, request_id, jsonable_encoder(raw),
                            getattr(request.app.state, "version", "unknown"), None, None, 0.0, 422)  # fmt: skip
    return JSONResponse(status_code=422, content=body, background=bg)


@app.post(PREDICT_PATH)
def predict(x: Features, bg: BackgroundTasks) -> Prediction:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())
    payload = x.model_dump()
    version = app.state.version
    try:
        frame = pd.DataFrame([payload]).reindex(columns=app.state.meta["features"])
        frame["Weekend"] = frame["Weekend"].astype(int)  # в обучении Weekend был 0/1
        score = float(app.state.pipeline.predict_proba(frame)[0, 1])
    except Exception:
        log.exception("ошибка инференса, request_id=%s", request_id)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        db.save_prediction(request_id, payload, version, None, None, latency_ms, 500)
        raise HTTPException(status_code=500, detail=f"inference failed, request_id={request_id}") from None

    purchase = score >= app.state.meta["threshold"]
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    # запись в БД уходит в фон: ответ не ждёт Postgres
    bg.add_task(db.save_prediction, request_id, payload, version, score, purchase, latency_ms, 200)
    return Prediction(score=score, purchase=purchase, model_version=version, request_id=request_id, latency_ms=latency_ms)
