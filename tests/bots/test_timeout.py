import time

import pytest

from utils.timeout import TimeoutManager, TimeoutManagerError


@pytest.mark.unit
def test_timeout():
    with pytest.raises(TimeoutManagerError):
        simple_timeout(4, 8)

    simple_timeout(8, 4)


def simple_timeout(expect_time: int, sleep_time: int):
    with TimeoutManager(expect_time):
        time.sleep(sleep_time)


@pytest.mark.unit
def test_deadline_is_not_an_exception():
    with pytest.raises(TimeoutManagerError):
        try:
            raise TimeoutManagerError
        except Exception:
            pytest.fail('cycle deadline was swallowed as an ordinary failure')


@pytest.mark.unit
def test_deadline_survives_provider_failover():
    def failover_loop():
        # web3-multi-provider's request loop: any error is an endpoint failure, try the next one.
        for _ in range(2):
            try:
                time.sleep(0.2)
            except Exception:
                continue

    with pytest.raises(TimeoutManagerError), TimeoutManager(0.1):
        failover_loop()
