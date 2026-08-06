import logging
from typing import cast

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract.contract import Contract
from web3.module import Module
from web3.types import BlockIdentifier

import variables
from blockchain.contracts.delegation import DelegationContract
from blockchain.contracts.deposit import DepositContract
from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract, DepositSecurityModuleContractV5
from blockchain.contracts.guardian import GuardianContract
from blockchain.contracts.lido import LidoContract
from blockchain.contracts.lido_locator import LidoLocatorContract
from blockchain.contracts.staking_module import StakingModuleContract
from blockchain.contracts.staking_router import StakingRouterContractV4
from blockchain.contracts.topup_gateway import TopUpGatewayContract

logger = logging.getLogger(__name__)

# The Execution Delegation Framework (LIP-37) — guardians as delegation contracts with rotatable
# delegate EOAs — ships with DSM v5. From this version on, the delegate-resolution path is active
# (guardians are contracts), guardian signatures are ERC-1271 blobs bound to the guardian address,
# and the digest folds the guardian in; below it, guardians are plain EOAs (the legacy path).
GUARDIAN_DELEGATION_DSM_VERSION = 5

# DSM contract class per on-chain version. Adding a version here is what "supports" it.
DSM_CONTRACT_BY_VERSION: dict[int, type[DepositSecurityModuleContract]] = {
    4: DepositSecurityModuleContract,
    5: DepositSecurityModuleContractV5,
}

ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'


