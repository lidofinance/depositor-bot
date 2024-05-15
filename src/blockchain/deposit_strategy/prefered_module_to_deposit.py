from typing import Callable

from blockchain.typings import Web3


def get_preferred_to_deposit_modules(w3: Web3, whitelist_modules: list[int]) -> list[int]:
	module_ids = w3.lido.staking_router.get_staking_module_ids()
	modules = w3.lido.staking_router.get_staking_module_digests(module_ids)

	modules = list(filter(get_module_depositable_filter(w3, whitelist_modules), modules))
	modules_ids = prioritize_modules(modules)
	return modules_ids


def prioritize_modules(modules: list) -> list[int]:
	modules = sorted(
		modules,
		#      totalDepositedValidators - totalExitedValidators
		key=lambda module: module[3][1] - module[3][0],
	)

	#       module_ids
	return [module[2][0] for module in modules]


def get_module_depositable_filter(w3: Web3, whitelist_modules: list[int]) -> Callable:
	def is_module_depositable(module: list) -> bool:
		module_id = module[2][0]

		return (
			module_id in whitelist_modules
			and w3.lido.staking_router.is_staking_module_active(module_id)
			and w3.lido.deposit_security_module.can_deposit(module_id)
		)

	return is_module_depositable
