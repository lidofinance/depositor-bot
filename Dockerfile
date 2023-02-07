FROM python:3.9-slim as base

RUN apt-get update && apt-get install -y --no-install-recommends -qq gcc=4:10.2.1-1 libffi-dev=3.3-6 g++=4:10.2.1-1 git=1:2.30.6-r0 curl=7.74.0-1.3+deb11u2 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app

FROM base as builder

ENV POETRY_VERSION=1.1.13
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

COPY pyproject.toml poetry.lock ./
RUN python -m venv --copies /venv

RUN . /venv/bin/activate && poetry install --no-dev --no-root


FROM base as production

COPY --from=builder /venv /venv
COPY . .

RUN mkdir -p /var/www && chown www-data /var/www && \
    apt-get clean && find /var/lib/apt/lists/ -type f -delete && \
    chown -R www-data /app/ && chown -R www-data /venv

ENV PYTHONPATH="/venv/lib/python3.9/site-packages/"
ENV PATH=$PATH:/venv/bin
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PULSE_SERVER_PORT 9010
ENV PROMETHEUS_PORT 9000

EXPOSE $PROMETHEUS_PORT
USER www-data

HEALTHCHECK --interval=10s --timeout=3s \
    CMD curl -f http://localhost:$PULSE_SERVER_PORT/healthcheck || exit 1

ENTRYPOINT ["brownie"]
CMD ["run", "depositor"]
