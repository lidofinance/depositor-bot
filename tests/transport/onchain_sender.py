from blockchain.contracts.data_bus import DataBusContract
from transport.msg_providers.onchain_transport import (
    DepositParser,
    PauseV2Parser,
    PauseV3Parser,
    PingParser,
    UnvetParser,
)
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.ping import PingMessage
from transport.msg_types.unvet import UnvetMessage
from web3 import Web3


class OnchainTransportSender:
    """
    Is used in tests to create sequence of the events emitted from the DataBus contract
    """

    _DEFAULT_SIGNATURE = ((0).to_bytes(32), (0).to_bytes(32))
    _DEFAULT_BLOCK_HASH = '0x42eef33d13c4440627c3fab6e3abee85af796ae6f77dcade628b183640b519d0'

    def __init__(self, w3: Web3, data_bus_contract: DataBusContract):
        self._w3 = w3
        self._data_bus = data_bus_contract

    def send_deposit(self, deposit_mes: DepositMessage):
        deposit_topic = self._w3.keccak(text=DepositParser.message_abi(deposit_mes['guardianAddress']))
        deposit_root, nonce, block_number, block_hash, staking_module_id, app = (
            deposit_mes['depositRoot'],
            deposit_mes['nonce'],
            deposit_mes['blockNumber'],
            deposit_mes['blockHash'],
            deposit_mes['stakingModuleId'],
            ((1).to_bytes(32),),
        )
        mes = self._w3.codec.encode(
            types=[DepositParser.DEPOSIT_V1_DATA_SCHEMA],
            args=[(block_number, block_hash, deposit_root, staking_module_id, nonce, self._DEFAULT_SIGNATURE, app)],
        )
        tx = self._data_bus.functions.sendMessage(deposit_topic, mes)
        return tx.transact()

    def send_pause_v2(self, pause_mes: PauseMessage):
        pause_topic = self._w3.keccak(text=PauseV2Parser.message_abi(pause_mes['guardianAddress']))
        block_number, staking_module_id, app = (
            pause_mes['blockNumber'],
            pause_mes['stakingModuleId'],
            ((1).to_bytes(32),),
        )
        mes = self._w3.codec.encode(
            types=[PauseV2Parser.PAUSE_V2_DATA_SCHEMA],
            args=[(block_number, self._DEFAULT_BLOCK_HASH, self._DEFAULT_SIGNATURE, staking_module_id, app)],
        )
        tx = self._data_bus.functions.sendMessage(pause_topic, mes)
        return tx.transact()

    def send_pause_v3(self, pause_mes: PauseMessage):
        pause_topic = self._w3.keccak(text=PauseV3Parser.message_abi(pause_mes['guardianAddress']))
        block_number, version = pause_mes['blockNumber'], (1).to_bytes(32)
        mes = self._w3.codec.encode(
            types=[PauseV3Parser.PAUSE_V3_DATA_SCHEMA], args=[(block_number, self._DEFAULT_BLOCK_HASH, self._DEFAULT_SIGNATURE, (version,))]
        )
        tx = self._data_bus.functions.sendMessage(pause_topic, mes)
        return tx.transact()

    def send_unvet(self, unvet_mes: UnvetMessage):
        unvet_topic = self._w3.keccak(text=UnvetParser.message_abi(unvet_mes['guardianAddress']))
        nonce, block_number, block_hash, staking_module_id, operator_ids, vetted_keys, version = (
            unvet_mes['nonce'],
            unvet_mes['blockNumber'],
            unvet_mes['blockHash'],
            unvet_mes['stakingModuleId'],
            unvet_mes['operatorIds'],
            unvet_mes['vettedKeysByOperator'],
            (1).to_bytes(32),
        )
        mes = self._w3.codec.encode(
            types=[UnvetParser.UNVET_V1_DATA_SCHEMA],
            args=[(block_number, block_hash, staking_module_id, nonce, operator_ids, vetted_keys, self._DEFAULT_SIGNATURE, (version,))],
        )
        tx = self._data_bus.functions.sendMessage(unvet_topic, mes)
        return tx.transact()

    def send_ping(self, ping_mes: PingMessage):
        ping_topic = self._w3.keccak(text=PingParser.message_abi(ping_mes['guardianAddress']))
        block_number, version = ping_mes['blockNumber'], (1).to_bytes(32)
        mes = self._w3.codec.encode(types=[PingParser.PING_V1_DATA_SCHEMA], args=[(block_number, (version,))])
        tx = self._data_bus.functions.sendMessage(ping_topic, mes)
        return tx.transact()
