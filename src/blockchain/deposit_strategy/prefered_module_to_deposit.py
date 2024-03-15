import logging
from typing import Optional

from blockchain.typings import Web3


logger = logging.getLogger(__name__)


def get_preferred_to_deposit_modules(w3: Web3, whitelist_modules: list[int]) -> list[int]:
    """
    Returns preferable module to deposit to make deposits balanced following the rules specified in Staking Router.
    Order is
    1. What module can accept bigger deposit? Checks available keys amount
    2. Check which module accepts more staking allocation
    """
    active_modules = get_active_modules(w3, whitelist_modules)
    modules = [module[1] for module in get_modules_stats(w3, active_modules)]
    logger.info({'msg': 'Calculate preferred modules.', 'value': modules})
    return modules


def get_active_modules(w3: Web3, whitelist_modules: list[int]) -> list[int]:
    # Get all module ids
    modules = w3.lido.staking_router.get_staking_module_ids()

    return [
        module for module in modules
        # Filter not-whitelisted modules
        if module in whitelist_modules and
        # Filter not-active modules
        w3.lido.staking_router.is_staking_module_active(module) and
        # Filter non-depositable module
        w3.lido.deposit_security_module.can_deposit(module)
    ]


def get_modules_stats(w3: Web3, modules: list[int]) -> list[tuple[int, int]]:
    depositable_ether = w3.lido.lido.get_depositable_ether()
    max_deposits = w3.lido.deposit_security_module.get_max_deposits()
    max_depositable_ether = min(max_deposits * 32 * 10**18, depositable_ether)

    module_stats = [(
            w3.lido.staking_router.get_staking_module_max_deposits_count(module, max_depositable_ether),
            module,
        ) for module in modules
    ]

    module_stats = sorted(module_stats, reverse=True)

    return module_stats
