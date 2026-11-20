import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import sklearn
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.metrics import average_precision_score, f1_score, precision_recall_curve, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split

from shoppers.training import FEATURES, SEED, TARGET, build_pipeline, pick_threshold

DATA_PATH = Path(os.getenv("DATA_PATH", "data/online_shoppers_intention.csv"))
MODEL_NAME = os.getenv("MODEL_NAME", "shoppers-rf")
EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "shoppers")
GATE_METRIC = "pr_auc"
MIN_GAIN = float(os.getenv("GATE_MIN_GAIN", "0.005"))
SKOPS_TRUSTED = [
    "numpy.dtype",
    "sklearn.compose._column_transformer._RemainderColsList",
    "sklearn.tree._tree.Tree",
]

HYPERPARAMS = {
    "n_estimators": int(os.getenv("N_ESTIMATORS", "200")),
    "max_depth": int(os.getenv("MAX_DEPTH", "11")),
    "min_samples_leaf": int(os.getenv("MIN_SAMPLES_LEAF", "18")),
    "max_features": os.getenv("MAX_FEATURES", "0.5"),
}


def file_md5(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def parse_max_features(value: str) -> str | float:
    return value if value in ("sqrt", "log2") else float(value)


def decide_promotion(new_metric: float, champion_metric: float | None, min_gain: float = MIN_GAIN) -> bool:
    return champion_metric is None or new_metric > champion_metric + min_gain


def load_and_validate(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = set(FEATURES + [TARGET]) - set(df.columns)
    if missing:
        raise ValueError(f"в данных нет колонок: {sorted(missing)}")
    if len(df) < 1000:
        raise ValueError(f"слишком мало строк: {len(df)}")
    df["Weekend"] = df["Weekend"].astype(int)
    df[TARGET] = df[TARGET].astype(int)
    if not set(df[TARGET].unique()) <= {0, 1}:
        raise ValueError(f"неожиданные значения таргета: {df[TARGET].unique()[:5]}")
    return df


def pr_curve_figure(y_true, proba, threshold: float, ap: float):
    """Артефакт прогона: PR-кривая с отмеченным порогом классификации."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    i = int(np.searchsorted(thresholds, threshold))
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    ax.plot(recall, precision, label=f"PR-AUC = {ap:.3f}")
    ax.axhline(float(np.mean(y_true)), ls="--", color="gray", label=f"доля покупок = {np.mean(y_true):.2f}")
    ax.scatter([recall[i]], [precision[i]], color="red", zorder=3, label=f"порог {threshold:.3f}")
    ax.set(xlabel="recall", ylabel="precision", title="Precision-recall, отложенная выборка", xlim=(0, 1), ylim=(0, 1.02))
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def feature_importance_figure(pipeline, top: int = 15):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = pipeline.named_steps["prep"].get_feature_names_out()
    imp = pipeline.named_steps["model"].feature_importances_
    order = np.argsort(imp)[::-1][:top][::-1]
    fig, ax = plt.subplots(figsize=(6, 4.8))
    ax.barh([names[i] for i in order], imp[order])
    ax.set(title=f"Top-{top} Feature Importances", xlabel="Importance")
    fig.tight_layout()
    return fig


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def current_champion(client: MlflowClient) -> tuple[str | None, float | None, str | None]:
    try:
        mv = client.get_model_version_by_alias(MODEL_NAME, "champion")
    except MlflowException:
        return None, None, None
    run = client.get_run(mv.run_id)
    return mv.version, run.data.metrics.get(GATE_METRIC), run.data.params.get("data_md5")


def main() -> dict:
    if not os.getenv("MLFLOW_TRACKING_URI"):
        sys.exit("Задайте MLFLOW_TRACKING_URI, например http://mlflow.localhost (иначе MLflow писал бы в локальную папку mlruns)")

    df = load_and_validate(DATA_PATH)
    data_md5 = file_md5(DATA_PATH)
    x_train, x_test, y_train, y_test = train_test_split(
        df[FEATURES], df[TARGET], test_size=0.2, stratify=df[TARGET], random_state=SEED
    )

    rf_params = {**HYPERPARAMS, "max_features": parse_max_features(HYPERPARAMS["max_features"])}
    pipeline = build_pipeline(**rf_params)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    oof = cross_val_predict(pipeline, x_train, y_train, cv=cv, method="predict_proba")[:, 1]
    threshold = pick_threshold(y_train, oof)

    pipeline.fit(x_train, y_train)
    proba = pipeline.predict_proba(x_test)[:, 1]
    pred = (proba >= threshold).astype(int)
    metrics = {
        "pr_auc": float(average_precision_score(y_test, proba)),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "f1": float(f1_score(y_test, pred)),
        "recall": float(recall_score(y_test, pred)),
        "threshold": float(threshold),
    }
    pipeline.set_params(model__n_jobs=1)  

    mlflow.set_experiment(EXPERIMENT)
    client = MlflowClient()
    with mlflow.start_run() as run:
        metadata = {
            "features": FEATURES,  
            "threshold": round(float(threshold), 4),
            "target": TARGET,
            "n_train": len(x_train),
            "data_rows": len(df),
            "data_md5": data_md5,
            "sklearn": sklearn.__version__,
        }
        mlflow.log_params({**HYPERPARAMS, "model": "RandomForest", "seed": SEED, "data_path": DATA_PATH.as_posix(),
                           "data_md5": data_md5, "data_rows": len(df), "git_commit": git_commit()}) 
        mlflow.log_metrics(metrics)
        mlflow.log_dict(metadata, "metadata.json")
        mlflow.log_figure(pr_curve_figure(y_test, proba, threshold, metrics["pr_auc"]), "pr_curve.png")
        mlflow.log_figure(feature_importance_figure(pipeline), "feature_importance.png")
        info = mlflow.sklearn.log_model(pipeline, name="model", registered_model_name=MODEL_NAME,
                                        skops_trusted_types=SKOPS_TRUSTED) 
        version = info.registered_model_version

    old_version, old_metric, old_md5 = current_champion(client)
    promoted = decide_promotion(metrics[GATE_METRIC], old_metric)
    client.set_registered_model_alias(MODEL_NAME, "challenger", version)
    if promoted:
        client.set_registered_model_alias(MODEL_NAME, "champion", version)

    result = {
        "run_id": run.info.run_id,
        "version": version,
        "data_md5": data_md5,
        GATE_METRIC: round(metrics[GATE_METRIC], 4),
        "champion_before": old_version,
        f"champion_{GATE_METRIC}_before": None if old_metric is None else round(old_metric, 4),
        "min_gain": MIN_GAIN,
        "promoted": promoted,
        "aliases_now": {"challenger": version, "champion": version if promoted else old_version},
    }
    if old_md5 and old_md5 != data_md5:
        result["warning"] = "champion обучен на других данных (data_md5 различается): метрики сравниваются на разных выборках"
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()
