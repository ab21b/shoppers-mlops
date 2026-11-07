FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# 1) слой зависимостей: меняется только при правке pyproject.toml / uv.lock
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) слой кода: правка кода пересобирает только его, зависимости берутся из кэша
COPY src/ src/
RUN uv sync --frozen --no-dev

# 3) артефакт модели
COPY artifact/ artifact/

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "shoppers.service.app:app", "--host", "0.0.0.0", "--port", "8000"]
# 