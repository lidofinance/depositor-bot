import abc
import logging
from collections import deque
from enum import Enum
from typing import List, Optional

import variables
from eth_account.account import VRS
from eth_typing import HexStr
from schema import Schema
from transport.msg_providers.common import BaseMessageProvider
from transport.msg_providers.rabbit import MessageType
from transport.msg_types.deposit import DepositMessage
from transport.msg_types.pause import PauseMessage
from transport.msg_types.ping import PingMessageDataBus
from transport.msg_types.unvet import UnvetMessage
from utils.bytes import bytes_to_hex_string
from web3 import Web3
from web3._utils.events import get_event_data
from web3.exceptions import BlockNotFound
from web3.types import FilterParams, LogReceipt
from web3_multi_provider import FallbackProvider

logger = logging.getLogger(__name__)

_MESSAGE = {
    'anonymous': True,
    'inputs': [
        {'indexed': True, 'name': 'eventId', 'type': 'bytes32'},
        {'indexed': True, 'name': 'sender', 'type': 'address'},
        {'indexed': False, 'name': 'data', 'type': 'bytes'},
    ],
    'name': 'Message',
    'type': 'event',
}


def signature_to_r_vs(signature: bytes) -> tuple[VRS, VRS]:
    # 0 byte - 0x
    r = signature[1:33]
    _vs = signature[33:]
    return HexStr(bytes_to_hex_string(r)), HexStr(bytes_to_hex_string(_vs))


class LogParser(abc.ABC):
    def __init__(self, w3: Web3, schema: str):
        self._w3 = w3
        self._schema = schema
        self._message_abi = w3.eth.contract(abi=[_MESSAGE]).events.Message().abi

    @abc.abstractmethod
    def _create_message(self, parsed_data: dict, guardian: str) -> dict:
        pass

    def parse(self, log: LogReceipt) -> Optional[dict]:
        try:
            e = get_event_data(self._w3.codec, self._message_abi, log)
            unparsed_event = e['args']['data']
            guardian = e['args']['sender']
            decoded_data = self._w3.codec.decode([self._schema], unparsed_event)[0]
            return self._create_message(decoded_data, guardian)
        except Exception as error:
            logger.debug(
                {
                    'msg': 'Failed to parse log',
                    'log': log,
                    'error': str(error),
                    'parser': type(self).__name__,
                }
            )
            return None


# event MessageDepositV1(address indexed guardianAddress, (bytes32 depositRoot, uint256 nonce, uint256 blockNumber, bytes32 blockHash,
# bytes signature, uint256 stakingModuleId, (bytes32 version) app) data)",
class DepositParser(LogParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, '(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32))')

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        deposit_root, nonce, block_number, block_hash, signature, staking_module_id, app = parsed_data
        r, _vs = signature_to_r_vs(signature)
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
                '_vs': _vs,
            },
            app={'version': app[0]},
        )


# event MessageUnvetV1(address indexed guardianAddress, (uint256 nonce, uint256 blockNumber, bytes32 blockHash, uint256 stakingModuleId,
# bytes signature, bytes32 operatorIds, bytes32 vettedKeysByOperator, (bytes32 version) app) data)",


class UnvetParser(LogParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, '(uint256,uint256,bytes32,uint256,bytes,bytes32,bytes32,(bytes32))')

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        nonce, block_number, block_hash, staking_module_id, signature, operator_ids, vetted_keys_by_operator, app = parsed_data
        r, _vs = signature_to_r_vs(signature)
        return UnvetMessage(
            type=MessageType.UNVET,
            nonce=nonce,
            blockHash=bytes_to_hex_string(block_hash),
            guardianAddress=guardian,
            stakingModuleId=staking_module_id,
            signature={
                'r': r,
                '_vs': _vs,
            },
            operatorIds=operator_ids,
            vettedKeysByOperator=vetted_keys_by_operator,
        )


# event MessagePingV1(address indexed guardianAddress, (uint256 blockNumber, (bytes32 version) app) data)",


class PingParser(LogParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, '(uint256,(bytes32))')

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, app = parsed_data
        return PingMessageDataBus(
            type=MessageType.PING,
            blockNumber=block_number,
            guardianAddress=guardian,
        )


# event MessagePauseV2(address indexed guardianAddress, (bytes32 depositRoot, uint256 nonce, uint256 blockNumber, bytes32 blockHash,
# bytes signature, uint256 stakingModuleId, (bytes32 version) app) data)",


