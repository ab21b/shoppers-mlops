"""Обучение Random Forest на online_shoppers_intention и сохранение joblib-бандла.

Бандл = {"pipeline": sklearn Pipeline (препроцессинг + модель одним объектом),
         "metadata": {версия, список фичей В ПРАВИЛЬНОМ ПОРЯДКЕ, порог, ...}}

Запуск:  uv run python -m shoppers.training
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.stats import randint
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, f1_score, precision_recall_curve, recall_score, roc_auc_score
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

MODEL_VERSION = "1.0.0"
SEED = 42
TARGET = "Revenue"

# Порядок = порядок колонок исходного датасета (без Revenue). Сервис делает reindex(columns=FEATURES).
FEATURES = [
    "Administrative", "Administrative_Duration", "Informational", "Informational_Duration",
    "ProductRelated", "ProductRelated_Duration", "BounceRates", "ExitRates", "PageValues",
    "SpecialDay", "Month", "OperatingSystems", "Browser", "Region", "TrafficType",
    "VisitorType", "Weekend",
]  # fmt: skip
# как в ноутбуке: log1p для тяжёлых хвостов, one-hot для категорий
LOG_COLS = [
    "Administrative", "Administrative_Duration", "Informational", "Informational_Duration",
    "ProductRelated", "ProductRelated_Duration", "PageValues",
]  # fmt: skip
CAT_COLS = ["Month", "VisitorType", "OperatingSystems", "Browser", "Region", "TrafficType"]
PASS_COLS = ["BounceRates", "ExitRates", "SpecialDay", "Weekend"]

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "data" / "online_shoppers_intention.csv"
DEFAULT_OUT = ROOT / "artifact" / "model.joblib"


def load_data(path: Path = DEFAULT_DATA) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(path).drop_duplicates().reset_index(drop=True)  # 12330 -> 12205, как в ноутбуке
    df["Weekend"] = df["Weekend"].astype(int)
    y = df[TARGET].astype(int)
    return df[FEATURES], y


def build_pipeline(**rf_params) -> Pipeline:
    """Препроцессинг и модель в одном Pipeline: сервис не знает ни про log1p, ни про one-hot."""
    pre = ColumnTransformer(
        [
            ("log", Pipeline([("imp", SimpleImputer(strategy="median")),
                              ("log1p", FunctionTransformer(np.log1p, feature_names_out="one-to-one"))]), LOG_COLS),
            ("cat", OneHotEncoder(handle_unknown="ignore", dtype=np.float64), CAT_COLS),
            ("num", SimpleImputer(strategy="median"), PASS_COLS),
        ],
        verbose_feature_names_out=False,
    )  # fmt: skip
    rf = RandomForestClassifier(random_state=SEED, n_jobs=-1, **rf_params)
    return Pipeline([("prep", pre), ("model", rf)])


def pick_threshold(y_true, proba) -> float:
    """Порог, максимизирующий F1 класса «покупка» (на out-of-fold предсказаниях train)."""
    prec, rec, thr = precision_recall_curve(y_true, proba)
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-12, None)
    return float(round(thr[int(np.argmax(f1))], 4))


def train(data_path: Path = DEFAULT_DATA, out_path: Path = DEFAULT_OUT, n_iter: int = 10, verbose: bool = True) -> dict:
    X, y = load_data(data_path)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    # то же пространство поиска, что в ноутбуке (раздел 5), критерий ROC-AUC
    param_dist = {
        "model__n_estimators": randint(100, 250),
        "model__max_depth": randint(3, 20),
        "model__min_samples_leaf": randint(1, 20),
        "model__max_features": ["sqrt", 0.3, 0.5],
    }
    search = RandomizedSearchCV(build_pipeline(), param_dist, n_iter=n_iter, cv=cv, scoring="roc_auc",
                                random_state=SEED, n_jobs=1)  # fmt: skip
    search.fit(X_train, y_train)
    pipe = search.best_estimator_

    # порог подбираем по OOF-предсказаниям train, тест трогаем один раз
    oof = cross_val_predict(pipe, X_train, y_train, cv=cv, method="predict_proba")[:, 1]
    threshold = pick_threshold(y_train, oof)

    pipe.fit(X_train, y_train)
    proba = pipe.predict_proba(X_test)[:, 1]
    pred = (proba >= threshold).astype(int)
    metrics = {
        "cv_roc_auc": round(float(search.best_score_), 4),
        "test_roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "test_pr_auc": round(float(average_precision_score(y_test, proba)), 4),
        "test_f1": round(float(f1_score(y_test, pred)), 4),
        "test_recall": round(float(recall_score(y_test, pred)), 4),
    }
    pipe.set_params(model__n_jobs=1)  # онлайн-инференс одной строки: потоки только мешают

    metadata = {
        "model_version": MODEL_VERSION,
        "features": FEATURES,
        "threshold": threshold,
        "target": TARGET,
        "best_params": {k: (v if not isinstance(v, np.generic) else v.item()) for k, v in search.best_params_.items()},
        "metrics": metrics,
        "n_train": int(len(X_train)),
        "trained_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "dataset": "online_shoppers_intention.csv (Kaggle, imakash3011), duplicates dropped",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipe, "metadata": metadata}, out_path)
    if verbose:
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        print(f"saved -> {out_path}")
    return metadata


if __name__ == "__main__":
    train(out_path=Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT)
