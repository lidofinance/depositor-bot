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
    updated_msgs = msg_storage.get_messages([lambda x: True])

    assert updated_msgs == [
        {'guardianAddress': '0x5fd0dDbC3351d009eb3f88DE7Cd081a614C519F1'},
        {'guardianAddress': '0x3dc4cF780F2599B528F37dedB34449Fb65Ef7d4A'},
    ]