class PauseV2Parser(LogParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, '(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32))')

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        deposit_root, nonce, block_number, block_hash, signature, staking_module_id, app = parsed_data
        r, _vs = signature_to_r_vs(signature)
        return PauseMessage(
            type=MessageType.PAUSE,
            blockNumber=block_number,
            guardianAddress=guardian,
            stakingModuleId=staking_module_id,
            signature={
                'r': r,
                '_vs': _vs,
            },
        )


# event MessagePauseV3(address indexed guardianAddress, (uint256 blockNumber, bytes signature, (bytes32 version) app) data)",


class PauseV3Parser(LogParser):
    def __init__(self, w3: Web3):
        super().__init__(w3, '(uint256,bytes,(bytes32))')

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, signature, app = parsed_data
        r, _vs = signature_to_r_vs(signature)
        return PauseMessage(
            type=MessageType.PAUSE,
            blockNumber=block_number,
            guardianAddress=guardian,
            signature={
                'r': r,
                '_vs': _vs,
            },
        )


class DataBusSinks(str, Enum):
    DEPOSIT_V1 = 'MessageDepositV1(address,(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32)))'
    PAUSE_V2 = 'MessagePauseV2(address,(bytes32,uint256,uint256,bytes32,bytes,uint256,(bytes32)))'
    PAUSE_V3 = 'MessagePauseV3(address,(uint256,bytes,(bytes32)))'
    PING_V1 = 'MessagePingV1(address,(uint256,(bytes32)))'
    UNVET_V1 = 'MessageUnvetV1(address,(uint256,uint256,bytes32,uint256,bytes,bytes32,bytes32,(bytes32)))'


def _construct_parsers(w3: Web3, sinks: List[DataBusSinks]) -> List[LogParser]:
    parser_mapping = {
        DataBusSinks.DEPOSIT_V1: DepositParser,
        DataBusSinks.PAUSE_V2: PauseV2Parser,
        DataBusSinks.PAUSE_V3: PauseV3Parser,
        DataBusSinks.PING_V1: PingParser,
        DataBusSinks.UNVET_V1: UnvetParser,
    }

    parsers = []
    for sink in sinks:
        parser_class = parser_mapping.get(sink)
        if parser_class:
            parsers.append(parser_class(w3))
        else:
            raise ValueError(f'Invalid sink in Data Bus sinks: {sink}')

    return parsers


class DataBusProvider(BaseMessageProvider):
    def __init__(self, message_schema: Schema, sinks: [DataBusSinks]):
        super().__init__('', message_schema)
        if len(sinks) == 0:
            raise ValueError('There must be at least a single sink for Data Bus provider')

        if not sinks:
            raise ValueError('There must be at least one sink for Data Bus provider')

        self._STANDARD_OFFSET = 256
        self._latest_block = -1
        self._queue: deque = deque()

        logger.info('Data bus client initialized.')

        self._w3 = Web3(FallbackProvider(variables.WEB3_RPC_GNOSIS_ENDPOINTS))
        self._topics = [self._w3.keccak(text=sink) for sink in sinks]
        self._parsers: List[LogParser] = _construct_parsers(self._w3, sinks)

    def _receive_message(self) -> Optional[LogReceipt]:
        if not self._w3.is_connected():
            raise ConnectionError('Connection Data Bus was lost.')

        if not self._queue:
            self._fetch_logs_into_queue()
        try:
            return self._queue.pop()
        except IndexError:
            return None

    def _fetch_logs_into_queue(self):
        try:
            latest_block_number = self._w3.eth.block_number
            from_block = max(0, latest_block_number - self._STANDARD_OFFSET) if self._latest_block == -1 else self._latest_block

            filter_params = FilterParams(
                fromBlock=from_block,
                address=variables.DATA_BUS_ADDRESS,
                topics=[self._topics],
            )

            logs = self._w3.eth.get_logs(filter_params)
            if logs:
                self._queue.extend(logs)
                self._latest_block = latest_block_number

        except BlockNotFound as e:
            logger.error(
                {
                    'msg': 'Block not found',
                    'err': repr(e),
                }
            )
        except Exception as e:
            logger.error(
                {
                    'msg': 'Failed to fetch logs',
                    'err': repr(e),
                }
            )

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
