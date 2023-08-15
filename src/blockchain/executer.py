import logging
from time import sleep
from typing import Callable, Any, Optional

from web3.types import BlockData
from web3_multi_provider import NoActiveProviderError

from blockchain.constants import SLOT_TIME
from blockchain.typings import Web3
from metrics import healthcheck_pulse
from utils.timeout import TimeoutManager, TimeoutManagerError


logger = logging.getLogger(__name__)


class Executor:
    """Executes periodically function with block_identifier."""
    def __init__(
        self,
        w3: Web3,
        function_to_execute: Callable[[BlockData], Any],
        blocks_between_execution: int,
        cycle_max_lifetime: int,
    ) -> None:
        """
        @param function_to_execute is functions that will be executed every N blocks
        @param blocks_between_execution is amount of EL blocks between function execution.
               Blocks could be missed, so waiting time could be higher than expected.
        """
        self.w3 = w3

        self.function_to_execute = function_to_execute
        self.blocks_between_execution = blocks_between_execution
        self.cycle_max_lifetime = cycle_max_lifetime

        self._latest_block_number = 0
        self._next_expected_block = 0

    def execute_as_daemon(self) -> None:
        """Run execution module """
        while True:
            self._wait_for_new_block_and_execute()

    def _wait_for_new_block_and_execute(self) -> Any:
        healthcheck_pulse.pulse()

        latest_block = self._exception_handler(self._wait_until_next_block)
        result = self._exception_handler(self._execute_function, latest_block)

        if result:
            self._next_expected_block += self.blocks_between_execution
        else:
            # If function do not return success code (True or whatever) retry function call with next block.
            self._next_expected_block += 1

        return result

    def _wait_until_next_block(self) -> BlockData:
        with TimeoutManager(max(
            # Wait at least 5 slots before throw exception
            5 * SLOT_TIME,
            self.blocks_between_execution * SLOT_TIME * 2
        )):
            while True:
                latest_block: BlockData = self.w3.eth.get_block('latest')
                logger.debug({'msg': 'Fetch latest block.', 'value': latest_block})

                if latest_block['number'] >= self._next_expected_block:
                    self._next_expected_block = latest_block['number']
                    return latest_block

                time_until_expected_block = (self._next_expected_block - latest_block.number - 1) * SLOT_TIME

                # If expected block is next
                if time_until_expected_block == 0:
                    time_until_expected_block = 5

                logger.debug({'msg': f'Sleep for {time_until_expected_block} seconds.'})
                sleep(time_until_expected_block)

    def _execute_function(self, block: BlockData) -> None:
        with TimeoutManager(self.cycle_max_lifetime):
            return self.function_to_execute(block)

    @staticmethod
    def _exception_handler(function: Callable, *args, **kwargs) -> Optional[Any]:
        try:
            return function(*args, **kwargs)
        except TimeoutManagerError as exception:
            logger.error({'msg': 'Timeout error.', 'error': str(exception), 'function': function.__name__})
            raise TimeoutManagerError('Bot stuck. Shut down.') from exception
        except NoActiveProviderError as exception:
            logger.error({'msg': 'No active node available. Shut down.', 'error': str(exception)})
            raise NoActiveProviderError from exception
        except Exception as error:
            logger.error({'msg': 'Unexpected error.', 'error': str(error), 'args': str(error.args)})
