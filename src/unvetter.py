import time

import variables
from blockchain.executor import Executor
from blockchain.typings import Web3
from bots.unvetter import UnvetterBot
from metrics.healthcheck_pulse import pulse
from metrics.logging import logging


logger = logging.getLogger(__name__)


def run_unvetter(w3: Web3):
    while w3.lido.deposit_security_module.__class__.__name__ != 'DepositSecurityModuleContractV2':
        logger.info({'msg': 'DepositSecurityModuleContractV2 deploy not found. Unvetter can\'t start.'})
        # time.sleep(12 * 32)
        time.sleep(1)
        pulse()
        w3.lido.has_contract_address_changed()

    unvetter = UnvetterBot(w3)
    e = Executor(
        w3,
        unvetter.execute,
        1,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute unvetter as daemon.'})
    e.execute_as_daemon()
