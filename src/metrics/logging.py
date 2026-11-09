import json
import logging
import sys
import traceback
from collections.abc import Iterable
from time import time
from urllib.parse import urlsplit

import variables

REDACTED = '****'
# Shorter fragments (a bare `/` or `/rpc` path) carry no credential and would mangle unrelated text.
_MIN_SECRET_LENGTH = 8


def _json_default(obj: object) -> str:
    if isinstance(obj, (bytes, bytearray)):
        return '0x' + bytes(obj).hex()
    return str(obj)


def url_secrets(url: str) -> set[str]:
    """Fragments of an endpoint URL that can carry a credential.

    Providers put API keys in the path or query, and HTTP client errors quote only that part
    (urllib3: "Max retries exceeded with url: /v2/<key>"), so redacting the full URL alone is not enough.
    """
    parts = urlsplit(url)
    fragments = {url, parts.path + (f'?{parts.query}' if parts.query else '')}
    if parts.password:
        fragments.add(parts.password)
    return {fragment for fragment in fragments if len(fragment) >= _MIN_SECRET_LENGTH}


def key_secrets(key: str | None) -> set[str]:
    if not key:
        return set()
    return {key, key.removeprefix('0x')}


def secrets_from_env() -> list[str]:
    urls = [
        *variables.WEB3_RPC_ENDPOINTS,
        *variables.TESTNET_WEB3_RPC_ENDPOINTS,
        *variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS,
        *variables.CL_API_URLS,
        variables.KEYS_API_URL,
        variables.RELAY_RPC,
    ]
    secrets = set().union(
        *(url_secrets(url) for url in urls if url),
        key_secrets(variables.WALLET_PRIVATE_KEY),
        key_secrets(variables.AUCTION_BUNDLER_PRIVATE_KEY),
    )
    return list(secrets)


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str] = ()):
        super().__init__()
        # Longest first, so a full URL is replaced whole rather than leaving its host behind a redacted path.
        self._secrets = sorted(secrets, key=len, reverse=True)

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
        # Redacting the rendered line covers every field, however an exception was stringified upstream.
        return self.redact(to_json_msg)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text


def _log_uncaught(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    # The default hook prints the raw traceback to stderr, bypassing the formatter — and provider
    # errors such as NoActiveProviderError carry endpoint URLs in their sub-exceptions.
    stack = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logging.getLogger(__name__).critical({'msg': 'Uncaught exception. Shut down.', 'error': repr(exc_value), 'stack': stack})


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter(secrets_from_env()))

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)

sys.excepthook = _log_uncaught
