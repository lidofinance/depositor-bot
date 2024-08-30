from unittest.mock import Mock

import pytest
import variables
from schema import Or, Schema
from transport.msg_providers.data_bus import DEPOSIT_V1_DATA_SCHEMA, PING_V1_DATA_SCHEMA, DataBusProvider, DataBusSinks
from transport.msg_types.deposit import DepositMessageSchema
from transport.msg_types.ping import PingMessageSchema
from web3 import Web3
from web3.types import EventData
from web3_multi_provider import FallbackProvider

_DEFAULT_GUARDIAN = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'


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
        w3=Web3(FallbackProvider(variables.WEB3_RPC_GNOSIS_ENDPOINTS)),
        message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
        sinks=[DataBusSinks.DEPOSIT_V1, DataBusSinks.PING_V1],
    )
    messages = provider.get_messages()
    for mes in messages:
        print(mes)
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


@pytest.mark.unit
def test_data_bus_mock_responses(web3_lido_unit):
    receipts = mock_receipts(web3_lido_unit)
    web3_lido_unit.eth.get_logs = Mock(side_effect=[receipts, None])
    web3_lido_unit.is_connected = Mock(return_value=True)
    web3_lido_unit.eth.get_block_number = Mock(return_value=1)
    provider = DataBusProvider(
        w3=web3_lido_unit,
        message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
        sinks=[DataBusSinks.DEPOSIT_V1, DataBusSinks.PING_V1],
    )

    for parser in provider._parsers:
        parser._decode_event = Mock(side_effect=lambda x: x)

    messages = provider.get_messages()
    for mes in messages:
        print(mes)
    assert len(messages) == len(receipts)


def mock_receipts(w3: Web3) -> list[EventData]:
    return [
        EventData(
            args={
                'sender': _DEFAULT_GUARDIAN,
                'data': w3.codec.encode(
                    types=[PING_V1_DATA_SCHEMA], args=[(1, ('0x0000000000000000000000000000000000000000000000000000000000000000',))]
                ),
            },
        ),
        EventData(
            args={
                'sender': _DEFAULT_GUARDIAN,
                'data': w3.codec.encode(
                    types=[DEPOSIT_V1_DATA_SCHEMA],
                    args=[
                        (
                            '0x0000000000000000000000000000000000000000000000000000000000000000',
                            40,
                            2,
                            '0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
                            '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000',
                            3,
                            ('0x0000000000000000000000000000000000000000000000000000000000000000',),
                        )
                    ],
                ),
            },
        ),
        EventData(
            args={
                'sender': _DEFAULT_GUARDIAN,
                'data': w3.codec.encode(
                    types=[PING_V1_DATA_SCHEMA], args=[(3, ('0x0000000000000000000000000000000000000000000000000000000000000000',))]
                ),
            },
        ),
        EventData(
            args={
                'sender': _DEFAULT_GUARDIAN,
                'data': w3.codec.encode(
                    types=[PING_V1_DATA_SCHEMA], args=[(4, ('0x0000000000000000000000000000000000000000000000000000000000000000',))]
                ),
            },
        ),
    ]
