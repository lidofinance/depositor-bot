import abc


class DepositStrategy(abc.ABC):
    @abc.abstractmethod
    def calculate_deposit_recommendation(self, module_id: int) -> bool:
        pass

    @abc.abstractmethod
    def is_gas_price_ok(self, module_id: int) -> bool:
        pass
