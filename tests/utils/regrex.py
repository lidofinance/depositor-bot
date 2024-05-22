import re

HASH_REGREX = re.compile(r'^0x[0-9,A-F]{64}$', flags=re.IGNORECASE)
ADDRESS_REGREX = re.compile('^0x[0-9,A-F]{40}$', flags=re.IGNORECASE)


def check_value_re(regrex, value) -> None:
    assert regrex.findall(value)


def check_value_type(value, _type) -> None:
    assert isinstance(value, _type)
