# Docker Hardened Images (DHI), Python 3.12 on Debian 13. lidofinance/dhi-python is the paid mirror of dhi.io/python:
# critical fixes come under SLA. Pulling needs a Docker Hub login with the DHI token (DHI_USERNAME / DHI_TOKEN in CI).
# Tags are exact and pinned by digest; bump both together.
FROM lidofinance/dhi-python:3.12.16-debian13-dev@sha256:fcf859cfc756541f139b1d14951d838c4d119fece09734f12968ddf94801f8ad AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    VENV_PATH=/.venv

# Poetry lives in its own venv; the app venv gets only the main dependencies. All of them install from wheels, so
# no compiler is needed.
RUN python3 -m venv /opt/poetry \
 && /opt/poetry/bin/pip install --no-cache-dir poetry==$POETRY_VERSION \
 && python3 -m venv $VENV_PATH

WORKDIR /build
COPY pyproject.toml poetry.lock ./
# pip is not needed at runtime: its vendored SBOM lists an old setuptools that scanners flag (CVE-2025-47273).
RUN VIRTUAL_ENV=$VENV_PATH PATH="$VENV_PATH/bin:$PATH" /opt/poetry/bin/poetry install --only main --no-root \
 && $VENV_PATH/bin/python -m pip uninstall --yes pip

# Build metadata for the startup log and the build_info metric. The build workflow passes these as build args;
# regenerate build-info.json from them. Local builds without the args keep the tracked "unknown" placeholders.
# Written here: the runtime image has no shell to run it.
ARG BUILD_VERSION
ARG BUILD_BRANCH
ARG BUILD_COMMIT
COPY build-info.json ./
# json.dump escapes the values: a quote or backslash in a branch name must not break the file.
RUN if [ -n "$BUILD_COMMIT" ]; then \
      python3 -c 'import json, os; json.dump({key: os.environ["BUILD_" + key.upper()] for key in ("version", "branch", "commit")}, open("build-info.json", "w"))'; \
    fi

# Runtime: no shell, no package manager.
FROM lidofinance/dhi-python:3.12.16-debian13@sha256:d730c81938acce56e361f94829e4979a542ada9195e54b32347478743147b5ac AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VENV_PATH=/.venv \
    PATH="/.venv/bin:$PATH"

COPY --from=builder $VENV_PATH $VENV_PATH

WORKDIR /app
COPY interfaces ./interfaces
COPY src ./src
COPY --from=builder /build/build-info.json ./

ENV PROMETHEUS_PORT=9000 \
    HEALTHCHECK_SERVER_HOST=0.0.0.0 \
    HEALTHCHECK_SERVER_PORT=9010

EXPOSE $PROMETHEUS_PORT $HEALTHCHECK_SERVER_PORT

# The app writes nothing to disk, so it runs with a read-only root filesystem. The files stay owned by root and are
# not writable by the app user. The platform sets its own uid/gid from the chart values.
USER 1000:1000

# Python instead of curl: the runtime image has no shell or curl. Calls HEALTHCHECK_SERVER_HOST (loopback for 0.0.0.0).
HEALTHCHECK --interval=10s --timeout=3s \
    CMD ["python3", "src/metrics/healthcheck_probe.py"]

ENTRYPOINT ["python3", "src/main.py"]
