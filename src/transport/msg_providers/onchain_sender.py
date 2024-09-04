from blockchain.contracts.data_bus import DataBusContract
from transport.msg_providers.onchain_transport import (
    DEPOSIT_V1_DATA_SCHEMA,
    PAUSE_V2_DATA_SCHEMA,
    PAUSE_V3_DATA_SCHEMA,
    PING_V1_DATA_SCHEMA,
    UNVET_V1_DATA_SCHEMA,
    OnchainTransportSinks,
)
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.ping import PingMessage
from transport.msg_types.unvet import UnvetMessage
from utils.bytes import from_hex_string_to_bytes
from web3 import Web3


class OnchainTransportSender:
    """
    Is used in tests to create sequence of the events emitted from the DataBus contract
    """

    _DEFAULT_SIGNATURE = from_hex_string_to_bytes(
        '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    )

    def __init__(self, w3: Web3, data_bus_contract: DataBusContract):
        self._w3 = w3
        self._data_bus = data_bus_contract

    def send_deposit(self, deposit_mes: DepositMessage):
        deposit_topic = self._w3.keccak(text=OnchainTransportSinks.DEPOSIT_V1)
        deposit_root, nonce, block_number, block_hash, staking_module_id, app = (
            deposit_mes['depositRoot'],
            deposit_mes['nonce'],
            deposit_mes['blockNumber'],
            deposit_mes['blockHash'],
            deposit_mes['stakingModuleId'],
            (deposit_mes['app']['version'],),
        )
        mes = self._w3.codec.encode(
            types=[DEPOSIT_V1_DATA_SCHEMA],
            args=[(deposit_root, nonce, block_number, block_hash, self._DEFAULT_SIGNATURE, staking_module_id, app)],
        )
        tx = self._data_bus.functions.sendMessage(deposit_topic, mes)
        return tx.transact()

    def send_pause_v2(self, pause_mes: PauseMessage):
        pause_topic = self._w3.keccak(text=OnchainTransportSinks.PAUSE_V2)
        deposit_root, nonce, block_number, block_hash, staking_module_id, app = (
            pause_mes['depositRoot'],
            pause_mes['nonce'],
            pause_mes['blockNumber'],
            pause_mes['blockHash'],
            pause_mes['stakingModuleId'],
            (pause_mes['app']['version'],),
        )
        mes = self._w3.codec.encode(
            types=[PAUSE_V2_DATA_SCHEMA],
            args=[(deposit_root, nonce, block_number, block_hash, self._DEFAULT_SIGNATURE, staking_module_id, app)],
        )
        tx = self._data_bus.functions.sendMessage(pause_topic, mes)
        return tx.transact()

    def send_pause_v3(self, pause_mes: PauseMessage):
        pause_topic = self._w3.keccak(text=OnchainTransportSinks.PAUSE_V3)
        block_number, version = pause_mes['blockNumber'], pause_mes['app']['version']
        mes = self._w3.codec.encode(types=[PAUSE_V3_DATA_SCHEMA], args=[(block_number, self._DEFAULT_SIGNATURE, (version,))])
        tx = self._data_bus.functions.sendMessage(pause_topic, mes)
        return tx.transact()

    def send_unvet(self, unvet_mes: UnvetMessage):
        unvet_topic = self._w3.keccak(text=OnchainTransportSinks.UNVET_V1)
        nonce, block_number, block_hash, staking_module_id, operator_ids, vetted_keys, version = (
            unvet_mes['nonce'],
            unvet_mes['blockNumber'],
            unvet_mes['blockHash'],
            unvet_mes['stakingModuleId'],
            unvet_mes['operatorIds'],
            unvet_mes['vettedKeysByOperator'],
            unvet_mes['app']['version'],
        )
        mes = self._w3.codec.encode(
            types=[UNVET_V1_DATA_SCHEMA],
            args=[(nonce, block_number, block_hash, staking_module_id, self._DEFAULT_SIGNATURE, operator_ids, vetted_keys, (version,))],
        )
        tx = self._data_bus.functions.sendMessage(unvet_topic, mes)
        return tx.transact()

    def send_ping(self, ping_mes: PingMessage):
        ping_topic = self._w3.keccak(text=OnchainTransportSinks.PING_V1)
        block_number, version = ping_mes['blockNumber'], ping_mes['app']['version']
        mes = self._w3.codec.encode(types=[PING_V1_DATA_SCHEMA], args=[(block_number, (version,))])
        tx = self._data_bus.functions.sendMessage(ping_topic, mes)
        return tx.transact()
