import abc
import logging
from enum import StrEnum
from typing import List, Optional

from cryptography.verify_signature import compute_vs
from eth_account.account import VRS
from eth_typing import ChecksumAddress, HexStr
from schema import Schema
from transport.msg_providers.common import BaseMessageProvider
from transport.msg_providers.rabbit import MessageType
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.ping import PingMessage
from transport.msg_types.unvet import UnvetMessage
from utils.bytes import bytes_to_hex_string
from web3 import Web3
from web3._utils.events import get_event_data
from web3.exceptions import BlockNotFound
from web3.types import EventData, FilterParams, LogReceipt

logger = logging.getLogger(__name__)

# event Message(
#     bytes32 indexed eventId,
#     address indexed sender,
#     bytes data
# ) anonymous;
MESSAGE_EVENT_ABI = {
    'anonymous': True,
    'inputs': [
        {'indexed': True, 'name': 'eventId', 'type': 'bytes32'},
        {'indexed': True, 'name': 'sender', 'type': 'address'},
        {'indexed': False, 'name': 'data', 'type': 'bytes'},
    ],
    'name': 'Message',
    'type': 'event',
}

UNVET_V1_DATA_SCHEMA = '(uint256,bytes32,uint256,uint256,bytes,bytes,(bytes32,bytes32),(bytes32))'
PING_V1_DATA_SCHEMA = '(uint256,(bytes32))'
DEPOSIT_V1_DATA_SCHEMA = '(uint256,bytes32,bytes32,uint256,uint256,(bytes32,bytes32),(bytes32))'
PAUSE_V2_DATA_SCHEMA = '(uint256,bytes32,(bytes32,bytes32),uint256,(bytes32))'
PAUSE_V3_DATA_SCHEMA = '(uint256,bytes32,(bytes32,bytes32),(bytes32))'


def signature_to_r_vs(signature: bytes) -> tuple[VRS, VRS]:
    r, s, v = signature[:32], signature[32:64], int.from_bytes(signature[64:])
    _vs = compute_vs(v, HexStr(bytes_to_hex_string(s)))
    return HexStr(bytes_to_hex_string(r)), HexStr(_vs)


class EventParser(abc.ABC):
    def __init__(self, w3: Web3, schema: str):
        self._w3 = w3
        self._schema = schema
        self._message_abi = w3.eth.contract(abi=[MESSAGE_EVENT_ABI]).events.Message().abi

    @abc.abstractmethod
    def _create_message(self, parsed_data: dict, guardian: str) -> dict:
        pass

    def _decode_event(self, log: LogReceipt) -> EventData:
        return get_event_data(self._w3.codec, self._message_abi, log)

    def parse(self, log: LogReceipt) -> Optional[dict]:
        e = self._decode_event(log)
        unparsed_event = e['args']['data']
        guardian = e['args']['sender']
        decoded_data = self._w3.codec.decode([self._schema], unparsed_event)[0]
        return self._create_message(decoded_data, guardian)


