from lru import LRU
from collections import defaultdict
from dataclasses import (
    dataclass,
    field,
)
from hashlib import sha256 as sha256_hash
from typing import (
    Any, Callable, Dict, DefaultDict, Set, Sequence, Tuple, Optional, TypeAlias, TypeVar, NamedTuple, Final
)

from ssz.bitfields import BitList, BitVector
from ssz.boolean import Boolean
from ssz.collections import List, ProgressiveList, Vector
from ssz.container import Container
from ssz.ssz_base import SSZType
from ssz.uint import BaseUint as Uint, Byte, Uint8, Uint16, Uint32, Uint64, Uint256
from eth_consensus_specs.utils.ssz.bytes import (
    Bytes1, Bytes4, Bytes20, Bytes32, Bytes48, Bytes96)
from eth_consensus_specs.utils.ssz.ssz_impl import ssz_deserialize, ssz_serialize
from eth_consensus_specs.utils import bls


SSZObject = TypeVar('SSZObject', bound=SSZType)


fork = 'phase0'


def ceillog2(x: int) -> Uint64:
    if x < 1:
        raise ValueError(f"ceillog2 accepts only positive values, x={x}")
    return Uint64((x - 1).bit_length())


def floorlog2(x: int) -> Uint64:
    if x < 1:
        raise ValueError(f"floorlog2 accepts only positive values, x={x}")
    return Uint64(x.bit_length() - 1)


class Domain(Bytes32):
    pass


class DomainType(Bytes4):
    pass


class Epoch(Uint64):
    pass


class Gwei(Uint64):
    pass


class Slot(Uint64):
    pass


class Version(Bytes4):
    pass


class ExecutionAddress(Bytes20):
    pass


# Constant vars
UINT64_MAX = Uint64(2**64 - 1)
UINT64_MAX_SQRT = Uint64(4294967295)
GENESIS_SLOT = Slot(0)
GENESIS_EPOCH = Epoch(0)
FAR_FUTURE_EPOCH = Epoch(2**64 - 1)
BASE_REWARDS_PER_EPOCH = Uint64(4)
JUSTIFICATION_BITS_LENGTH = Uint64(4)
ENDIANNESS: Final = 'little'
BLS_WITHDRAWAL_PREFIX = Bytes1('0x00')
ETH1_ADDRESS_WITHDRAWAL_PREFIX = Bytes1('0x01')
DOMAIN_BEACON_PROPOSER = DomainType('0x00000000')
DOMAIN_BEACON_ATTESTER = DomainType('0x01000000')
DOMAIN_RANDAO = DomainType('0x02000000')
DOMAIN_DEPOSIT = DomainType('0x03000000')
DOMAIN_VOLUNTARY_EXIT = DomainType('0x04000000')
DOMAIN_SELECTION_PROOF = DomainType('0x05000000')
DOMAIN_AGGREGATE_AND_PROOF = DomainType('0x06000000')
DOMAIN_APPLICATION_MASK = DomainType('0x00000001')
DEPOSIT_CONTRACT_TREE_DEPTH = Uint64(2**5)
COMMITTEE_WEIGHT_ESTIMATION_ADJUSTMENT_FACTOR = Uint64(5)
BASIS_POINTS = Uint64(10000)
NODE_ID_BITS = Uint64(256)
MAX_CONCURRENT_REQUESTS = Uint64(2)
TARGET_AGGREGATORS_PER_COMMITTEE = Uint64(2**4)
ETH_TO_GWEI = Uint64(10**9)
SAFETY_DECAY = Uint64(10)


# Preset vars
MAX_COMMITTEES_PER_SLOT = Uint64(64)
TARGET_COMMITTEE_SIZE = Uint64(128)
MAX_VALIDATORS_PER_COMMITTEE = Uint64(2048)
SHUFFLE_ROUND_COUNT = Uint64(90)
HYSTERESIS_QUOTIENT = Uint64(4)
HYSTERESIS_DOWNWARD_MULTIPLIER = Uint64(1)
HYSTERESIS_UPWARD_MULTIPLIER = Uint64(5)
MIN_DEPOSIT_AMOUNT = Gwei(1000000000)
MAX_EFFECTIVE_BALANCE = Gwei(32000000000)
EFFECTIVE_BALANCE_INCREMENT = Gwei(1000000000)
MIN_ATTESTATION_INCLUSION_DELAY = Slot(1)
SLOTS_PER_EPOCH = Slot(32)
MIN_SEED_LOOKAHEAD = Epoch(1)
MAX_SEED_LOOKAHEAD = Epoch(4)
MIN_EPOCHS_TO_INACTIVITY_PENALTY = Epoch(4)
EPOCHS_PER_ETH1_VOTING_PERIOD = Epoch(64)
SLOTS_PER_HISTORICAL_ROOT = Slot(8192)
EPOCHS_PER_HISTORICAL_VECTOR = Epoch(65536)
EPOCHS_PER_SLASHINGS_VECTOR = Epoch(8192)
HISTORICAL_ROOTS_LIMIT = Uint64(16777216)
VALIDATOR_REGISTRY_LIMIT = Uint64(1099511627776)
BASE_REWARD_FACTOR = Uint64(64)
WHISTLEBLOWER_REWARD_QUOTIENT = Uint64(512)
PROPOSER_REWARD_QUOTIENT = Uint64(8)
INACTIVITY_PENALTY_QUOTIENT = Uint64(67108864)
MIN_SLASHING_PENALTY_QUOTIENT = Uint64(128)
PROPORTIONAL_SLASHING_MULTIPLIER = Uint64(1)
MAX_PROPOSER_SLASHINGS = Uint64(16)
MAX_ATTESTER_SLASHINGS = Uint64(2)
MAX_ATTESTATIONS = Uint64(128)
MAX_DEPOSITS = Uint64(16)
MAX_VOLUNTARY_EXITS = Uint64(16)


# Preset computed constants


class Configuration(NamedTuple):
    PRESET_BASE: str
    MIN_GENESIS_ACTIVE_VALIDATOR_COUNT: Uint64
    MIN_GENESIS_TIME: Uint64
    GENESIS_FORK_VERSION: Version
    GENESIS_DELAY: Uint64
    SLOT_DURATION_MS: Uint64
    SECONDS_PER_ETH1_BLOCK: Uint64
    MIN_VALIDATOR_WITHDRAWABILITY_DELAY: Epoch
    SHARD_COMMITTEE_PERIOD: Epoch
    ETH1_FOLLOW_DISTANCE: Uint64
    EJECTION_BALANCE: Gwei
    MIN_PER_EPOCH_CHURN_LIMIT: Uint64
    CHURN_LIMIT_QUOTIENT: Uint64
    DEPOSIT_CHAIN_ID: Uint64
    DEPOSIT_NETWORK_ID: Uint64
    DEPOSIT_CONTRACT_ADDRESS: ExecutionAddress
    CONFIRMATION_BYZANTINE_THRESHOLD: Uint64
    PROPOSER_SCORE_BOOST: Uint64
    REORG_HEAD_WEIGHT_THRESHOLD: Uint64
    REORG_PARENT_WEIGHT_THRESHOLD: Uint64
    REORG_MAX_EPOCHS_SINCE_FINALIZATION: Epoch
    PROPOSER_REORG_CUTOFF_BPS: Uint64
    MAX_PAYLOAD_SIZE: Uint64
    MAX_REQUEST_BLOCKS: Uint64
    EPOCHS_PER_SUBNET_SUBSCRIPTION: Epoch
    ATTESTATION_PROPAGATION_SLOT_RANGE: Slot
    MAXIMUM_GOSSIP_CLOCK_DISPARITY: Uint64
    MESSAGE_DOMAIN_INVALID_SNAPPY: DomainType
    MESSAGE_DOMAIN_VALID_SNAPPY: DomainType
    SUBNETS_PER_NODE: Uint64
    ATTESTATION_SUBNET_COUNT: Uint64
    ATTESTATION_SUBNET_EXTRA_BITS: Uint64
    ATTESTATION_DUE_BPS: Uint64
    AGGREGATE_DUE_BPS: Uint64


config = Configuration(
    PRESET_BASE="mainnet",
    MIN_GENESIS_ACTIVE_VALIDATOR_COUNT=Uint64(16384),
    MIN_GENESIS_TIME=Uint64(1606824000),
    GENESIS_FORK_VERSION=Version('0x00000000'),
    GENESIS_DELAY=Uint64(604800),
    SLOT_DURATION_MS=Uint64(12000),
    SECONDS_PER_ETH1_BLOCK=Uint64(14),
    MIN_VALIDATOR_WITHDRAWABILITY_DELAY=Epoch(256),
    SHARD_COMMITTEE_PERIOD=Epoch(256),
    ETH1_FOLLOW_DISTANCE=Uint64(2048),
    EJECTION_BALANCE=Gwei(16000000000),
    MIN_PER_EPOCH_CHURN_LIMIT=Uint64(4),
    CHURN_LIMIT_QUOTIENT=Uint64(65536),
    DEPOSIT_CHAIN_ID=Uint64(1),
    DEPOSIT_NETWORK_ID=Uint64(1),
    DEPOSIT_CONTRACT_ADDRESS=ExecutionAddress('0x00000000219ab540356cBB839Cbe05303d7705Fa'),
    CONFIRMATION_BYZANTINE_THRESHOLD=Uint64(25),
    PROPOSER_SCORE_BOOST=Uint64(40),
    REORG_HEAD_WEIGHT_THRESHOLD=Uint64(20),
    REORG_PARENT_WEIGHT_THRESHOLD=Uint64(160),
    REORG_MAX_EPOCHS_SINCE_FINALIZATION=Epoch(2),
    PROPOSER_REORG_CUTOFF_BPS=Uint64(1667),
    MAX_PAYLOAD_SIZE=Uint64(10485760),
    MAX_REQUEST_BLOCKS=Uint64(1024),
    EPOCHS_PER_SUBNET_SUBSCRIPTION=Epoch(256),
    ATTESTATION_PROPAGATION_SLOT_RANGE=Slot(32),
    MAXIMUM_GOSSIP_CLOCK_DISPARITY=Uint64(500),
    MESSAGE_DOMAIN_INVALID_SNAPPY=DomainType('0x00000000'),
    MESSAGE_DOMAIN_VALID_SNAPPY=DomainType('0x01000000'),
    SUBNETS_PER_NODE=Uint64(2),
    ATTESTATION_SUBNET_COUNT=Uint64(64),
    ATTESTATION_SUBNET_EXTRA_BITS=Uint64(0),
    ATTESTATION_DUE_BPS=Uint64(3333),
    AGGREGATE_DUE_BPS=Uint64(6667),
)


class GossipIgnore(Exception):
    pass


class GossipReject(Exception):
    pass


class AggregationBits(BitList):
    """
    The participation bits of a single committee, one bit per member in
    committee order.
    """

    LIMIT = MAX_VALIDATORS_PER_COMMITTEE


class Balances(List[Gwei]):
    """
    The balances of all validators.
    """

    LIMIT = VALIDATOR_REGISTRY_LIMIT


class DepositProof(Vector[Bytes32]):
    """
    A Merkle proof of a deposit in the deposit contract's tree. The node
    beyond the tree depth accounts for the deposit count mix-in.
    """

    LENGTH = DEPOSIT_CONTRACT_TREE_DEPTH + 1


class JustificationBits(BitVector):
    """
    The justification status of the last ``JUSTIFICATION_BITS_LENGTH`` epochs.
    """

    LENGTH = JUSTIFICATION_BITS_LENGTH


class RandaoMixes(Vector[Bytes32]):
    """
    A rolling window of accumulated RANDAO mixes, indexed by epoch modulo
    ``EPOCHS_PER_HISTORICAL_VECTOR``.
    """

    LENGTH = EPOCHS_PER_HISTORICAL_VECTOR


class Slashings(Vector[Gwei]):
    """
    Per-epoch sums of slashed effective balances, indexed by epoch modulo
    ``EPOCHS_PER_SLASHINGS_VECTOR``.
    """

    LENGTH = EPOCHS_PER_SLASHINGS_VECTOR


class Fork(Container):
    previous_version: Version
    current_version: Version
    epoch: Epoch


class Attnets(BitVector):
    """
    The attestation subnets a node is subscribed to, one bit per subnet.
    """

    LENGTH = config.ATTESTATION_SUBNET_COUNT


class ErrorMessage(List[Byte]):
    """
    The error message of an unsuccessful response chunk.
    """

    LIMIT = 256


class BLSPubkey(Bytes48):
    pass


class DepositMessage(Container):
    pubkey: BLSPubkey
    withdrawal_credentials: Bytes32
    amount: Gwei


class Validator(Container):
    pubkey: BLSPubkey
    withdrawal_credentials: Bytes32
    effective_balance: Gwei
    slashed: Boolean
    activation_eligibility_epoch: Epoch
    activation_epoch: Epoch
    exit_epoch: Epoch
    withdrawable_epoch: Epoch


class Validators(List[Validator]):
    """
    The validator registry.
    """

    LIMIT = VALIDATOR_REGISTRY_LIMIT


class BLSSignature(Bytes96):
    pass


class DepositData(Container):
    pubkey: BLSPubkey
    withdrawal_credentials: Bytes32
    amount: Gwei
    signature: BLSSignature


class DepositDataList(List[DepositData]):
    """
    The ``DepositData`` of deposits made to the deposit contract.
    """

    LIMIT = 2**DEPOSIT_CONTRACT_TREE_DEPTH


class Deposit(Container):
    proof: DepositProof
    data: DepositData


class Deposits(List[Deposit]):
    """
    The deposits included in a beacon block.
    """

    LIMIT = MAX_DEPOSITS


class CommitteeIndex(Uint64):
    pass


class ForkDigest(Bytes4):
    pass


class Hash32(Bytes32):
    pass


class Root(Bytes32):
    pass


class Eth1Block(Container):
    timestamp: Uint64
    deposit_root: Root
    deposit_count: Uint64


class BeaconBlockRoots(List[Root]):
    """
    Beacon block roots requested in a ``BeaconBlocksByRoot`` request.
    """

    LIMIT = config.MAX_REQUEST_BLOCKS


class SigningData(Container):
    object_root: Root
    domain: Domain


class Eth1Data(Container):
    deposit_root: Root
    deposit_count: Uint64
    block_hash: Hash32


class Eth1DataVotes(List[Eth1Data]):
    """
    The ``Eth1Data`` votes of the current voting period.
    """

    LIMIT = Uint64(EPOCHS_PER_ETH1_VOTING_PERIOD) * Uint64(SLOTS_PER_EPOCH)


class Checkpoint(Container):
    epoch: Epoch
    root: Root


class AttestationData(Container):
    slot: Slot
    index: CommitteeIndex
    beacon_block_root: Root
    source: Checkpoint
    target: Checkpoint


class Attestation(Container):
    aggregation_bits: AggregationBits
    data: AttestationData
    signature: BLSSignature


class Attestations(List[Attestation]):
    """
    The attestations included in a beacon block.
    """

    LIMIT = MAX_ATTESTATIONS


class ForkData(Container):
    current_version: Version
    genesis_validators_root: Root


class StateRoots(Vector[Root]):
    """
    A rolling window of recent state roots, indexed by slot modulo
    ``SLOTS_PER_HISTORICAL_ROOT``.
    """

    LENGTH = SLOTS_PER_HISTORICAL_ROOT


class HistoricalRoots(List[Root]):
    """
    The roots of ``HistoricalBatch`` objects.
    """

    LIMIT = HISTORICAL_ROOTS_LIMIT


class BlockRoots(Vector[Root]):
    """
    A rolling window of recent block roots, indexed by slot modulo
    ``SLOTS_PER_HISTORICAL_ROOT``.
    """

    LENGTH = SLOTS_PER_HISTORICAL_ROOT


class HistoricalBatch(Container):
    block_roots: BlockRoots
    state_roots: StateRoots


class ValidatorIndex(Uint64):
    pass


class AggregateAndProof(Container):
    aggregator_index: ValidatorIndex
    aggregate: Attestation
    selection_proof: BLSSignature


class SignedAggregateAndProof(Container):
    message: AggregateAndProof
    signature: BLSSignature


class VoluntaryExit(Container):
    epoch: Epoch
    validator_index: ValidatorIndex


class SignedVoluntaryExit(Container):
    message: VoluntaryExit
    signature: BLSSignature


class VoluntaryExits(List[SignedVoluntaryExit]):
    """
    The signed voluntary exits included in a beacon block.
    """

    LIMIT = MAX_VOLUNTARY_EXITS


class BeaconBlockHeader(Container):
    slot: Slot
    proposer_index: ValidatorIndex
    parent_root: Root
    state_root: Root
    body_root: Root


class SignedBeaconBlockHeader(Container):
    message: BeaconBlockHeader
    signature: BLSSignature


class ProposerSlashing(Container):
    signed_header_1: SignedBeaconBlockHeader
    signed_header_2: SignedBeaconBlockHeader


class ProposerSlashings(List[ProposerSlashing]):
    """
    The proposer slashings included in a beacon block.
    """

    LIMIT = MAX_PROPOSER_SLASHINGS


class PendingAttestation(Container):
    aggregation_bits: AggregationBits
    data: AttestationData
    inclusion_delay: Slot
    proposer_index: ValidatorIndex


class PendingAttestations(List[PendingAttestation]):
    """
    The attestations included in blocks during an epoch.
    """

    LIMIT = MAX_ATTESTATIONS * SLOTS_PER_EPOCH


class BeaconState(Container):
    genesis_time: Uint64
    genesis_validators_root: Root
    slot: Slot
    fork: Fork
    latest_block_header: BeaconBlockHeader
    block_roots: BlockRoots
    state_roots: StateRoots
    historical_roots: HistoricalRoots
    eth1_data: Eth1Data
    eth1_data_votes: Eth1DataVotes
    eth1_deposit_index: Uint64
    validators: Validators
    balances: Balances
    randao_mixes: RandaoMixes
    slashings: Slashings
    previous_epoch_attestations: PendingAttestations
    current_epoch_attestations: PendingAttestations
    justification_bits: JustificationBits
    previous_justified_checkpoint: Checkpoint
    current_justified_checkpoint: Checkpoint
    finalized_checkpoint: Checkpoint


class AttestingIndices(List[ValidatorIndex]):
    """
    The indices of the validators participating in an attestation.
    """

    LIMIT = MAX_VALIDATORS_PER_COMMITTEE


class IndexedAttestation(Container):
    attesting_indices: AttestingIndices
    data: AttestationData
    signature: BLSSignature


class AttesterSlashing(Container):
    attestation_1: IndexedAttestation
    attestation_2: IndexedAttestation


class AttesterSlashings(List[AttesterSlashing]):
    """
    The attester slashings included in a beacon block.
    """

    LIMIT = MAX_ATTESTER_SLASHINGS


class BeaconBlockBody(Container):
    randao_reveal: BLSSignature
    eth1_data: Eth1Data
    graffiti: Bytes32
    proposer_slashings: ProposerSlashings
    attester_slashings: AttesterSlashings
    attestations: Attestations
    deposits: Deposits
    voluntary_exits: VoluntaryExits


