import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

DUMP_SCRIPT = """
import sys

import metrics.metrics  # noqa: F401
from prometheus_client import generate_latest

sys.stdout.write(generate_latest().decode())
"""


def _exposition(whitelist: str) -> str:
    result = subprocess.run(
        [sys.executable, '-c', DUMP_SCRIPT],
        cwd=REPO_ROOT,
        env={
            'PATH': '/usr/bin:/bin',
            'PYTHONPATH': str(REPO_ROOT / 'src'),
            'PROMETHEUS_PREFIX': 'depositor_bot',
            'DEPOSIT_MODULES_WHITELIST': whitelist,
        },
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return result.stdout


@pytest.mark.unit
@pytest.mark.parametrize(
    'series',
    [
        'depositor_bot_possible_deposits_amount',
        'depositor_bot_is_deposit_amount_ok',
    ],
)
def test_module_series_exported_before_first_cycle(series):
    exposition = _exposition('1,3')

    for module_id in ('1', '3'):
        assert f'{series}{{module_id="{module_id}"}} 0.0' in exposition


@pytest.mark.unit
def test_liveness_series_exported_before_first_cycle():
    assert 'depositor_bot_bot_last_cycle_timestamp_seconds 0.0' in _exposition('1')
