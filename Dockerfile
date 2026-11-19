FROM python:3.12.4-slim as base

RUN apt-get update && apt-get install -y --no-install-recommends -qq \
    gcc=4:12.2.0-3 \
    libffi-dev=3.4.4-1 \
    g++=4:12.2.0-3 \
    curl=7.88.1-10+deb12u15 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    VENV_PATH="/.venv"

ENV PATH="$VENV_PATH/bin:$PATH"

FROM base as builder

ENV POETRY_VERSION=1.8.2
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

WORKDIR /
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root


FROM base as production

COPY --from=builder $VENV_PATH $VENV_PATH
WORKDIR /app
COPY . .

# Build metadata for the startup log and the build_info metric. The build workflow passes these as build args;
# regenerate build-info.json from them. Local builds without the args keep the tracked "unknown" placeholders.
ARG BUILD_VERSION
ARG BUILD_BRANCH
ARG BUILD_COMMIT
# json.dump escapes the values: a quote or backslash in a branch name must not break the file.
RUN if [ -n "$BUILD_COMMIT" ]; then \
      python3 -c 'import json, os; json.dump({key: os.environ["BUILD_" + key.upper()] for key in ("version", "branch", "commit")}, open("build-info.json", "w"))'; \
    fi

RUN apt-get clean && find /var/lib/apt/lists/ -type f -delete && chown -R www-data /app/

ENV PROMETHEUS_PORT 9000
ENV HEALTHCHECK_SERVER_PORT 9010

EXPOSE $PROMETHEUS_PORT
USER www-data

HEALTHCHECK --interval=10s --timeout=3s \
    CMD curl -f http://localhost:$HEALTHCHECK_SERVER_PORT/healthcheck || exit 1

WORKDIR /app/

ENTRYPOINT ["python3", "src/main.py"]
