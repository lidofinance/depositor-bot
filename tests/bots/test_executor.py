import time
from unittest.mock import Mock

import pytest
from web3.types import BlockData

from blockchain.executor import Executor
from metrics import healthcheck_pulse
from utils.timeout import TimeoutManagerError


def pure_func(block: BlockData):
    return block.number


def pure_func_false(block: BlockData):
    return False


def pure_func_sleep(block: BlockData):
    time.sleep(8)
    return True


@pytest.fixture
def remove_metrics():
    healthcheck_pulse.pulse = Mock()


@pytest.mark.integration
def test_timeout(web3_lido_integration, remove_metrics):
    e = Executor(
        web3_lido_integration,
        pure_func_sleep,
        1,
        4,
    )

    with pytest.raises(TimeoutManagerError):
        e.execute_as_daemon()


@pytest.mark.integration
def test_blocks_diff_call(web3_lido_integration, remove_metrics):
    e = Executor(
        web3_lido_integration,
        pure_func,
        1,
        4,
    )

    block_1 = e._wait_for_new_block_and_execute()
    block_2 = e._wait_for_new_block_and_execute()
    block_3 = e._wait_for_new_block_and_execute()

    assert block_1 + 2 == block_2 + 1 == block_3


@pytest.mark.integration
def test_blocks_true_result(web3_lido_integration, remove_metrics):
    e = Executor(
        web3_lido_integration,
        pure_func,
        2,
        4,
    )

    block_1 = e._wait_for_new_block_and_execute()
    block_2 = e._wait_for_new_block_and_execute()

    assert block_1 + 2 == block_2


@pytest.mark.integration
def test_blocks_false_result(web3_lido_integration, remove_metrics):
    e = Executor(
        web3_lido_integration,
        pure_func_false,
        2,
        4,
    )

    e._wait_for_new_block_and_execute()
    block_1 = e._next_expected_block
    e._wait_for_new_block_and_execute()
    block_2 = e._next_expected_block

    assert block_1 + 1 == block_2
