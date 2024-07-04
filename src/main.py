import sys
from enum import StrEnum

import variables
from blockchain.typings import Web3
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.requests_metric_middleware import add_requests_metric_middleware
from blockchain.web3_extentions.transaction import TransactionUtils
from bots.depositor import run_depositor
from bots.pauser import run_pauser
from bots.unvetter import run_unvetter
from metrics.healthcheck_pulse import start_pulse_server
from metrics.logging import logging
from metrics.metrics import BUILD_INFO
from prometheus_client import start_http_server
from web3_multi_provider import FallbackProvider

logger = logging.getLogger(__name__)


class BotModule(StrEnum):
    DEPOSITOR = 'depositor'
    PAUSER = 'pauser'
    UNVETTER = 'unvetter'


def main(bot_name: str):
    logger.info(
        {
            'msg': 'Bot env variables',
            'value': variables.PUBLIC_ENV_VARS,
            'bot_name': bot_name
        }
    )
    if bot_name not in list(BotModule):
        msg = f'Last arg should be one of {[str(item) for item in BotModule]}, received {BotModule}.'
        logger.error({'msg': msg})
        raise ValueError(msg)

    logger.info({'msg': f'Start up healthcheck service on port: {variables.HEALTHCHECK_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    # Send vars to metrics
    BUILD_INFO.labels(
        'Depositor bot',
        variables.MAX_GAS_FEE,
        variables.MAX_BUFFERED_ETHERS,
        variables.CONTRACT_GAS_LIMIT,
        variables.GAS_FEE_PERCENTILE_1,
        variables.GAS_FEE_PERCENTILE_DAYS_HISTORY_1,
        variables.GAS_PRIORITY_FEE_PERCENTILE,
        variables.MIN_PRIORITY_FEE,
        variables.MAX_PRIORITY_FEE,
        variables.ACCOUNT.address if variables.ACCOUNT else '0x0',
        variables.CREATE_TRANSACTIONS,
        variables.DEPOSIT_MODULES_WHITELIST,
    )

    logger.info({'msg': 'Connect MultiHTTPProviders.', 'rpc_count': len(variables.WEB3_RPC_ENDPOINTS)})
    w3 = Web3(FallbackProvider(variables.WEB3_RPC_ENDPOINTS))
    logger.info({'msg': 'Current chain_id', 'chain_id': w3.eth.chain_id})

    logger.info({'msg': 'Initialize Lido contracts.'})
    w3.attach_modules(
        {
            'lido': LidoContracts,
            'transaction': TransactionUtils,
        }
    )

    logger.info({'msg': 'Add metrics to web3 requests.'})
    add_requests_metric_middleware(w3)

    if bot_name == BotModule.DEPOSITOR:
        run_depositor(w3)
    elif bot_name == BotModule.PAUSER:
        run_pauser(w3)
    elif bot_name == BotModule.UNVETTER:
        run_unvetter(w3)


if __name__ == '__main__':
    main(sys.argv[-1])
