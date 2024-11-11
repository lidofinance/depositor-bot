from datetime import datetime, timedelta
from typing import Callable

from web3 import Web3

_TIMEOUTS = {
    1: timedelta(minutes=10),
    2: timedelta(minutes=10),
}


class DepositModuleRecommender:
    def __init__(self, w3: Web3):
        self._w3 = w3
        self._module_timeouts = dict()

    def get_preferred_to_deposit_modules(self, whitelist_modules: list[int]) -> list[int]:
        module_ids = self._w3.lido.staking_router.get_staking_module_ids()
        modules = self._w3.lido.staking_router.get_staking_module_digests(module_ids)

        depositable_modules = list(filter(self._get_module_depositable_filter(whitelist_modules), modules))
        modules_ids = self.prioritize_modules(depositable_modules)
        return modules_ids

    def _get_module_depositable_filter(self, whitelist_modules: list[int]) -> Callable:
        def is_module_depositable(module: list) -> bool:
            module_id = module[2][0]

            if self._is_timeout_passed(module_id):
                self.reset_timeout(module_id)

            return (
                module_id not in self._module_timeouts
                and module_id in whitelist_modules
                and self._w3.lido.staking_router.is_staking_module_active(module_id)
                and self._w3.lido.deposit_security_module.can_deposit(module_id)
            )

        return is_module_depositable

    @staticmethod
    def prioritize_modules(modules: list) -> list[int]:
        modules = sorted(
            modules,
            #      totalDepositedValidators - totalExitedValidators
            key=lambda module: module[3][1] - module[3][0],
        )

        #       module_ids
        return [module[2][0] for module in modules]

    def set_timeout(self, module_id: int):
        self._module_timeouts[module_id] = datetime.now()

    def reset_timeout(self, module_id: int):
        return self._module_timeouts.pop(module_id, None)

    def _is_timeout_passed(self, module_id: int) -> bool:
        if module_id not in _TIMEOUTS or module_id not in self._module_timeouts:
            return True
        init = self._module_timeouts[module_id]
        now = datetime.now()
        return abs(now - init) >= _TIMEOUTS[module_id]
