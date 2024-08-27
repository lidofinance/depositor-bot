import pytest
from web3 import Web3
from web3._utils.events import get_event_data
from web3.types import FilterParams

from transport.msg_providers.data_bus import MESSAGE


# Started with config: {
#  NODE_HOST: 'http://127.0.0.1:8888',
#  DATA_BUS_ADDRESS: '0x5FbDB2315678afecb367f032d93F642f64180aa3'
# }
@pytest.mark.unit
def test_data_bus_provider():
    host = 'http://127.0.0.1:8888'
    contract = '0x5FbDB2315678afecb367f032d93F642f64180aa3'
    w3 = Web3(Web3.HTTPProvider(host))
    assert w3.is_connected()
    contract_address = Web3.to_checksum_address(contract)
    from_block = 0
    message_event_topic = w3.keccak(text='MessageDepositV1(address,(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32)))')

    filter_params = FilterParams(
        fromBlock=from_block,
        address=contract_address,
        topics=[message_event_topic],
    )

    logs = w3.eth.get_logs(filter_params)
    message_contract = w3.eth.contract(abi=[MESSAGE])

    for log in logs:
        e = get_event_data(w3.codec, message_contract.events.Message().abi, log)
        unparsed_event = e['args']['data']
        guardian = e['args']['sender']
        d = w3.codec.decode(
            ['(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32))'], unparsed_event)
        depositRoot, nonce, blockNumber, blockHash, signature, stakingModuleId, app = d[0]
        print('nonce', nonce)
        print('blockNumber', blockNumber)
        print('stakingModuleId', stakingModuleId)
