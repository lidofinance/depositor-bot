from blockchain.buffered_eth import get_recommended_buffered_ether_to_deposit


def test_recommended_buffered_ether():
    buffered_ether = get_recommended_buffered_ether_to_deposit(10**9)
    assert 1 < buffered_ether / 10**18 < 100

    buffered_ether = get_recommended_buffered_ether_to_deposit(50 * 10**9)
    assert 250 < buffered_ether / 10**18 < 300

    buffered_ether = get_recommended_buffered_ether_to_deposit(70 * 10**9)
    assert 300 < buffered_ether / 10**18 < 400

    buffered_ether = get_recommended_buffered_ether_to_deposit(150 * 10**9)
    assert 400 < buffered_ether / 10**18 < 500
