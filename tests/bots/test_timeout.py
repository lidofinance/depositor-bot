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
