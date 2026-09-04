from typing import cast
from unittest import mock
from unittest.mock import Mock

import pytest
from eth_typing import ChecksumAddress, HexAddress, HexStr
from schema import Or, Schema
from web3 import Web3

import variables
from blockchain.contracts.data_bus import DataBusContract
from tests.conftest import COUNCIL_ADDRESS_1, COUNCIL_PK_1
from tests.transport.onchain_sender import OnchainTransportSender
from transport.msg_providers.onchain_transport import (
    DepositV1Parser,
    DepositV2Parser,
    OnchainTransportProvider,
    PauseV3Parser,
    PauseV4Parser,
    PingParser,
    UnvetV1Parser,
    UnvetV2Parser,
)
from transport.msg_types.common import get_messages_sign_filter
from transport.msg_types.deposit import DepositMessageSchema
from transport.msg_types.pause import PauseMessage, PauseMessageSchema
from transport.msg_types.ping import PingMessageSchema
from transport.msg_types.unvet import UnvetMessage, UnvetMessageSchema

# Under the LIP-37 delegation model the Data Bus `sender` is the guardian's delegate EOA, which the
# provider reverse-maps to the guardian contract via the {delegate: guardian} map it is given.
_DEFAULT_DELEGATE = '0x1be2A219CBD0F18B825a4dDd580F7b3B33Bacb41'
_ANVIL_DELEGATE = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'
_FAKE_DELEGATE = '0x4E93C8c7B06F1CEEb03A8e13B0371b35F0000000'
_GUARDIAN_CONTRACT = '0x2C44CdDdB6a900fa2b585dd299e03d12FA4293BC'
_ZERO_HASH = '0x0000000000000000000000000000000000000000000000000000000000000000'

# Resolved at import time by pytest's parametrize decorators. The endpoint is only used when the
# integration tests actually run (env var set); unit collection must not fail when it is unset.
_ONCHAIN_TRANSPORT_ENDPOINT = variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS[0] if variables.ONCHAIN_TRANSPORT_RPC_ENDPOINTS else ''


