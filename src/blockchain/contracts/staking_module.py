import logging
from functools import lru_cache

from blockchain.contracts.base_interface import ContractInterface

logger = logging.getLogger(__name__)


class StakingModuleContract(ContractInterface):
    abi_path = './interfaces/IStakingModule.json'

    @lru_cache(maxsize=1)
    def get_type(self) -> bytes:
        result = self.functions.getType().call()
        logger.info({'msg': 'Call `getType()`.', 'value': result, 'address': self.address})
        return result
