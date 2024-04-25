FROM python:3.10.6-slim as base

RUN apt-get update && apt-get install -y --no-install-recommends -qq \
    gcc=4:10.2.1-1 \
    libffi-dev=3.3-6 \
    g++=4:10.2.1-1 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    VENV_PATH="/.venv"

WORKDIR /app

FROM base as builder

ENV POETRY_VERSION=1.4.2 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    POETRY_HOME=/opt/poetry \
    PATH="/opt/poetry/bin:$PATH"

# Set the SHELL option -o pipefail before RUN with a pipe in
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# install poetry - respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://install.python-poetry.org | python -

COPY pyproject.toml poetry.lock ./
RUN poetry install

FROM base as production

COPY --from=builder /app /app
COPY . /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PULSE_SERVER_PORT 9010
ENV PROMETHEUS_PORT 9000

EXPOSE $PROMETHEUS_PORT
USER www-data

HEALTHCHECK --interval=10s --timeout=3s \
    CMD wget --no-verbose --tries=1 --spider http://localhost:$PULSE_SERVER_PORT/healthcheck || exit 1

ENTRYPOINT ["python3"]
CMD ["src/depositor.py"]
