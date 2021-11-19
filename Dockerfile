FROM python:3.9-slim as builder

RUN apt-get update && \
    apt-get install -y curl python3-dev gcc g++ libc-dev

COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.9-slim as production

WORKDIR /app

RUN mkdir /var/www && chown www-data /var/www && \
    apt-get update && apt-get install -y curl && \
    apt-get clean && find /var/lib/apt/lists/ -type f -delete && \
    chown www-data /app/

COPY --from=builder /usr/local/ /usr/local/
COPY . .

ENV PATH=$PATH:/usr/local/bin
ENV PYTHONPATH="/usr/local/lib/python3.9/site-packages/"

EXPOSE 8080
USER www-data

HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:8080/healthcheck || exit 1

ENTRYPOINT ["/usr/local/bin/brownie"]
CMD ["run", "depositor"]
