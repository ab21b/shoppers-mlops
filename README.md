# shoppers-service: вероятность покупки в интернет-магазине
Random Forest на датасете [Online Shoppers Purchasing Intention](https://www.kaggle.com/datasets/imakash3011/online-shoppers-purchasing-intention-dataset), обёрнутый в FastAPI-сервис с журналированием запросов в PostgreSQL, Docker Compose и Kubernetes (kind).

ROC-AUC на отложенной тестовой выборке: 0.934. Подробности обучения, архитектуры и экспериментов приведены в [REPORT.md](REPORT.md).

## 1. Структура проекта

- `artifact/model.joblib` — обученная модель и metadata.
- `src/shoppers/` — FastAPI-приложение, схема запроса, настройки и работа с PostgreSQL.
- `tests/` — unit-, contract- и integration-тесты.
- `good.json` — пример корректного запроса.
- `bad.json` — пример некорректного запроса.
- `compose.yaml` — конфигурация API и PostgreSQL для Docker Compose.
- `k8s/` — Kubernetes-манифесты.
- `scripts/kind_up.py` — сборка образа и локальное развёртывание в kind.
- `REPORT.md` — подробный отчет и результаты проверок.

## 2. Требования

Python 3.11, uv, Docker Desktop, kind, kubectl, k9s.

## 3. Проверка 


```bash
git clone https://github.com/ab21b/shoppers-mlops.git
cd shoppers-mlops
```

Установка Python 3.11 и зависимости из lock-файла:

```bash
uv python install 3.11
uv sync --locked
```

Запустите анализ и тесты:

```bash
uv run ruff check src tests
uv run pytest -q
```

Интеграционные тесты, которым нужна PostgreSQL, пропускаются, если `DATABASE_URL` не задан. Для их выполнения надо указать `DATABASE_URL` работающей тестовой базы данных, например:

```bash
# Linux/macOS
export DATABASE_URL='postgresql://postgres:postgres@localhost:5432/shoppers'

# PowerShell
$env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5432/shoppers'
```

```bash
uv run pytest -q
```

## 4. Проверка через Docker Compose

Docker Desktop должен быть запущен запущен.

```bash
docker compose up --build -d
```

Проверка состояния контейнеров:

```bash
docker compose ps
```

Проверка liveness и readiness API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Корректный пример запроса:

```bash
curl -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  --data @good.json
```

Некорректный пример запроса (ожидается HTTP 422):

```bash
curl -i -X POST http://localhost:8000/v1/predict \
  -H 'Content-Type: application/json' \
  --data @bad.json
```

Проверка, что успешные запросы и ошибки валидации записаны в PostgreSQL:

```bash
docker compose exec db psql -U postgres -d shoppers -c \
  "SELECT request_id, score, purchase, status_code FROM predictions ORDER BY ts DESC LIMIT 10;"
```

Снос контейнеров:

```bash
docker compose down
```

## 5. Проверка через Kubernetes (kind)

```bash
uv run python scripts/kind_up.py --keep
```

Скрипт собирает Docker-образ `shoppers-service:1.0`, создает кластер kind с именем `mlpro`, загружает образ в кластер, создает локальный Secret, развертывает PostgreSQL, ConfigMap, API и Service,затем при готовности API открывает port-forward.

Пока скрипт работает, API доступен по адресу http://localhost:8080. Проверка:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl -X POST http://localhost:8080/v1/predict \
  -H 'Content-Type: application/json' \
  --data @good.json
```

Swagger UI: http://localhost:8080/docs.

В другом окне терминала можно проверить состояние ресурсов:

```bash
kubectl --context kind-mlpro get pods -o wide
kubectl --context kind-mlpro get deployments
kubectl --context kind-mlpro get services
```

Для просмотра ресурсов через k9s:

```bash
k9s --context kind-mlpro
```

Чтобы удалить кластер kind:

```bash
uv run python scripts/kind_up.py --delete
```

## 6. API

- `GET /health` — проверка работоспособности процесса, версии модели и порога классификации.
- `GET /ready` — проверка, что модель загружена и сервис готов принимать запросы.
- `POST /v1/predict` — получение вероятности покупки (`score`) и класса (`purchase`). В ответе также возвращаются `model_version`, `request_id` и `latency_ms`.

Запросы с успешным предсказанием записываются в PostgreSQL со статусом 200. Ошибки валидации записываются со статусом 422. При исключении во время инференса сервис возвращает 500 и сохраняет запись с тем же `request_id`, `score = NULL` и `purchase = NULL`.

## Результаты

**pytest зелёный**

![pytest](docs/screens/01_pytest.png)

**SELECT из таблицы логов (после compose): строки 200 и 422**

![select](docs/screens/02_select_logs.png)

**`kubectl get pods` и ответ `/v1/predict` через port-forward**

![pods and predict](docs/screens/03_get_pods_and_predict.png)

**k9s с подами сервиса**

![k9s](docs/screens/04_k9s.png)
