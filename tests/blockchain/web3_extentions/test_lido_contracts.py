from unittest.mock import Mock

import pytest
from web3 import Web3

from blockchain.contracts.deposit_security_module import DepositSecurityModuleContract, DepositSecurityModuleContractV5
from blockchain.web3_extentions.lido_contracts import (
    DSM_CONTRACT_BY_VERSION,
    GUARDIAN_DELEGATION_DSM_VERSION,
    ZERO_ADDRESS,
    LidoContracts,
)

# Distinct valid addresses used across the resolver tests.
_GUARDIAN_1 = Web3.to_checksum_address('0x1111111111111111111111111111111111111111')
_GUARDIAN_2 = Web3.to_checksum_address('0x2222222222222222222222222222222222222222')
_DELEGATE_1 = Web3.to_checksum_address('0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
_DELEGATE_2 = Web3.to_checksum_address('0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')


def _make_lido_contracts(
    guardians: list[str],
    delegate_of: dict[str, str],
    dsm_version: int = GUARDIAN_DELEGATION_DSM_VERSION,
) -> LidoContracts:
    """Build a LidoContracts without touching the chain: bypass __init__ and stub the two calls
    get_guardian_delegates depends on (getGuardians + each guardian's getDelegate). Defaults to the
    delegation-era DSM version so the resolver takes the getDelegate() path."""
    obj = LidoContracts.__new__(LidoContracts)
    obj.w3 = Web3()
    obj.dsm_version = dsm_version
    obj.deposit_security_module = Mock()
    obj.deposit_security_module.get_guardians = Mock(return_value=guardians)

    def guardian_contract(address):
        contract = Mock()
        contract.get_delegate = Mock(return_value=delegate_of[address])
        return contract

    obj._guardian_contract = Mock(side_effect=guardian_contract)
    return obj


@pytest.mark.unit
def test_get_guardian_delegates_reverse_maps():
    lido = _make_lido_contracts(
        guardians=[_GUARDIAN_1, _GUARDIAN_2],
        delegate_of={_GUARDIAN_1: _DELEGATE_1, _GUARDIAN_2: _DELEGATE_2},
    )
    assert lido.get_guardian_delegates() == {_DELEGATE_1: _GUARDIAN_1, _DELEGATE_2: _GUARDIAN_2}


@pytest.mark.unit
def test_get_guardian_delegates_skips_zero_delegate():
    # A guardian with no active delegate (revoked/terminated) must not appear — its messages fail closed.
    lido = _make_lido_contracts(
        guardians=[_GUARDIAN_1, _GUARDIAN_2],
        delegate_of={_GUARDIAN_1: _DELEGATE_1, _GUARDIAN_2: ZERO_ADDRESS},
    )
    assert lido.get_guardian_delegates() == {_DELEGATE_1: _GUARDIAN_1}


@pytest.mark.unit
def test_get_guardian_delegates_shared_delegate_last_wins():
    # Should not happen on-chain, but a delegate shared by two guardians must not silently duplicate.
    lido = _make_lido_contracts(
        guardians=[_GUARDIAN_1, _GUARDIAN_2],
        delegate_of={_GUARDIAN_1: _DELEGATE_1, _GUARDIAN_2: _DELEGATE_1},
    )
    assert lido.get_guardian_delegates() == {_DELEGATE_1: _GUARDIAN_2}


@pytest.mark.unit
def test_get_guardian_delegates_pre_v5_returns_identity_map():
    """On a pre-delegation DSM (guardians are EOAs) guardians map to themselves and getDelegate() is
    never called — safe on-chain state, and behaviourally identical to the old bot."""
    lido = _make_lido_contracts(
        guardians=[_GUARDIAN_1, _GUARDIAN_2],
        delegate_of={},  # unused — must not be read
        dsm_version=GUARDIAN_DELEGATION_DSM_VERSION - 1,
    )
    assert lido.get_guardian_delegates() == {_GUARDIAN_1: _GUARDIAN_1, _GUARDIAN_2: _GUARDIAN_2}
    lido._guardian_contract.assert_not_called()


@pytest.mark.unit
def test_guardian_delegation_active_gates_on_version():
    lido = _make_lido_contracts(guardians=[], delegate_of={}, dsm_version=GUARDIAN_DELEGATION_DSM_VERSION)
    assert lido.guardian_delegation_active()

    lido.dsm_version = GUARDIAN_DELEGATION_DSM_VERSION - 1
    assert not lido.guardian_delegation_active()


@pytest.mark.unit
def test_dsm_contract_class_by_version():
    # v5 selects the delegation-aware contract class; v4 the legacy one.
    assert DSM_CONTRACT_BY_VERSION[5] is DepositSecurityModuleContractV5
    assert DSM_CONTRACT_BY_VERSION[4] is DepositSecurityModuleContract
