import logging
import logging_loki


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)


logger = logging.getLogger("depositor-bot")


handler = logging_loki.LokiHandler(
    url="https://logs-prod-us-central1.grafana.net/loki/api/v1/push",
    tags={"application": "deposit-bot"},
    auth=("103382", "eyJrIjoiZWZmYWVlYWMyZjYwZmI2YTE0MWMyZDZlMjIxY2M0NDZiYTBmOGZiNiIsIm4iOiJuZXcga2V5IiwiaWQiOjU0NDAxNX0="),
    version="1",
)

logger.addHandler(handler)
