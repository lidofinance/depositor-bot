import abc
import logging
from typing import Callable, List, Optional

from eth_typing import ChecksumAddress
from eth_utils import to_bytes
from metrics.metrics import ONCHAIN_TRANSPORT_FETCHED_MESSAGES, ONCHAIN_TRANSPORT_PROCESSED_MESSAGES, ONCHAIN_TRANSPORT_VALID_MESSAGES
from prometheus_client import Gauge
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
EVENT_ABI = {
    'anonymous': True,
    'inputs': [
        {'indexed': True, 'name': 'eventId', 'type': 'bytes32'},
        {'indexed': True, 'name': 'sender', 'type': 'address'},
        {'indexed': False, 'name': 'data', 'type': 'bytes'},
    ],
    'name': 'Message',
    'type': 'event',
}


class EventParser(abc.ABC):
    """
    Abstract base class for parsing Ethereum event logs.

    This class provides a structure for decoding Ethereum logs and transforming the extracted
    data into a structured message using the Web3.py library. It abstracts the process of:

    - Decoding logs from blockchain events based on a predefined event ABI (Application Binary Interface).
    - Extracting relevant data from the decoded log.
    - Creating a structured message (usually a dictionary) from the parsed data.

    Attributes:
        _w3 (Web3): A Web3 instance for interacting with the Ethereum blockchain.
        _schema (str): A schema defining the structure for decoding the event data.
        _message_abi (dict): The ABI for the 'Message' event used to decode event logs.

    Methods:
        _create_message(parsed_data: dict, guardian: str) -> dict:
            Abstract method to be implemented by subclasses to create a structured message
            from the parsed event data.

        _decode_event(log: LogReceipt) -> EventData:
            Decodes the given log using the provided 'Message' event ABI and returns the decoded event data.

        parse(log: LogReceipt) -> Optional[dict]:
            Parses the given Ethereum log, decodes the 'Message' event data, and uses the subclass-specific
            message creation logic to return a structured message. If parsing fails, it returns None.

    Usage:
        Subclasses should implement the `_create_message` method, which transforms the parsed
        event data and sender (guardian) address into a meaningful structure, such as a dictionary.

    Example:
        class MyEventParser(EventParser):
            def _create_message(self, parsed_data, guardian):
                return {"guardian": guardian, "data": parsed_data}
    """

    def __init__(self, w3: Web3, schema: str):
        self._w3 = w3
        self._schema = schema
        self._message_abi: dict = w3.eth.contract(abi=[EVENT_ABI]).events.Message().abi

    @abc.abstractmethod
    def _create_message(self, parsed_data: dict, guardian: str) -> dict:
        pass

    @property
    @abc.abstractmethod
    def message_abi(self):
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
    DEPOSIT_V1_DATA_SCHEMA = '(uint256,bytes32,bytes32,uint256,uint256,(bytes32,bytes32),(bytes32))'
    message_abi = f'MessageDepositV1(address,{DEPOSIT_V1_DATA_SCHEMA})'

    def __init__(self, w3: Web3):
        super().__init__(w3, self.DEPOSIT_V1_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> DepositMessage:
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
                'r': bytes_to_hex_string(r),
                '_vs': bytes_to_hex_string(vs),
            },
        )


