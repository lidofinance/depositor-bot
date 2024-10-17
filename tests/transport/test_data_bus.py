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
    PauseV2Parser,
    PauseV3Parser,
    PingParser,
    UnvetParser,
)
from transport.msg_types.deposit import DepositMessageSchema
from transport.msg_types.pause import PauseMessage, PauseMessageSchema
from transport.msg_types.ping import PingMessageSchema
from transport.msg_types.unvet import UnvetMessage, UnvetMessageSchema
from web3 import Web3
from web3.types import EventData

from tests.transport.onchain_sender import OnchainTransportSender

_DEFAULT_GUARDIAN = '0xf060ab3d5dCfdC6a0DFd5ca0645ac569b8f105CA'
_ANVIL_GUARDIAN = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'


# Started with config: {
#  NODE_HOST: 'http://127.0.0.1:8888',
#  DATA_BUS_ADDRESS: '0x5FbDB2315678afecb367f032d93F642f64180aa3'
# }
@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS[0]}],
    indirect=['web3_provider_integration'],
)
def test_data_bus_provider(
    web3_transaction_integration,
):
    """
    Utilise this function for an adhoc testing of data bus transport
    """
    variables.ONCHAIN_TRANSPORT_ADDRESS = ChecksumAddress(HexAddress(HexStr('0x37De961D6bb5865867aDd416be07189D2Dd960e6')))
    web3_transaction_integration.eth.get_balance = Mock(return_value=1)
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
    assert messages


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS[0]}],
    indirect=['web3_provider_integration'],
)
def test_data_bus_provider_unvet(
    web3_transaction_integration,
):
    """
    Utilise this function for an adhoc testing of data bus transport
    """
    variables.ONCHAIN_TRANSPORT_ADDRESS = ChecksumAddress(HexAddress(HexStr('0x37De961D6bb5865867aDd416be07189D2Dd960e6')))
    data_bus_contract = cast(
        DataBusContract,
        web3_transaction_integration.eth.contract(
            address=variables.ONCHAIN_TRANSPORT_ADDRESS,
            ContractFactoryClass=DataBusContract,
        ),
    )
    onchain_sender = OnchainTransportSender(w3=web3_transaction_integration, data_bus_contract=data_bus_contract)
    onchain_sender.send_unvet(
        unvet_mes=UnvetMessage(
            type='unvet',
            blockNumber=2,
            blockHash='0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
            guardianAddress=_ANVIL_GUARDIAN,
            stakingModuleId=1,
            nonce=32,
            operatorIds='0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
            vettedKeysByOperator='0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
            app={'version': b'3.2.0'.rjust(32, b'\0')},
        )
    )
    web3_transaction_integration.provider.make_request('anvil_mine', [10])
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(UnvetMessageSchema)),
        parsers_providers=[UnvetParser],
        allowed_guardians_provider=lambda: [Web3.to_checksum_address(_ANVIL_GUARDIAN[:-1] + '7')],
    )
    messages = provider.get_messages()
    assert not messages
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(UnvetMessageSchema)),
        parsers_providers=[UnvetParser],
        allowed_guardians_provider=lambda: [Web3.to_checksum_address(_ANVIL_GUARDIAN)],
    )
    messages = provider.get_messages()
    assert len(messages) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS[0]}],
    indirect=['web3_provider_integration'],
)
def test_data_bus_provider_pause_v2(
    web3_transaction_integration,
):
    """
    Utilise this function for an adhoc testing of data bus transport
    """
    variables.ONCHAIN_TRANSPORT_ADDRESS = ChecksumAddress(HexAddress(HexStr('0x37De961D6bb5865867aDd416be07189D2Dd960e6')))
    data_bus_contract = cast(
        DataBusContract,
        web3_transaction_integration.eth.contract(
            address=variables.ONCHAIN_TRANSPORT_ADDRESS,
            ContractFactoryClass=DataBusContract,
        ),
    )
    onchain_sender = OnchainTransportSender(w3=web3_transaction_integration, data_bus_contract=data_bus_contract)
    onchain_sender.send_pause_v2(
        pause_mes=PauseMessage(
            type='pause',
            blockNumber=2,
            guardianAddress=_ANVIL_GUARDIAN,
            stakingModuleId=1,
            app={'version': b'3.2.0'.rjust(32, b'\0')},
        )
    )
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(PauseMessageSchema)),
        parsers_providers=[PauseV2Parser],
        allowed_guardians_provider=lambda: [Web3.to_checksum_address(_ANVIL_GUARDIAN[:-1] + '7')],
    )
    messages = provider.get_messages()
    assert not messages
    web3_transaction_integration.provider.make_request('anvil_mine', [10])
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(PauseMessageSchema)),
        parsers_providers=[PauseV2Parser],
        allowed_guardians_provider=lambda: [Web3.to_checksum_address(_ANVIL_GUARDIAN)],
    )
    messages = provider.get_messages()
    assert len(messages) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS[0]}],
    indirect=['web3_provider_integration'],
)
def test_data_bus_provider_pause_v3(
    web3_transaction_integration,
):
    """
    Utilise this function for an adhoc testing of data bus transport
    """
    variables.ONCHAIN_TRANSPORT_ADDRESS = ChecksumAddress(HexAddress(HexStr('0x37De961D6bb5865867aDd416be07189D2Dd960e6')))
    data_bus_contract = cast(
        DataBusContract,
        web3_transaction_integration.eth.contract(
            address=variables.ONCHAIN_TRANSPORT_ADDRESS,
            ContractFactoryClass=DataBusContract,
        ),
    )
    onchain_sender = OnchainTransportSender(w3=web3_transaction_integration, data_bus_contract=data_bus_contract)
    onchain_sender.send_pause_v3(
        pause_mes=PauseMessage(
            type='pause',
            blockNumber=2,
            guardianAddress=_ANVIL_GUARDIAN,
            stakingModuleId=1,
            app={'version': b'3.2.0'.rjust(32, b'\0')},
        )
    )
    web3_transaction_integration.provider.make_request('anvil_mine', [10])
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(PauseMessageSchema)),
        parsers_providers=[PauseV3Parser],
        allowed_guardians_provider=lambda: [Web3.to_checksum_address(_ANVIL_GUARDIAN)],
    )
    messages = provider.get_messages()
    assert len(messages) == 1


@pytest.mark.unit
def test_data_bus_mock_responses(web3_lido_unit):
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        receipts = mock_receipts(web3_lido_unit)
        web3_lido_unit.eth.get_logs = Mock(side_effect=[receipts, None])
        web3_lido_unit.is_connected = Mock(return_value=True)
        web3_lido_unit.eth.get_balance = Mock(return_value=1)
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
