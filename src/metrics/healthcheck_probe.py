"""Docker HEALTHCHECK: exit 0 when /healthcheck answers 200, 1 otherwise.

Standalone on purpose (stdlib only, no bot imports): it runs in a separate process every few seconds.
"""

import os
import sys
import urllib.request

# A wildcard bind accepts loopback connections; a specific address has to be called as it is.
_WILDCARD_HOSTS = ('', '0.0.0.0', '::')


def probe_url(host: str, port: str) -> str:
    if host in _WILDCARD_HOSTS:
        host = '127.0.0.1'
    elif ':' in host:
        host = f'[{host}]'
    return f'http://{host}:{port}/healthcheck'


def main() -> int:
    url = probe_url(os.getenv('HEALTHCHECK_SERVER_HOST', '0.0.0.0'), os.getenv('HEALTHCHECK_SERVER_PORT', '9010'))
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 0 if response.status == 200 else 1
    except OSError:
        return 1


if __name__ == '__main__':
    sys.exit(main())
