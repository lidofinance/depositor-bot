"""Delegated execution wrapping, checked against the real ABIs (no RPC — encoding only)."""

import pytest
from web3 import Web3

from blockchain.contracts.delegation import DelegationContract
from blockchain.contracts.topup_gateway import TopUpGatewayContract
from blockchain.topup.types import TopUpProofData, ValidatorWitness

DELEGATION_ADDRESS = '0x1111111111111111111111111111111111111111'
GATEWAY_ADDRESS = '0x2222222222222222222222222222222222222222'


@pytest.fixture
def proof_data() -> TopUpProofData:
    return TopUpProofData(
        child_block_timestamp=1_700_000_000,
        slot=9_999,
        proposer_index=7,
        witnesses=[
            ValidatorWitness(
                proofs=[b'\x11' * 32, b'\x22' * 32],
                pubkey=b'\xab' * 48,
                effective_balance=32_000_000_000,
                activation_eligibility_epoch=1,
                activation_epoch=2,
                exit_epoch=2**64 - 1,
                withdrawable_epoch=2**64 - 1,
                slashed=False,
            )
        ],
        validator_indices=[42],
        key_indices=[3],
        operator_ids=[5],
        pending_balances_gwei=[0],
    )


@pytest.fixture
def contracts() -> tuple[DelegationContract, TopUpGatewayContract]:
    w3 = Web3()
    delegation = w3.eth.contract(address=DELEGATION_ADDRESS, ContractFactoryClass=DelegationContract)
    gateway = w3.eth.contract(address=GATEWAY_ADDRESS, ContractFactoryClass=TopUpGatewayContract)
    return delegation, gateway


@pytest.mark.unit
def test_wrap_targets_the_delegation_contract(contracts, proof_data):
    delegation, gateway = contracts

    wrapped = delegation.wrap(gateway.top_up(1, proof_data))

    assert wrapped.address == DELEGATION_ADDRESS
    assert wrapped.fn_name == 'execute'


@pytest.mark.unit
def test_wrap_preserves_the_original_target_and_calldata(contracts, proof_data):
    """execute(target, data) must carry the gateway address and the untouched topUp() calldata —
    otherwise the delegated call would hit the wrong contract or mangle the proof."""
    delegation, gateway = contracts
    original = gateway.top_up(1, proof_data)

    wrapped = delegation.wrap(original)

    target, calldata = wrapped.args
    assert target == GATEWAY_ADDRESS
    assert calldata == bytes.fromhex(gateway.encode_abi(original.fn_name, original.args)[2:])


@pytest.mark.unit
def test_wrapped_calldata_decodes_back_to_the_original_top_up_args(contracts, proof_data):
    """Round-trip through execute() to prove no argument is lost or re-ordered on the way in."""
    delegation, gateway = contracts
    module_id = 3
    original = gateway.top_up(module_id, proof_data)

    wrapped = delegation.wrap(original)
    _, inner_calldata = wrapped.args
    fn, args = gateway.decode_function_input(Web3.to_hex(inner_calldata))

    assert fn.fn_name == 'topUp'
    decoded = args['_topUps']
    assert decoded['moduleId'] == module_id
    assert decoded['keyIndices'] == proof_data.key_indices
    assert decoded['operatorIds'] == proof_data.operator_ids
    assert decoded['validatorIndices'] == proof_data.validator_indices
    assert decoded['beaconRootData'] == {
        'childBlockTimestamp': proof_data.child_block_timestamp,
        'slot': proof_data.slot,
        'proposerIndex': proof_data.proposer_index,
    }
    assert decoded['pendingBalanceGwei'] == proof_data.pending_balances_gwei
    assert decoded['validatorWitness'][0]['pubkey'] == proof_data.witnesses[0].pubkey
    assert decoded['validatorWitness'][0]['proofValidator'] == proof_data.witnesses[0].proofs
