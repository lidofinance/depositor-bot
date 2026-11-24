import logging
import sys

from logmask import setup_logging

from variables import LOG_LEVEL, PRIVATE_ENV_VARS

# JSON lines to stdout. Every line is masked with every form of the private values (raw value, URL parts, hex and
# encoded forms), including the messages of third-party libraries, warnings and the traceback of an unhandled
# exception (sys, threading and unraisable hooks).
setup_logging(PRIVATE_ENV_VARS, level=LOG_LEVEL, stream=sys.stdout)

__all__ = ['logging']
