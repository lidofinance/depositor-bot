import signal


class TimeoutManagerError(BaseException):
    """Not an Exception: the cycle deadline must survive every `except Exception` between the
    signal handler and the Executor — provider failover loops treat a caught one as an endpoint
    failure, retry elsewhere and leave the cycle running with the one-shot alarm already spent.
    """


class TimeoutManager:
    """Simple timeout manager"""

    @staticmethod
    def handler(signum, frame):
        raise TimeoutManagerError

    def __init__(self, seconds: float):
        self.old = -1
        self.seconds = seconds

    def __enter__(self):
        # Set timer
        self.old = signal.signal(signal.SIGALRM, self.handler)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        # Remove timer
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.old)
