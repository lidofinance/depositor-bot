from eth_account import Account

import variables
from blockchain.executor import Executor
from blockchain.web3_extentions.bundle import activate_relay
from bots.depositor import DepositorBot
from metrics.logging import logging


logger = logging.getLogger(__name__)


def run_depositor(w3):
    if variables.AUCTION_BUNDLER_PRIVATE_KEY and variables.AUCTION_BUNDLER_URIS:
        logger.info({'msg': 'Add private relays.'})
        activate_relay(w3, Account.from_key(variables.AUCTION_BUNDLER_PRIVATE_KEY), variables.AUCTION_BUNDLER_URIS)
    else:
        logger.info({'msg': 'No flashbots available for this network.'})

    logger.info({'msg': 'Initialize Depositor bot.'})
    depositor_bot = DepositorBot(w3)

    e = Executor(
        w3,
        depositor_bot.execute,
        5,
        variables.MAX_CYCLE_LIFETIME_IN_SECONDS,
    )
    logger.info({'msg': 'Execute depositor as daemon.'})
    e.execute_as_daemon()
