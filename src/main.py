import sys
from enum import StrEnum
from typing import cast

import variables
import web3_multi_provider
from blockchain.typings import Web3
from blockchain.web3_extentions.lido_contracts import LidoContracts
from blockchain.web3_extentions.transaction import TransactionUtils
from bots.depositor import run_depositor
from bots.pauser import run_pauser
from bots.unvetter import run_unvetter
from metrics.healthcheck_pulse import start_pulse_server
from metrics.logging import logging
from prometheus_client import start_http_server
from providers.consensus import ConsensusClient
from providers.fallback_provider import FallbackProviderModule
from providers.keys_api import KeysAPIClient

logger = logging.getLogger(__name__)


class BotModule(StrEnum):
    DEPOSITOR = 'depositor'
    PAUSER = 'pauser'
    UNVETTER = 'unvetter'


def check_providers_chain_ids(w3: Web3, cl: ConsensusClient, keys_api: KeysAPIClient):
    execution_chain_id = cast(FallbackProviderModule, w3.provider).check_providers_consistency()
    consensus_chain_id = cl.check_providers_consistency()
    keys_api_chain_id = keys_api.check_providers_consistency()

    if execution_chain_id == consensus_chain_id == keys_api_chain_id:
        logger.info(
            {
                'msg': 'All providers chain ids match.',
                'chain_id': execution_chain_id,
            }
        )
        return

    raise ValueError(
        'Different chain ids detected:\n'
        f'Execution chain id: {execution_chain_id}\n'
        f'Consensus chain id: {consensus_chain_id}\n'
        f'Keys API chain id: {keys_api_chain_id}\n'
    )


def main(bot_name: str):
    logger.info({'msg': 'Bot env variables', 'value': variables.PUBLIC_ENV_VARS, 'bot_name': bot_name})
    if bot_name not in list(BotModule):
        msg = f'Last arg should be one of {[str(item) for item in BotModule]}, received {BotModule}.'
        logger.error({'msg': msg})
        raise ValueError(msg)

    logger.info({'msg': f'Start up healthcheck service on port: {variables.HEALTHCHECK_SERVER_PORT}.'})
    start_pulse_server()

    logger.info({'msg': f'Start up metrics service on port: {variables.PROMETHEUS_PORT}.'})
    start_http_server(variables.PROMETHEUS_PORT)

    logger.info({'msg': 'Connect MultiHTTPProviders.', 'rpc_count': len(variables.WEB3_RPC_ENDPOINTS)})
    w3 = Web3(FallbackProviderModule(variables.WEB3_RPC_ENDPOINTS, cache_allowed_requests=True))
    logger.info({'msg': 'Current chain_id', 'chain_id': w3.eth.chain_id})

    logger.info({'msg': 'Initialize Lido contracts.'})
    w3.attach_modules(
        {
            'lido': LidoContracts,
            'transaction': TransactionUtils,
        }
    )

    logger.info({'msg': 'Add metrics to web3 requests.'})
    web3_multi_provider.init_metrics()

    if bot_name == BotModule.DEPOSITOR:
        keys_api = KeysAPIClient(host=variables.KEYS_API_URL)
        cl = ConsensusClient(
            hosts=variables.CL_API_URLS,
            request_timeout=variables.HTTP_REQUEST_TIMEOUT_CONSENSUS,
            retry_total=variables.HTTP_REQUEST_RETRY_COUNT_CONSENSUS,
            retry_backoff_factor=variables.HTTP_REQUEST_SLEEP_BEFORE_RETRY_IN_SECONDS_CONSENSUS,
        )

        check_providers_chain_ids(w3, cl, keys_api)
        run_depositor(w3, keys_api, cl)
    elif bot_name == BotModule.PAUSER:
        run_pauser(w3)
    elif bot_name == BotModule.UNVETTER:
        run_unvetter(w3)


if __name__ == '__main__':
    main(sys.argv[-1])