class LidoContracts(Module):
    def __init__(self, w3: Web3):
        super().__init__(w3)
        self._staking_module_cache: dict[int, StakingModuleContract] = {}
        self._guardian_cache: dict[ChecksumAddress, GuardianContract] = {}
        self._load_contracts()

    def has_contract_address_changed(self) -> bool:
        """If contracts changed all cache related to contracts should be cleared"""
        addresses = [contract.address for contract in self.__dict__.values() if isinstance(contract, Contract)]
        self._load_contracts()
        new_addresses = [contract.address for contract in self.__dict__.values() if isinstance(contract, Contract)]
        return addresses != new_addresses

    def _load_contracts(self):
        self.deposit_contract: DepositContract = cast(
            DepositContract,
            self.w3.eth.contract(
                address=variables.DEPOSIT_CONTRACT,
                ContractFactoryClass=DepositContract,
            ),
        )

        self.lido_locator: LidoLocatorContract = cast(
            LidoLocatorContract,
            self.w3.eth.contract(
                address=variables.LIDO_LOCATOR,
                ContractFactoryClass=LidoLocatorContract,
            ),
        )

        self.lido: LidoContract = cast(
            LidoContract,
            self.w3.eth.contract(
                address=self.lido_locator.lido(),
                ContractFactoryClass=LidoContract,
            ),
        )
        self._load_staking_router()
        self._load_dsm()
        self._load_topup_gateway()
        self._load_delegation()
        self._load_staking_modules()

    def _load_staking_router(self):
        self.staking_router = cast(
            StakingRouterContractV4,
            self.w3.eth.contract(
                address=self.lido_locator.staking_router(),
                ContractFactoryClass=StakingRouterContractV4,
                decode_tuples=True,
            ),
        )

    def _load_dsm(self):
        dsm_address = self.lido_locator.deposit_security_module()

        # Read the version off the base ABI (VERSION() is stable across versions), then bind the
        # version-specific contract class so deposit/pause/unvet encode the right signature shape.
        probe = cast(
            DepositSecurityModuleContract,
            self.w3.eth.contract(address=dsm_address, ContractFactoryClass=DepositSecurityModuleContract),
        )
        self.dsm_version = probe.version()
        contract_class = DSM_CONTRACT_BY_VERSION.get(self.dsm_version)
        if contract_class is None:
            raise ValueError(f'Unsupported DSM version: {self.dsm_version} (expected one of {sorted(DSM_CONTRACT_BY_VERSION)})')

        self.deposit_security_module = cast(
            DepositSecurityModuleContract,
            self.w3.eth.contract(address=dsm_address, ContractFactoryClass=contract_class),
        )
        self._guardian_cache.clear()

    def guardian_delegation_active(self) -> bool:
        """Whether the DSM uses the LIP-37 delegation model (guardians are contracts with delegates).

        Single source of truth for the version gate: drives delegate resolution, the guardian-bound
        signing digest, and the GuardianSignature submission shape.
        """
        return self.dsm_version >= GUARDIAN_DELEGATION_DSM_VERSION

    def _guardian_contract(self, address: ChecksumAddress) -> GuardianContract:
        """Returns a (cached) GuardianContract wrapper for a guardian delegation contract address.

        The wrapper only holds the address + ABI, so caching it is safe across delegate rotations —
        the mutable delegate is read fresh on every `get_delegate()` call.
        """
        contract = self._guardian_cache.get(address)
        if contract is None:
            contract = cast(
                GuardianContract,
                self.w3.eth.contract(address=address, ContractFactoryClass=GuardianContract),
            )
            self._guardian_cache[address] = contract
        return contract

    def get_guardian_delegates(self, block_identifier: BlockIdentifier = 'latest') -> dict[ChecksumAddress, ChecksumAddress]:
        """Resolves the current delegate EOA of every registered guardian.

        Returns a reverse map ``{delegate_EOA: guardian_contract}``. This is the mapping the Data Bus
        transport needs: council messages are posted by the delegate EOA (the event `sender`), which
        must be resolved back to its guardian contract, and the topic filter is built from the keys.

        Guardians whose delegate is the zero address (never assigned, revoked, or terminated) are
        omitted — they cannot produce a valid message, so their absence makes such messages fail
        closed. A delegate shared by two guardians (must not happen on-chain) is logged and the last
        guardian wins.

        Before DSM v5 (``GUARDIAN_DELEGATION_DSM_VERSION``) guardians are plain EOAs, so this returns
        the identity map ``{guardian: guardian}``: the reverse mapping becomes a no-op, the Data Bus
        filter keeps targeting guardian addresses, and — since the guardian is its own delegate —
        signature verification and quorum behave exactly as before. Crucially it never calls
        ``getDelegate()``, which would revert on an EOA. The switch is driven entirely by the on-chain
        DSM version, so it cannot desync from chain state the way an operator-set flag could.
        """
        guardians = [self.w3.to_checksum_address(g) for g in self.deposit_security_module.get_guardians(block_identifier)]
        if self.dsm_version < GUARDIAN_DELEGATION_DSM_VERSION:
            return {guardian: guardian for guardian in guardians}

        delegates: dict[ChecksumAddress, ChecksumAddress] = {}
        for guardian in guardians:
            guardian = self.w3.to_checksum_address(guardian)
            delegate = self._guardian_contract(guardian).get_delegate(block_identifier)
            if delegate == ZERO_ADDRESS:
                logger.debug({'msg': 'Guardian has no active delegate.', 'guardian': guardian})
                continue
            delegate = self.w3.to_checksum_address(delegate)
            if delegate in delegates and delegates[delegate] != guardian:
                logger.warning(
                    {
                        'msg': 'Delegate EOA is shared by multiple guardians.',
                        'delegate': delegate,
                        'guardians': [delegates[delegate], guardian],
                    }
                )
            delegates[delegate] = guardian
        return delegates

    def _load_staking_modules(self):
        """Pre-load StakingModuleContract instances for all whitelisted modules."""
        self._staking_module_cache.clear()
        digests = self.staking_router.get_all_staking_module_digests()
        for digest in digests:
            module_id = digest['module_id']
            if module_id not in variables.DEPOSIT_MODULES_WHITELIST:
                continue
            checksum = self.w3.to_checksum_address(digest['address'])
            self._staking_module_cache[module_id] = cast(
                StakingModuleContract,
                self.w3.eth.contract(address=checksum, ContractFactoryClass=StakingModuleContract),
            )
        logger.debug({'msg': 'Loaded staking modules for whitelist.', 'ids': list(self._staking_module_cache.keys())})

    def staking_module(self, module_id: int) -> StakingModuleContract:
        """Returns the cached StakingModuleContract for the given module id."""
        return self._staking_module_cache[module_id]

    def _load_topup_gateway(self):
        topup_gateway_address = self.lido_locator.top_up_gateway()
        self.topup_gateway = cast(
            TopUpGatewayContract,
            self.w3.eth.contract(
                address=topup_gateway_address,
                ContractFactoryClass=TopUpGatewayContract,
            ),
        )
        logger.debug({'msg': 'Loaded TopUpGateway.', 'address': topup_gateway_address})

    def _load_delegation(self):
        """Binds the EDF delegation contract top-ups are executed through, if one is configured.

        Comes from configuration rather than LidoLocator: the contract is deployed per bot operator
        (DelegationFactory), not part of the protocol's address book. `None` means direct calls —
        `TOP_UP_ROLE` is then expected on the bot's own account.
        """
        if variables.EDF_DELEGATION_CONTRACT is None:
            self.delegation: DelegationContract | None = None
            logger.debug({'msg': 'No EDF delegation contract configured. Top-ups will be sent as direct calls.'})
            return

        self.delegation = cast(
            DelegationContract,
            self.w3.eth.contract(
                address=variables.EDF_DELEGATION_CONTRACT,
                ContractFactoryClass=DelegationContract,
            ),
        )
        logger.debug({'msg': 'Loaded EDF delegation contract.', 'address': variables.EDF_DELEGATION_CONTRACT})
