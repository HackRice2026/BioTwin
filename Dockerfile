FROM node:22-bookworm-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY core/ core/
COPY ingestion/ ingestion/
COPY modeling/ modeling/
COPY narration/ narration/
COPY shared/ shared/
COPY --from=web /app/frontend/dist frontend/dist/
RUN useradd --create-home --uid 10001 biotwin && mkdir /app/data && chown -R biotwin:biotwin /app/data
USER biotwin
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "core.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