class BeaconBlock(Container):
    slot: Slot
    proposer_index: ValidatorIndex
    parent_root: Root
    state_root: Root
    body: BeaconBlockBody


class SignedBeaconBlock(Container):
    message: BeaconBlock
    signature: BLSSignature


class SignedBeaconBlocks(List[SignedBeaconBlock]):
    """
    Signed beacon blocks returned in a ``BeaconBlocksByRange`` or
    ``BeaconBlocksByRoot`` response.
    """

    LIMIT = config.MAX_REQUEST_BLOCKS


class NodeID(Uint256):
    pass


class SubnetID(Uint64):
    pass


class Ether(Uint64):
    pass


@dataclass(eq=True, frozen=True)
class ForkChoiceNode:
    root: Root


@dataclass(eq=True, frozen=True)
class LatestMessage:
    epoch: Epoch
    root: Root


@dataclass
class Store:
    time: Uint64
    genesis_time: Uint64
    justified_checkpoint: Checkpoint
    finalized_checkpoint: Checkpoint
    unrealized_justified_checkpoint: Checkpoint
    unrealized_finalized_checkpoint: Checkpoint
    proposer_boost_root: Root
    equivocating_indices: Set[ValidatorIndex]
    blocks: Dict[Root, BeaconBlock]
    block_states: Dict[Root, BeaconState]
    block_timeliness: Dict[Root, bool]
    checkpoint_states: Dict[Checkpoint, BeaconState]
    latest_messages: Dict[ValidatorIndex, LatestMessage]
    unrealized_justifications: Dict[Root, Checkpoint]


@dataclass
class FastConfirmationStore:
    store: Store
    confirmed_root: Root
    previous_epoch_observed_justified_checkpoint: Checkpoint
    current_epoch_observed_justified_checkpoint: Checkpoint
    previous_epoch_greatest_unrealized_checkpoint: Checkpoint
    previous_slot_head: Root
    current_slot_head: Root


@dataclass
class Seen:
    proposer_slots: Set[Tuple[Slot, ValidatorIndex]]
    aggregator_epochs: Set[Tuple[Epoch, ValidatorIndex]]
    aggregate_data_roots: Dict[Root, Set[Tuple[bool, ...]]]
    voluntary_exit_indices: Set[ValidatorIndex]
    proposer_slashing_indices: Set[ValidatorIndex]
    attester_slashing_indices: Set[ValidatorIndex]
    attestation_validator_epochs: Set[Tuple[Epoch, ValidatorIndex]]


def get_set_bit_count(bits: Sequence[Boolean]) -> Uint64:
    """
    Return the number of bits that are set in ``bits``.
    """
    return Uint64(sum(1 for bit in bits if bit))


