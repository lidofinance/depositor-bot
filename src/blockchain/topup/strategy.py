import abc
import logging
from typing import Optional

import variables
from blockchain.deposit_strategy.gas_price_calculator import GasPriceCalculator
from blockchain.topup.types import TopUpProofData
from blockchain.typings import Web3
from providers.consensus import ConsensusClient
from providers.keys_api import KeysAPIClient
from web3.types import Wei

logger = logging.getLogger(__name__)


class TopUpStrategy(abc.ABC):
    def __init__(self, w3: Web3, gas_price_calculator: GasPriceCalculator):
        self.w3 = w3
        self._gas_price_calculator = gas_price_calculator

    def is_gas_price_ok(self) -> bool:
        current_gas_fee = self._gas_price_calculator.get_pending_base_fee()
        current_buffered_ether = self.w3.lido.lido.get_depositable_ether()
        recommended_gas_fee = self._gas_price_calculator.get_recommended_gas_fee()

        if current_buffered_ether > variables.MAX_BUFFERED_ETHERS:
            success = current_gas_fee <= variables.MAX_GAS_FEE
        else:
            success = recommended_gas_fee >= current_gas_fee

        logger.info(
            {
                'msg': 'Top-up gas price check.',
                'current_gas_fee': current_gas_fee,
                'recommended_gas_fee': recommended_gas_fee,
                'max_gas_fee': variables.MAX_GAS_FEE,
                'buffered_ether': current_buffered_ether,
                'success': success,
            }
        )
        return success

    @abc.abstractmethod
    def get_topup_candidates(
        self,
        keys_api: KeysAPIClient,
        cl: ConsensusClient,
        module_id: int,
        module_address: str,
        module_allocation: Wei,
        max_validators: int,
    ) -> Optional[TopUpProofData]:
        pass
