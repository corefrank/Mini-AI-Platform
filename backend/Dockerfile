FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    HF_HOME=/model-cache OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked
COPY app app
COPY tests tests
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /indexes /model-cache \
    && chown -R appuser:appuser /indexes /model-cache
USER appuser