# event MessageDepositV1(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, bytes32 depositRoot,
# uint256 stakingModuleId, uint256 nonce, (bytes32 r, bytes32 vs) signature, (bytes32 version) app) data),
class DepositParser(EventParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, DEPOSIT_V1_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, block_hash, deposit_root, staking_module_id, nonce, (r, vs), app = parsed_data
        return DepositMessage(
            type=MessageType.DEPOSIT,
            depositRoot=bytes_to_hex_string(deposit_root),
            nonce=nonce,
            blockNumber=block_number,
            blockHash=bytes_to_hex_string(block_hash),
            guardianAddress=guardian,
            stakingModuleId=staking_module_id,
            signature={
                'r': r,
                '_vs': vs,
            },
        )


# event MessageUnvetV1(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, uint256 stakingModuleId, uint256 nonce,
# bytes operatorIds, bytes vettedKeysByOperator, (bytes32 r, bytes32 vs) signature, (bytes32 version) app) data)
class UnvetParser(EventParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, UNVET_V1_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, block_hash, staking_module_id, nonce, operator_ids, vetted_keys_by_operator, (r, vs), app = parsed_data
        return UnvetMessage(
            type=MessageType.UNVET,
            nonce=nonce,
            blockHash=bytes_to_hex_string(block_hash),
            guardianAddress=guardian,
            stakingModuleId=staking_module_id,
            signature={
                'r': r,
                '_vs': vs,
            },
            operatorIds=operator_ids,
            vettedKeysByOperator=vetted_keys_by_operator,
        )


# event MessagePingV1(address indexed guardianAddress, (uint256 blockNumber, (bytes32 version) app) data)",
class PingParser(EventParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, PING_V1_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, app = parsed_data
        return PingMessage(
            type=MessageType.PING,
            blockNumber=block_number,
            guardianAddress=guardian,
        )


# event MessagePauseV2(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, (bytes32 r, bytes32 vs) signature,
# uint256 stakingModuleId, (bytes32 version) app) data)
class PauseV2Parser(EventParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, PAUSE_V2_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, block_hash, (r, vs), staking_module_id, app = parsed_data
        return PauseMessage(
            type=MessageType.PAUSE,
            blockNumber=block_number,
            guardianAddress=guardian,
            stakingModuleId=staking_module_id,
            signature={
                'r': r,
                '_vs': vs,
            },
        )


# event MessagePauseV3(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, (bytes32 r, bytes32 vs) signature,
# (bytes32 version) app) data)
class PauseV3Parser(EventParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, PAUSE_V3_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, block_hash, (r, vs), app = parsed_data
        return PauseMessage(
            type=MessageType.PAUSE,
            blockNumber=block_number,
            guardianAddress=guardian,
            signature={
                'r': r,
                '_vs': vs,
            },
        )


class OnchainTransportSinks(StrEnum):
    DEPOSIT_V1 = f'MessageDepositV1(address,{DEPOSIT_V1_DATA_SCHEMA})'
    PAUSE_V2 = f'MessagePauseV2(address,{PAUSE_V2_DATA_SCHEMA})'
    PAUSE_V3 = f'MessagePauseV3(address,{PAUSE_V3_DATA_SCHEMA})'
    PING_V1 = f'MessagePingV1(address,{PING_V1_DATA_SCHEMA})'
    UNVET_V1 = f'MessageUnvetV1(address,{UNVET_V1_DATA_SCHEMA})'


class OnchainTransportProvider(BaseMessageProvider):
    STANDARD_OFFSET: int = 256

    def __init__(self, w3: Web3, onchain_address: ChecksumAddress, message_schema: Schema, sinks: list[OnchainTransportSinks]):
        super().__init__(message_schema)
        self._onchain_address = onchain_address
        if not sinks:
            raise ValueError('There must be at least a single sink for Data Bus provider')
        self._latest_block = -1

        logger.info('Data bus client initialized.')

        self._w3 = w3
        self._topics = [self._w3.keccak(text=sink) for sink in sinks]
        self._parsers: List[EventParser] = self._construct_parsers(sinks)

    def _construct_parsers(self, sinks: List[OnchainTransportSinks]) -> List[EventParser]:
        parser_mapping = {
            OnchainTransportSinks.DEPOSIT_V1: DepositParser,
            OnchainTransportSinks.PAUSE_V2: PauseV2Parser,
            OnchainTransportSinks.PAUSE_V3: PauseV3Parser,
            OnchainTransportSinks.PING_V1: PingParser,
            OnchainTransportSinks.UNVET_V1: UnvetParser,
        }

        parsers = []
        for sink in sinks:
            parser_class = parser_mapping.get(sink)
            if parser_class:
                parsers.append(parser_class(self._w3))
            else:
                raise ValueError(f'Invalid sink in Data Bus sinks: {sink}')

        return parsers

    def _fetch_messages(self) -> list:
        latest_block_number = self._w3.eth.block_number
        from_block = max(0, latest_block_number - self.STANDARD_OFFSET) if self._latest_block == -1 else self._latest_block
        # If block distance is 0, then skip fetching to avoid looping on a single block
        if from_block == latest_block_number:
            return []
        filter_params = FilterParams(
            fromBlock=from_block,
            toBlock=latest_block_number,
            address=self._onchain_address,
            topics=[self._topics],
        )
        try:
            logs = self._w3.eth.get_logs(filter_params)
            if logs:
                self._latest_block = latest_block_number
            return logs
        except BlockNotFound as e:
            logger.error(
                {
                    'msg': 'Block not found',
                    'err': repr(e),
                }
            )
            return []
        except Exception as e:
            logger.error(
                {
                    'msg': 'Failed to fetch logs',
                    'err': repr(e),
                }
            )
            return []

    def _process_msg(self, log: LogReceipt) -> Optional[dict]:
        for parser in self._parsers:
            try:
                return parser.parse(log)
            except Exception as error:
                logger.debug(
                    {
                        'msg': 'Data Bus parser failed to parse log',
                        'log': log,
                        'error': str(error),
                        'parser': type(parser).__name__,
                    }
                )
        return None
