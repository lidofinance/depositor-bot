import pytest

from metrics.metrics import PAUSE_MESSAGES, PING_MESSAGES
from metrics.transport_message_metrics import message_metrics_filter
from transport.msg_providers.rabbit import MessageType

GUARDIAN = '0x89e1bEBAf6857312bCDc313B93F29aB9cA98000f'
DELEGATE = '0x43464Fe06c18848a2E2e913194D64c1970f4326a'


def _sample(metric, **labels):
    expected = {key: str(value) for key, value in labels.items()}
    for family in metric.collect():
        for sample in family.samples:
            if sample.labels == expected:
                return sample.value
    return None


def _pause_message(**extra) -> dict:
    return {
        'type': MessageType.PAUSE,
        'guardianAddress': GUARDIAN,
        'blockNumber': 1,
        'app': {'version': '1.0.0'},
        'transport': 'onchain',
        'chain_id': '17000',
        'stakingModuleId': 1,
        **extra,
    }


@pytest.mark.unit
def test_message_labelled_by_delegate():
    assert message_metrics_filter(_pause_message(guardianDelegate=DELEGATE)) is True

    assert (
        _sample(
            PAUSE_MESSAGES,
            address=DELEGATE,
            guardian=GUARDIAN,
            module_id=1,
            version='1.0.0',
            transport='onchain',
            chain_id='17000',
        )
        == 1
    )


@pytest.mark.unit
def test_message_without_delegate_falls_back_to_guardian():
    assert message_metrics_filter(_pause_message(transport='rabbit')) is True

    assert (
        _sample(
            PAUSE_MESSAGES,
            address=GUARDIAN,
            guardian=GUARDIAN,
            module_id=1,
            version='1.0.0',
            transport='rabbit',
            chain_id='17000',
        )
        == 1
    )


@pytest.mark.unit
def test_ping_labelled_by_delegate():
    msg = _pause_message(type=MessageType.PING, guardianDelegate=DELEGATE)
    msg.pop('stakingModuleId')

    assert message_metrics_filter(msg) is False

    assert (
        _sample(
            PING_MESSAGES,
            address=DELEGATE,
            guardian=GUARDIAN,
            version='1.0.0',
            transport='onchain',
            chain_id='17000',
        )
        == 1
    )
