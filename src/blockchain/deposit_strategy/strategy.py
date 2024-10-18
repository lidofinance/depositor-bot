import abc


class DepositStrategy(abc.ABC):
    @abc.abstractmethod
    def can_deposit_keys_based_on_ether(self, module_id: int) -> bool:
        pass

    @abc.abstractmethod
    def is_gas_price_ok(self, module_id: int) -> bool:
        pass
