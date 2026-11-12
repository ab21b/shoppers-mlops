# HW2: CI/CD для shoppers-mlops

Инструкция относится к текущей структуре репозитория: пакет `shoppers`, модель `artifact/model.joblib`, запрос `good.json`, сервис `shoppers-service`.

## 1. Подготовка GitHub

1. В GitHub откройте `Settings → Secrets and variables → Actions → New repository secret`.
2. Создайте `POSTGRES_PASSWORD`. Используйте длинный случайный пароль из латинских букв и цифр (URL в workflow собирается напрямую, поэтому не используйте `@`, `:`, `/`, `%` и другие специальные символы).
3. Убедитесь, что пакет GHCR может публиковаться из Actions. Workflow использует `GITHUB_TOKEN`, отдельный PAT не нужен.

## 2. Ветка и постепенное добавление workflow

Работайте в локальной копии репозитория, в которой сохранена папка `.git`:

```bash
git switch -c feature/homework-2-cicd
```

Сначала добавьте файлы HW2, кроме `.github/workflows/ci.yml`, и зафиксируйте их:

```bash
git add src tests k8s scripts/kind_up.py docs/CI_CD_GUIDE.md docs/workflow-stages

git add REPORT.md
git commit -m "Add CI/CD deployment configuration and integration tests"
```

Затем добавляйте workflow последовательно, чтобы история отражала развитие pipeline:

```bash
cp docs/workflow-stages/ci-01-tests.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "Add CI tests workflow"

cp docs/workflow-stages/ci-02-build.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "Add GHCR image build job"

cp docs/workflow-stages/ci-03-deploy.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "Add kind deployment and smoke tests"
```

Перед push проверьте `uv sync --locked`, `uv run ruff check src tests`, `uv run pytest -q`. Для тестов с PostgreSQL задайте `DATABASE_URL` на доступную базу. CI запускает настоящий PostgreSQL service container.

```bash
git push -u origin feature/homework-2-cicd
```

Откройте PR в `main`. На PR должны запускаться только `tests`; `build` и `deploy` пропускаются условиями `if`.

## 3. Намеренно сломанный тест в PR

После того как обычные проверки прошли, сделайте отдельный коммит с намеренно неверным ожиданием, например в `tests/test_smoke.py` временно измените проверку `h.json()["status"] == "ok"` на `== "broken"`:

```bash
git add tests/test_smoke.py
git commit -m "test: intentionally break CI for homework demonstration"
git push
```

Дождитесь красного run и сохраните URL. Затем исправьте ожидание на `== "ok"`, сделайте отдельный коммит и push. Дождитесь зелёного run и сохраните URL. В PR merge только после зелёного run.

## 4. Три намеренные ошибки на main

После merge выполняйте сценарии по одному. Для каждого сценария: внесите ошибку, commit + push в `main`, дождитесь красного deploy run и сохраните URL; затем отдельным commit исправьте ошибку, push, дождитесь зелёного run и сохраните URL.

### 4.1. Неверный путь к модели

В `k8s/configmap.yaml` временно укажите `MODEL_PATH: "artifact/missing-model.joblib"`. API контейнер завершится с `FileNotFoundError`; Kubernetes будет перезапускать его, Pod перейдёт в `CrashLoopBackOff`. Исправление: вернуть `artifact/model.joblib`.

### 4.2. Неверное имя Secret

В `k8s/deployment.yaml` измените имя Secret в `secretKeyRef` для `DATABASE_URL` с `shoppers-db` на `shoppers-db-wrong`. Контейнер не сможет получить переменную окружения; Pod будет показывать `CreateContainerConfigError`, в Events будет указано отсутствие Secret. Исправление: вернуть `shoppers-db`.

### 4.3. Невозможный memory request

В `k8s/deployment.yaml` временно задайте `resources.requests.memory: "1000000000Mi"`. Планировщик не сможет разместить Pod; он останется `Pending`, Events покажут `FailedScheduling` / `Insufficient memory`. Исправление: вернуть `256Mi`.

В каждом красном run откройте шаг `Diagnose failed deployment`: он выводит `kubectl get pods`, deployments, Events, `kubectl describe` и логи API/PostgreSQL. Сохраните URL красного и следующего зелёного run для каждого сценария.

## 5. Что именно проверяет pipeline

- `tests`: Ruff и pytest против настоящего PostgreSQL. Интеграционные тесты проверяют сохранение записи с `status_code=200`, а также невалидного и malformed JSON запроса с `status_code=422`.
- `build`: только после успешного `tests` на push в `main`; публикует `ghcr.io/<owner>/<repo>:<полный SHA коммита>`. BuildKit GHA cache сохраняет слои между сборками.
- `deploy`: только после `build` на push в `main`; создаёт kind, PostgreSQL, Kubernetes Secret и ConfigMap, разворачивает API, делает smoke test `/health` и `/v1/predict`, проверяет строки аудита в БД.

Пароль хранится в GitHub Secret `POSTGRES_PASSWORD`; он передаётся в PostgreSQL Pod и формирует `DATABASE_URL` для API через Kubernetes Secret. ConfigMap задаёт `MODEL_PATH`, `LOG_LEVEL` и `PREDICTION_THRESHOLD`; порог возвращается в `/health`.
