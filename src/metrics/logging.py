import json
import logging
from time import time


def _json_default(obj: object) -> str:
    if isinstance(obj, (bytes, bytearray)):
        return '0x' + bytes(obj).hex()
    return str(obj)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.msg if isinstance(record.msg, dict) else {'msg': record.getMessage()}

        to_json_msg = json.dumps(
            {
                'name': record.name,
                'levelname': record.levelname,
                'funcName': record.funcName,
                'lineno': record.lineno,
                'module': record.module,
                'pathname': record.pathname,
                'timestamp': int(time()),
                **message,
            },
            default=_json_default,
        )
        return to_json_msg


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)