def integer_squareroot(n: Uint64) -> Uint64:
    """
    Return the largest integer ``x`` such that ``x**2 <= n``.
    """
    if n == UINT64_MAX:
        return UINT64_MAX_SQRT
    x = n
    y = (x + 1) // 2
    while y < x:
        x = y
        y = (x + n // x) // 2
    return x


def xor(bytes_1: Bytes32, bytes_2: Bytes32) -> Bytes32:
    """
    Return the exclusive-or of two 32-byte strings.
    """
    return Bytes32(a ^ b for a, b in zip(bytes_1, bytes_2, strict=True))


def uint_to_bytes(n: Uint) -> bytes:
    """
    Return the SSZ serialization of ``n``, a ``Uint``.
    """
    return ssz_serialize(n)


def bytes_to_uint64(data: bytes) -> Uint64:
    """
    Return the integer deserialization of ``data`` as a ``Uint64``.
    """
    return Uint64(int.from_bytes(data, ENDIANNESS))


def sha256(data: bytes) -> Bytes32:
    """
    Return the SHA256 hash of ``data``.
    """
    return Bytes32(sha256_hash(data).digest())


def hash_tree_root(object: SSZObject) -> Root:
    """
    Return the hash tree root of ``object``.
    """
    return Root(object.hash_tree_root())


def is_active_validator(validator: Validator, epoch: Epoch) -> bool:
    """
    Check if ``validator`` is active.
    """
    return validator.activation_epoch <= epoch < validator.exit_epoch


def is_eligible_for_activation_queue(validator: Validator) -> bool:
    """
    Check if ``validator`` is eligible to be placed into the activation queue.
    """
    return (
        validator.activation_eligibility_epoch == FAR_FUTURE_EPOCH
        and validator.effective_balance == MAX_EFFECTIVE_BALANCE
    )


def is_eligible_for_activation(state: BeaconState, validator: Validator) -> bool:
    """
    Check if ``validator`` is eligible for activation.
    """
    return (
        # Placement in queue is finalized
        validator.activation_eligibility_epoch <= state.finalized_checkpoint.epoch
        # Has not yet been activated
        and validator.activation_epoch == FAR_FUTURE_EPOCH
    )


def is_slashable_validator(validator: Validator, epoch: Epoch) -> bool:
    """
    Check if ``validator`` is slashable.
    """
    return (not validator.slashed) and (
        validator.activation_epoch <= epoch < validator.withdrawable_epoch
    )


def is_slashable_attestation_data(data_1: AttestationData, data_2: AttestationData) -> bool:
    """
    Check if ``data_1`` and ``data_2`` are slashable according to Casper FFG rules.
    """
    return (
        # Double vote
        (data_1 != data_2 and data_1.target.epoch == data_2.target.epoch)
        or
        # Surround vote
        (data_1.source.epoch < data_2.source.epoch and data_2.target.epoch < data_1.target.epoch)
    )


def is_valid_indexed_attestation(
    state: BeaconState, indexed_attestation: IndexedAttestation
) -> bool:
    """
    Check if ``indexed_attestation`` is not empty, has sorted and unique indices and has a valid aggregate signature.
    """
    # Verify indices are sorted and unique
    indices = indexed_attestation.attesting_indices
    if len(indices) == 0 or list(indices) != sorted(set(indices)):
        return False
    # Verify aggregate signature
    pubkeys = [state.validators[i].pubkey for i in indices]
    domain = get_domain(state, DOMAIN_BEACON_ATTESTER, indexed_attestation.data.target.epoch)
    signing_root = compute_signing_root(indexed_attestation.data, domain)
    return bls.FastAggregateVerify(pubkeys, signing_root, indexed_attestation.signature)


def compute_merkle_branch_root(
    leaf: Bytes32, branch: Sequence[Bytes32], depth: Uint64, index: Uint64
) -> Root:
    """
    Return the Merkle root obtained by hashing ``leaf`` at ``index`` with ``branch``.
    """
    value = leaf
    for i in range(depth):
        if index // (2**i) % 2:
            value = sha256(branch[i] + value)
        else:
            value = sha256(value + branch[i])
    return Root(value)


def is_valid_merkle_branch(
    leaf: Bytes32, branch: Sequence[Bytes32], depth: Uint64, index: Uint64, root: Root
) -> bool:
    """
    Check if ``leaf`` at ``index`` verifies against the Merkle ``root`` and ``branch``.
    """
    if depth != len(branch):
        return False
    return compute_merkle_branch_root(leaf, branch, depth, index) == root


def compute_shuffled_permutation(index_count: Uint64, seed: Bytes32) -> Sequence[Uint64]:
    """
    Return the full shuffled permutation corresponding to ``seed`` (and ``index_count``).
    """
    # Swap or not (https://link.springer.com/content/pdf/10.1007%2F978-3-642-32009-5_1.pdf)
    # See the 'generalized domain' algorithm on page 3
    indices = [Uint64(i) for i in range(index_count)]
    for current_round in range(SHUFFLE_ROUND_COUNT):
        round_bytes = uint_to_bytes(Uint8(current_round))
        pivot = bytes_to_uint64(sha256(seed + round_bytes)[0:8]) % index_count
        source_by_bucket: Dict[Uint64, Bytes32] = {}
        for i in range(index_count):
            flip = (pivot + index_count - indices[i]) % index_count
            position = max(indices[i], flip)
            position_bucket = position // 256
            if position_bucket not in source_by_bucket:
                source_by_bucket[position_bucket] = sha256(
                    seed + round_bytes + uint_to_bytes(Uint32(position_bucket))
                )
            source = source_by_bucket[position_bucket]
            byte_val = source[(position % 256) // 8]
            bit = (byte_val >> (position % 8)) % 2
            indices[i] = flip if bit else indices[i]
    return indices


def compute_shuffled_index(index: Uint64, index_count: Uint64, seed: Bytes32) -> Uint64:
    """
    Return the shuffled index corresponding to ``seed`` (and ``index_count``).
    """
    assert index < index_count
    return compute_shuffled_permutation(index_count, seed)[index]


def compute_proposer_index(
    state: BeaconState, indices: Sequence[ValidatorIndex], seed: Bytes32
) -> ValidatorIndex:
    """
    Return from ``indices`` a random index sampled by effective balance.
    """
    assert len(indices) > 0
    MAX_RANDOM_BYTE = 2**8 - 1
    i = Uint64(0)
    total = Uint64(len(indices))
    while True:
        candidate_index = indices[compute_shuffled_index(i % total, total, seed)]
        random_byte = sha256(seed + uint_to_bytes(Uint64(i // 32)))[i % 32]
        effective_balance = state.validators[candidate_index].effective_balance
        if effective_balance * MAX_RANDOM_BYTE >= MAX_EFFECTIVE_BALANCE * random_byte:
            return candidate_index
        i += 1


def compute_committee(
    indices: Sequence[ValidatorIndex], seed: Bytes32, index: Uint64, count: Uint64
) -> Sequence[ValidatorIndex]:
    """
    Return the committee corresponding to ``indices``, ``seed``, ``index``, and committee ``count``.
    """
    start = (len(indices) * index) // count
    end = (len(indices) * Uint64(index + 1)) // count
    return [
        indices[compute_shuffled_index(Uint64(i), Uint64(len(indices)), seed)]
        for i in range(start, end)
    ]


def compute_time_at_slot(state: BeaconState, slot: Slot) -> Uint64:
    slots_since_genesis = slot - GENESIS_SLOT
    return Uint64(state.genesis_time + slots_since_genesis * config.SLOT_DURATION_MS // 1000)


def compute_epoch_at_slot(slot: Slot) -> Epoch:
    """
    Return the epoch number at ``slot``.
    """
    return Epoch(slot // SLOTS_PER_EPOCH)


def compute_start_slot_at_epoch(epoch: Epoch) -> Slot:
    """
    Return the start slot of ``epoch``.
    """
    return Slot(epoch) * SLOTS_PER_EPOCH


def compute_activation_exit_epoch(epoch: Epoch) -> Epoch:
    """
    Return the epoch during which validator activations and exits initiated in ``epoch`` take effect.
    """
    return epoch + 1 + MAX_SEED_LOOKAHEAD


def compute_fork_data_root(current_version: Version, genesis_validators_root: Root) -> Root:
    """
    Return the 32-byte fork data root for the ``current_version`` and ``genesis_validators_root``.
    This is used primarily in signature domains to avoid collisions across forks/chains.
    """
    return hash_tree_root(
        ForkData(
            current_version=current_version,
            genesis_validators_root=genesis_validators_root,
        )
    )


def compute_domain(
    domain_type: DomainType,
    fork_version: Optional[Version] = None,
    genesis_validators_root: Optional[Root] = None,
) -> Domain:
    """
    Return the domain for the ``domain_type`` and ``fork_version``.
    """
    if fork_version is None:
        fork_version = config.GENESIS_FORK_VERSION
    if genesis_validators_root is None:
        genesis_validators_root = Root()  # all bytes zero by default
    fork_data_root = compute_fork_data_root(fork_version, genesis_validators_root)
    return Domain(domain_type + fork_data_root[:28])


def compute_signing_root(ssz_object: SSZObject, domain: Domain) -> Root:
    """
    Return the signing root for the corresponding signing data.
    """
    return hash_tree_root(
        SigningData(
            object_root=hash_tree_root(ssz_object),
            domain=domain,
        )
    )


def get_current_epoch(state: BeaconState) -> Epoch:
    """
    Return the current epoch.
    """
    return compute_epoch_at_slot(state.slot)


def get_previous_epoch(state: BeaconState) -> Epoch:
    """`
    Return the previous epoch (unless the current epoch is ``GENESIS_EPOCH``).
    """
    current_epoch = get_current_epoch(state)
    return GENESIS_EPOCH if current_epoch == GENESIS_EPOCH else current_epoch - 1


def get_block_root(state: BeaconState, epoch: Epoch) -> Root:
    """
    Return the block root at the start of a recent ``epoch``.
    """
    return get_block_root_at_slot(state, compute_start_slot_at_epoch(epoch))


def get_block_root_at_slot(state: BeaconState, slot: Slot) -> Root:
    """
    Return the block root at a recent ``slot``.
    """
    assert slot < state.slot <= slot + SLOTS_PER_HISTORICAL_ROOT
    return state.block_roots[slot % SLOTS_PER_HISTORICAL_ROOT]


def get_randao_mix(state: BeaconState, epoch: Epoch) -> Bytes32:
    """
    Return the randao mix at a recent ``epoch``.
    """
    return state.randao_mixes[epoch % EPOCHS_PER_HISTORICAL_VECTOR]


def get_active_validator_indices(state: BeaconState, epoch: Epoch) -> Sequence[ValidatorIndex]:
    """
    Return the sequence of active validator indices at ``epoch``.
    """
    return [
        ValidatorIndex(i) for i, v in enumerate(state.validators) if is_active_validator(v, epoch)
    ]


def get_validator_churn_limit(state: BeaconState) -> Uint64:
    """
    Return the validator churn limit for the current epoch.
    """
    active_validator_indices = get_active_validator_indices(state, get_current_epoch(state))
    return max(
        config.MIN_PER_EPOCH_CHURN_LIMIT, Uint64(len(active_validator_indices)) // config.CHURN_LIMIT_QUOTIENT
    )


def get_seed(state: BeaconState, epoch: Epoch, domain_type: DomainType) -> Bytes32:
    """
    Return the seed at ``epoch``.
    """
    mix = get_randao_mix(
        state, epoch + EPOCHS_PER_HISTORICAL_VECTOR - MIN_SEED_LOOKAHEAD - 1
    )  # Avoid underflow
    return sha256(domain_type + uint_to_bytes(epoch) + mix)


def get_committee_count_per_slot(state: BeaconState, epoch: Epoch) -> Uint64:
    """
    Return the number of committees in each slot for the given ``epoch``.
    """
    return max(
        Uint64(1),
        min(
            MAX_COMMITTEES_PER_SLOT,
            Uint64(len(get_active_validator_indices(state, epoch)))
            // Uint64(SLOTS_PER_EPOCH)
            // TARGET_COMMITTEE_SIZE,
        ),
    )


def get_beacon_committee(
    state: BeaconState, slot: Slot, index: CommitteeIndex
) -> Sequence[ValidatorIndex]:
    """
    Return the beacon committee at ``slot`` for ``index``.
    """
    epoch = compute_epoch_at_slot(slot)
    committees_per_slot = get_committee_count_per_slot(state, epoch)
    return compute_committee(
        indices=get_active_validator_indices(state, epoch),
        seed=get_seed(state, epoch, DOMAIN_BEACON_ATTESTER),
        index=Uint64(slot % SLOTS_PER_EPOCH) * committees_per_slot + index,
        count=committees_per_slot * Uint64(SLOTS_PER_EPOCH),
    )


def get_beacon_proposer_index(state: BeaconState) -> ValidatorIndex:
    """
    Return the beacon proposer index at the current slot.
    """
    epoch = get_current_epoch(state)
    seed = sha256(get_seed(state, epoch, DOMAIN_BEACON_PROPOSER) + uint_to_bytes(state.slot))
    indices = get_active_validator_indices(state, epoch)
    return compute_proposer_index(state, indices, seed)


def get_total_balance(state: BeaconState, indices: Set[ValidatorIndex]) -> Gwei:
    """
    Return the combined effective balance of the ``indices``.
    ``EFFECTIVE_BALANCE_INCREMENT`` Gwei minimum to avoid divisions by zero.
    Math safe up to ~10B ETH, after which this overflows Uint64.
    """
    return Gwei(
        max(
            EFFECTIVE_BALANCE_INCREMENT,
            sum([state.validators[index].effective_balance for index in indices]),
        )
    )


def get_total_active_balance(state: BeaconState) -> Gwei:
    """
    Return the combined effective balance of the active validators.
    Note: ``get_total_balance`` returns ``EFFECTIVE_BALANCE_INCREMENT`` Gwei minimum to avoid divisions by zero.
    """
    return get_total_balance(
        state, set(get_active_validator_indices(state, get_current_epoch(state)))
    )


def get_domain(
    state: BeaconState, domain_type: DomainType, epoch: Optional[Epoch] = None
) -> Domain:
    """
    Return the signature domain (fork version concatenated with domain type) of a message.
    """
    epoch = get_current_epoch(state) if epoch is None else epoch
    fork_version = (
        state.fork.previous_version if epoch < state.fork.epoch else state.fork.current_version
    )
    return compute_domain(domain_type, fork_version, state.genesis_validators_root)


def get_indexed_attestation(state: BeaconState, attestation: Attestation) -> IndexedAttestation:
    """
    Return the indexed attestation corresponding to ``attestation``.
    """
    attesting_indices = get_attesting_indices(state, attestation)

    return IndexedAttestation(
        attesting_indices=AttestingIndices(data=sorted(attesting_indices)),
        data=attestation.data,
        signature=attestation.signature,
    )


def get_attesting_indices(state: BeaconState, attestation: Attestation) -> Set[ValidatorIndex]:
    """
    Return the set of attesting indices corresponding to ``data`` and ``bits``.
    """
    committee = get_beacon_committee(state, attestation.data.slot, attestation.data.index)
    return {index for i, index in enumerate(committee) if attestation.aggregation_bits[i]}


def get_pending_attesting_indices(
    state: BeaconState, attestation: PendingAttestation
) -> Set[ValidatorIndex]:
    """
    Return the set of attesting indices for a ``PendingAttestation``.
    """
    committee = get_beacon_committee(state, attestation.data.slot, attestation.data.index)
    return {index for i, index in enumerate(committee) if attestation.aggregation_bits[i]}


def increase_balance(state: BeaconState, index: ValidatorIndex, delta: Gwei) -> None:
    """
    Increase the validator balance at index ``index`` by ``delta``.
    """
    state.balances[index] += delta


def decrease_balance(state: BeaconState, index: ValidatorIndex, delta: Gwei) -> None:
    """
    Decrease the validator balance at index ``index`` by ``delta``, with underflow protection.
    """
    if delta > state.balances[index]:
        state.balances[index] = Gwei(0)
    else:
        state.balances[index] -= delta


def initiate_validator_exit(state: BeaconState, index: ValidatorIndex) -> None:
    """
    Initiate the exit of the validator with index ``index``.
    """
    # Return if validator already initiated exit
    validator = state.validators[index]
    if validator.exit_epoch != FAR_FUTURE_EPOCH:
        return

    # Compute exit queue epoch
    exit_epochs = [v.exit_epoch for v in state.validators if v.exit_epoch != FAR_FUTURE_EPOCH]
    exit_queue_epoch = max(exit_epochs + [compute_activation_exit_epoch(get_current_epoch(state))])
    exit_queue_churn = len([v for v in state.validators if v.exit_epoch == exit_queue_epoch])
    if exit_queue_churn >= get_validator_churn_limit(state):
        exit_queue_epoch += 1

    # Set validator exit epoch and withdrawable epoch
    validator.exit_epoch = exit_queue_epoch
    validator.withdrawable_epoch = validator.exit_epoch + config.MIN_VALIDATOR_WITHDRAWABILITY_DELAY


def slash_validator(
    state: BeaconState,
    slashed_index: ValidatorIndex,
    whistleblower_index: Optional[ValidatorIndex] = None,
) -> None:
    """
    Slash the validator with index ``slashed_index``.
    """
    epoch = get_current_epoch(state)
    initiate_validator_exit(state, slashed_index)
    validator = state.validators[slashed_index]
    validator.slashed = Boolean(True)
    validator.withdrawable_epoch = max(
        validator.withdrawable_epoch, epoch + EPOCHS_PER_SLASHINGS_VECTOR
    )
    state.slashings[epoch % EPOCHS_PER_SLASHINGS_VECTOR] += validator.effective_balance
    decrease_balance(
        state, slashed_index, validator.effective_balance // MIN_SLASHING_PENALTY_QUOTIENT
    )

    # Apply proposer and whistleblower rewards
    proposer_index = get_beacon_proposer_index(state)
    if whistleblower_index is None:
        whistleblower_index = proposer_index
    whistleblower_reward = validator.effective_balance // WHISTLEBLOWER_REWARD_QUOTIENT
    proposer_reward = whistleblower_reward // PROPOSER_REWARD_QUOTIENT
    increase_balance(state, proposer_index, proposer_reward)
    increase_balance(state, whistleblower_index, whistleblower_reward - proposer_reward)


def initialize_beacon_state_from_eth1(
    eth1_block_hash: Hash32, eth1_timestamp: Uint64, deposits: Sequence[Deposit]
) -> BeaconState:
    state = BeaconState.empty()
    state.genesis_time = eth1_timestamp + config.GENESIS_DELAY
    state.fork = Fork(
        previous_version=config.GENESIS_FORK_VERSION,
        current_version=config.GENESIS_FORK_VERSION,
        epoch=GENESIS_EPOCH,
    )
    state.eth1_data.deposit_count = Uint64(len(deposits))
    state.eth1_data.block_hash = eth1_block_hash
    state.latest_block_header.body_root = hash_tree_root(BeaconBlockBody.empty())
    state.randao_mixes = RandaoMixes(data=[eth1_block_hash] * EPOCHS_PER_HISTORICAL_VECTOR)

    # Process deposits
    leaves = [deposit.data for deposit in deposits]
    for index, deposit in enumerate(deposits):
        deposit_data_list = DepositDataList(data=leaves[: index + 1])
        state.eth1_data.deposit_root = hash_tree_root(deposit_data_list)
        process_deposit(state, deposit)

    # Process activations
    for index, validator in enumerate(state.validators):
        balance = state.balances[index]
        validator.effective_balance = min(
            balance - balance % EFFECTIVE_BALANCE_INCREMENT, MAX_EFFECTIVE_BALANCE
        )
        if validator.effective_balance == MAX_EFFECTIVE_BALANCE:
            validator.activation_eligibility_epoch = GENESIS_EPOCH
            validator.activation_epoch = GENESIS_EPOCH

    # Set genesis validators root for domain separation and chain versioning
    state.genesis_validators_root = hash_tree_root(state.validators)

    return state


def is_valid_genesis_state(state: BeaconState) -> bool:
    if state.genesis_time < config.MIN_GENESIS_TIME:
        return False
    if len(get_active_validator_indices(state, GENESIS_EPOCH)) < config.MIN_GENESIS_ACTIVE_VALIDATOR_COUNT:
        return False
    return True


def state_transition(
    state: BeaconState, signed_block: SignedBeaconBlock, validate_result: bool = True
) -> None:
    block = signed_block.message
    # Process slots (including those with no blocks) since block
    process_slots(state, block.slot)
    # Verify signature
    if validate_result:
        assert verify_block_signature(state, signed_block)
    # Process block
    process_block(state, block)
    # Verify state root
    if validate_result:
        assert block.state_root == hash_tree_root(state)


def verify_block_signature(state: BeaconState, signed_block: SignedBeaconBlock) -> bool:
    proposer = state.validators[signed_block.message.proposer_index]
    signing_root = compute_signing_root(
        signed_block.message, get_domain(state, DOMAIN_BEACON_PROPOSER)
    )
    return bls.Verify(proposer.pubkey, signing_root, signed_block.signature)


def process_slots(state: BeaconState, slot: Slot) -> None:
    assert state.slot < slot
    while state.slot < slot:
        process_slot(state)
        # Process epoch on the start slot of the next epoch
        if (state.slot + 1) % SLOTS_PER_EPOCH == 0:
            process_epoch(state)
        state.slot = state.slot + 1


def process_slot(state: BeaconState) -> None:
    slot_index = state.slot % SLOTS_PER_HISTORICAL_ROOT
    # Cache state root
    previous_state_root = hash_tree_root(state)
    state.state_roots[slot_index] = previous_state_root
    # Cache latest block header state root
    if state.latest_block_header.state_root == Bytes32():
        state.latest_block_header.state_root = previous_state_root
    # Cache block root
    previous_block_root = hash_tree_root(state.latest_block_header)
    state.block_roots[slot_index] = previous_block_root


def process_epoch(state: BeaconState) -> None:
    process_justification_and_finalization(state)
    process_rewards_and_penalties(state)
    process_registry_updates(state)
    process_slashings(state)
    process_eth1_data_reset(state)
    process_effective_balance_updates(state)
    process_slashings_reset(state)
    process_randao_mixes_reset(state)
    process_historical_roots_update(state)
    process_participation_record_updates(state)


def get_matching_source_attestations(
    state: BeaconState, epoch: Epoch
) -> Sequence[PendingAttestation]:
    assert epoch in (get_previous_epoch(state), get_current_epoch(state))
    return (
        state.current_epoch_attestations
        if epoch == get_current_epoch(state)
        else state.previous_epoch_attestations
    )


def get_matching_target_attestations(
    state: BeaconState, epoch: Epoch
) -> Sequence[PendingAttestation]:
    return [
        a
        for a in get_matching_source_attestations(state, epoch)
        if a.data.target.root == get_block_root(state, epoch)
    ]


def get_matching_head_attestations(
    state: BeaconState, epoch: Epoch
) -> Sequence[PendingAttestation]:
    return [
        a
        for a in get_matching_target_attestations(state, epoch)
        if a.data.beacon_block_root == get_block_root_at_slot(state, a.data.slot)
    ]


def get_unslashed_attesting_indices(
    state: BeaconState, attestations: Sequence[PendingAttestation]
) -> Set[ValidatorIndex]:
    output: Set[ValidatorIndex] = set()
    for a in attestations:
        output = output.union(get_pending_attesting_indices(state, a))
    return set(filter(lambda index: not state.validators[index].slashed, output))


def get_attesting_balance(state: BeaconState, attestations: Sequence[PendingAttestation]) -> Gwei:
    """
    Return the combined effective balance of the set of unslashed validators participating in ``attestations``.
    Note: ``get_total_balance`` returns ``EFFECTIVE_BALANCE_INCREMENT`` Gwei minimum to avoid divisions by zero.
    """
    return get_total_balance(state, get_unslashed_attesting_indices(state, attestations))


def process_justification_and_finalization(state: BeaconState) -> None:
    # Initial FFG checkpoint values have a `0x00` stub for `root`.
    # Skip FFG updates in the first two epochs to avoid corner cases that might result in modifying this stub.
    if get_current_epoch(state) <= GENESIS_EPOCH + 1:
        return
    previous_attestations = get_matching_target_attestations(state, get_previous_epoch(state))
    current_attestations = get_matching_target_attestations(state, get_current_epoch(state))
    total_active_balance = get_total_active_balance(state)
    previous_target_balance = get_attesting_balance(state, previous_attestations)
    current_target_balance = get_attesting_balance(state, current_attestations)
    weigh_justification_and_finalization(
        state, total_active_balance, previous_target_balance, current_target_balance
    )


def weigh_justification_and_finalization(
    state: BeaconState,
    total_active_balance: Gwei,
    previous_epoch_target_balance: Gwei,
    current_epoch_target_balance: Gwei,
) -> None:
    previous_epoch = get_previous_epoch(state)
    current_epoch = get_current_epoch(state)
    old_previous_justified_checkpoint = state.previous_justified_checkpoint
    old_current_justified_checkpoint = state.current_justified_checkpoint

    # Process justifications
    state.previous_justified_checkpoint = state.current_justified_checkpoint
    state.justification_bits[1:] = state.justification_bits[: JUSTIFICATION_BITS_LENGTH - 1]
    state.justification_bits[0] = Boolean(False)
    if previous_epoch_target_balance * 3 >= total_active_balance * 2:
        state.current_justified_checkpoint = Checkpoint(
            epoch=previous_epoch, root=get_block_root(state, previous_epoch)
        )
        state.justification_bits[1] = Boolean(True)
    if current_epoch_target_balance * 3 >= total_active_balance * 2:
        state.current_justified_checkpoint = Checkpoint(
            epoch=current_epoch, root=get_block_root(state, current_epoch)
        )
        state.justification_bits[0] = Boolean(True)

    # Process finalizations
    bits = state.justification_bits
    # The 2nd/3rd/4th most recent epochs are justified, the 2nd using the 4th as source
    if all(bits[1:4]) and old_previous_justified_checkpoint.epoch + 3 == current_epoch:
        state.finalized_checkpoint = old_previous_justified_checkpoint
    # The 2nd/3rd most recent epochs are justified, the 2nd using the 3rd as source
    if all(bits[1:3]) and old_previous_justified_checkpoint.epoch + 2 == current_epoch:
        state.finalized_checkpoint = old_previous_justified_checkpoint
    # The 1st/2nd/3rd most recent epochs are justified, the 1st using the 3rd as source
    if all(bits[0:3]) and old_current_justified_checkpoint.epoch + 2 == current_epoch:
        state.finalized_checkpoint = old_current_justified_checkpoint
    # The 1st/2nd most recent epochs are justified, the 1st using the 2nd as source
    if all(bits[0:2]) and old_current_justified_checkpoint.epoch + 1 == current_epoch:
        state.finalized_checkpoint = old_current_justified_checkpoint


def get_base_reward(state: BeaconState, index: ValidatorIndex) -> Gwei:
    total_balance = get_total_active_balance(state)
    effective_balance = state.validators[index].effective_balance
    return Gwei(
        effective_balance
        * BASE_REWARD_FACTOR
        // integer_squareroot(total_balance)
        // BASE_REWARDS_PER_EPOCH
    )


def get_proposer_reward(state: BeaconState, attesting_index: ValidatorIndex) -> Gwei:
    return get_base_reward(state, attesting_index) // PROPOSER_REWARD_QUOTIENT


def get_finality_delay(state: BeaconState) -> Uint64:
    return Uint64(get_previous_epoch(state) - state.finalized_checkpoint.epoch)


def is_in_inactivity_leak(state: BeaconState) -> bool:
    return get_finality_delay(state) > MIN_EPOCHS_TO_INACTIVITY_PENALTY


def get_eligible_validator_indices(state: BeaconState) -> Sequence[ValidatorIndex]:
    previous_epoch = get_previous_epoch(state)
    return [
        ValidatorIndex(index)
        for index, v in enumerate(state.validators)
        if is_active_validator(v, previous_epoch)
        or (v.slashed and previous_epoch + 1 < v.withdrawable_epoch)
    ]


def get_attestation_component_deltas(
    state: BeaconState, attestations: Sequence[PendingAttestation]
) -> Tuple[Sequence[Gwei], Sequence[Gwei]]:
    """
    Helper with shared logic for use by get source, target, and head deltas functions
    """
    rewards = [Gwei(0)] * len(state.validators)
    penalties = [Gwei(0)] * len(state.validators)
    total_balance = get_total_active_balance(state)
    unslashed_attesting_indices = get_unslashed_attesting_indices(state, attestations)
    attesting_balance = get_total_balance(state, unslashed_attesting_indices)
    for index in get_eligible_validator_indices(state):
        if index in unslashed_attesting_indices:
            increment = EFFECTIVE_BALANCE_INCREMENT  # Factored out from balance totals to avoid Uint64 overflow
            if is_in_inactivity_leak(state):
                # Since full base reward will be canceled out by inactivity penalty deltas,
                # optimal participation receives full base reward compensation here.
                rewards[index] += get_base_reward(state, index)
            else:
                reward_numerator = get_base_reward(state, index) * (attesting_balance // increment)
                rewards[index] += reward_numerator // (total_balance // increment)
        else:
            penalties[index] += get_base_reward(state, index)
    return rewards, penalties


def get_source_deltas(state: BeaconState) -> Tuple[Sequence[Gwei], Sequence[Gwei]]:
    """
    Return attester micro-rewards/penalties for source-vote for each validator.
    """
    matching_source_attestations = get_matching_source_attestations(
        state, get_previous_epoch(state)
    )
    return get_attestation_component_deltas(state, matching_source_attestations)


def get_target_deltas(state: BeaconState) -> Tuple[Sequence[Gwei], Sequence[Gwei]]:
    """
    Return attester micro-rewards/penalties for target-vote for each validator.
    """
    matching_target_attestations = get_matching_target_attestations(
        state, get_previous_epoch(state)
    )
    return get_attestation_component_deltas(state, matching_target_attestations)


def get_head_deltas(state: BeaconState) -> Tuple[Sequence[Gwei], Sequence[Gwei]]:
    """
    Return attester micro-rewards/penalties for head-vote for each validator.
    """
    matching_head_attestations = get_matching_head_attestations(state, get_previous_epoch(state))
    return get_attestation_component_deltas(state, matching_head_attestations)


def get_inclusion_delay_deltas(state: BeaconState) -> Tuple[Sequence[Gwei], Sequence[Gwei]]:
    """
    Return proposer and inclusion delay micro-rewards/penalties for each validator.
    """
    rewards = [Gwei(0)] * len(state.validators)
    matching_source_attestations = get_matching_source_attestations(
        state, get_previous_epoch(state)
    )
    for index in get_unslashed_attesting_indices(state, matching_source_attestations):
        attestation = min(
            [
                a
                for a in matching_source_attestations
                if index in get_pending_attesting_indices(state, a)
            ],
            key=lambda a: a.inclusion_delay,
        )
        rewards[attestation.proposer_index] += get_proposer_reward(state, index)
        max_attester_reward = get_base_reward(state, index) - get_proposer_reward(state, index)
        rewards[index] += max_attester_reward // Uint64(attestation.inclusion_delay)

    # No penalties associated with inclusion delay
    penalties = [Gwei(0)] * len(state.validators)
    return rewards, penalties


def get_inactivity_penalty_deltas(state: BeaconState) -> Tuple[Sequence[Gwei], Sequence[Gwei]]:
    """
    Return inactivity reward/penalty deltas for each validator.
    """
    penalties = [Gwei(0)] * len(state.validators)
    if is_in_inactivity_leak(state):
        matching_target_attestations = get_matching_target_attestations(
            state, get_previous_epoch(state)
        )
        matching_target_attesting_indices = get_unslashed_attesting_indices(
            state, matching_target_attestations
        )
        for index in get_eligible_validator_indices(state):
            # If validator is performing optimally this cancels all rewards for a neutral balance
            base_reward = get_base_reward(state, index)
            penalties[index] += BASE_REWARDS_PER_EPOCH * base_reward - get_proposer_reward(
                state, index
            )
            if index not in matching_target_attesting_indices:
                effective_balance = state.validators[index].effective_balance
                penalties[index] += (
                    effective_balance * get_finality_delay(state) // INACTIVITY_PENALTY_QUOTIENT
                )

    # No rewards associated with inactivity penalties
    rewards = [Gwei(0)] * len(state.validators)
    return rewards, penalties


def get_attestation_deltas(state: BeaconState) -> Tuple[Sequence[Gwei], Sequence[Gwei]]:
    """
    Return attestation reward/penalty deltas for each validator.
    """
    source_rewards, source_penalties = get_source_deltas(state)
    target_rewards, target_penalties = get_target_deltas(state)
    head_rewards, head_penalties = get_head_deltas(state)
    inclusion_delay_rewards, _ = get_inclusion_delay_deltas(state)
    _, inactivity_penalties = get_inactivity_penalty_deltas(state)

    rewards = [
        source_rewards[i] + target_rewards[i] + head_rewards[i] + inclusion_delay_rewards[i]
        for i in range(len(state.validators))
    ]

    penalties = [
        source_penalties[i] + target_penalties[i] + head_penalties[i] + inactivity_penalties[i]
        for i in range(len(state.validators))
    ]

    return rewards, penalties


def process_rewards_and_penalties(state: BeaconState) -> None:
    # No rewards are applied at the end of `GENESIS_EPOCH` because rewards are for work done in the previous epoch
    if get_current_epoch(state) == GENESIS_EPOCH:
        return

    rewards, penalties = get_attestation_deltas(state)
    for index in range(len(state.validators)):
        increase_balance(state, ValidatorIndex(index), rewards[index])
        decrease_balance(state, ValidatorIndex(index), penalties[index])


def process_registry_updates(state: BeaconState) -> None:
    # Process activation eligibility and ejections
    for index, validator in enumerate(state.validators):
        if is_eligible_for_activation_queue(validator):
            validator.activation_eligibility_epoch = get_current_epoch(state) + 1

        if (
            is_active_validator(validator, get_current_epoch(state))
            and validator.effective_balance <= config.EJECTION_BALANCE
        ):
            initiate_validator_exit(state, ValidatorIndex(index))

    # Queue validators eligible for activation and not yet dequeued for activation
    activation_queue = sorted(
        [
            index
            for index, validator in enumerate(state.validators)
            if is_eligible_for_activation(state, validator)
        ],
        # Order by the sequence of activation_eligibility_epoch setting and then index
        key=lambda index: (state.validators[index].activation_eligibility_epoch, index),
    )
    # Dequeued validators for activation up to churn limit
    for index in activation_queue[: get_validator_churn_limit(state)]:
        validator = state.validators[index]
        validator.activation_epoch = compute_activation_exit_epoch(get_current_epoch(state))


def process_slashings(state: BeaconState) -> None:
    epoch = get_current_epoch(state)
    total_balance = get_total_active_balance(state)
    adjusted_total_slashing_balance = min(
        Gwei(sum(state.slashings)) * PROPORTIONAL_SLASHING_MULTIPLIER, total_balance
    )
    for index, validator in enumerate(state.validators):
        if (
            validator.slashed
            and epoch + EPOCHS_PER_SLASHINGS_VECTOR // 2 == validator.withdrawable_epoch
        ):
            increment = EFFECTIVE_BALANCE_INCREMENT  # Factored out from penalty numerator to avoid Uint64 overflow
            penalty_numerator = (
                validator.effective_balance // increment * adjusted_total_slashing_balance
            )
            penalty = penalty_numerator // total_balance * increment
            decrease_balance(state, ValidatorIndex(index), penalty)


def process_eth1_data_reset(state: BeaconState) -> None:
    next_epoch = get_current_epoch(state) + 1
    # Reset eth1 data votes
    if next_epoch % EPOCHS_PER_ETH1_VOTING_PERIOD == 0:
        state.eth1_data_votes = Eth1DataVotes()


def process_effective_balance_updates(state: BeaconState) -> None:
    # Update effective balances with hysteresis
    for index, validator in enumerate(state.validators):
        balance = state.balances[index]
        HYSTERESIS_INCREMENT = Uint64(EFFECTIVE_BALANCE_INCREMENT // HYSTERESIS_QUOTIENT)
        DOWNWARD_THRESHOLD = HYSTERESIS_INCREMENT * HYSTERESIS_DOWNWARD_MULTIPLIER
        UPWARD_THRESHOLD = HYSTERESIS_INCREMENT * HYSTERESIS_UPWARD_MULTIPLIER
        if (
            balance + DOWNWARD_THRESHOLD < validator.effective_balance
            or validator.effective_balance + UPWARD_THRESHOLD < balance
        ):
            validator.effective_balance = min(
                balance - balance % EFFECTIVE_BALANCE_INCREMENT, MAX_EFFECTIVE_BALANCE
            )


def process_slashings_reset(state: BeaconState) -> None:
    next_epoch = get_current_epoch(state) + 1
    # Reset slashings
    state.slashings[next_epoch % EPOCHS_PER_SLASHINGS_VECTOR] = Gwei(0)


def process_randao_mixes_reset(state: BeaconState) -> None:
    current_epoch = get_current_epoch(state)
    next_epoch = current_epoch + 1
    # Set randao mix
    state.randao_mixes[next_epoch % EPOCHS_PER_HISTORICAL_VECTOR] = get_randao_mix(
        state, current_epoch
    )


def process_historical_roots_update(state: BeaconState) -> None:
    # Set historical root accumulator
    next_epoch = get_current_epoch(state) + 1
    if next_epoch % Uint64(SLOTS_PER_HISTORICAL_ROOT // SLOTS_PER_EPOCH) == 0:
        historical_batch = HistoricalBatch(
            block_roots=state.block_roots, state_roots=state.state_roots
        )
        state.historical_roots.append(hash_tree_root(historical_batch))


def process_participation_record_updates(state: BeaconState) -> None:
    # Rotate current/previous epoch attestations
    state.previous_epoch_attestations = state.current_epoch_attestations
    state.current_epoch_attestations = PendingAttestations()


def process_block(state: BeaconState, block: BeaconBlock) -> None:
    process_block_header(state, block)
    process_randao(state, block.body)
    process_eth1_data(state, block.body)
    process_operations(state, block.body)


def process_block_header(state: BeaconState, block: BeaconBlock) -> None:
    # Verify that the slots match
    assert block.slot == state.slot
    # Verify that the block is newer than latest block header
    assert block.slot > state.latest_block_header.slot
    # Verify that proposer index is the correct index
    assert block.proposer_index == get_beacon_proposer_index(state)
    # Verify that the parent matches
    assert block.parent_root == hash_tree_root(state.latest_block_header)
    # Cache current block as the new latest block
    state.latest_block_header = BeaconBlockHeader(
        slot=block.slot,
        proposer_index=block.proposer_index,
        parent_root=block.parent_root,
        state_root=Root(),  # Overwritten in the next process_slot call
        body_root=hash_tree_root(block.body),
    )

    # Verify proposer is not slashed
    proposer = state.validators[block.proposer_index]
    assert not proposer.slashed


def process_randao(state: BeaconState, body: BeaconBlockBody) -> None:
    epoch = get_current_epoch(state)
    # Verify RANDAO reveal
    proposer = state.validators[get_beacon_proposer_index(state)]
    signing_root = compute_signing_root(epoch, get_domain(state, DOMAIN_RANDAO))
    assert bls.Verify(proposer.pubkey, signing_root, body.randao_reveal)
    # Mix in RANDAO reveal
    mix = xor(get_randao_mix(state, epoch), sha256(body.randao_reveal))
    state.randao_mixes[epoch % EPOCHS_PER_HISTORICAL_VECTOR] = mix


def process_eth1_data(state: BeaconState, body: BeaconBlockBody) -> None:
    state.eth1_data_votes.append(body.eth1_data)
    if (
        state.eth1_data_votes.count(body.eth1_data) * 2
        > Uint64(EPOCHS_PER_ETH1_VOTING_PERIOD) * SLOTS_PER_EPOCH
    ):
        state.eth1_data = body.eth1_data


def process_operations(state: BeaconState, body: BeaconBlockBody) -> None:
    # Verify that outstanding deposits are processed up to the maximum number of deposits
    assert len(body.deposits) == min(
        MAX_DEPOSITS, state.eth1_data.deposit_count - state.eth1_deposit_index
    )

    def for_ops(operations: Sequence[Any], fn: Callable[[BeaconState, Any], None]) -> None:
        for operation in operations:
            fn(state, operation)

    for_ops(body.proposer_slashings, process_proposer_slashing)
    for_ops(body.attester_slashings, process_attester_slashing)
    for_ops(body.attestations, process_attestation)
    for_ops(body.deposits, process_deposit)
    for_ops(body.voluntary_exits, process_voluntary_exit)


def process_proposer_slashing(state: BeaconState, proposer_slashing: ProposerSlashing) -> None:
    header_1 = proposer_slashing.signed_header_1.message
    header_2 = proposer_slashing.signed_header_2.message

    # Verify header slots match
    assert header_1.slot == header_2.slot
    # Verify header proposer indices match
    assert header_1.proposer_index == header_2.proposer_index
    # Verify the headers are different
    assert header_1 != header_2
    # Verify the proposer is slashable
    proposer = state.validators[header_1.proposer_index]
    assert is_slashable_validator(proposer, get_current_epoch(state))
    # Verify signatures
    for signed_header in (proposer_slashing.signed_header_1, proposer_slashing.signed_header_2):
        domain = get_domain(
            state, DOMAIN_BEACON_PROPOSER, compute_epoch_at_slot(signed_header.message.slot)
        )
        signing_root = compute_signing_root(signed_header.message, domain)
        assert bls.Verify(proposer.pubkey, signing_root, signed_header.signature)

    slash_validator(state, header_1.proposer_index)


def process_attester_slashing(state: BeaconState, attester_slashing: AttesterSlashing) -> None:
    attestation_1 = attester_slashing.attestation_1
    attestation_2 = attester_slashing.attestation_2
    assert is_slashable_attestation_data(attestation_1.data, attestation_2.data)
    assert is_valid_indexed_attestation(state, attestation_1)
    assert is_valid_indexed_attestation(state, attestation_2)

    slashed_any = False
    indices = set(attestation_1.attesting_indices).intersection(attestation_2.attesting_indices)
    for index in sorted(indices):
        if is_slashable_validator(state.validators[index], get_current_epoch(state)):
            slash_validator(state, index)
            slashed_any = True
    assert slashed_any


def process_attestation(state: BeaconState, attestation: Attestation) -> None:
    data = attestation.data
    assert data.target.epoch in (get_previous_epoch(state), get_current_epoch(state))
    assert data.target.epoch == compute_epoch_at_slot(data.slot)
    assert data.slot + MIN_ATTESTATION_INCLUSION_DELAY <= state.slot <= data.slot + SLOTS_PER_EPOCH
    assert data.index < get_committee_count_per_slot(state, data.target.epoch)

    committee = get_beacon_committee(state, data.slot, data.index)
    assert len(attestation.aggregation_bits) == len(committee)

    pending_attestation = PendingAttestation(
        aggregation_bits=attestation.aggregation_bits,
        data=data,
        inclusion_delay=state.slot - data.slot,
        proposer_index=get_beacon_proposer_index(state),
    )

    if data.target.epoch == get_current_epoch(state):
        assert data.source == state.current_justified_checkpoint
        state.current_epoch_attestations.append(pending_attestation)
    else:
        assert data.source == state.previous_justified_checkpoint
        state.previous_epoch_attestations.append(pending_attestation)

    # Verify signature
    assert is_valid_indexed_attestation(state, get_indexed_attestation(state, attestation))


def get_validator_from_deposit(
    pubkey: BLSPubkey, withdrawal_credentials: Bytes32, amount: Gwei
) -> Validator:
    effective_balance = min(amount - amount % EFFECTIVE_BALANCE_INCREMENT, MAX_EFFECTIVE_BALANCE)

    return Validator(
        pubkey=pubkey,
        withdrawal_credentials=withdrawal_credentials,
        effective_balance=effective_balance,
        slashed=Boolean(False),
        activation_eligibility_epoch=FAR_FUTURE_EPOCH,
        activation_epoch=FAR_FUTURE_EPOCH,
        exit_epoch=FAR_FUTURE_EPOCH,
        withdrawable_epoch=FAR_FUTURE_EPOCH,
    )


def add_validator_to_registry(
    state: BeaconState, pubkey: BLSPubkey, withdrawal_credentials: Bytes32, amount: Gwei
) -> None:
    state.validators.append(get_validator_from_deposit(pubkey, withdrawal_credentials, amount))
    state.balances.append(amount)


def apply_deposit(
    state: BeaconState,
    pubkey: BLSPubkey,
    withdrawal_credentials: Bytes32,
    amount: Gwei,
    signature: BLSSignature,
) -> None:
    validator_pubkeys = [v.pubkey for v in state.validators]
    if pubkey not in validator_pubkeys:
        # Verify the deposit signature (proof of possession) which is not checked by the deposit contract
        deposit_message = DepositMessage(
            pubkey=pubkey,
            withdrawal_credentials=withdrawal_credentials,
            amount=amount,
        )
        # Fork-agnostic domain since deposits are valid across forks
        domain = compute_domain(DOMAIN_DEPOSIT)
        signing_root = compute_signing_root(deposit_message, domain)
        if bls.Verify(pubkey, signing_root, signature):
            add_validator_to_registry(state, pubkey, withdrawal_credentials, amount)
    else:
        # Increase balance by deposit amount
        index = ValidatorIndex(validator_pubkeys.index(pubkey))
        increase_balance(state, index, amount)


def process_deposit(state: BeaconState, deposit: Deposit) -> None:
    # Verify the Merkle branch
    assert is_valid_merkle_branch(
        leaf=hash_tree_root(deposit.data),
        branch=deposit.proof,
        # Add 1 for the List length mix-in
        depth=DEPOSIT_CONTRACT_TREE_DEPTH + 1,
        index=state.eth1_deposit_index,
        root=state.eth1_data.deposit_root,
    )

    # Deposits must be processed in order
    state.eth1_deposit_index += 1

    apply_deposit(
        state=state,
        pubkey=deposit.data.pubkey,
        withdrawal_credentials=deposit.data.withdrawal_credentials,
        amount=deposit.data.amount,
        signature=deposit.data.signature,
    )


def process_voluntary_exit(state: BeaconState, signed_voluntary_exit: SignedVoluntaryExit) -> None:
    voluntary_exit = signed_voluntary_exit.message
    validator = state.validators[voluntary_exit.validator_index]
    # Verify the validator is active
    assert is_active_validator(validator, get_current_epoch(state))
    # Verify exit has not been initiated
    assert validator.exit_epoch == FAR_FUTURE_EPOCH
    # Exits must specify an epoch when they become valid; they are not valid before then
    assert get_current_epoch(state) >= voluntary_exit.epoch
    # Verify the validator has been active long enough
    assert get_current_epoch(state) >= validator.activation_epoch + config.SHARD_COMMITTEE_PERIOD
    # Verify signature
    domain = get_domain(state, DOMAIN_VOLUNTARY_EXIT, voluntary_exit.epoch)
    signing_root = compute_signing_root(voluntary_exit, domain)
    assert bls.Verify(validator.pubkey, signing_root, signed_voluntary_exit.signature)
    # Initiate exit
    initiate_validator_exit(state, voluntary_exit.validator_index)


def get_fast_confirmation_store(store: Store) -> FastConfirmationStore:
    return FastConfirmationStore(
        store=store,
        confirmed_root=store.finalized_checkpoint.root,
        previous_epoch_observed_justified_checkpoint=store.finalized_checkpoint,
        current_epoch_observed_justified_checkpoint=store.finalized_checkpoint,
        previous_epoch_greatest_unrealized_checkpoint=store.finalized_checkpoint,
        previous_slot_head=store.finalized_checkpoint.root,
        current_slot_head=store.finalized_checkpoint.root,
    )


def get_node_for_root(block_root: Root) -> ForkChoiceNode:
    return ForkChoiceNode(root=block_root)


def get_block_slot(store: Store, block_root: Root) -> Slot:
    """
    Return a slot of the block.
    """
    return store.blocks[block_root].slot


def get_block_epoch(store: Store, block_root: Root) -> Epoch:
    """
    Return an epoch of the block.
    """
    return compute_epoch_at_slot(store.blocks[block_root].slot)


def get_checkpoint_for_block(store: Store, block_root: Root, epoch: Epoch) -> Checkpoint:
    """
    Return a checkpoint in the chain of the block at the ``epoch``.
    """
    return Checkpoint(epoch=epoch, root=get_checkpoint_block(store, block_root, epoch))


def get_current_target(store: Store) -> Checkpoint:
    """
    Return current epoch target.
    """
    head = get_head(store).root
    current_epoch = get_current_store_epoch(store)
    return get_checkpoint_for_block(store, head, current_epoch)


def is_start_slot_at_epoch(slot: Slot) -> bool:
    """
    Return ``True`` if ``slot`` is the start slot of an epoch.
    """
    return compute_slots_since_epoch_start(slot) == 0


def get_ancestor_roots(store: Store, block_root: Root, terminal_root: Root) -> Sequence[Root]:
    """
    Return a list of ancestors of ``block_root`` inclusive until ``terminal_root`` exclusive.
    """
    root = block_root
    ancestor_roots: list[Root] = []
    while store.blocks[root].slot > store.blocks[terminal_root].slot:
        ancestor_roots.insert(0, root)
        root = store.blocks[root].parent_root

        # Return when terminal_root is reached
        if root == terminal_root:
            return ancestor_roots

    # Return empty list if terminal_root is not in the chain of block_root
    return []


def get_slot_committee(store: Store, slot: Slot) -> Set[ValidatorIndex]:
    """
    Return participants of all committees in ``slot``.
    """
    head = get_head(store).root
    shuffling_source = store.block_states[head]
    committees_count = get_committee_count_per_slot(shuffling_source, compute_epoch_at_slot(slot))
    participants: Set[ValidatorIndex] = set()
    for i in range(committees_count):
        participants.update(get_beacon_committee(shuffling_source, slot, CommitteeIndex(i)))
    return participants


def get_pulled_up_head_state(store: Store) -> BeaconState:
    """
    Return the state of the head pulled up to the current epoch if needed.
    """
    head = get_head(store).root
    head_state = store.block_states[head]
    if get_current_epoch(head_state) < get_current_store_epoch(store):
        pulled_up_state = head_state.copy()
        process_slots(pulled_up_state, compute_start_slot_at_epoch(get_current_store_epoch(store)))
        return pulled_up_state
    else:
        return head_state


def get_previous_balance_source(fcr_store: FastConfirmationStore) -> BeaconState:
    store = fcr_store.store
    return store.checkpoint_states[fcr_store.previous_epoch_observed_justified_checkpoint]


def get_current_balance_source(fcr_store: FastConfirmationStore) -> BeaconState:
    store = fcr_store.store
    return store.checkpoint_states[fcr_store.current_epoch_observed_justified_checkpoint]


def get_block_support_between_slots(
    store: Store,
    balance_source: BeaconState,
    block_root: Root,
    start_slot: Slot,
    end_slot: Slot,
) -> Gwei:
    """
    Return support of the block by validators assigned to slots
    between ``start_slot`` and ``end_slot`` (inclusive of both).
    """
    participants: Set[ValidatorIndex] = set()
    for slot in range(start_slot, end_slot + 1):
        participants.update(get_slot_committee(store, Slot(slot)))

    # Keep validators that were active at the balance_source epoch to be consistent
    # with get_total_active_balance() computation, also filter out slashed validators
    unslashed_and_active_indices = [
        i
        for i in participants
        if (
            not balance_source.validators[i].slashed
            and is_active_validator(balance_source.validators[i], get_current_epoch(balance_source))
        )
    ]

    return Gwei(
        sum(
            balance_source.validators[i].effective_balance
            for i in unslashed_and_active_indices
            # Check that validator has voted in the support of the block
            # and has not been slashed
            if (
                i in store.latest_messages
                and store.latest_messages[i].root == block_root
                and i not in store.equivocating_indices
            )
        )
    )


def is_full_validator_set_covered(start_slot: Slot, end_slot: Slot) -> bool:
    """
    Return ``True`` if the range between ``start_slot`` and ``end_slot`` (inclusive of both) includes an entire epoch.
    """
    start_full_epoch = compute_epoch_at_slot(start_slot + SLOTS_PER_EPOCH - 1)
    end_full_epoch = compute_epoch_at_slot(end_slot + 1)
    return start_full_epoch < end_full_epoch


def adjust_committee_weight_estimate_to_ensure_safety(estimate: Gwei) -> Gwei:
    """
    Return adjusted ``estimate`` of the weight of a committee for a sequence of slots
    spanning an epoch boundary that does not cover any full epoch.
    """
    ceil = (estimate + 999) // 1000
    return ceil * (1000 + COMMITTEE_WEIGHT_ESTIMATION_ADJUSTMENT_FACTOR)


def estimate_committee_weight_between_slots(
    total_active_balance: Gwei, start_slot: Slot, end_slot: Slot
) -> Gwei:
    """
    Return estimate of the total weight of committees
    between ``start_slot`` and ``end_slot`` (inclusive of both).
    """

    # Sanity check
    if start_slot > end_slot:
        return Gwei(0)

    # If an entire epoch is covered by the range, return the total active balance
    if is_full_validator_set_covered(start_slot, end_slot):
        return total_active_balance

    start_epoch = compute_epoch_at_slot(start_slot)
    end_epoch = compute_epoch_at_slot(end_slot)
    committee_weight = total_active_balance // Uint64(SLOTS_PER_EPOCH)
    if start_epoch == end_epoch:
        return committee_weight * Uint64(end_slot - start_slot + 1)
    else:
        # First, calculate the number of committees in the end epoch
        num_slots_in_end_epoch = Uint64(compute_slots_since_epoch_start(end_slot) + 1)
        # Next, calculate the number of slots remaining in the end epoch
        remaining_slots_in_end_epoch = Uint64(SLOTS_PER_EPOCH) - num_slots_in_end_epoch
        # Then, calculate the number of slots in the start epoch
        num_slots_in_start_epoch = Uint64(
            SLOTS_PER_EPOCH - compute_slots_since_epoch_start(start_slot)
        )

        start_epoch_weight = committee_weight * num_slots_in_start_epoch
        end_epoch_weight = committee_weight * num_slots_in_end_epoch

        # A range that spans an epoch boundary, but does not span any full epoch
        # needs pro-rata calculation, see https://gist.github.com/saltiniroberto/9ee53d29c33878d79417abb2b4468c20
        # start_epoch_weight_pro_rated = start_epoch_weight * (1 - num_slots_in_end_epoch / SLOTS_PER_EPOCH)
        start_epoch_weight_pro_rated = (
            start_epoch_weight // Uint64(SLOTS_PER_EPOCH) * remaining_slots_in_end_epoch
        )

        return adjust_committee_weight_estimate_to_ensure_safety(
            start_epoch_weight_pro_rated + end_epoch_weight
        )


def get_equivocation_score(
    store: Store,
    balance_source: BeaconState,
    start_slot: Slot,
    end_slot: Slot,
) -> Gwei:
    """
    Return total weight of equivocating participants of all committees
    in the slots between ``start_slot`` and ``end_slot`` (inclusive of both).
    """
    committee_indices: Set[ValidatorIndex] = set()
    for slot in range(start_slot, end_slot + 1):
        committee_indices.update(get_slot_committee(store, Slot(slot)))

    # Keep equivocating validators that were active at the balance_source epoch to be consistent
    # with get_total_active_balance() computation
    active_equivocating_indices = [
        i
        for i in committee_indices.intersection(store.equivocating_indices)
        if is_active_validator(balance_source.validators[i], get_current_epoch(balance_source))
    ]

    return Gwei(
        sum(balance_source.validators[i].effective_balance for i in active_equivocating_indices)
    )


def compute_adversarial_weight(
    store: Store,
    balance_source: BeaconState,
    start_slot: Slot,
    end_slot: Slot,
) -> Gwei:
    """
    Return maximum possible adversarial weight in the committees of the slots
    between ``start_slot`` and ``end_slot`` (inclusive of both).
    """
    total_active_balance = get_total_active_balance(balance_source)
    maximum_weight = estimate_committee_weight_between_slots(
        total_active_balance, start_slot, end_slot
    )
    max_adversarial_weight = maximum_weight // 100 * config.CONFIRMATION_BYZANTINE_THRESHOLD

    # Discount total weight of equivocating validators
    equivocation_score = get_equivocation_score(store, balance_source, start_slot, end_slot)
    if max_adversarial_weight > equivocation_score:
        return max_adversarial_weight - equivocation_score
    else:
        return Gwei(0)


def get_adversarial_weight(store: Store, balance_source: BeaconState, block_root: Root) -> Gwei:
    """
    Return maximum adversarial weight that can support the block.
    """
    current_slot = get_current_slot(store)
    block = store.blocks[block_root]
    if get_block_epoch(store, block_root) > get_block_epoch(store, block.parent_root):
        # Use the first epoch slot as the start slot when crossing epoch boundary
        start_slot = compute_start_slot_at_epoch(get_block_epoch(store, block_root))
        return compute_adversarial_weight(store, balance_source, start_slot, current_slot - 1)
    else:
        return compute_adversarial_weight(store, balance_source, block.slot, current_slot - 1)


def compute_empty_slot_support_discount(
    store: Store, balance_source: BeaconState, block_root: Root
) -> Gwei:
    """
    Return weight that can be discounted during the safety threshold computation
    if there are empty slots preceding the block.
    """
    block = store.blocks[block_root]
    parent_block = store.blocks[block.parent_root]
    # No empty slot
    if parent_block.slot + 1 == block.slot:
        return Gwei(0)

    # Discount votes supporting the parent block if they are from the committees of empty slots
    parent_support_in_empty_slots = get_block_support_between_slots(
        store,
        balance_source,
        block.parent_root,
        parent_block.slot + 1,
        block.slot - 1,
    )
    # Adversarial weight is not discounted
    adversarial_weight = compute_adversarial_weight(
        store, balance_source, parent_block.slot + 1, block.slot - 1
    )
    if parent_support_in_empty_slots > adversarial_weight:
        return parent_support_in_empty_slots - adversarial_weight
    else:
        return Gwei(0)


def get_support_discount(store: Store, balance_source: BeaconState, block_root: Root) -> Gwei:
    """
    Return weight that can be discounted during the safety threshold computation for the block.
    """
    return compute_empty_slot_support_discount(store, balance_source, block_root)


def compute_safety_threshold(store: Store, block_root: Root, balance_source: BeaconState) -> Gwei:
    """
    Compute the LMD-GHOST safety threshold for ``block_root``.
    """
    current_slot = get_current_slot(store)
    block = store.blocks[block_root]
    parent_block = store.blocks[block.parent_root]

    total_active_balance = get_total_active_balance(balance_source)
    proposer_score = compute_proposer_score(balance_source)
    maximum_support = estimate_committee_weight_between_slots(
        total_active_balance, parent_block.slot + 1, current_slot - 1
    )
    support_discount = get_support_discount(store, balance_source, block_root)
    adversarial_weight = get_adversarial_weight(store, balance_source, block_root)

    # Return (maximum_support + proposer_score - support_discount) // 2 + adversarial_weight
    # with an underflow guard
    if support_discount < maximum_support + proposer_score + 2 * adversarial_weight:
        return (maximum_support + proposer_score + 2 * adversarial_weight - support_discount) // 2
    else:
        return Gwei(0)


def is_one_confirmed(store: Store, balance_source: BeaconState, block_root: Root) -> bool:
    """
    Return ``True`` if and only if the block is LMD-GHOST safe.
    """
    support = get_attestation_score(store, get_node_for_root(block_root), balance_source)
    safety_threshold = compute_safety_threshold(store, block_root, balance_source)
    return support > safety_threshold


def is_confirmed_chain_safe(fcr_store: FastConfirmationStore, confirmed_root: Root) -> bool:
    """
    Return ``True`` if and only if all blocks of the confirmed chain
    starting from current_epoch_observed_justified_checkpoint are LMD-GHOST safe.
    """
    store = fcr_store.store
    # Check if the confirmed_root has current_epoch_observed_justified_checkpoint in its chain
    if fcr_store.current_epoch_observed_justified_checkpoint != get_checkpoint_for_block(
        store, confirmed_root, fcr_store.current_epoch_observed_justified_checkpoint.epoch
    ):
        return False

    current_epoch = get_current_store_epoch(store)
    if fcr_store.current_epoch_observed_justified_checkpoint.epoch + 1 >= current_epoch:
        # Exclude the justified checkpoint block if it is from the previous epoch
        # as then this block will always be canonical in this case.
        start_root_exclusive = fcr_store.current_epoch_observed_justified_checkpoint.root
    else:
        # Limit reconfirmation to the first block of the previous epoch
        # as if it is successful, reconfirmation of the ancestors is implied.
        ancestor_at_previous_epoch_start = get_ancestor(
            store,
            get_node_for_root(confirmed_root),
            compute_start_slot_at_epoch(current_epoch - 1),
        ).root
        if get_block_epoch(store, ancestor_at_previous_epoch_start) + 1 == current_epoch:
            # The parent of the first block of the previous epoch
            start_root_exclusive = store.blocks[ancestor_at_previous_epoch_start].parent_root
        else:
            # The last block of the epoch before the previous one
            start_root_exclusive = ancestor_at_previous_epoch_start

    # Run is_one_confirmed for each block in the confirmed chain with the previous epoch balance source
    chain_roots = get_ancestor_roots(store, confirmed_root, start_root_exclusive)
    return all(
        is_one_confirmed(store, get_previous_balance_source(fcr_store), root)
        for root in chain_roots
    )


def get_current_target_score(store: Store) -> Gwei:
    """
    Return the estimate of FFG support of the current epoch target by using LMD-GHOST votes.
    """
    target = get_current_target(store)
    state = get_pulled_up_head_state(store)
    unslashed_and_active_indices = [
        i
        for i in get_active_validator_indices(state, get_current_epoch(state))
        if not state.validators[i].slashed
    ]
    return Gwei(
        sum(
            state.validators[i].effective_balance
            for i in unslashed_and_active_indices
            if (
                i in store.latest_messages
                and i not in store.equivocating_indices
                and target
                == get_checkpoint_for_block(
                    store,
                    store.latest_messages[i].root,
                    get_latest_message_epoch(store.latest_messages[i]),
                )
            )
        )
    )


def compute_honest_ffg_support_for_current_target(store: Store) -> Gwei:
    """
    Compute honest FFG support of the current epoch target.
    """
    current_slot = get_current_slot(store)
    current_epoch = compute_epoch_at_slot(current_slot)
    balance_source = get_pulled_up_head_state(store)
    total_active_balance = get_total_active_balance(balance_source)

    # Compute FFG support for the target
    ffg_support_for_checkpoint = get_current_target_score(store)

    # Compute the total FFG weight up to, but excluding, the current slot
    ffg_weight_till_now = estimate_committee_weight_between_slots(
        total_active_balance, compute_start_slot_at_epoch(current_epoch), current_slot - 1
    )

    # Compute remaining honest FFG weight
    remaining_ffg_weight = total_active_balance - ffg_weight_till_now
    remaining_honest_ffg_weight = (
        remaining_ffg_weight // 100 * (100 - config.CONFIRMATION_BYZANTINE_THRESHOLD)
    )

    # Compute potential adversarial weight
    adversarial_weight = compute_adversarial_weight(
        store, balance_source, compute_start_slot_at_epoch(current_epoch), current_slot - 1
    )

    # Compute min honest FFG support
    min_honest_ffg_support = ffg_support_for_checkpoint - min(
        adversarial_weight, ffg_support_for_checkpoint
    )

    return min_honest_ffg_support + remaining_honest_ffg_weight


def will_no_conflicting_checkpoint_be_justified(store: Store) -> bool:
    """
    Return ``True`` if and only if no checkpoint conflicting with the current target can ever be justified.
    """

    # If the target is unrealized justified then no conflicting checkpoint can be justified
    if get_current_target(store) == store.unrealized_justified_checkpoint:
        return True

    state = get_pulled_up_head_state(store)
    total_active_balance = get_total_active_balance(state)
    honest_ffg_support = compute_honest_ffg_support_for_current_target(store)
    return 3 * honest_ffg_support > 1 * total_active_balance


def will_current_target_be_justified(store: Store) -> bool:
    """
    Return ``True`` if and only if the current target will eventually be justified.
    """
    state = get_pulled_up_head_state(store)
    total_active_balance = get_total_active_balance(state)
    honest_ffg_support = compute_honest_ffg_support_for_current_target(store)
    return 3 * honest_ffg_support >= 2 * total_active_balance


def update_fast_confirmation_variables(fcr_store: FastConfirmationStore) -> None:
    # Update prev and curr slot head
    store = fcr_store.store
    fcr_store.previous_slot_head = fcr_store.current_slot_head
    fcr_store.current_slot_head = get_head(store).root

    # Update greatest unrealized justified checkpoint at the last slot of an epoch
    if is_start_slot_at_epoch(get_current_slot(store) + 1):
        fcr_store.previous_epoch_greatest_unrealized_checkpoint = (
            store.unrealized_justified_checkpoint
        )

    # Update observed justified checkpoints at the start of an epoch
    if is_start_slot_at_epoch(get_current_slot(store)):
        fcr_store.previous_epoch_observed_justified_checkpoint = (
            fcr_store.current_epoch_observed_justified_checkpoint
        )
        fcr_store.current_epoch_observed_justified_checkpoint = (
            fcr_store.previous_epoch_greatest_unrealized_checkpoint
        )


def find_latest_confirmed_descendant(
    fcr_store: FastConfirmationStore, latest_confirmed_root: Root
) -> Root:
    """
    Return the most recent confirmed block in the suffix of the canonical chain
    starting from ``latest_confirmed_root``.
    """
    store = fcr_store.store
    head = get_head(store).root
    current_epoch = get_current_store_epoch(store)
    confirmed_root = latest_confirmed_root

    if (
        get_block_epoch(store, confirmed_root) + 1 == current_epoch
        and get_voting_source(store, fcr_store.previous_slot_head).epoch + 2 >= current_epoch
        and (
            is_start_slot_at_epoch(get_current_slot(store))
            or (
                will_no_conflicting_checkpoint_be_justified(store)
                and (
                    store.unrealized_justifications[fcr_store.previous_slot_head].epoch + 1
                    >= current_epoch
                    or store.unrealized_justifications[head].epoch + 1 >= current_epoch
                )
            )
        )
    ):
        # Get suffix of the canonical chain
        canonical_roots = get_ancestor_roots(store, head, confirmed_root)

        # Starting with the child of the latest_confirmed_root
        # move towards the head in attempt to advance the confirmed block
        # and stop when the first unconfirmed descendant is encountered
        for block_root in canonical_roots:
            block_epoch = get_block_epoch(store, block_root)

            # If the current epoch is reached, exit the loop
            # as this code is meant to confirm blocks from the previous epoch
            if block_epoch == current_epoch:
                break

            # The algorithm can only rely on the previous head
            # if it is a descendant of the block that is attempted to be confirmed
            if not is_ancestor(
                store,
                get_node_for_root(fcr_store.previous_slot_head),
                get_node_for_root(block_root),
            ):
                break

            if not is_one_confirmed(store, get_current_balance_source(fcr_store), block_root):
                break

            confirmed_root = block_root

    if (
        is_start_slot_at_epoch(get_current_slot(store))
        or store.unrealized_justifications[head].epoch + 1 >= current_epoch
    ):
        # Get suffix of the canonical chain
        canonical_roots = get_ancestor_roots(store, head, confirmed_root)

        tentative_confirmed_root = confirmed_root

        for block_root in canonical_roots:
            block_epoch = get_block_epoch(store, block_root)
            tentative_confirmed_epoch = get_block_epoch(store, tentative_confirmed_root)

            # The following condition can only be true the first time
            # the algorithm advances to a block from the current epoch
            if block_epoch > tentative_confirmed_epoch:
                # To confirm blocks from the current epoch ensure that
                # current epoch target will be justified
                if not will_current_target_be_justified(store):
                    break

            if not is_one_confirmed(store, get_current_balance_source(fcr_store), block_root):
                break

            tentative_confirmed_root = block_root

        # The tentative_confirmed_root can only be confirmed
        # if it is for sure not going to be reorged out in either the current or next epoch.
        if get_block_epoch(store, tentative_confirmed_root) == current_epoch or (
            get_voting_source(store, tentative_confirmed_root).epoch + 2 >= current_epoch
            and (
                is_start_slot_at_epoch(get_current_slot(store))
                or will_no_conflicting_checkpoint_be_justified(store)
            )
        ):
            confirmed_root = tentative_confirmed_root

    return confirmed_root


def get_latest_confirmed(fcr_store: FastConfirmationStore) -> Root:
    """
    Return the most recent confirmed block by executing the FCR algorithm.
    """
    store = fcr_store.store
    confirmed_root = fcr_store.confirmed_root
    current_epoch = get_current_store_epoch(store)

    # Revert to finalized block if either of the following is true:
    # 1) the latest confirmed block's epoch is older than the previous epoch,
    # 2) the latest confirmed block does not belong to the canonical chain,
    # 3) the confirmed chain starting from the current epoch observed justified checkpoint
    #    cannot be re-confirmed at the start of the current epoch.
    head = get_head(store).root
    if (
        get_block_epoch(store, confirmed_root) + 1 < current_epoch
        or not is_ancestor(store, get_node_for_root(head), get_node_for_root(confirmed_root))
        or (
            is_start_slot_at_epoch(get_current_slot(store))
            and not is_confirmed_chain_safe(fcr_store, confirmed_root)
        )
    ):
        confirmed_root = store.finalized_checkpoint.root

    # Restart the confirmation chain if each of the following conditions are true:
    # 1) it is the start of the current epoch,
    # 2) epoch of fcr_store.current_epoch_observed_justified_checkpoint.root equals to the previous epoch,
    # 3) fcr_store.current_epoch_observed_justified_checkpoint equals to unrealized justification of the head,
    # 4) confirmed block is older than the block of fcr_store.current_epoch_observed_justified_checkpoint.
    is_epoch_start = is_start_slot_at_epoch(get_current_slot(store))
    observed_justified_block_slot = get_block_slot(
        store, fcr_store.current_epoch_observed_justified_checkpoint.root
    )
    is_observed_justified_block_epoch_ok = (
        compute_epoch_at_slot(observed_justified_block_slot) + 1 == current_epoch
    )
    is_head_unrealized_justified_ok = (
        fcr_store.current_epoch_observed_justified_checkpoint
        == store.unrealized_justifications[head]
    )
    is_confirmed_block_stale = get_block_slot(store, confirmed_root) < observed_justified_block_slot
    if (
        is_epoch_start
        and is_observed_justified_block_epoch_ok
        and is_head_unrealized_justified_ok
        and is_confirmed_block_stale
    ):
        confirmed_root = fcr_store.current_epoch_observed_justified_checkpoint.root

    # Attempt to further advance the latest confirmed block
    if get_block_epoch(store, confirmed_root) + 1 >= current_epoch:
        return find_latest_confirmed_descendant(fcr_store, confirmed_root)
    else:
        return confirmed_root


def on_fast_confirmation(fcr_store: FastConfirmationStore) -> None:
    update_fast_confirmation_variables(fcr_store)
    fcr_store.confirmed_root = get_latest_confirmed(fcr_store)


def get_forkchoice_store(anchor_state: BeaconState, anchor_block: BeaconBlock) -> Store:
    assert anchor_block.state_root == hash_tree_root(anchor_state)
    anchor_root = hash_tree_root(anchor_block)
    anchor_epoch = get_current_epoch(anchor_state)
    justified_checkpoint = Checkpoint(epoch=anchor_epoch, root=anchor_root)
    finalized_checkpoint = Checkpoint(epoch=anchor_epoch, root=anchor_root)
    proposer_boost_root = Root()
    return Store(
        time=Uint64(anchor_state.genesis_time + config.SLOT_DURATION_MS * anchor_state.slot // 1000),
        genesis_time=anchor_state.genesis_time,
        justified_checkpoint=justified_checkpoint,
        finalized_checkpoint=finalized_checkpoint,
        unrealized_justified_checkpoint=justified_checkpoint,
        unrealized_finalized_checkpoint=finalized_checkpoint,
        proposer_boost_root=proposer_boost_root,
        equivocating_indices=set(),
        blocks={anchor_root: anchor_block.copy()},
        block_states={anchor_root: anchor_state.copy()},
        block_timeliness={},
        checkpoint_states={justified_checkpoint: anchor_state.copy()},
        latest_messages={},
        unrealized_justifications={anchor_root: justified_checkpoint},
    )


def get_slots_since_genesis(store: Store) -> int:
    return (store.time - store.genesis_time) * 1000 // config.SLOT_DURATION_MS


def get_current_slot(store: Store) -> Slot:
    return GENESIS_SLOT + get_slots_since_genesis(store)


def get_current_store_epoch(store: Store) -> Epoch:
    return compute_epoch_at_slot(get_current_slot(store))


def compute_slots_since_epoch_start(slot: Slot) -> int:
    return slot - compute_start_slot_at_epoch(compute_epoch_at_slot(slot))


def get_ancestor(store: Store, node: ForkChoiceNode, slot: Slot) -> ForkChoiceNode:
    block = store.blocks[node.root]
    if block.slot > slot:
        parent = ForkChoiceNode(root=block.parent_root)
        return get_ancestor(store, parent, slot)
    return node


def is_ancestor(store: Store, node: ForkChoiceNode, ancestor: ForkChoiceNode) -> bool:
    return get_ancestor(store, node, store.blocks[ancestor.root].slot) == ancestor


def calculate_committee_fraction(state: BeaconState, committee_percent: Uint64) -> Gwei:
    committee_weight = get_total_active_balance(state) // Uint64(SLOTS_PER_EPOCH)
    return (committee_weight * committee_percent) // 100


def get_checkpoint_block(store: Store, root: Root, epoch: Epoch) -> Root:
    """
    Compute the checkpoint block for epoch ``epoch`` in the chain of block ``root``
    """
    epoch_first_slot = compute_start_slot_at_epoch(epoch)
    node = ForkChoiceNode(root=root)
    return get_ancestor(store, node, epoch_first_slot).root


def get_supported_node(
    store: Store,  # noqa: ARG001
    message: LatestMessage,
) -> ForkChoiceNode:
    """
    Return a node supported by the ``message``.
    """
    return ForkChoiceNode(root=message.root)


def get_attestation_score(store: Store, node: ForkChoiceNode, state: BeaconState) -> Gwei:
    unslashed_and_active_indices = [
        i
        for i in get_active_validator_indices(state, get_current_epoch(state))
        if not state.validators[i].slashed
    ]
    return Gwei(
        sum(
            state.validators[i].effective_balance
            for i in unslashed_and_active_indices
            if (
                i in store.latest_messages
                and i not in store.equivocating_indices
                and is_ancestor(store, get_supported_node(store, store.latest_messages[i]), node)
            )
        )
    )


def compute_proposer_score(state: BeaconState) -> Gwei:
    committee_weight = get_total_active_balance(state) // Uint64(SLOTS_PER_EPOCH)
    return (committee_weight * config.PROPOSER_SCORE_BOOST) // 100


def get_proposer_score(store: Store) -> Gwei:
    justified_checkpoint_state = store.checkpoint_states[store.justified_checkpoint]
    return compute_proposer_score(justified_checkpoint_state)


def get_weight(store: Store, node: ForkChoiceNode) -> Gwei:
    state = store.checkpoint_states[store.justified_checkpoint]
    attestation_score = get_attestation_score(store, node, state)
    if store.proposer_boost_root == Root():
        # Return only attestation score if ``proposer_boost_root`` is not set
        return attestation_score

    # Calculate proposer score if ``proposer_boost_root`` is set
    proposer_score = Gwei(0)
    proposer_boost_node = ForkChoiceNode(root=store.proposer_boost_root)
    # Boost is applied if ``node`` is an ancestor of ``proposer_boost_node``
    if is_ancestor(store, proposer_boost_node, node):
        proposer_score = get_proposer_score(store)

    return attestation_score + proposer_score


def get_voting_source(store: Store, block_root: Root) -> Checkpoint:
    """
    Compute the voting source checkpoint in event that block with root ``block_root`` is the head block
    """
    block = store.blocks[block_root]
    current_epoch = get_current_store_epoch(store)
    block_epoch = compute_epoch_at_slot(block.slot)
    if current_epoch > block_epoch:
        # The block is from a prior epoch, the voting source will be pulled-up
        return store.unrealized_justifications[block_root]
    else:
        # The block is not from a prior epoch, therefore the voting source is not pulled up
        head_state = store.block_states[block_root]
        return head_state.current_justified_checkpoint


def filter_block_tree(store: Store, block_root: Root, blocks: Dict[Root, BeaconBlock]) -> bool:
    block = store.blocks[block_root]
    children = [root for root in store.blocks if store.blocks[root].parent_root == block_root]

    # If any children branches contain expected finalized/justified checkpoints,
    # add to filtered block-tree and signal viability to parent.
    if any(children):
        filter_block_tree_result = [filter_block_tree(store, child, blocks) for child in children]
        if any(filter_block_tree_result):
            blocks[block_root] = block
            return True
        return False

    current_epoch = get_current_store_epoch(store)
    voting_source = get_voting_source(store, block_root)

    # The voting source should be either at the same height as the store's justified checkpoint or
    # not more than two epochs ago
    correct_justified = (
        store.justified_checkpoint.epoch == GENESIS_EPOCH
        or voting_source.epoch == store.justified_checkpoint.epoch
        or voting_source.epoch + 2 >= current_epoch
    )

    finalized_checkpoint_block = get_checkpoint_block(
        store,
        block_root,
        store.finalized_checkpoint.epoch,
    )

    correct_finalized = (
        store.finalized_checkpoint.epoch == GENESIS_EPOCH
        or store.finalized_checkpoint.root == finalized_checkpoint_block
    )

    # If expected finalized/justified, add to viable block-tree and signal viability to parent.
    if correct_justified and correct_finalized:
        blocks[block_root] = block
        return True

    # Otherwise, branch not viable
    return False


def get_filtered_block_tree(store: Store) -> Dict[Root, BeaconBlock]:
    """
    Retrieve a filtered block tree from ``store``, only returning branches
    whose leaf state's justified/finalized info agrees with that in ``store``.
    """
    base = store.justified_checkpoint.root
    blocks: Dict[Root, BeaconBlock] = {}
    filter_block_tree(store, base, blocks)
    return blocks


def get_node_children(
    store: Store,  # noqa: ARG001
    blocks: Dict[Root, BeaconBlock],
    node: ForkChoiceNode,
) -> Sequence[ForkChoiceNode]:
    return [ForkChoiceNode(root=root) for root in blocks if blocks[root].parent_root == node.root]


def get_head(store: Store) -> ForkChoiceNode:
    # Get filtered block tree that only includes viable branches
    blocks = get_filtered_block_tree(store)
    # Execute the LMD-GHOST fork choice
    head = ForkChoiceNode(root=store.justified_checkpoint.root)
    while True:
        children = get_node_children(store, blocks, head)
        if len(children) == 0:
            return head
        # Sort by latest attesting balance with ties broken lexicographically
        # Ties broken by favoring block with lexicographically higher root
        head = max(children, key=lambda child: (get_weight(store, child), child.root))


def update_checkpoints(
    store: Store, justified_checkpoint: Checkpoint, finalized_checkpoint: Checkpoint
) -> None:
    """
    Update checkpoints in store if necessary
    """
    # Update justified checkpoint
    if justified_checkpoint.epoch > store.justified_checkpoint.epoch:
        store.justified_checkpoint = justified_checkpoint

    # Update finalized checkpoint
    if finalized_checkpoint.epoch > store.finalized_checkpoint.epoch:
        store.finalized_checkpoint = finalized_checkpoint


def update_unrealized_checkpoints(
    store: Store,
    unrealized_justified_checkpoint: Checkpoint,
    unrealized_finalized_checkpoint: Checkpoint,
) -> None:
    """
    Update unrealized checkpoints in store if necessary
    """
    # Update unrealized justified checkpoint
    if unrealized_justified_checkpoint.epoch > store.unrealized_justified_checkpoint.epoch:
        store.unrealized_justified_checkpoint = unrealized_justified_checkpoint

    # Update unrealized finalized checkpoint
    if unrealized_finalized_checkpoint.epoch > store.unrealized_finalized_checkpoint.epoch:
        store.unrealized_finalized_checkpoint = unrealized_finalized_checkpoint


def get_latest_message_epoch(latest_message: LatestMessage) -> Epoch:
    """
    Return epoch of the ``latest_message``.
    """
    return latest_message.epoch


def seconds_to_milliseconds(seconds: Uint64) -> Uint64:
    """
    Convert seconds to milliseconds with overflow protection.
    Returns ``UINT64_MAX`` if the result would overflow.
    """
    if seconds > UINT64_MAX // 1000:
        return UINT64_MAX
    return seconds * 1000


def get_slot_component_duration_ms(basis_points: Uint64) -> Uint64:
    """
    Calculate the duration of a slot component in milliseconds.
    """
    return basis_points * config.SLOT_DURATION_MS // BASIS_POINTS


def get_attestation_due_ms() -> Uint64:
    return get_slot_component_duration_ms(config.ATTESTATION_DUE_BPS)


def get_proposer_reorg_cutoff_ms() -> Uint64:
    return get_slot_component_duration_ms(config.PROPOSER_REORG_CUTOFF_BPS)


def get_aggregate_due_ms() -> Uint64:
    return get_slot_component_duration_ms(config.AGGREGATE_DUE_BPS)


def is_head_late(store: Store, head_root: Root) -> bool:
    return not store.block_timeliness[head_root]


def is_shuffling_stable(slot: Slot) -> bool:
    return slot % SLOTS_PER_EPOCH != 0


def is_ffg_competitive(store: Store, head_root: Root, parent_root: Root) -> bool:
    return (
        store.unrealized_justifications[head_root] == store.unrealized_justifications[parent_root]
    )


def is_finalization_ok(store: Store, slot: Slot) -> bool:
    epochs_since_finalization = compute_epoch_at_slot(slot) - store.finalized_checkpoint.epoch
    return epochs_since_finalization <= config.REORG_MAX_EPOCHS_SINCE_FINALIZATION


def is_proposing_on_time(store: Store) -> bool:
    seconds_since_genesis = store.time - store.genesis_time
    time_into_slot_ms = seconds_to_milliseconds(seconds_since_genesis) % config.SLOT_DURATION_MS
    proposer_reorg_cutoff_ms = get_proposer_reorg_cutoff_ms()
    return time_into_slot_ms <= proposer_reorg_cutoff_ms


def is_head_weak(store: Store, head_root: Root) -> bool:
    # Calculate weight threshold for weak head
    justified_state = store.checkpoint_states[store.justified_checkpoint]
    reorg_threshold = calculate_committee_fraction(justified_state, config.REORG_HEAD_WEIGHT_THRESHOLD)

    # Compute head weight including equivocations
    head_state = store.block_states[head_root]
    head_block = store.blocks[head_root]
    epoch = compute_epoch_at_slot(head_block.slot)
    head_node = ForkChoiceNode(root=head_root)
    head_weight = get_attestation_score(store, head_node, justified_state)
    for index in range(get_committee_count_per_slot(head_state, epoch)):
        committee = get_beacon_committee(head_state, head_block.slot, CommitteeIndex(index))
        head_weight += Gwei(
            sum(
                justified_state.validators[i].effective_balance
                for i in committee
                if i in store.equivocating_indices
            )
        )

    return head_weight < reorg_threshold


def is_parent_strong(store: Store, root: Root) -> bool:
    justified_state = store.checkpoint_states[store.justified_checkpoint]
    parent_threshold = calculate_committee_fraction(justified_state, config.REORG_PARENT_WEIGHT_THRESHOLD)
    parent_root = store.blocks[root].parent_root
    parent_node = ForkChoiceNode(root=parent_root)
    parent_weight = get_attestation_score(store, parent_node, justified_state)
    return parent_weight > parent_threshold


def is_proposer_equivocation(store: Store, root: Root) -> bool:
    block = store.blocks[root]
    proposer_index = block.proposer_index
    slot = block.slot
    # roots from the same slot and proposer
    matching_roots = [
        root
        for root, block in store.blocks.items()
        if (block.proposer_index == proposer_index and block.slot == slot)
    ]
    return len(matching_roots) > 1


def get_proposer_head(store: Store, head_node: ForkChoiceNode, slot: Slot) -> ForkChoiceNode:
    head_block = store.blocks[head_node.root]
    parent_root = head_block.parent_root
    parent_block = store.blocks[parent_root]
    parent_node = ForkChoiceNode(root=parent_root)

    # Only re-org the head block if it arrived later than the attestation deadline.
    head_late = is_head_late(store, head_node.root)

    # Do not re-org on an epoch boundary where the proposer shuffling could change.
    shuffling_stable = is_shuffling_stable(slot)

    # Ensure that the FFG information of the new head will be competitive with the current head.
    ffg_competitive = is_ffg_competitive(store, head_node.root, parent_root)

    # Do not re-org if the chain is not finalizing with acceptable frequency.
    finalization_ok = is_finalization_ok(store, slot)

    # Only re-org if we are proposing on-time.
    proposing_on_time = is_proposing_on_time(store)

    # Only re-org a single slot at most.
    parent_slot_ok = parent_block.slot + 1 == head_block.slot
    current_time_ok = head_block.slot + 1 == slot
    single_slot_reorg = parent_slot_ok and current_time_ok

    # Check that the head has few enough votes to be overpowered by our proposer boost.
    assert store.proposer_boost_root != head_node.root  # ensure boost has worn off
    head_weak = is_head_weak(store, head_node.root)

    # Check that the missing votes are assigned to the parent and not being hoarded.
    parent_strong = is_parent_strong(store, head_node.root)

    # Re-org more aggressively if there is a proposer equivocation in the previous slot.
    proposer_equivocation = is_proposer_equivocation(store, head_node.root)

    if all([
        head_late,
        shuffling_stable,
        ffg_competitive,
        finalization_ok,
        proposing_on_time,
        single_slot_reorg,
        head_weak,
        parent_strong,
    ]):
        # We can re-org the current head by building upon its parent node.
        return parent_node
    elif all([head_weak, current_time_ok, proposer_equivocation]):
        return parent_node
    else:
        return head_node


def compute_pulled_up_tip(store: Store, block_root: Root) -> None:
    state = store.block_states[block_root].copy()
    # Pull up the post-state of the block to the next epoch boundary
    process_justification_and_finalization(state)

    store.unrealized_justifications[block_root] = state.current_justified_checkpoint
    update_unrealized_checkpoints(
        store, state.current_justified_checkpoint, state.finalized_checkpoint
    )

    # If the block is from a prior epoch, apply the realized values
    block_epoch = compute_epoch_at_slot(store.blocks[block_root].slot)
    current_epoch = get_current_store_epoch(store)
    if block_epoch < current_epoch:
        update_checkpoints(store, state.current_justified_checkpoint, state.finalized_checkpoint)


def on_tick_per_slot(store: Store, time: Uint64) -> None:
    previous_slot = get_current_slot(store)

    # Update store time
    store.time = time

    current_slot = get_current_slot(store)

    # If this is a new slot, reset store.proposer_boost_root
    if current_slot > previous_slot:
        store.proposer_boost_root = Root()

    # If a new epoch, pull-up justification and finalization from previous epoch
    if current_slot > previous_slot and compute_slots_since_epoch_start(current_slot) == 0:
        update_checkpoints(
            store, store.unrealized_justified_checkpoint, store.unrealized_finalized_checkpoint
        )


def validate_target_epoch_against_current_time(store: Store, attestation: Attestation) -> None:
    target = attestation.data.target

    # Attestations must be from the current or previous epoch
    current_epoch = get_current_store_epoch(store)
    # Use GENESIS_EPOCH for previous when genesis to avoid underflow
    previous_epoch = current_epoch - 1 if current_epoch > GENESIS_EPOCH else GENESIS_EPOCH
    # If attestation target is from a future epoch, delay consideration until the epoch arrives
    assert target.epoch in [current_epoch, previous_epoch]


def validate_on_attestation(store: Store, attestation: Attestation, is_from_block: bool) -> None:
    target = attestation.data.target

    # If the given attestation is not from a beacon block message, we have to check the target epoch scope.
    if not is_from_block:
        validate_target_epoch_against_current_time(store, attestation)

    # Check that the epoch number and slot number are matching
    assert target.epoch == compute_epoch_at_slot(attestation.data.slot)

    # Attestation target must be for a known block. If target block is unknown, delay consideration until block is found
    assert target.root in store.blocks

    # Attestations must be for a known block. If block is unknown, delay consideration until the block is found
    assert attestation.data.beacon_block_root in store.blocks
    # Attestations must not be for blocks in the future. If not, the attestation should not be considered
    assert store.blocks[attestation.data.beacon_block_root].slot <= attestation.data.slot

    # LMD vote must be consistent with FFG vote target
    assert target.root == get_checkpoint_block(
        store, attestation.data.beacon_block_root, target.epoch
    )

    # Attestations can only affect the fork choice of subsequent slots.
    # Delay consideration in the fork choice until their slot is in the past.
    assert get_current_slot(store) >= attestation.data.slot + 1


def store_target_checkpoint_state(store: Store, target: Checkpoint) -> None:
    # Store target checkpoint state if not yet seen
    if target not in store.checkpoint_states:
        base_state = store.block_states[target.root].copy()
        if base_state.slot < compute_start_slot_at_epoch(target.epoch):
            process_slots(base_state, compute_start_slot_at_epoch(target.epoch))
        store.checkpoint_states[target] = base_state


def update_latest_messages(
    store: Store, attesting_indices: Sequence[ValidatorIndex], attestation: Attestation
) -> None:
    target = attestation.data.target
    beacon_block_root = attestation.data.beacon_block_root
    non_equivocating_attesting_indices = [
        i for i in attesting_indices if i not in store.equivocating_indices
    ]
    for i in non_equivocating_attesting_indices:
        if i not in store.latest_messages or target.epoch > store.latest_messages[i].epoch:
            store.latest_messages[i] = LatestMessage(epoch=target.epoch, root=beacon_block_root)


def record_block_timeliness(store: Store, root: Root) -> None:
    block = store.blocks[root]
    seconds_since_genesis = store.time - store.genesis_time
    time_into_slot_ms = seconds_to_milliseconds(seconds_since_genesis) % config.SLOT_DURATION_MS
    attestation_threshold_ms = get_attestation_due_ms()
    is_before_attesting_interval = time_into_slot_ms < attestation_threshold_ms
    is_timely = get_current_slot(store) == block.slot and is_before_attesting_interval
    store.block_timeliness[root] = is_timely


def compute_shuffling_dependent_slot(epoch: Epoch) -> Slot:
    if epoch <= MIN_SEED_LOOKAHEAD:
        return GENESIS_SLOT
    return compute_start_slot_at_epoch(epoch - MIN_SEED_LOOKAHEAD) - 1


def get_shuffling_dependent_root(store: Store, root: Root, epoch: Epoch) -> Root:
    node = ForkChoiceNode(root=root)
    dependent_slot = compute_shuffling_dependent_slot(epoch)
    return get_ancestor(store, node, dependent_slot).root


def update_proposer_boost_root(store: Store, head: Root, root: Root) -> None:
    is_first_block = store.proposer_boost_root == Root()
    is_timely = store.block_timeliness[root]
    epoch = get_current_store_epoch(store)
    head_dependent_root = get_shuffling_dependent_root(store, head, epoch)
    block_dependent_root = get_shuffling_dependent_root(store, root, epoch)
    is_same_dependent_root = head_dependent_root == block_dependent_root

    # Add proposer score boost if the block is timely, not conflicting with an
    # existing block, with the same dependent root as the canonical chain head.
    if is_timely and is_first_block and is_same_dependent_root:
        store.proposer_boost_root = root


def on_tick(store: Store, time: Uint64) -> None:
    # If the ``store.time`` falls behind, while loop catches up slot by slot
    # to ensure that every previous slot is processed with ``on_tick_per_slot``
    tick_slot = (time - store.genesis_time) * 1000 // config.SLOT_DURATION_MS
    while get_current_slot(store) < tick_slot:
        previous_time = (
            store.genesis_time + (get_current_slot(store) + 1) * config.SLOT_DURATION_MS // 1000
        )
        on_tick_per_slot(store, previous_time)
    on_tick_per_slot(store, time)


def on_block(store: Store, signed_block: SignedBeaconBlock) -> None:
    """
    Run ``on_block`` upon receiving a new block.
    """
    block = signed_block.message
    block_root = hash_tree_root(block)

    # Return early if the block is already known
    if block_root in store.blocks:
        return

    # Parent block must be known
    assert block.parent_root in store.block_states
    # Make a copy of the state to avoid mutability issues
    pre_state = store.block_states[block.parent_root].copy()
    # Blocks cannot be in the future. If they are, their consideration must be delayed until they are in the past.
    assert get_current_slot(store) >= block.slot

    # Check that block is later than the finalized epoch slot (optimization to reduce calls to get_ancestor)
    finalized_slot = compute_start_slot_at_epoch(store.finalized_checkpoint.epoch)
    assert block.slot > finalized_slot
    # Check block is a descendant of the finalized block at the checkpoint finalized slot
    finalized_checkpoint_block = get_checkpoint_block(
        store,
        block.parent_root,
        store.finalized_checkpoint.epoch,
    )
    assert store.finalized_checkpoint.root == finalized_checkpoint_block

    # Check the block is valid and compute the post-state
    state = pre_state.copy()
    state_transition(state, signed_block, validate_result=True)

    # Compute head before applying the block
    head = get_head(store)
    # Add new block to the store
    store.blocks[block_root] = block
    # Add new state for this block to the store
    store.block_states[block_root] = state

    record_block_timeliness(store, block_root)
    update_proposer_boost_root(store, head.root, block_root)

    # Update checkpoints in store if necessary
    update_checkpoints(store, state.current_justified_checkpoint, state.finalized_checkpoint)

    # Eagerly compute unrealized justification and finality
    compute_pulled_up_tip(store, block_root)


def on_attestation(store: Store, attestation: Attestation, is_from_block: bool = False) -> None:
    """
    Run ``on_attestation`` upon receiving a new attestation from either within a block or directly on the wire.

    An ``attestation`` that is asserted as invalid may be valid at a later time,
    consider scheduling it for later processing in such case.
    """
    validate_on_attestation(store, attestation, is_from_block)

    store_target_checkpoint_state(store, attestation.data.target)

    # Get state at the `target` to fully validate attestation
    target_state = store.checkpoint_states[attestation.data.target]
    indexed_attestation = get_indexed_attestation(target_state, attestation)
    assert is_valid_indexed_attestation(target_state, indexed_attestation)

    # Update latest messages for attesting indices
    update_latest_messages(store, indexed_attestation.attesting_indices, attestation)


def on_attester_slashing(store: Store, attester_slashing: AttesterSlashing) -> None:
    """
    Run ``on_attester_slashing`` immediately upon receiving a new attester slashing
    from either within a block or directly on the wire.
    """
    attestation_1 = attester_slashing.attestation_1
    attestation_2 = attester_slashing.attestation_2
    assert is_slashable_attestation_data(attestation_1.data, attestation_2.data)
    state = store.block_states[store.justified_checkpoint.root]
    assert is_valid_indexed_attestation(state, attestation_1)
    assert is_valid_indexed_attestation(state, attestation_2)

    indices = set(attestation_1.attesting_indices).intersection(attestation_2.attesting_indices)
    for index in indices:
        store.equivocating_indices.add(index)


def compute_fork_version(epoch: Epoch) -> Version:  # noqa: ARG001
    """
    Return the fork version at the given ``epoch``.
    """
    return config.GENESIS_FORK_VERSION


def compute_fork_digest(
    genesis_validators_root: Root,
    epoch: Epoch,
) -> ForkDigest:
    """
    Return the 4-byte fork digest for the ``genesis_validators_root`` at a given ``epoch``.

    This is a digest primarily used for domain separation on the p2p layer.
    4-bytes suffices for practical separation of forks/chains.
    """
    fork_version = compute_fork_version(epoch)
    base_digest = compute_fork_data_root(fork_version, genesis_validators_root)
    return ForkDigest(base_digest[:4])


def compute_time_at_slot_ms(store: Store, slot: Slot) -> Uint64:
    """
    Return the time in milliseconds at the start of the given slot.
    """
    slots_since_genesis = slot - GENESIS_SLOT
    return Uint64(store.genesis_time * 1000 + slots_since_genesis * config.SLOT_DURATION_MS)


def is_future_slot(
    store: Store,
    slot: Slot,
    current_time_ms: Uint64,
) -> bool:
    """
    Check if the given slot is in the future
    (with config.MAXIMUM_GOSSIP_CLOCK_DISPARITY allowance).
    """
    slot_time_ms = compute_time_at_slot_ms(store, slot)
    return current_time_ms + config.MAXIMUM_GOSSIP_CLOCK_DISPARITY < slot_time_ms


def is_future_epoch(
    store: Store,
    epoch: Epoch,
    current_time_ms: Uint64,
) -> bool:
    """
    Check if the given epoch is in the future
    (with config.MAXIMUM_GOSSIP_CLOCK_DISPARITY allowance).
    """
    time_since_genesis_ms = current_time_ms - store.genesis_time * 1000
    time_since_genesis_ms += config.MAXIMUM_GOSSIP_CLOCK_DISPARITY
    current_slot = Slot(time_since_genesis_ms // config.SLOT_DURATION_MS)
    return compute_epoch_at_slot(current_slot) < epoch


def is_within_slot_range(
    store: Store,
    slot: Slot,
    slot_range: Uint64,
    current_time_ms: Uint64,
) -> bool:
    """
    Check if the current time is within the inclusive slot range ``[slot, slot + slot_range]``
    (with config.MAXIMUM_GOSSIP_CLOCK_DISPARITY allowance on both ends).
    """
    start_time_ms = compute_time_at_slot_ms(store, slot)
    if current_time_ms + config.MAXIMUM_GOSSIP_CLOCK_DISPARITY < start_time_ms:
        return False
    end_time_ms = compute_time_at_slot_ms(store, slot + slot_range + 1)
    if end_time_ms + config.MAXIMUM_GOSSIP_CLOCK_DISPARITY < current_time_ms:
        return False
    return True


def compute_attestation_subnet_prefix_bits() -> Uint64:
    """
    Return the number of NodeId bits to use when mapping to a subscribed subnet.
    """
    return ceillog2(config.ATTESTATION_SUBNET_COUNT) + config.ATTESTATION_SUBNET_EXTRA_BITS


def compute_min_epochs_for_block_requests() -> Uint64:
    """
    Return the minimum epoch range over which a node must serve blocks.
    """
    return Uint64(config.MIN_VALIDATOR_WITHDRAWABILITY_DELAY + config.CHURN_LIMIT_QUOTIENT // 2)


def is_non_strict_superset(
    seen_bits_set: Set[Tuple[bool, ...]],
    new_bits: Tuple[bool, ...],
) -> bool:
    """
    Return True if any prior bitset in ``seen_bits_set`` is a non-strict
    superset of ``new_bits`` (every bit set in new is also set in that prior).
    """
    for prior_bits in seen_bits_set:
        is_superset = True
        for prior_bit, new_bit in zip(prior_bits, new_bits, strict=True):
            if new_bit and not prior_bit:
                is_superset = False
                break
        if is_superset:
            return True
    return False


def max_compressed_len(n: Uint64) -> Uint64:
    # Worst-case compressed length for a given payload of size n when using snappy:
    # https://github.com/google/snappy/blob/32ded457c0b1fe78ceb8397632c416568d6714a0/snappy.cc#L218C1-L218C47
    return 32 + n + n // 6


def max_message_size() -> Uint64:
    # Allow 1024 bytes for framing and encoding overhead but at least 1MiB in case config.MAX_PAYLOAD_SIZE is small.
    return max(max_compressed_len(config.MAX_PAYLOAD_SIZE) + 1024, Uint64(1024 * 1024))


def validate_beacon_block_gossip(
    seen: Seen,
    store: Store,
    signed_beacon_block: SignedBeaconBlock,
    current_time_ms: Uint64,
) -> None:
    """
    Validate a SignedBeaconBlock for gossip propagation.
    Raises GossipIgnore or GossipReject on validation failure.
    """
    block = signed_beacon_block.message

    # [IGNORE] The block is the first block with valid signature received for the slot and proposer
    proposer_slot_key = (block.slot, block.proposer_index)
    if proposer_slot_key in seen.proposer_slots:
        raise GossipIgnore("block is not the first valid block for this slot and proposer")

    # [IGNORE] The block is not from a future slot
    # (MAY be queued for processing at the appropriate slot)
    if is_future_slot(store, block.slot, current_time_ms):
        raise GossipIgnore("block is from a future slot")

    # [IGNORE] The block is from a slot greater than the latest finalized slot
    # (MAY choose to validate and store such blocks for additional purposes
    # -- e.g. slashing detection, archive nodes, etc)
    finalized_slot = compute_start_slot_at_epoch(store.finalized_checkpoint.epoch)
    if block.slot <= finalized_slot:
        raise GossipIgnore("block is not from a slot greater than the latest finalized slot")

    # [IGNORE] The block's parent has been seen (via gossip or non-gossip sources)
    # (MAY be queued until parent is retrieved)
    if block.parent_root not in store.blocks:
        raise GossipIgnore("block's parent has not been seen")

    # [REJECT] The block's parent passes validation
    if block.parent_root not in store.block_states:
        raise GossipReject("block's parent is invalid")

    state = store.block_states[get_head(store).root]

    # [REJECT] The proposer index is a valid validator index
    if block.proposer_index >= len(state.validators):
        raise GossipReject("proposer index out of range")

    # [REJECT] The proposer signature is valid
    proposer = state.validators[block.proposer_index]
    domain = get_domain(state, DOMAIN_BEACON_PROPOSER, compute_epoch_at_slot(block.slot))
    signing_root = compute_signing_root(block, domain)
    if not bls.Verify(proposer.pubkey, signing_root, signed_beacon_block.signature):
        raise GossipReject("invalid proposer signature")

    # [REJECT] The block is from a higher slot than its parent
    if block.slot <= store.blocks[block.parent_root].slot:
        raise GossipReject("block is not from a higher slot than its parent")

    # [REJECT] The current finalized checkpoint is an ancestor of the block
    finalized_epoch = store.finalized_checkpoint.epoch
    finalized_checkpoint_block = get_checkpoint_block(store, block.parent_root, finalized_epoch)
    if finalized_checkpoint_block != store.finalized_checkpoint.root:
        raise GossipReject("finalized checkpoint is not an ancestor of block")

    # [REJECT] The block is proposed by the expected proposer for the slot
    # (if shuffling is not available, IGNORE instead and MAY be queued for later)
    parent_state = store.block_states[block.parent_root].copy()
    process_slots(parent_state, block.slot)
    expected_proposer = get_beacon_proposer_index(parent_state)
    if block.proposer_index != expected_proposer:
        raise GossipReject("block proposer_index does not match expected proposer")

    # Mark this block as seen
    seen.proposer_slots.add(proposer_slot_key)


def validate_beacon_aggregate_and_proof_gossip(
    seen: Seen,
    store: Store,
    signed_aggregate_and_proof: SignedAggregateAndProof,
    current_time_ms: Uint64,
) -> None:
    """
    Validate a SignedAggregateAndProof for gossip propagation.
    Raises GossipIgnore or GossipReject on validation failure.
    """
    aggregate_and_proof = signed_aggregate_and_proof.message
    aggregate = aggregate_and_proof.aggregate
    index = aggregate.data.index
    aggregation_bits = aggregate.aggregation_bits

    # [IGNORE] A valid aggregate with a superset of aggregation bits has not already been seen
    aggregate_data_root = hash_tree_root(aggregate.data)
    aggregate_bits = tuple(bool(bit) for bit in aggregation_bits)
    seen_bits = seen.aggregate_data_roots.get(aggregate_data_root, set())
    if is_non_strict_superset(seen_bits, aggregate_bits):
        raise GossipIgnore("already seen aggregate for this data")

    # [IGNORE] This is the first valid aggregate for this epoch and aggregator
    aggregator_index = aggregate_and_proof.aggregator_index
    target_epoch = aggregate.data.target.epoch
    aggregator_epoch_key = (target_epoch, aggregator_index)
    if aggregator_epoch_key in seen.aggregator_epochs:
        raise GossipIgnore("already seen aggregate for this epoch and aggregator")

    # [IGNORE] The block being voted for has been seen (via gossip or non-gossip sources)
    # (MAY be queued until block is retrieved)
    block_root = aggregate.data.beacon_block_root
    if block_root not in store.blocks:
        raise GossipIgnore("block being voted for has not been seen")

    # [REJECT] The block being voted for passes validation
    if block_root not in store.block_states:
        raise GossipReject("block being voted for failed validation")

    state = store.block_states[get_head(store).root]

    # [REJECT] The committee index is within the expected range
    committee_count = get_committee_count_per_slot(state, aggregate.data.target.epoch)
    if index >= committee_count:
        raise GossipReject("committee index out of range")

    # [IGNORE] The aggregate attestation's slot is within the propagation range
    # (MAY be queued for processing at the appropriate slot)
    if not is_within_slot_range(
        store, aggregate.data.slot, config.ATTESTATION_PROPAGATION_SLOT_RANGE, current_time_ms
    ):
        raise GossipIgnore("attestation slot not within propagation range")

    # [REJECT] The aggregate attestation's epoch matches its target
    if aggregate.data.target.epoch != compute_epoch_at_slot(aggregate.data.slot):
        raise GossipReject("attestation epoch does not match target epoch")

    # [REJECT] The number of aggregation bits matches the committee size
    committee = get_beacon_committee(state, aggregate.data.slot, index)
    if len(aggregation_bits) != len(committee):
        raise GossipReject("aggregation bits length does not match committee size")

    # [REJECT] The aggregate attestation has participants
    attesting_indices = get_attesting_indices(state, aggregate)
    if len(attesting_indices) < 1:
        raise GossipReject("aggregate has no participants")

    # [REJECT] The selection proof selects the validator as an aggregator
    if not is_aggregator(state, aggregate.data.slot, index, aggregate_and_proof.selection_proof):
        raise GossipReject("validator is not selected as aggregator")

    # [REJECT] The aggregator is a member of the committee
    if aggregator_index not in committee:
        raise GossipReject("aggregator is not a member of the committee")

    # [REJECT] The selection proof signature is valid
    aggregator = state.validators[aggregator_index]
    domain = get_domain(state, DOMAIN_SELECTION_PROOF, target_epoch)
    signing_root = compute_signing_root(aggregate.data.slot, domain)
    if not bls.Verify(aggregator.pubkey, signing_root, aggregate_and_proof.selection_proof):
        raise GossipReject("invalid selection proof signature")

    # [REJECT] The aggregator signature is valid
    domain = get_domain(state, DOMAIN_AGGREGATE_AND_PROOF, target_epoch)
    signing_root = compute_signing_root(aggregate_and_proof, domain)
    if not bls.Verify(aggregator.pubkey, signing_root, signed_aggregate_and_proof.signature):
        raise GossipReject("invalid aggregator signature")

    # [REJECT] The aggregate signature is valid
    if not is_valid_indexed_attestation(state, get_indexed_attestation(state, aggregate)):
        raise GossipReject("invalid aggregate signature")

    # [REJECT] The target block is an ancestor of the LMD vote block
    checkpoint_block = get_checkpoint_block(store, block_root, aggregate.data.target.epoch)
    if checkpoint_block != aggregate.data.target.root:
        raise GossipReject("target block is not an ancestor of LMD vote block")

    # [IGNORE] The finalized checkpoint is an ancestor of the block
    finalized_epoch = store.finalized_checkpoint.epoch
    finalized_checkpoint_block = get_checkpoint_block(store, block_root, finalized_epoch)
    if finalized_checkpoint_block != store.finalized_checkpoint.root:
        raise GossipIgnore("finalized checkpoint is not an ancestor of block")

    # Mark this aggregate as seen
    seen.aggregator_epochs.add(aggregator_epoch_key)
    if aggregate_data_root not in seen.aggregate_data_roots:
        seen.aggregate_data_roots[aggregate_data_root] = set()
    seen.aggregate_data_roots[aggregate_data_root].add(aggregate_bits)


def validate_voluntary_exit_gossip(
    seen: Seen,
    store: Store,
    signed_voluntary_exit: SignedVoluntaryExit,
    current_time_ms: Uint64,
) -> None:
    """
    Validate a SignedVoluntaryExit for gossip propagation.
    Raises GossipIgnore or GossipReject on validation failure.
    """
    voluntary_exit = signed_voluntary_exit.message
    validator_index = voluntary_exit.validator_index

    # [IGNORE] The voluntary exit is the first valid voluntary exit received for the validator
    if validator_index in seen.voluntary_exit_indices:
        raise GossipIgnore("already seen voluntary exit for this validator")

    # [IGNORE] The voluntary exit epoch is not in the future
    if is_future_epoch(store, voluntary_exit.epoch, current_time_ms):
        raise GossipIgnore("voluntary exit epoch is in the future")

    state = store.block_states[get_head(store).root]

    # [REJECT] The validator index is valid
    if validator_index >= len(state.validators):
        raise GossipReject("validator index out of range")

    validator = state.validators[validator_index]
    current_epoch = get_current_epoch(state)

    # [IGNORE] The validator has not already initiated exit
    if validator.exit_epoch != FAR_FUTURE_EPOCH:
        raise GossipIgnore("validator has already initiated exit")

    # [REJECT] The validator is active
    if not is_active_validator(validator, current_epoch):
        raise GossipReject("validator is not active")

    # [REJECT] The validator has been active long enough
    if current_epoch < validator.activation_epoch + config.SHARD_COMMITTEE_PERIOD:
        raise GossipReject("validator has not been active long enough")

    # [REJECT] The signature is valid
    domain = get_domain(state, DOMAIN_VOLUNTARY_EXIT, voluntary_exit.epoch)
    signing_root = compute_signing_root(voluntary_exit, domain)
    if not bls.Verify(validator.pubkey, signing_root, signed_voluntary_exit.signature):
        raise GossipReject("invalid voluntary exit signature")

    # Mark this voluntary exit as seen
    seen.voluntary_exit_indices.add(validator_index)


def validate_proposer_slashing_gossip(
    seen: Seen,
    store: Store,
    proposer_slashing: ProposerSlashing,
) -> None:
    """
    Validate a ProposerSlashing for gossip propagation.
    Raises GossipIgnore or GossipReject on validation failure.
    """
    header_1 = proposer_slashing.signed_header_1.message
    header_2 = proposer_slashing.signed_header_2.message
    proposer_index = header_1.proposer_index

    # [IGNORE] The proposer slashing is the first valid proposer slashing received for this proposer
    if proposer_index in seen.proposer_slashing_indices:
        raise GossipIgnore("already seen proposer slashing for this proposer")

    # [REJECT] The header slots match
    if header_1.slot != header_2.slot:
        raise GossipReject("header slots do not match")

    # [REJECT] The header proposer indices match
    if header_1.proposer_index != header_2.proposer_index:
        raise GossipReject("header proposer indices do not match")

    # [REJECT] The headers are different
    if header_1 == header_2:
        raise GossipReject("headers are not different")

    state = store.block_states[get_head(store).root]

    # [REJECT] The proposer index is a valid validator index
    if proposer_index >= len(state.validators):
        raise GossipReject("proposer index out of range")

    # [REJECT] The proposer is slashable
    proposer = state.validators[proposer_index]
    if not is_slashable_validator(proposer, get_current_epoch(state)):
        raise GossipReject("proposer is not slashable")

    # [REJECT] The signatures are valid
    for signed_header in (proposer_slashing.signed_header_1, proposer_slashing.signed_header_2):
        domain = get_domain(
            state, DOMAIN_BEACON_PROPOSER, compute_epoch_at_slot(signed_header.message.slot)
        )
        signing_root = compute_signing_root(signed_header.message, domain)
        if not bls.Verify(proposer.pubkey, signing_root, signed_header.signature):
            raise GossipReject("invalid proposer slashing signature")

    # Mark this proposer slashing as seen
    seen.proposer_slashing_indices.add(proposer_index)


def validate_attester_slashing_gossip(
    seen: Seen,
    store: Store,
    attester_slashing: AttesterSlashing,
) -> None:
    """
    Validate an AttesterSlashing for gossip propagation.
    Raises GossipIgnore or GossipReject on validation failure.
    """
    attestation_1 = attester_slashing.attestation_1
    attestation_2 = attester_slashing.attestation_2

    attesting_indices_1 = set(attestation_1.attesting_indices)
    attesting_indices_2 = set(attestation_2.attesting_indices)
    slashable_indices = attesting_indices_1.intersection(attesting_indices_2)

    # [IGNORE] At least one index in the intersection has not yet been seen
    new_indices = slashable_indices.difference(seen.attester_slashing_indices)
    if len(new_indices) == 0:
        raise GossipIgnore("all attester slashing indices already seen")

    # [REJECT] The attestation data is slashable (double vote or surround vote)
    if not is_slashable_attestation_data(attestation_1.data, attestation_2.data):
        raise GossipReject("attestation data is not slashable")

    state = store.block_states[get_head(store).root]

    # [REJECT] All validator indices in the first indexed attestation are valid
    if any(index >= len(state.validators) for index in attestation_1.attesting_indices):
        raise GossipReject("validator index out of range in indexed attestation 1")

    # [REJECT] The first indexed attestation has valid properties
    if not is_valid_indexed_attestation(state, attestation_1):
        raise GossipReject("invalid indexed attestation 1")

    # [REJECT] All validator indices in the second indexed attestation are valid
    if any(index >= len(state.validators) for index in attestation_2.attesting_indices):
        raise GossipReject("validator index out of range in indexed attestation 2")

    # [REJECT] The second indexed attestation has valid properties
    if not is_valid_indexed_attestation(state, attestation_2):
        raise GossipReject("invalid indexed attestation 2")

    # [REJECT] At least one validator in the intersection is slashable
    slashable_any = False
    current_epoch = get_current_epoch(state)
    for index in slashable_indices:
        if is_slashable_validator(state.validators[index], current_epoch):
            slashable_any = True
            break
    if not slashable_any:
        raise GossipReject("no slashable validators in intersection")

    # Mark these indices as seen
    seen.attester_slashing_indices.update(slashable_indices)


def validate_beacon_attestation_gossip(
    seen: Seen,
    store: Store,
    attestation: Attestation,
    current_time_ms: Uint64,
    subnet_id: SubnetID,
) -> None:
    """
    Validate an Attestation for gossip propagation on a subnet.
    Raises GossipIgnore or GossipReject on validation failure.
    """
    data = attestation.data
    committee_index = data.index
    target_epoch = data.target.epoch
    aggregation_bits = attestation.aggregation_bits

    # [IGNORE] The block being voted for has been seen (via gossip or non-gossip sources)
    # (MAY be queued until block is retrieved)
    block_root = data.beacon_block_root
    if block_root not in store.blocks:
        raise GossipIgnore("block being voted for has not been seen")

    # [REJECT] The block being voted for passes validation
    if block_root not in store.block_states:
        raise GossipReject("block being voted for failed validation")

    state = store.block_states[get_head(store).root]

    # [REJECT] The committee index is within the expected range
    committees_per_slot = get_committee_count_per_slot(state, target_epoch)
    if committee_index >= committees_per_slot:
        raise GossipReject("committee index out of range")

    # [REJECT] The attestation is for the correct subnet
    expected_subnet = compute_subnet_for_attestation(
        committees_per_slot, data.slot, committee_index
    )
    if expected_subnet != subnet_id:
        raise GossipReject("attestation is for wrong subnet")

    # [IGNORE] The attestation slot is within the propagation range
    # (MAY be queued for processing at the appropriate slot)
    if not is_within_slot_range(
        store, data.slot, config.ATTESTATION_PROPAGATION_SLOT_RANGE, current_time_ms
    ):
        raise GossipIgnore("attestation slot not within propagation range")

    # [REJECT] The attestation's epoch matches its target
    if target_epoch != compute_epoch_at_slot(data.slot):
        raise GossipReject("attestation epoch does not match target epoch")

    # [REJECT] The attestation is unaggregated (exactly one bit set)
    num_bits_set = get_set_bit_count(aggregation_bits)
    if num_bits_set != 1:
        raise GossipReject("attestation is not unaggregated")

    # [REJECT] The number of aggregation bits matches the committee size
    committee = get_beacon_committee(state, data.slot, committee_index)
    if len(aggregation_bits) != len(committee):
        raise GossipReject("aggregation bits length does not match committee size")

    # [IGNORE] No other valid attestation seen for this target epoch and validator
    set_bit_indices = [index for index, bit in enumerate(aggregation_bits) if bit]
    participant_index = committee[set_bit_indices[0]]
    attestation_epoch_key = (target_epoch, participant_index)
    if attestation_epoch_key in seen.attestation_validator_epochs:
        raise GossipIgnore("already seen attestation for this epoch and validator")

    # [REJECT] The attestation signature is valid
    indexed_attestation = get_indexed_attestation(state, attestation)
    if not is_valid_indexed_attestation(state, indexed_attestation):
        raise GossipReject("invalid attestation signature")

    # [REJECT] The attestation's target block is an ancestor of the LMD vote block
    target_checkpoint_block = get_checkpoint_block(store, block_root, target_epoch)
    if target_checkpoint_block != data.target.root:
        raise GossipReject("target block is not an ancestor of LMD vote block")

    # [IGNORE] The current finalized_checkpoint is an ancestor of the block
    finalized_epoch = store.finalized_checkpoint.epoch
    finalized_checkpoint_block = get_checkpoint_block(store, block_root, finalized_epoch)
    if finalized_checkpoint_block != store.finalized_checkpoint.root:
        raise GossipIgnore("finalized checkpoint is not an ancestor of block")

    # Mark this attestation as seen
    seen.attestation_validator_epochs.add(attestation_epoch_key)


def compute_subscribed_subnet(node_id: NodeID, epoch: Epoch, index: int) -> SubnetID:
    prefix_bits = int(compute_attestation_subnet_prefix_bits())
    node_id_prefix = node_id >> int(NODE_ID_BITS - prefix_bits)
    node_offset = Uint64(node_id % Uint256(config.EPOCHS_PER_SUBNET_SUBSCRIPTION))
    permutation_seed = sha256(
        uint_to_bytes(Uint64((epoch + node_offset) // config.EPOCHS_PER_SUBNET_SUBSCRIPTION))
    )
    permutated_prefix = compute_shuffled_index(
        Uint64(node_id_prefix),
        Uint64(1 << prefix_bits),
        permutation_seed,
    )
    return SubnetID((permutated_prefix + index) % config.ATTESTATION_SUBNET_COUNT)


def compute_subscribed_subnets(node_id: NodeID, epoch: Epoch) -> Sequence[SubnetID]:
    return [compute_subscribed_subnet(node_id, epoch, index) for index in range(config.SUBNETS_PER_NODE)]


def check_if_validator_active(state: BeaconState, validator_index: ValidatorIndex) -> bool:
    validator = state.validators[validator_index]
    return is_active_validator(validator, get_current_epoch(state))


def get_committee_assignment(
    state: BeaconState, epoch: Epoch, validator_index: ValidatorIndex
) -> Optional[Tuple[Sequence[ValidatorIndex], CommitteeIndex, Slot]]:
    """
    Return the committee assignment in the ``epoch`` for ``validator_index``.
    ``assignment`` returned is a tuple of the following form:
        * ``assignment[0]`` is the list of validators in the committee
        * ``assignment[1]`` is the index to which the committee is assigned
        * ``assignment[2]`` is the slot at which the committee is assigned
    Return None if no assignment.
    """
    next_epoch = get_current_epoch(state) + 1
    assert epoch <= next_epoch

    start_slot = compute_start_slot_at_epoch(epoch)
    committee_count_per_slot = get_committee_count_per_slot(state, epoch)
    for slot in range(start_slot, start_slot + SLOTS_PER_EPOCH):
        for index in range(committee_count_per_slot):
            committee = get_beacon_committee(state, Slot(slot), CommitteeIndex(index))
            if validator_index in committee:
                return committee, CommitteeIndex(index), Slot(slot)
    return None


def is_proposer(state: BeaconState, validator_index: ValidatorIndex) -> bool:
    return get_beacon_proposer_index(state) == validator_index


def get_epoch_signature(state: BeaconState, block: BeaconBlock, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_RANDAO, compute_epoch_at_slot(block.slot))
    signing_root = compute_signing_root(compute_epoch_at_slot(block.slot), domain)
    return bls.Sign(privkey, signing_root)


def voting_period_start_time(state: BeaconState) -> Uint64:
    eth1_voting_period_start_slot = state.slot - state.slot % (
        Uint64(EPOCHS_PER_ETH1_VOTING_PERIOD) * SLOTS_PER_EPOCH
    )
    return compute_time_at_slot(state, eth1_voting_period_start_slot)


def is_candidate_block(block: Eth1Block, period_start: Uint64) -> bool:
    return (
        block.timestamp + config.SECONDS_PER_ETH1_BLOCK * config.ETH1_FOLLOW_DISTANCE <= period_start
        and block.timestamp + config.SECONDS_PER_ETH1_BLOCK * config.ETH1_FOLLOW_DISTANCE * 2 >= period_start
    )


def get_eth1_vote(state: BeaconState, eth1_chain: Sequence[Eth1Block]) -> Eth1Data:
    period_start = voting_period_start_time(state)
    # `eth1_chain` abstractly represents all blocks in the eth1 chain sorted by ascending block height
    votes_to_consider = [
        get_eth1_data(block)
        for block in eth1_chain
        if (
            is_candidate_block(block, period_start)
            # Ensure cannot move back to earlier deposit contract states
            and get_eth1_data(block).deposit_count >= state.eth1_data.deposit_count
        )
    ]

    # Valid votes already cast during this period
    valid_votes = [vote for vote in state.eth1_data_votes if vote in votes_to_consider]

    # Default vote on latest eth1 block data in the period range unless eth1 chain is not live
    # Non-substantive casting for linter
    state_eth1_data: Eth1Data = state.eth1_data
    default_vote = (
        votes_to_consider[len(votes_to_consider) - 1] if any(votes_to_consider) else state_eth1_data
    )

    return max(
        valid_votes,
        # Tiebreak by smallest distance
        key=lambda v: (
            valid_votes.count(v),
            -valid_votes.index(v),
        ),
        default=default_vote,
    )


def compute_new_state_root(state: BeaconState, block: BeaconBlock) -> Root:
    temp_state: BeaconState = state.copy()
    signed_block = SignedBeaconBlock(message=block, signature=BLSSignature())
    state_transition(temp_state, signed_block, validate_result=False)
    return hash_tree_root(temp_state)


def get_block_signature(state: BeaconState, block: BeaconBlock, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_BEACON_PROPOSER, compute_epoch_at_slot(block.slot))
    signing_root = compute_signing_root(block, domain)
    return bls.Sign(privkey, signing_root)


def get_attestation_signature(
    state: BeaconState, attestation_data: AttestationData, privkey: int
) -> BLSSignature:
    domain = get_domain(state, DOMAIN_BEACON_ATTESTER, attestation_data.target.epoch)
    signing_root = compute_signing_root(attestation_data, domain)
    return bls.Sign(privkey, signing_root)


def compute_subnet_for_attestation(
    committees_per_slot: Uint64, slot: Slot, committee_index: CommitteeIndex
) -> SubnetID:
    """
    Compute the correct subnet for an attestation for Phase 0.
    Note, this mimics expected future behavior where attestations will be mapped to their shard subnet.
    """
    slots_since_epoch_start = Uint64(slot % SLOTS_PER_EPOCH)
    committees_since_epoch_start = committees_per_slot * slots_since_epoch_start

    return SubnetID((committees_since_epoch_start + committee_index) % config.ATTESTATION_SUBNET_COUNT)


def get_slot_signature(state: BeaconState, slot: Slot, privkey: int) -> BLSSignature:
    domain = get_domain(state, DOMAIN_SELECTION_PROOF, compute_epoch_at_slot(slot))
    signing_root = compute_signing_root(slot, domain)
    return bls.Sign(privkey, signing_root)


def is_aggregator(
    state: BeaconState, slot: Slot, index: CommitteeIndex, slot_signature: BLSSignature
) -> bool:
    committee = get_beacon_committee(state, slot, index)
    modulo = max(1, len(committee) // TARGET_AGGREGATORS_PER_COMMITTEE)
    return bytes_to_uint64(sha256(slot_signature)[0:8]) % modulo == 0


def get_aggregate_signature(attestations: Sequence[Attestation]) -> BLSSignature:
    signatures = [attestation.signature for attestation in attestations]
    return bls.Aggregate(signatures)


def get_aggregate_and_proof(
    state: BeaconState, aggregator_index: ValidatorIndex, aggregate: Attestation, privkey: int
) -> AggregateAndProof:
    return AggregateAndProof(
        aggregator_index=aggregator_index,
        aggregate=aggregate,
        selection_proof=get_slot_signature(state, aggregate.data.slot, privkey),
    )


def get_aggregate_and_proof_signature(
    state: BeaconState, aggregate_and_proof: AggregateAndProof, privkey: int
) -> BLSSignature:
    aggregate = aggregate_and_proof.aggregate
    domain = get_domain(
        state, DOMAIN_AGGREGATE_AND_PROOF, compute_epoch_at_slot(aggregate.data.slot)
    )
    signing_root = compute_signing_root(aggregate_and_proof, domain)
    return bls.Sign(privkey, signing_root)


def compute_weak_subjectivity_period(state: BeaconState) -> Uint64:
    """
    Returns the weak subjectivity period for the current ``state``.
    This computation takes into account the effect of:
        - validator set churn (bounded by ``get_validator_churn_limit()`` per epoch), and
        - validator balance top-ups (bounded by ``MAX_DEPOSITS * SLOTS_PER_EPOCH`` per epoch).
    A detailed calculation can be found at:
    https://github.com/runtimeverification/beacon-chain-verification/blob/master/weak-subjectivity/weak-subjectivity-analysis.pdf
    """
    ws_period = config.MIN_VALIDATOR_WITHDRAWABILITY_DELAY
    N = len(get_active_validator_indices(state, get_current_epoch(state)))
    t = get_total_active_balance(state) // N // ETH_TO_GWEI
    T = MAX_EFFECTIVE_BALANCE // ETH_TO_GWEI
    delta = get_validator_churn_limit(state)
    Delta = MAX_DEPOSITS * SLOTS_PER_EPOCH
    D = SAFETY_DECAY

    if t * (200 + 12 * D) > T * (200 + 3 * D):
        epochs_for_validator_set_churn = (
            N * (t * (200 + 12 * D) - T * (200 + 3 * D)) // (600 * delta * (2 * t + T))
        )
        epochs_for_balance_top_ups = N * (200 + 3 * D) // (600 * Delta)
        ws_period += max(epochs_for_validator_set_churn, epochs_for_balance_top_ups)
    else:
        ws_period += 3 * N * D * t // (200 * Delta * (T - t))

    return ws_period


def is_within_weak_subjectivity_period(
    store: Store, ws_state: BeaconState, ws_checkpoint: Checkpoint
) -> bool:
    # Clients may choose to validate the input state against the input Weak Subjectivity Checkpoint
    assert get_block_root(ws_state, ws_checkpoint.epoch) == ws_checkpoint.root
    assert compute_epoch_at_slot(ws_state.slot) == ws_checkpoint.epoch

    ws_period = compute_weak_subjectivity_period(ws_state)
    ws_state_epoch = compute_epoch_at_slot(ws_state.slot)
    current_epoch = compute_epoch_at_slot(get_current_slot(store))
    return current_epoch <= ws_state_epoch + ws_period


def get_eth1_data(block: Eth1Block) -> Eth1Data:
    """
    A stub function return mocking Eth1Data.
    """
    return Eth1Data(
        deposit_root=block.deposit_root,
        deposit_count=block.deposit_count,
        block_hash=Hash32(hash_tree_root(block)))


def cache_this(key_fn, value_fn, lru_size):
    cache_dict = LRU(size=lru_size)

    def wrapper(*args, **kw):
        key = key_fn(*args, **kw)
        if key not in cache_dict:
            cache_dict[key] = value_fn(*args, **kw)
        return cache_dict[key]
    return wrapper


_compute_shuffled_permutation = compute_shuffled_permutation
compute_shuffled_permutation = cache_this(
    lambda index_count, seed: (index_count, seed),
    _compute_shuffled_permutation, lru_size=256)

_get_total_active_balance = get_total_active_balance
get_total_active_balance = cache_this(
    lambda state: (state.validators.hash_tree_root(), compute_epoch_at_slot(state.slot)),
    _get_total_active_balance, lru_size=10)

_get_base_reward = get_base_reward
get_base_reward = cache_this(
    lambda state, index: (state.validators.hash_tree_root(), state.slot, index),
    _get_base_reward, lru_size=2048)

_get_committee_count_per_slot = get_committee_count_per_slot
get_committee_count_per_slot = cache_this(
    lambda state, epoch: (state.validators.hash_tree_root(), epoch),
    _get_committee_count_per_slot, lru_size=SLOTS_PER_EPOCH * 3)

_get_active_validator_indices = get_active_validator_indices
get_active_validator_indices = cache_this(
    lambda state, epoch: (state.validators.hash_tree_root(), epoch),
    _get_active_validator_indices, lru_size=3)

_get_beacon_committee = get_beacon_committee
get_beacon_committee = cache_this(
    lambda state, slot, index: (state.validators.hash_tree_root(), state.randao_mixes.hash_tree_root(), slot, index),
    _get_beacon_committee, lru_size=SLOTS_PER_EPOCH * MAX_COMMITTEES_PER_SLOT * 3)

_get_attesting_indices = get_attesting_indices
get_attesting_indices = cache_this(
    lambda state, attestation: (
        state.randao_mixes.hash_tree_root(),
        state.validators.hash_tree_root(), attestation.hash_tree_root()
    ),
    _get_attesting_indices, lru_size=SLOTS_PER_EPOCH * MAX_COMMITTEES_PER_SLOT * 3)
