import pytest
import variables
from schema import Or, Schema
from transport.msg_providers.data_bus import DataBusProvider, DataBusSinks
from transport.msg_types.deposit import DepositMessageSchema
from transport.msg_types.ping import PingMessageDataBusSchema


# Started with config: {
#  NODE_HOST: 'http://127.0.0.1:8888',
#  DATA_BUS_ADDRESS: '0x5FbDB2315678afecb367f032d93F642f64180aa3'
# }
@pytest.mark.integration_manual
def test_data_bus_provider():
    """
    Utilise this function for an adhoc testing of data bus transport
    """
    variables.WEB3_RPC_GNOSIS_ENDPOINTS = ['http://127.0.0.1:8888']
    variables.DATA_BUS_ADDRESS = '0x5FbDB2315678afecb367f032d93F642f64180aa3'
    provider = DataBusProvider(
        message_schema=Schema(Or(DepositMessageSchema, PingMessageDataBusSchema)), sinks=[DataBusSinks.DEPOSIT_V1, DataBusSinks.PING_V1]
    )
    messages = provider.get_messages()
    print(messages)
    # contract_address = Web3.to_checksum_address(contract)
    # from_block = 0
    # message_event_topic = w3.keccak(text='MessageDepositV1(address,(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32)))')

    # filter_params = FilterParams(
    #    fromBlock=from_block,
    #    address=contract_address,
    #    topics=[message_event_topic],
    # )

    # logs = w3.eth.get_logs(filter_params)
    # message_contract = w3.eth.contract(abi=[_MESSAGE])

    # for log in logs:
    #    e = get_event_data(w3.codec, message_contract.events.Message().abi, log)
    #    unparsed_event = e['args']['data']
    #    _ = e['args']['sender']
    #    d = w3.codec.decode(['(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32))'], unparsed_event)
    #    depositRoot, nonce, blockNumber, blockHash, signature, stakingModuleId, app = d[0]
    #    print('nonce', nonce)
    #    print('blockNumber', blockNumber)
    #    print('stakingModuleId', stakingModuleId)
