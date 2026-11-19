FROM python:3.12.16-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    VENV_PATH="/.venv"

ENV PATH="$VENV_PATH/bin:$PATH"

# Security fix newer than the base image (Trivy HIGH CVE-2026-85091). Drop when the base image ships it.
RUN apt-get update && apt-get install -y --no-install-recommends -qq \
    zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

FROM base AS builder

# Build tools stay in this stage: the production stage gets only the venv.
RUN apt-get update && apt-get install -y --no-install-recommends -qq \
    gcc=4:14.2.0-1 \
    g++=4:14.2.0-1 \
    libffi-dev=3.4.8-2 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=1.8.2 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

WORKDIR /
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

FROM base AS production

COPY --from=builder $VENV_PATH $VENV_PATH

WORKDIR /app
COPY interfaces ./interfaces
COPY src ./src

# Build metadata for the startup log and the build_info metric. The build workflow passes these as build args;
# regenerate build-info.json from them. Local builds without the args keep the tracked "unknown" placeholders.
ARG BUILD_VERSION
ARG BUILD_BRANCH
ARG BUILD_COMMIT
COPY build-info.json ./
# json.dump escapes the values: a quote or backslash in a branch name must not break the file.
RUN if [ -n "$BUILD_COMMIT" ]; then \
      python3 -c 'import json, os; json.dump({key: os.environ["BUILD_" + key.upper()] for key in ("version", "branch", "commit")}, open("build-info.json", "w"))'; \
    fi

ENV PROMETHEUS_PORT=9000 \
    HEALTHCHECK_SERVER_HOST=0.0.0.0 \
    HEALTHCHECK_SERVER_PORT=9010

EXPOSE $PROMETHEUS_PORT $HEALTHCHECK_SERVER_PORT

# The app writes nothing to disk, so it runs with a read-only root filesystem. The files stay owned by root and are
# not writable by the app user. The platform sets its own uid/gid from the chart values.
USER 1000:1000

# Python instead of curl: no extra package in the runtime image. Calls HEALTHCHECK_SERVER_HOST (loopback for 0.0.0.0).
HEALTHCHECK --interval=10s --timeout=3s \
    CMD ["python3", "src/metrics/healthcheck_probe.py"]

ENTRYPOINT ["python3", "src/main.py"]