# Started with config: {
#  NODE_HOST: 'http://127.0.0.1:8888',
#  DATA_BUS_ADDRESS: '0x5FbDB2315678afecb367f032d93F642f64180aa3'
# }
@pytest.mark.skip()
@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': _ONCHAIN_TRANSPORT_ENDPOINT}],
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
        parsers_providers=[DepositV1Parser, DepositV2Parser, PingParser],
        delegates_provider=lambda: {Web3.to_checksum_address(_FAKE_DELEGATE): Web3.to_checksum_address(_GUARDIAN_CONTRACT)},
    )
    messages = provider.get_messages()
    assert not messages
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(DepositMessageSchema, PingMessageSchema)),
        parsers_providers=[DepositV1Parser, DepositV2Parser, PingParser],
        delegates_provider=lambda: {Web3.to_checksum_address(_DEFAULT_DELEGATE): Web3.to_checksum_address(_GUARDIAN_CONTRACT)},
    )
    messages = provider.get_messages()
    assert messages


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': _ONCHAIN_TRANSPORT_ENDPOINT}],
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
    onchain_sender.send_unvet_v1(
        unvet_mes=UnvetMessage(
            type='unvet',
            blockNumber=2,
            blockHash='0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
            guardianAddress=_ANVIL_DELEGATE,
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
        parsers_providers=[UnvetV1Parser],
        delegates_provider=lambda: {Web3.to_checksum_address(_ANVIL_DELEGATE[:-1] + '7'): Web3.to_checksum_address(_GUARDIAN_CONTRACT)},
    )
    messages = provider.get_messages()
    assert not messages
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(UnvetMessageSchema)),
        parsers_providers=[UnvetV1Parser],
        delegates_provider=lambda: {Web3.to_checksum_address(_ANVIL_DELEGATE): Web3.to_checksum_address(_GUARDIAN_CONTRACT)},
    )
    messages = provider.get_messages()
    assert len(messages) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': _ONCHAIN_TRANSPORT_ENDPOINT}],
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
            guardianAddress=_ANVIL_DELEGATE,
            app={'version': b'3.2.0'.rjust(32, b'\0')},
        )
    )
    web3_transaction_integration.provider.make_request('anvil_mine', [10])
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(PauseMessageSchema)),
        parsers_providers=[PauseV3Parser],
        delegates_provider=lambda: {Web3.to_checksum_address(_ANVIL_DELEGATE): Web3.to_checksum_address(_GUARDIAN_CONTRACT)},
    )
    messages = provider.get_messages()
    assert len(messages) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    'web3_provider_integration',
    [{'endpoint': _ONCHAIN_TRANSPORT_ENDPOINT}],
    indirect=['web3_provider_integration'],
)
def test_data_bus_provider_pause_v4(
    web3_transaction_integration,
):
    """
    Same round trip as pause v3, over the council v5 event that carries a flat `bytes` signature.
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
    onchain_sender.send_pause_v4(
        pause_mes=PauseMessage(
            type='pause',
            blockNumber=2,
            guardianAddress=_ANVIL_DELEGATE,
            app={'version': b'3.2.0'.rjust(32, b'\0')},
        )
    )
    web3_transaction_integration.provider.make_request('anvil_mine', [10])
    provider = OnchainTransportProvider(
        w3=web3_transaction_integration,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=Schema(Or(PauseMessageSchema)),
        parsers_providers=[PauseV3Parser, PauseV4Parser],
        delegates_provider=lambda: _delegate_map(delegate=_ANVIL_DELEGATE),
    )
    messages = provider.get_messages()
    assert len(messages) == 1


def _delegate_map(delegate: str = _DEFAULT_DELEGATE, guardian: str = _GUARDIAN_CONTRACT) -> dict:
    return {Web3.to_checksum_address(delegate): Web3.to_checksum_address(guardian)}


@pytest.mark.unit
def test_data_bus_mock_responses(web3_lido_unit):
    """Both deposit event generations reach the storage through a single provider."""
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        receipts = mock_receipts(web3_lido_unit)
        web3_lido_unit.eth.get_logs = Mock(side_effect=[receipts, None])
        web3_lido_unit.is_connected = Mock(return_value=True)
        web3_lido_unit.eth.get_balance = Mock(return_value=1)
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        provider = _stubbed_provider(web3_lido_unit, [DepositV1Parser, DepositV2Parser, PingParser])

        messages = provider.get_messages()
        assert len(messages) == len(receipts)


@pytest.mark.unit
def test_parsers_are_dispatched_by_event_id(web3_lido_unit):
    """A log must be handed to the parser that declared its event id, not to the first parser that
    happens to decode it: the V1 layout decodes a V2 payload without raising (the offset word reads as
    blockNumber), so a fallback chain would silently turn every council v5 message into garbage.
    """
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        v1_log = _deposit_v1_log(web3_lido_unit, block_number=11, nonce=1)
        v2_log = _deposit_v2_log(web3_lido_unit, block_number=22, nonce=2, signature=bytes(65))
        web3_lido_unit.eth.get_logs = Mock(side_effect=[[v1_log, v2_log], None])
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        # V1 first, so the removed fallback chain would have claimed the V2 log here.
        provider = _stubbed_provider(web3_lido_unit, [DepositV1Parser, DepositV2Parser])

        messages = provider.get_messages()

        assert [message['blockNumber'] for message in messages] == [11, 22]
        assert [message['nonce'] for message in messages] == [1, 2]


@pytest.mark.unit
def test_data_bus_reverse_maps_sender_to_guardian(web3_lido_unit):
    """The event `sender` (delegate EOA) is reverse-mapped to its guardian contract; the delegate is
    retained under `guardianDelegate`."""
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        receipts = mock_receipts(web3_lido_unit)
        web3_lido_unit.eth.get_logs = Mock(side_effect=[receipts, None])
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        provider = _stubbed_provider(web3_lido_unit, [DepositV1Parser, DepositV2Parser, PingParser])

        messages = provider.get_messages()

        assert messages
        for message in messages:
            assert message['guardianAddress'] == Web3.to_checksum_address(_GUARDIAN_CONTRACT)
            assert message['guardianDelegate'] == Web3.to_checksum_address(_DEFAULT_DELEGATE)


@pytest.mark.unit
def test_data_bus_drops_unmapped_sender(web3_lido_unit):
    """A message whose sender is not a current delegate is dropped (fail closed on rotation)."""
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        receipts = mock_receipts(web3_lido_unit)
        web3_lido_unit.eth.get_logs = Mock(side_effect=[receipts, None])
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        # sender in the receipts (_DEFAULT_DELEGATE) is absent from the map → all dropped.
        provider = _stubbed_provider(
            web3_lido_unit,
            [DepositV1Parser, DepositV2Parser, PingParser],
            delegates_provider=lambda: _delegate_map(delegate=_FAKE_DELEGATE),
        )

        assert provider.get_messages() == []


@pytest.mark.unit
def test_deposit_v2_signature_passes_sign_filter(web3_lido_unit):
    """The flat 65-byte `r || s || v` blob of a council v5 message must normalise into a compact
    `(r, _vs)` pair the sign filter still recovers the guardian from.
    """
    prefix = bytes(31) + b'\x01'
    block_number, block_hash, deposit_root, module_id, nonce = 42, bytes(32), bytes(32), 1, 7
    msg_hash = Web3.solidity_keccak(
        ['bytes32', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256'],
        [prefix, block_number, block_hash, deposit_root, module_id, nonce],
    )
    signed = web3_lido_unit.eth.account._sign_hash(msg_hash, private_key=COUNCIL_PK_1)
    signature = signed.r.to_bytes(32, 'big') + signed.s.to_bytes(32, 'big') + signed.v.to_bytes(1, 'big')

    parser = DepositV2Parser(web3_lido_unit)
    parser._decode_event = Mock(side_effect=lambda log: log)
    message = parser.parse(
        _deposit_v2_log(
            web3_lido_unit,
            block_number=block_number,
            nonce=nonce,
            signature=signature,
            sender=COUNCIL_ADDRESS_1,
            staking_module_id=module_id,
        )
    )

    assert DepositMessageSchema.is_valid(message)
    assert list(filter(get_messages_sign_filter(prefix), [message]))


@pytest.mark.unit
def test_unvet_v2_signature_passes_sign_filter(web3_lido_unit):
    """Same round-trip as the deposit V2 case, for unvet: the flat blob must normalise into a compact
    pair the sign filter still recovers the guardian from. This is what pins the V2 field order —
    a reordered schema changes the digest and only shows up as a silently dropped message.
    """
    prefix = bytes(31) + b'\x02'
    block_number, block_hash, module_id, nonce = 42, bytes(32), 1, 7
    operator_ids, vetted_keys = (1).to_bytes(8, 'big'), (2).to_bytes(16, 'big')
    msg_hash = Web3.solidity_keccak(
        ['bytes32', 'uint256', 'bytes32', 'uint256', 'uint256', 'bytes', 'bytes'],
        [prefix, block_number, block_hash, module_id, nonce, operator_ids, vetted_keys],
    )
    signed = web3_lido_unit.eth.account._sign_hash(msg_hash, private_key=COUNCIL_PK_1)
    signature = signed.r.to_bytes(32, 'big') + signed.s.to_bytes(32, 'big') + signed.v.to_bytes(1, 'big')

    parser = UnvetV2Parser(web3_lido_unit)
    parser._decode_event = Mock(side_effect=lambda log: log)
    message = parser.parse(
        _unvet_v2_log(
            web3_lido_unit,
            block_number=block_number,
            nonce=nonce,
            signature=signature,
            sender=COUNCIL_ADDRESS_1,
            staking_module_id=module_id,
            operator_ids=operator_ids,
            vetted_keys_by_operator=vetted_keys,
        )
    )

    assert UnvetMessageSchema.is_valid(message)
    assert list(filter(get_messages_sign_filter(prefix), [message]))


@pytest.mark.unit
def test_unvet_parsers_are_dispatched_by_event_id(web3_lido_unit):
    """Both unvet generations reach the storage through one provider, each via its own parser."""
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        v1_log = _unvet_v1_log(web3_lido_unit, block_number=11, nonce=1)
        v2_log = _unvet_v2_log(web3_lido_unit, block_number=22, nonce=2, signature=bytes(65))
        web3_lido_unit.eth.get_logs = Mock(side_effect=[[v1_log, v2_log], None])
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        provider = _stubbed_provider(web3_lido_unit, [UnvetV1Parser, UnvetV2Parser], message_schema=Schema(UnvetMessageSchema))

        messages = provider.get_messages()

        assert [message['blockNumber'] for message in messages] == [11, 22]
        assert [message['nonce'] for message in messages] == [1, 2]


@pytest.mark.unit
def test_unvet_v2_rejects_malformed_signature(web3_lido_unit):
    """A signature blob of the wrong length is dropped, not silently truncated into a valid message."""
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        malformed = _unvet_v2_log(web3_lido_unit, block_number=1, nonce=1, signature=bytes(64))
        web3_lido_unit.eth.get_logs = Mock(side_effect=[[malformed], None])
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        provider = _stubbed_provider(web3_lido_unit, [UnvetV2Parser], message_schema=Schema(UnvetMessageSchema))

        assert not provider.get_messages()


@pytest.mark.unit
def test_deposit_v2_rejects_malformed_signature(web3_lido_unit):
    """A signature blob of the wrong length is dropped, not silently truncated into a valid message."""
    with mock.patch('web3.eth.Eth.chain_id', new_callable=mock.PropertyMock) as mock_chain_id:
        mock_chain_id.return_value = 1
        web3_lido_unit.eth.get_logs = Mock(side_effect=[[_deposit_v2_log(web3_lido_unit, 1, 1, signature=bytes(64))], None])
        web3_lido_unit.eth.get_block_number = Mock(return_value=1)
        provider = _stubbed_provider(web3_lido_unit, [DepositV2Parser])

        assert not provider.get_messages()


def _stubbed_provider(
    w3: Web3,
    parsers_providers: list,
    delegates_provider=_delegate_map,
    message_schema: Schema = Schema(Or(DepositMessageSchema, PingMessageSchema)),
) -> OnchainTransportProvider:
    """Provider whose parsers skip log decoding — the mock logs already carry decoded `args`."""
    provider = OnchainTransportProvider(
        w3=w3,
        onchain_address=variables.ONCHAIN_TRANSPORT_ADDRESS,
        message_schema=message_schema,
        parsers_providers=parsers_providers,
        delegates_provider=delegates_provider,
    )
    for parser in provider._parsers_by_event_id.values():
        parser._decode_event = Mock(side_effect=lambda log: log)
    return provider


def _log(w3: Web3, message_abi: str, data: bytes, sender: str = _DEFAULT_DELEGATE) -> dict:
    """A Data Bus log shaped just enough for the provider: topic0 selects the parser, `args` stands in
    for what `_decode_event` would have produced."""
    return {'topics': [w3.keccak(text=message_abi)], 'args': {'sender': sender, 'data': data}}


def _ping_log(w3: Web3, block_number: int) -> dict:
    return _log(w3, PingParser.message_abi, w3.codec.encode(types=[PingParser.PING_V1_DATA_SCHEMA], args=[(block_number, (_ZERO_HASH,))]))


def _deposit_v1_log(w3: Web3, block_number: int, nonce: int, staking_module_id: int = 3) -> dict:
    data = w3.codec.encode(
        types=[DepositV1Parser.DEPOSIT_V1_DATA_SCHEMA],
        args=[
            (
                block_number,
                '0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0',
                _ZERO_HASH,
                staking_module_id,
                nonce,
                ((0).to_bytes(32), (0).to_bytes(32)),
                (_ZERO_HASH,),
            )
        ],
    )
    return _log(w3, DepositV1Parser.message_abi, data)


def _deposit_v2_log(
    w3: Web3,
    block_number: int,
    nonce: int,
    signature: bytes,
    sender: str = _DEFAULT_DELEGATE,
    staking_module_id: int = 3,
) -> dict:
    data = w3.codec.encode(
        types=[DepositV2Parser.DEPOSIT_V2_DATA_SCHEMA],
        args=[(block_number, _ZERO_HASH, _ZERO_HASH, staking_module_id, nonce, signature, (_ZERO_HASH,))],
    )
    return _log(w3, DepositV2Parser.message_abi, data, sender=sender)


def _unvet_v1_log(w3: Web3, block_number: int, nonce: int, staking_module_id: int = 1) -> dict:
    data = w3.codec.encode(
        types=[UnvetV1Parser.UNVET_V1_DATA_SCHEMA],
        args=[
            (
                block_number,
                _ZERO_HASH,
                staking_module_id,
                nonce,
                (0).to_bytes(8, 'big'),
                (0).to_bytes(16, 'big'),
                ((0).to_bytes(32), (0).to_bytes(32)),
                (_ZERO_HASH,),
            )
        ],
    )
    return _log(w3, UnvetV1Parser.message_abi, data)


def _unvet_v2_log(
    w3: Web3,
    block_number: int,
    nonce: int,
    signature: bytes,
    sender: str = _DEFAULT_DELEGATE,
    staking_module_id: int = 1,
    operator_ids: bytes = (0).to_bytes(8, 'big'),
    vetted_keys_by_operator: bytes = (0).to_bytes(16, 'big'),
) -> dict:
    data = w3.codec.encode(
        types=[UnvetV2Parser.UNVET_V2_DATA_SCHEMA],
        args=[
            (
                block_number,
                _ZERO_HASH,
                staking_module_id,
                nonce,
                operator_ids,
                vetted_keys_by_operator,
                signature,
                (_ZERO_HASH,),
            )
        ],
    )
    return _log(w3, UnvetV2Parser.message_abi, data, sender=sender)


def mock_receipts(w3: Web3) -> list[dict]:
    return [
        _ping_log(w3, block_number=1),
        _deposit_v1_log(w3, block_number=2, nonce=40),
        _deposit_v2_log(w3, block_number=3, nonce=41, signature=bytes(65)),
        _ping_log(w3, block_number=4),
    ]
