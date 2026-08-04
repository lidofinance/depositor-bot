from web3 import Web3

from blockchain.contracts.data_bus import DataBusContract
from transport.msg_providers.onchain_transport import (
    DepositV1Parser,
    DepositV2Parser,
    PauseV3Parser,
    PauseV4Parser,
    PingParser,
    UnvetV1Parser,
    UnvetV2Parser,
)
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.ping import PingMessage
from transport.msg_types.unvet import UnvetMessage


class OnchainTransportSender:
    """
    Is used in tests to create sequence of the events emitted from the DataBus contract
    """

    # Council v4 publishes the compact (r, vs) pair; council v5 publishes a flat 65-byte r||s||v blob.
    _DEFAULT_SIGNATURE = ((0).to_bytes(32), (0).to_bytes(32))
    _DEFAULT_SIGNATURE_BYTES = bytes(65)
    _DEFAULT_BLOCK_HASH = '0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0'

    def __init__(self, w3: Web3, data_bus_contract: DataBusContract):
        self._w3 = w3
        self._data_bus = data_bus_contract

    def send_deposit_v1(self, deposit_mes: DepositMessage):
        event_id = self._w3.keccak(text=DepositV1Parser.message_abi)
        mes = self._w3.codec.encode(
            types=[DepositV1Parser.DEPOSIT_V1_DATA_SCHEMA],
            args=[(*self._deposit_body(deposit_mes), self._DEFAULT_SIGNATURE, ((1).to_bytes(32),))],
        )
        tx = self._data_bus.functions.sendMessage(event_id, mes)
        return tx.transact()

    def send_deposit_v2(self, deposit_mes: DepositMessage):
        event_id = self._w3.keccak(text=DepositV2Parser.message_abi)
        mes = self._w3.codec.encode(
            types=[DepositV2Parser.DEPOSIT_V2_DATA_SCHEMA],
            args=[(*self._deposit_body(deposit_mes), self._DEFAULT_SIGNATURE_BYTES, ((1).to_bytes(32),))],
        )
        tx = self._data_bus.functions.sendMessage(event_id, mes)
        return tx.transact()

    def send_pause_v3(self, pause_mes: PauseMessage):
        pause_topic = self._w3.keccak(text=PauseV3Parser.message_abi)
        mes = self._w3.codec.encode(
            types=[PauseV3Parser.PAUSE_V3_DATA_SCHEMA],
            args=[(pause_mes['blockNumber'], self._DEFAULT_BLOCK_HASH, self._DEFAULT_SIGNATURE, ((1).to_bytes(32),))],
        )
        tx = self._data_bus.functions.sendMessage(pause_topic, mes)
        return tx.transact()

    def send_pause_v4(self, pause_mes: PauseMessage):
        pause_topic = self._w3.keccak(text=PauseV4Parser.message_abi)
        mes = self._w3.codec.encode(
            types=[PauseV4Parser.PAUSE_V4_DATA_SCHEMA],
            args=[(pause_mes['blockNumber'], self._DEFAULT_BLOCK_HASH, self._DEFAULT_SIGNATURE_BYTES, ((1).to_bytes(32),))],
        )
        tx = self._data_bus.functions.sendMessage(pause_topic, mes)
        return tx.transact()

    def send_unvet_v1(self, unvet_mes: UnvetMessage):
        event_id = self._w3.keccak(text=UnvetV1Parser.message_abi)
        mes = self._w3.codec.encode(
            types=[UnvetV1Parser.UNVET_V1_DATA_SCHEMA],
            args=[(*self._unvet_body(unvet_mes), self._DEFAULT_SIGNATURE, ((1).to_bytes(32),))],
        )
        tx = self._data_bus.functions.sendMessage(event_id, mes)
        return tx.transact()

    def send_unvet_v2(self, unvet_mes: UnvetMessage):
        event_id = self._w3.keccak(text=UnvetV2Parser.message_abi)
        mes = self._w3.codec.encode(
            types=[UnvetV2Parser.UNVET_V2_DATA_SCHEMA],
            args=[(*self._unvet_body(unvet_mes), self._DEFAULT_SIGNATURE_BYTES, ((1).to_bytes(32),))],
        )
        tx = self._data_bus.functions.sendMessage(event_id, mes)
        return tx.transact()

    def send_ping(self, ping_mes: PingMessage):
        event_id = self._w3.keccak(text=PingParser.message_abi)
        block_number, version = ping_mes['blockNumber'], (1).to_bytes(32)
        mes = self._w3.codec.encode(types=[PingParser.PING_V1_DATA_SCHEMA], args=[(block_number, (version,))])
        tx = self._data_bus.functions.sendMessage(event_id, mes)
        return tx.transact()

    @staticmethod
    def _deposit_body(deposit_mes: DepositMessage) -> tuple:
        """The fields both deposit event generations share, in wire order."""
        return (
            deposit_mes['blockNumber'],
            deposit_mes['blockHash'],
            deposit_mes['depositRoot'],
            deposit_mes['stakingModuleId'],
            deposit_mes['nonce'],
        )

    @staticmethod
    def _unvet_body(unvet_mes: UnvetMessage) -> tuple:
        """The fields both unvet event generations share, in wire order."""
        return (
            unvet_mes['blockNumber'],
            unvet_mes['blockHash'],
            unvet_mes['stakingModuleId'],
            unvet_mes['nonce'],
            unvet_mes['operatorIds'],
            unvet_mes['vettedKeysByOperator'],
        )
