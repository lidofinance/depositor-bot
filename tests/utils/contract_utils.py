import logging
from typing import Callable, Any, Optional

from blockchain.contracts.base_interface import ContractInterface


def check_contract(
    contract: ContractInterface,
    functions_spec: list[tuple[str, Optional[tuple], Callable[[Any], None]]],
    caplog,
):
    caplog.set_level(logging.INFO)

    for function in functions_spec:
        # get method
        method = contract.__getattribute__(function[0])
        # call method with args
        if function[1] is not None:
            response = method(*function[1])
        else:
            response = method()
        # check response
        function[2](response)

    assert len(functions_spec) == len(caplog.messages)
