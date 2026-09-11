import pytest
from transport.msg_storage import MessageStorage
from transport.msg_types.ping import to_check_sum_address


class Transport:
    @staticmethod
    def get_messages():
        return [
            {'guardianAddress': '0x5fd0ddbc3351d009eb3f88de7cd081a614c519f1'},
            {'guardianAddress': '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A'},
        ]


@pytest.fixture
def msg_storage():
    yield MessageStorage(
        [Transport()],
        filters=[
            to_check_sum_address,
        ],
    )


@pytest.mark.unit
def test_checksum_address_parsing(msg_storage: MessageStorage):
    updated_msgs = msg_storage.get_messages_and_actualize(lambda x: True)

    assert updated_msgs == [
        {'guardianAddress': '0x5fd0dDbC3351d009eb3f88DE7Cd081a614C519F1'},
        {'guardianAddress': '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A'},
    ]


class OneShotTransport:
    def __init__(self, messages):
        self._messages = messages

    def get_messages(self):
        messages, self._messages = self._messages, []
        return messages


VALID = {'guardianAddress': '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A'}
MALFORMED = {'guardianAddress': '0x5fd0dDbC3351d009eb3f88DE7Cd081a614C519F1'}


def _raises_on_malformed(msg):
    if msg == MALFORMED:
        raise KeyError('nonce')
    return True


@pytest.mark.unit
def test_malformed_message_does_not_hide_valid_ones():
    storage = MessageStorage([OneShotTransport([MALFORMED, VALID])], filters=[])

    assert storage.get_messages_and_actualize(_raises_on_malformed) == [VALID]


@pytest.mark.unit
def test_malformed_message_is_not_retained():
    storage = MessageStorage([OneShotTransport([MALFORMED, VALID])], filters=[])
    storage.get_messages_and_actualize(_raises_on_malformed)

    assert storage.get_messages_and_actualize(lambda x: True) == [VALID]
