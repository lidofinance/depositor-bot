import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        to_json_msg = json.dumps({
            'name': record.name,
            'levelname': record.levelname,
            'funcName': record.funcName,
            'lineno': record.lineno,
            'module': record.module,
            'pathname': record.pathname,
            **record.msg,
        })
        return to_json_msg


steam_log_handler = logging.StreamHandler()
steam_log_handler.setFormatter(JsonFormatter())


logging.basicConfig(
    level=logging.INFO,
    handlers=[steam_log_handler]
)

logger = logging.getLogger("depositor-bot")
