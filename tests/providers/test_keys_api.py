import pytest

from providers.keys_api import LidoKey, group_keys_by_operator


def _key(pubkey: str, index: int, operator_index: int) -> LidoKey:
    return LidoKey(key=pubkey, index=index, operatorIndex=operator_index)


@pytest.mark.unit
def test_group_keys_by_operator_distributes_by_operator_index():
    keys = [
        _key('0xaa', 1, 11),
        _key('0xbb', 2, 12),
        _key('0xcc', 3, 11),  # same operator as the first key
    ]

    result = group_keys_by_operator(keys, [11, 12])

    assert result == {11: [keys[0], keys[2]], 12: [keys[1]]}


@pytest.mark.unit
def test_group_keys_by_operator_requested_operator_without_keys_is_empty():
    keys = [_key('0xaa', 1, 11)]

    result = group_keys_by_operator(keys, [11, 12])

    assert result == {11: [keys[0]], 12: []}


@pytest.mark.unit
def test_group_keys_by_operator_drops_keys_of_unrequested_operators():
    keys = [
        _key('0xaa', 1, 11),
        _key('0xbb', 2, 99),  # operator not in the requested list
    ]

    result = group_keys_by_operator(keys, [11])

    assert result == {11: [keys[0]]}


@pytest.mark.unit
def test_group_keys_by_operator_empty_inputs():
    assert group_keys_by_operator([], []) == {}
    assert group_keys_by_operator([], [11, 12]) == {11: [], 12: []}
