import logging

import logging_loki

from scripts.depositor_utils.variables import LOKI_URL, LOKI_AUTH_USERNAME, LOKI_AUTH_PASSWORD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)

handler = logging_loki.LokiHandler(
    url=LOKI_URL,
    tags={"application": "deposit-bot"},
    auth=(LOKI_AUTH_USERNAME, LOKI_AUTH_PASSWORD),
    version="1",
)

logger = logging.getLogger("depositor-bot")
logger.addHandler(handler)
