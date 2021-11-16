FROM python:3.9 as builder

COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.9

WORKDIR /app

COPY --from=builder /root/.local /root/.local

COPY . .

EXPOSE 8080

ENV PATH=/root/.local/bin:$PATH

HEALTHCHECK --interval=5m --timeout=3s \
  CMD curl -f http://localhost:8080/ || exit 1

CMD ["sh", "-c", "brownie run $SCRIPT_NAME"]
