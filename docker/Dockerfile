FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv

ENV PATH="/uv/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# ---------- shared base ----------
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# ---------- lean runtime (production / dev) ----------
# Only the virtualenv and src/ are copied; tests, docs, and other repo
# content are intentionally excluded to keep the runtime image small.
FROM base AS runtime

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src

USER appuser
EXPOSE 8501

CMD ["streamlit", "run", "src/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# ---------- test target (CI) ----------
# Full repo + dev extras so the entire test suite (including repo-structure
# smoke tests that read docs/ and .github/) runs against the live stack.
FROM base AS test

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv
ENV PATH="/uv/bin:$PATH"

COPY --from=builder --chown=appuser:appuser /app /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev

USER appuser
CMD ["pytest"]
