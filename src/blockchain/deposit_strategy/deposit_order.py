from blockchain.contracts.staking_router import StakingModuleDigest
from blockchain.typings import Web3


def get_preferred_to_deposit_modules_ids(w3: Web3, whitelist_modules: list[int]) -> list[int]:
    """Filter non-whitelisted modules and sort them by active validators count."""
    module_ids = w3.lido.staking_router.get_staking_module_ids()

    modules_digests = w3.lido.staking_router.get_staking_module_digests(module_ids)

    active_modules = [module for module in modules_digests if module.state.id in whitelist_modules]

    return get_prioritized_module_ids(active_modules)


def get_prioritized_module_ids(modules: list[StakingModuleDigest]) -> list[int]:
    return [module.state.id for module in sorted(modules, key=get_module_weight)]


def get_module_weight(module: StakingModuleDigest):
    return module.summary.total_deposited_validators - module.summary.total_exited_validators
