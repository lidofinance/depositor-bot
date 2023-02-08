FROM python:3.10.6-slim-bullseye as base

RUN apt-get update && apt-get install -y --no-install-recommends -qq gcc=4:10.2.1-1 libffi-dev=3.3-6 g++=4:10.2.1-1 git=1:2.30.6-r0 curl=7.74.0-1.3+deb11u2 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

FROM base as builder

ENV POETRY_VERSION=1.1.13
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

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
    CMD curl -f http://localhost:$PULSE_SERVER_PORT/healthcheck || exit 1

ENTRYPOINT ["python3"]
CMD ["src/depositor.py"]
