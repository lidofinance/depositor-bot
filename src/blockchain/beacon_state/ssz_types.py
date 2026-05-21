"""
SSZ type definitions for Ethereum Consensus Layer (Fulu fork).

Used for deserializing beacon state and building Merkle proofs.
Based on the Ethereum consensus-specs.
"""

from ssz.sedes.bitvector import Bitvector
from ssz.sedes.boolean import boolean
from ssz.sedes.byte_vector import ByteVector
from ssz.sedes.container import Container
from ssz.sedes.list import List as SSZList
from ssz.sedes.uint import (
    uint8,
    uint64,
    uint256,
)
from ssz.sedes.vector import Vector

# ============================================
# Constants (Mainnet)
# ============================================
VALIDATOR_REGISTRY_LIMIT = 2**40
SLOTS_PER_HISTORICAL_ROOT = 8192
EPOCHS_PER_HISTORICAL_VECTOR = 65536
EPOCHS_PER_SLASHINGS_VECTOR = 8192
HISTORICAL_ROOTS_LIMIT = 16777216
ETH1_DATA_VOTES_LIMIT = 2048
JUSTIFICATION_BITS_LENGTH = 4
SYNC_COMMITTEE_SIZE = 512
EPOCHS_PER_SYNC_COMMITTEE_PERIOD = 256
MIN_SEED_LOOKAHEAD = 1
SLOTS_PER_EPOCH = 32
PROPOSER_LOOKAHEAD_SIZE = (MIN_SEED_LOOKAHEAD + 1) * SLOTS_PER_EPOCH  # = 64

# Electra-specific limits
PENDING_DEPOSITS_LIMIT = 134217728
PENDING_PARTIAL_WITHDRAWALS_LIMIT = 134217728
PENDING_CONSOLIDATIONS_LIMIT = 262144

FAR_FUTURE_EPOCH = 2**64 - 1

# ============================================
# Byte vector types
# ============================================
bytes4 = ByteVector(4)
bytes20 = ByteVector(20)
bytes32 = ByteVector(32)
bytes48 = ByteVector(48)
bytes96 = ByteVector(96)

# ============================================
# SSZ Container types
# ============================================

Fork = Container(field_sedes=(bytes4, bytes4, uint64))

Checkpoint = Container(field_sedes=(uint64, bytes32))

Validator = Container(
    field_sedes=(
        bytes48,  # 0: pubkey
        bytes32,  # 1: withdrawal_credentials
        uint64,  # 2: effective_balance
        boolean,  # 3: slashed
        uint64,  # 4: activation_eligibility_epoch
        uint64,  # 5: activation_epoch
        uint64,  # 6: exit_epoch
        uint64,  # 7: withdrawable_epoch
    )
)

Eth1Data = Container(field_sedes=(bytes32, uint64, bytes32))

BeaconBlockHeader = Container(
    field_sedes=(
        uint64,  # 0: slot
        uint64,  # 1: proposer_index
        bytes32,  # 2: parent_root
        bytes32,  # 3: state_root
        bytes32,  # 4: body_root
    )
)

SyncCommittee = Container(
    field_sedes=(
        Vector(bytes48, SYNC_COMMITTEE_SIZE),  # 0: pubkeys
        bytes48,  # 1: aggregate_pubkey
    )
)

ExecutionPayloadHeader = Container(
    field_sedes=(
        bytes32,  # 0: parent_hash
        bytes20,  # 1: fee_recipient
        bytes32,  # 2: state_root
        bytes32,  # 3: receipts_root
        ByteVector(256),  # 4: logs_bloom
        bytes32,  # 5: prev_randao
        uint64,  # 6: block_number
        uint64,  # 7: gas_limit
        uint64,  # 8: gas_used
        uint64,  # 9: timestamp
        SSZList(uint8, 32),  # 10: extra_data
        uint256,  # 11: base_fee_per_gas
        bytes32,  # 12: block_hash
        bytes32,  # 13: transactions_root
        bytes32,  # 14: withdrawals_root
        uint64,  # 15: blob_gas_used
        uint64,  # 16: excess_blob_gas
    )
)

HistoricalSummary = Container(field_sedes=(bytes32, bytes32))

PendingDeposit = Container(
    field_sedes=(
        bytes48,  # 0: pubkey
        bytes32,  # 1: withdrawal_credentials
        uint64,  # 2: amount
        bytes96,  # 3: signature
        uint64,  # 4: slot
    )
)

PendingPartialWithdrawal = Container(field_sedes=(uint64, uint64, uint64))

PendingConsolidation = Container(field_sedes=(uint64, uint64))

