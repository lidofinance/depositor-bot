import functools
import datetime


def cache(ttl=datetime.timedelta(hours=1)):
    def wrap(func):
        time, value = None, None

        @functools.wraps(func)
        def wrapped(*args, **kw):
            nonlocal time
            nonlocal value

            now = datetime.datetime.now()
            if not time or now - time > ttl:
                value = func(*args, **kw)
                time = now
            return value
        return wrapped

    return wrap
