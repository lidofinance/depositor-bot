from abc import ABC, abstractmethod

from blockchain.typings import Web3


class ModuleDepositStrategyInterface(ABC):
	def __init__(self, w3: Web3, module_id: int):
		self.w3 = w3
		self.module_id = module_id

	@abstractmethod
	def is_gas_price_ok(self) -> bool:
		pass

	@abstractmethod
	def is_deposited_keys_amount_ok(self) -> bool:
		pass
