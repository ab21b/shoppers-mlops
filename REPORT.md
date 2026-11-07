# Сервис для модели RandomForest


### Модель и паспорт

- Данные: 12330 строк, дубли удалены (12205), пропусков нет, доля покупок 15.6%.
- Pipeline одним объектом: `log1p` + median-imputer, `OneHotEncoder(handle_unknown="ignore")` для `Month, VisitorType, OperatingSystems, Browser, Region, TrafficType`. Препроцессинг внутри пайплайна: сервис получает сырые признаки.
- Метрики на тесте: ROC-AUC 0.9345, PR-AUC 0.7578, F1 0.6958, recall 0.7094.
- `metadata`: `model_version`, `features` (17 штук в порядке датасета), `threshold`, метрики, параметры, версия sklearn, дата.

### Схема запроса

17 фичей, `extra="forbid"`, границы из смысла и датасета: счётчики `ge=0`, доли `BounceRates/ExitRates/SpecialDay` в `[0, 1]`, `OperatingSystems 1..8`, `Browser 1..13`, `Region 1..9`, `TrafficType 1..20`, `Month` и `VisitorType` как `Literal` из значений датасета, `Weekend: bool`.

Про опциональные поля: в этом датасете пропусков нет, поэтому обязательны все поля. Для `SimpleImputer` тест проверяет, что NaN и незнакомая категория не роняют инференс.

Ограничение схемы: `Month` принимает только 10 месяцев из датасета (январь и апрель в данных нет), остальные дают 422.

### Логи

Таблица `predictions`: `request_id uuid PK, ts, model_version, features jsonb, score, purchase, latency_ms, status_code`.

- `status_code` (новое поле) пишется для всех запросов к `/v1/predict`: 200, 422 (валидация; в `features` сырое тело запроса, `score` пустой), 500 (сбой инференса).
- Без `DATABASE_URL` сервис работает и просто не логирует.


## 3. Скрины чекпоинтов


**1. pytest**  

```bash
uv run pytest
```

![pytest](docs/screens/01_pytest.png)

**2. SELECT из логов** После `docker compose up -d --build` специально один хороший и один плохой запрос:

```bash
curl -X POST localhost:8000/v1/predict -H "Content-Type: application/json" -d @good.json
curl -X POST localhost:8000/v1/predict -H "Content-Type: application/json" -d @bad.json
docker compose exec db psql -U postgres -d shoppers -c "SELECT request_id, ts, score, purchase, latency_ms, status_code FROM predictions ORDER BY ts DESC LIMIT 5;"
```

![select](docs/screens/02_select_logs.png)

**3. get pods + ответ predict через port-forward**  Водном окне `uv run python scripts/kind_up.py --keep` (port-forward остается открытым), во втором окне:

```bash
kubectl get pods
kubectl get deploy
curl -X POST localhost:8080/v1/predict -H "Content-Type: application/json" -d @good.json
```


![pods and predict](docs/screens/03_get_pods_and_predict.png)

**4. k9s**  

```bash
k9s --context kind-mlpro
```

![k9s](docs/screens/04_k9s.png)

## 4. Журнал проблем

| # | Что не получилось | Ошибка | Решение |
|---|---|---|---|
| 1 | `docker compose up -d --build`: контейнер api не стартовал | Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint shoppers-mlops-api-1 (...): Bind for 0.0.0.0:8000 failed: port is already allocated | Был активен старый контейнер с прошлого запуска этого проекта пришлось снести его docker stop online_shoppers_mlops-api-1 online_shoppers_mlops-db-1|
| 2 | `SELECT ... FROM predictions`|  relation "predictions" does not exist| запросы уходили в старый api и писались в его базу. После освобождения порта и пересоздания стека таблица появилась |
