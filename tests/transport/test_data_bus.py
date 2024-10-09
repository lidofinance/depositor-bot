from typing import cast
from unittest import mock
from unittest.mock import Mock

import pytest
import variables
from blockchain.contracts.data_bus import DataBusContract
from eth_typing import ChecksumAddress, HexAddress, HexStr
from schema import Or, Schema
from transport.msg_providers.onchain_transport import (
    DepositParser,
    OnchainTransportProvider,
    PingParser,
)
from transport.msg_types.deposit import DepositMessage, DepositMessageSchema
from transport.msg_types.ping import PingMessage, PingMessageSchema
from transport.msg_types.unvet import UnvetMessage
from web3 import Web3
from web3.types import EventData

from tests.transport.onchain_sender import OnchainTransportSender

_DEFAULT_GUARDIAN = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'


# Started with config: {
#  NODE_HOST: 'http://127.0.0.1:8888',
#  DATA_BUS_ADDRESS: '0x5FbDB2315678afecb367f032d93F642f64180aa3'
# }
@pytest.mark.integration_chiado
def test_data_bus_provider(web3_transaction_integration):
    """
    Utilise this function for an adhoc testing of data bus transport
    """
    variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS = ['https://gnosis-chiado-rpc.publicnode.com']
    variables.ONCHAIN_TRANSPORT_ADDRESS = ChecksumAddress(HexAddress(HexStr('0x42E1DEfC18388E3AA1fCADa851499A11405cf37f')))
    data_bus_contract = cast(
        DataBusContract,
        web3_transaction_integration.eth.contract(
            address=variables.ONCHAIN_TRANSPORT_ADDRESS,
            ContractFactoryClass=DataBusContract,
        ),
    )

    onchain_sender = OnchainTransportSender(w3=web3_transaction_integration, data_bus_contract=data_bus_contract)
    onchain_sender.send_deposit(
        deposit_mes=DepositMessage(
            type='deposit',
            depositRoot='0x0000000000000000000000000000000000000000000000000000000000000000',
            nonce=40,
            blockNumber=2,
            blockHash='0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
            guardianAddress=_DEFAULT_GUARDIAN,
            stakingModuleId=1,
            app={'version': (1).to_bytes(32)},
        )
    )
    onchain_sender.send_ping(
        ping_mes=PingMessage(
            type='ping',
            blockNumber=2,
            guardianAddress=_DEFAULT_GUARDIAN,
            app={'version': (1).to_bytes(32)},
        )
    )
    onchain_sender.send_unvet(
        unvet_mes=UnvetMessage(
            type='unvet',
            blockNumber=2,
            blockHash='0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
            guardianAddress=_DEFAULT_GUARDIAN,
            stakingModuleId=1,
            nonce=32,
            operatorIds=bytes(32),
            vettedKeysByOperator=bytes(32),
            app={'version': (1).to_bytes(32)},
        )
    )
    web3_transaction_integration.provider.make_request('anvil_mine', [10])
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
        parsers_providers=[DepositParser, PingParser],
        allowed_guardians_provider=lambda: [Web3.to_checksum_address(_DEFAULT_GUARDIAN[:-1] + '7')],
    )
    messages = provider.get_messages()
    assert not messages
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
        parsers_providers=[DepositParser, PingParser],
        allowed_guardians_provider=lambda: [Web3.to_checksum_address(_DEFAULT_GUARDIAN)],
    )
    messages = provider.get_messages()
    for mes in messages:
        print(mes)
    assert messages


@pytest.mark.unit
def test_data_bus_mock_responses(web3_lido_unit):
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        receipts = mock_receipts(web3_lido_unit)
        web3_lido_unit.eth.get_logs = Mock(side_effect=[receipts, None])
        web3_lido_unit.is_connected = Mock(return_value=True)
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        provider = OnchainTransportProvider(
            w3=web3_lido_unit,
            onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
            message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
            parsers_providers=[DepositParser, PingParser],
            allowed_guardians_provider=lambda: [Web3.to_checksum_address(_DEFAULT_GUARDIAN)],
        )

        for parser in provider._parsers:
            parser._decode_event = Mock(side_effect=lambda x: x)

        messages = provider.get_messages()
        assert len(messages) == len(receipts)


# event MessageDepositV1(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, bytes32 depositRoot,
# uint256 stakingModuleId, uint256 nonce, (bytes32 r, bytes32 vs) signature, (bytes32 version) app) data),

# event MessageDepositV1(address indexed guardianAddress, (bytes32 depositRoot, uint256 nonce, uint256 blockNumber, bytes32 blockHash,
# bytes signature, uint256 stakingModuleId, (bytes32 version) app) data)",


def mock_receipts(w3: Web3) -> list[EventData]:
    return [
        EventData(
            args={
                'sender': _DEFAULT_GUARDIAN,
                'data': w3.codec.encode(
                    types=[PingParser.PING_V1_DATA_SCHEMA],
                    args=[(1, ('0x0000000000000000000000000000000000000000000000000000000000000000',))],
                ),
            },
        ),
        EventData(
            args={
                'sender': _DEFAULT_GUARDIAN,
                'data': w3.codec.encode(
                    types=[DepositParser.DEPOSIT_V1_DATA_SCHEMA],
                    args=[
                        (
                            2,
                            '0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
                            '0x0000000000000000000000000000000000000000000000000000000000000000',
                            3,
                            40,
                            ((0).to_bytes(32), (0).to_bytes(32)),
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
                    types=[PingParser.PING_V1_DATA_SCHEMA],
                    args=[(3, ('0x0000000000000000000000000000000000000000000000000000000000000000',))],
                ),
            },
        ),
        EventData(
            args={
                'sender': _DEFAULT_GUARDIAN,
                'data': w3.codec.encode(
                    types=[PingParser.PING_V1_DATA_SCHEMA],
                    args=[(4, ('0x0000000000000000000000000000000000000000000000000000000000000000',))],
                ),
            },
        ),
    ]