# ============================================
# BeaconState (Fulu)
# ============================================
BeaconState = Container(
    field_sedes=(
        # Versioning [0-3]
        uint64,  # 0: genesis_time
        bytes32,  # 1: genesis_validators_root
        uint64,  # 2: slot
        Fork,  # 3: fork
        # History [4-7]
        BeaconBlockHeader,  # 4: latest_block_header
        Vector(bytes32, SLOTS_PER_HISTORICAL_ROOT),  # 5: block_roots
        Vector(bytes32, SLOTS_PER_HISTORICAL_ROOT),  # 6: state_roots
        SSZList(bytes32, HISTORICAL_ROOTS_LIMIT),  # 7: historical_roots
        # Eth1 [8-10]
        Eth1Data,  # 8: eth1_data
        SSZList(Eth1Data, ETH1_DATA_VOTES_LIMIT),  # 9: eth1_data_votes
        uint64,  # 10: eth1_deposit_index
        # Registry [11-12]
        SSZList(Validator, VALIDATOR_REGISTRY_LIMIT),  # 11: validators
        SSZList(uint64, VALIDATOR_REGISTRY_LIMIT),  # 12: balances
        # Randomness [13]
        Vector(bytes32, EPOCHS_PER_HISTORICAL_VECTOR),  # 13: randao_mixes
        # Slashings [14]
        Vector(uint64, EPOCHS_PER_SLASHINGS_VECTOR),  # 14: slashings
        # Participation [15-16]
        SSZList(uint8, VALIDATOR_REGISTRY_LIMIT),  # 15: previous_epoch_participation
        SSZList(uint8, VALIDATOR_REGISTRY_LIMIT),  # 16: current_epoch_participation
        # Finality [17-20]
        Bitvector(JUSTIFICATION_BITS_LENGTH),  # 17: justification_bits
        Checkpoint,  # 18: previous_justified_checkpoint
        Checkpoint,  # 19: current_justified_checkpoint
        Checkpoint,  # 20: finalized_checkpoint
        # Inactivity [21]
        SSZList(uint64, VALIDATOR_REGISTRY_LIMIT),  # 21: inactivity_scores
        # Sync committees [22-23]
        SyncCommittee,  # 22: current_sync_committee
        SyncCommittee,  # 23: next_sync_committee
        # Execution [24]
        ExecutionPayloadHeader,  # 24: latest_execution_payload_header
        # Withdrawals [25-26]
        uint64,  # 25: next_withdrawal_index
        uint64,  # 26: next_withdrawal_validator_index
        # Deep history [27]
        SSZList(HistoricalSummary, HISTORICAL_ROOTS_LIMIT),  # 27: historical_summaries
        # Electra [28-36]
        uint64,  # 28: deposit_requests_start_index
        uint64,  # 29: deposit_balance_to_consume
        uint64,  # 30: exit_balance_to_consume
        uint64,  # 31: earliest_exit_epoch
        uint64,  # 32: consolidation_balance_to_consume
        uint64,  # 33: earliest_consolidation_epoch
        SSZList(PendingDeposit, PENDING_DEPOSITS_LIMIT),  # 34: pending_deposits
        SSZList(PendingPartialWithdrawal, PENDING_PARTIAL_WITHDRAWALS_LIMIT),  # 35: pending_partial_withdrawals
        SSZList(PendingConsolidation, PENDING_CONSOLIDATIONS_LIMIT),  # 36: pending_consolidations
        # Fulu [37]
        Vector(uint64, PROPOSER_LOOKAHEAD_SIZE),  # 37: proposer_lookahead
    )
)

# ============================================
# Field indices
# ============================================

# BeaconState field indices
STATE_VALIDATORS = 11
STATE_BALANCES = 12
STATE_PENDING_DEPOSITS = 34
STATE_PENDING_CONSOLIDATIONS = 36

# Validator field indices
VALIDATOR_PUBKEY = 0
VALIDATOR_WITHDRAWAL_CREDENTIALS = 1
VALIDATOR_EFFECTIVE_BALANCE = 2
VALIDATOR_SLASHED = 3
VALIDATOR_ACTIVATION_ELIGIBILITY_EPOCH = 4
VALIDATOR_ACTIVATION_EPOCH = 5
VALIDATOR_EXIT_EPOCH = 6
VALIDATOR_WITHDRAWABLE_EPOCH = 7

# PendingDeposit field indices
PENDING_DEPOSIT_PUBKEY = 0
PENDING_DEPOSIT_AMOUNT = 2

# PendingConsolidation field indices
CONSOLIDATION_TARGET_INDEX = 1

# BeaconBlockHeader field indices
HEADER_SLOT = 0
HEADER_PROPOSER_INDEX = 1
HEADER_PARENT_ROOT = 2
HEADER_STATE_ROOT = 3
HEADER_BODY_ROOT = 4
