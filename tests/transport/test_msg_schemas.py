import pytest
from transport.msg_types.ping import to_check_sum_address


@pytest.mark.unit
def test_to_check_sum_address():
    council_message = {'guardianAddress': '0x43464fe06c18848a2E2e913194d64c1970f4326a'}

    to_check_sum_address(council_message)

    assert council_message['guardianAddress'] == '0x43464Fe06c18848a2E2e913194D64c1970f4326a'