# event MessageUnvetV1(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, uint256 stakingModuleId, uint256 nonce,
# bytes operatorIds, bytes vettedKeysByOperator, (bytes32 r, bytes32 vs) signature, (bytes32 version) app) data)
class UnvetParser(EventParser):
    UNVET_V1_DATA_SCHEMA = '(uint256,bytes32,uint256,uint256,bytes,bytes,(bytes32,bytes32),(bytes32))'
    message_abi = f'MessageUnvetV1(address,{UNVET_V1_DATA_SCHEMA})'

    def __init__(self, w3: Web3):
        super().__init__(w3, self.UNVET_V1_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> UnvetMessage:
        block_number, block_hash, staking_module_id, nonce, operator_ids, vetted_keys_by_operator, (r, vs), app = parsed_data
        return UnvetMessage(
            type=MessageType.UNVET,
            nonce=nonce,
            blockHash=bytes_to_hex_string(block_hash),
            guardianAddress=guardian,
            stakingModuleId=staking_module_id,
            signature={
                'r': bytes_to_hex_string(r),
                '_vs': bytes_to_hex_string(vs),
            },
            operatorIds=operator_ids,
            vettedKeysByOperator=vetted_keys_by_operator,
        )


# event MessagePingV1(address indexed guardianAddress, (uint256 blockNumber, (bytes32 version) app) data)",
class PingParser(EventParser):
    PING_V1_DATA_SCHEMA = '(uint256,(bytes32))'
    message_abi = f'MessagePingV1(address,{PING_V1_DATA_SCHEMA})'

    def __init__(self, w3: Web3):
        super().__init__(w3, self.PING_V1_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> PingMessage:
        block_number, app = parsed_data
        return PingMessage(
            type=MessageType.PING,
            blockNumber=block_number,
            guardianAddress=guardian,
        )


# event MessagePauseV2(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, (bytes32 r, bytes32 vs) signature,
# uint256 stakingModuleId, (bytes32 version) app) data)
class PauseV2Parser(EventParser):
    PAUSE_V2_DATA_SCHEMA = '(uint256,bytes32,(bytes32,bytes32),uint256,(bytes32))'
    message_abi = f'MessagePauseV2(address,{PAUSE_V2_DATA_SCHEMA})'

    def __init__(self, w3: Web3):
        super().__init__(w3, self.PAUSE_V2_DATA_SCHEMA)

    def _create_message(self, parsed_data: tuple, guardian: str) -> dict:
        block_number, block_hash, (r, vs), staking_module_id, app = parsed_data
        return PauseMessage(
            type=MessageType.PAUSE,
            blockNumber=block_number,
            guardianAddress=guardian,
            stakingModuleId=staking_module_id,
            signature={
                'r': bytes_to_hex_string(r),
                '_vs': bytes_to_hex_string(vs),
            },
        )


# event MessagePauseV3(address indexed guardianAddress, (uint256 blockNumber, bytes32 blockHash, (bytes32 r, bytes32 vs) signature,
# (bytes32 version) app) data)
class PauseV3Parser(EventParser):
    PAUSE_V3_DATA_SCHEMA = '(uint256,bytes32,(bytes32,bytes32),(bytes32))'
    message_abi = f'MessagePauseV3(address,{PAUSE_V3_DATA_SCHEMA})'

    def __init__(self, w3: Web3):
        super().__init__(w3, self.PAUSE_V3_DATA_SCHEMA)

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


def _32padding_address(address: ChecksumAddress) -> bytes:
    address_bytes = to_bytes(hexstr=address)
    return address_bytes.rjust(32, b'\0')


class OnchainTransportProvider(BaseMessageProvider):
    STANDARD_OFFSET: int = 256

    def __init__(
        self,
        w3: Web3,
        onchain_address: ChecksumAddress,
        message_schema: Schema,
        parsers_providers: list[Callable[[Web3], EventParser]],
        allowed_guardians_provider: Callable[[], list[ChecksumAddress]],
    ):
        super().__init__(message_schema)
        self._onchain_address = onchain_address
        if not parsers_providers:
            raise ValueError('There must be at least a single parser for Data Bus provider')
        self._latest_block = -1

        logger.info('Data bus client initialized.')

        self._w3 = w3
        self._chain_id = self._w3.eth.chain_id
        self._allowed_guardians_provider = allowed_guardians_provider
        self._parsers: List[EventParser] = [provider(w3) for provider in parsers_providers]

    def _fetch_messages(self) -> list:
        latest_block_number = self._w3.eth.block_number
        from_block = max(0, latest_block_number - self.STANDARD_OFFSET) if self._latest_block == -1 else self._latest_block
        # If block distance is 0, then skip fetching to avoid looping on a single block
        if from_block == latest_block_number:
            return []
        event_ids = [self._w3.keccak(text=parser.message_abi) for parser in self._parsers]
        addresses_with_padding = [_32padding_address(address) for address in self._allowed_guardians_provider()]
        filter_params = FilterParams(
            fromBlock=from_block,
            toBlock=latest_block_number,
            address=self._onchain_address,
            topics=[event_ids, addresses_with_padding],
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

    @property
    def fetched_messages_metric(self) -> Gauge:
        return ONCHAIN_TRANSPORT_FETCHED_MESSAGES.labels(self._chain_id)

    @property
    def processed_messages_metric(self) -> Gauge:
        return ONCHAIN_TRANSPORT_PROCESSED_MESSAGES.labels(self._chain_id)

    @property
    def valid_messages_metric(self) -> Gauge:
        return ONCHAIN_TRANSPORT_VALID_MESSAGES.labels(self._chain_id)
