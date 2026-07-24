import time
from unittest.mock import Mock, patch

import pytest
from blockchain.executor import Executor
from metrics import healthcheck_pulse
from utils.timeout import TimeoutManagerError
from web3.types import BlockData
from web3_multi_provider import NoActiveProviderError


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


# ─── EL freshness / error metrics (unit, no network) ─────────────────


@pytest.mark.unit
def test_wait_until_next_block_reports_el_freshness():
    w3 = Mock()
    w3.eth.get_block = Mock(return_value={'number': 100, 'timestamp': 1000})
    e = Executor(w3, pure_func, 1, 4)

    with (
        patch('blockchain.executor.EL_HEAD_BLOCK_NUMBER') as block_number_gauge,
        patch('blockchain.executor.EL_HEAD_BLOCK_AGE_SECONDS') as block_age_gauge,
        patch('blockchain.executor.time', return_value=1050),
    ):
        block = e._wait_until_next_block()

    assert block['number'] == 100
    block_number_gauge.set.assert_called_with(100)
    block_age_gauge.set.assert_called_with(50)


@pytest.mark.unit
def test_exception_handler_counts_timeout():
    def raiser():
        raise TimeoutManagerError('boom')

    with patch('blockchain.executor.UNEXPECTED_EXCEPTIONS') as counter, pytest.raises(TimeoutManagerError):
        Executor._exception_handler(raiser)

    counter.labels.assert_called_once_with('timeout')
    counter.labels.return_value.inc.assert_called_once()


@pytest.mark.unit
def test_exception_handler_counts_no_active_provider():
    def raiser():
        raise NoActiveProviderError('no active provider', [ValueError('rpc down')])

    with patch('blockchain.executor.UNEXPECTED_EXCEPTIONS') as counter, pytest.raises(NoActiveProviderError):
        Executor._exception_handler(raiser)

    counter.labels.assert_called_once_with('no_active_provider')
    counter.labels.return_value.inc.assert_called_once()


@pytest.mark.unit
def test_exception_handler_counts_and_swallows_generic_exception():
    """The generic branch swallows the exception (no re-raise) so one bad cycle doesn't kill the
    daemon — the counter is the only way to notice this happened."""

    def raiser():
        raise ValueError('unexpected')

    with patch('blockchain.executor.UNEXPECTED_EXCEPTIONS') as counter:
        result = Executor._exception_handler(raiser)

    assert result is None
    counter.labels.assert_called_once_with('ValueError')
    counter.labels.return_value.inc.assert_called_once()
