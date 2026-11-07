# Отчёт: ДЗ 1, сервис предсказаний для своей модели

## 1. Что сделано

| Блок | Что в репозитории |
|---|---|
| Артефакт с паспортом | `artifact/model.joblib` = `{"pipeline", "metadata"}`; обучение: `notebooks/train_model.ipynb` (и тот же код как `uv run python -m shoppers.training`) |
| uv-проект | `src/shoppers/`, `pyproject.toml`, `.python-version` (3.11), `uv.lock` в git |
| Сервис | `src/shoppers/service/app.py`: `/health`, `/ready`, `/v1/predict`, `/docs`; модель грузится один раз в `lifespan` |
| Логи в Postgres | `src/shoppers/db.py`, таблица `predictions` (+ колонка `status_code`) |
| Тесты | `tests/`: 25 тестов + 1 интеграционный (нужен `DATABASE_URL`) |
| Docker / compose | `Dockerfile`, `compose.yaml` (healthcheck у БД, `depends_on: service_healthy` у api) |
| Kubernetes | `k8s/deployment.yaml`, `k8s/service.yaml`, `scripts/kind_up.py` |

### Модель и паспорт

- Данные: 12330 строк, дубли удалены (12205), пропусков нет, доля покупок 15.6%.
- Pipeline одним объектом: `log1p` + median-imputer для 7 тяжёлых числовых признаков, `OneHotEncoder(handle_unknown="ignore")` для `Month, VisitorType, OperatingSystems, Browser, Region, TrafficType`, остальное насквозь. Препроцессинг, который в исследовательском ноутбуке жил вне модели (`np.log1p`, `get_dummies`), здесь внутри пайплайна: сервис получает сырые признаки.
- Гиперпараметры: `RandomizedSearchCV` по тому же пространству, что в `onlineshoppers.ipynb`, критерий ROC-AUC (`max_depth=11, min_samples_leaf=18, max_features=0.5, n_estimators=231`).
- Порог 0.393 подобран по out-of-fold предсказаниям train, максимизируя F1 класса «покупка» (при 0.5 модель пропускает слишком много покупателей: классы 84/16).
- Метрики на тесте (один раз): ROC-AUC 0.9345, PR-AUC 0.7578, F1 0.6958, recall 0.7094. Это согласуется с EDA-ноутбуком (ROC-AUC 0.933).
- `metadata`: `model_version`, `features` (17 штук в порядке датасета), `threshold`, метрики, параметры, версия sklearn, дата.

### Схема запроса (контракт)

17 фичей, `extra="forbid"`, границы из смысла и датасета: счётчики `ge=0`, доли `BounceRates/ExitRates/SpecialDay` в `[0, 1]`, `OperatingSystems 1..8`, `Browser 1..13`, `Region 1..9`, `TrafficType 1..20`, `Month` и `VisitorType` как `Literal` из значений датасета, `Weekend: bool`.

Про опциональные поля: в этом датасете пропусков нет, поэтому обязательны все поля. Изобретать опциональность там, где её нет в данных, значило бы разрешать входы, которых модель не видела. Страховка осталась в пайплайне (`SimpleImputer`), и тест проверяет, что NaN и незнакомая категория не роняют инференс.

Ограничение схемы: `Month` принимает только 10 месяцев из датасета (январь и апрель в данных отсутствуют, модель их не знает), остальные дают 422.

### Логи

Таблица `predictions`: `request_id uuid PK, ts, model_version, features jsonb, score, purchase, latency_ms, status_code`.

- `status_code` (новое поле) пишется для всех запросов к `/v1/predict`: 200, 422 (валидация; в `features` сырое тело запроса, `score` пустой), 500 (сбой инференса).
- Запись идёт в `BackgroundTasks`: ответ не ждёт БД. Сбой БД логируется, но не превращает успешный предикт в ошибку.
- Без `DATABASE_URL` сервис работает и просто не логирует.


## 3. Скрины чекпоинтов


**1. pytest**  `docs/screens/01_pytest.png`

```bash
uv run pytest
```

![pytest](docs/screens/01_pytest.png)

**2. SELECT из логов** `docs/screens/02_select_logs.png`. После `docker compose up -d --build` один хороший и один плохой запрос:

```bash
curl -X POST localhost:8000/v1/predict -H "Content-Type: application/json" -d @good.json
curl -X POST localhost:8000/v1/predict -H "Content-Type: application/json" -d @bad.json
docker compose exec db psql -U postgres -d shoppers -c "SELECT request_id, ts, score, purchase, latency_ms, status_code FROM predictions ORDER BY ts DESC LIMIT 5;"
```

![select](docs/screens/02_select_logs.png)

**3. get pods + ответ predict через port-forward**  `docs/screens/03_get_pods_and_predict.png`. Водном окне `uv run python scripts/kind_up.py --keep` (port-forward остается открытым), во втором окне:

```bash
kubectl get pods
kubectl get deploy
curl -X POST localhost:8080/v1/predict -H "Content-Type: application/json" -d @good.json
```


![pods and predict](docs/screens/03_get_pods_and_predict.png)

**4. k9s**  `docs/screens/04_k9s.png` 

```bash
k9s --context kind-mlpro
```

![k9s](docs/screens/04_k9s.png)

## 4. Журнал проблем

| # | Что не получилось | Ошибка | Решение |
|---|---|---|---|
| 1 | `docker compose up -d --build`: контейнер api не стартовал | `Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint shoppers-mlops-api-1 (...): Bind for 0.0.0.0:8000 failed: port is already allocated` | `docker ps -a` показал, что порт 8000 держит старый контейнер `online_shoppers_mlops-api-1` с прошлого запуска этого проекта (api в статусе `Created`, не запущен).`docker stop online_shoppers_mlops-api-1 online_shoppers_mlops-db-1`, затем `docker compose down -v` и `docker compose up -d --build`. |
| 2 | `SELECT ... FROM predictions` в compose-базе | `ERROR:  relation "predictions" does not exist` | Причина: api нового стека не поднялся (см. п. 1), таблица создаётся именно при его старте, а запросы curl на `localhost:8000` уходили в старый api и писались в его базу. После освобождения порта и пересоздания стека таблица появилась |
