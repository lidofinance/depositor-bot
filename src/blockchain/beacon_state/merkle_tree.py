import hashlib
from typing import List, Optional


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def hash_concat(left: bytes, right: bytes) -> bytes:
    return sha256(left + right)


def next_power_of_two(n: int) -> int:
    """Return the smallest power of 2 >= n."""
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


ZERO_HASHES: List[bytes] = [b"\x00" * 32]
for _i in range(1, 64):
    ZERO_HASHES.append(sha256(ZERO_HASHES[-1] + ZERO_HASHES[-1]))


class MerkleTree:
    """
    A Merkle tree built from leaf chunks, supporting proof extraction.
    """

    def __init__(self, chunks: List[bytes], limit: Optional[int] = None):
        self.limit = limit
        self.original_length = len(chunks)

        if limit is not None:
            target_len = next_power_of_two(limit)
        else:
            target_len = next_power_of_two(len(chunks)) if chunks else 1

        self.depth = target_len.bit_length() - 1 if target_len > 1 else 0

        # Pad with zero chunks
        self.leaves = list(chunks) + [ZERO_HASHES[0]] * (target_len - len(chunks))

        # Build all layers (layer 0 = leaves, last layer = root)
        self.layers: List[List[bytes]] = [self.leaves]
        current = self.leaves
        while len(current) > 1:
            next_layer = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else ZERO_HASHES[0]
                next_layer.append(hash_concat(left, right))
            self.layers.append(next_layer)
            current = next_layer

        self.root = current[0] if current else ZERO_HASHES[0]

    def get_proof(self, index: int) -> List[bytes]:
        """Get Merkle proof for leaf at index. Returns proof bottom-up."""
        proof = []
        idx = index
        for layer in self.layers[:-1]:
            sibling_idx = idx ^ 1
            if sibling_idx < len(layer):
                proof.append(layer[sibling_idx])
            else:
                proof.append(ZERO_HASHES[0])
            idx //= 2
        return proof

    def build_sparse_list_proof(
        self, chunks: List[bytes], index: int, depth: int
    ) -> List[bytes]:
        """
        Build Merkle proof for item at index.
        Efficient: computes only sibling subtree roots needed for the path.
        """

        n = len(chunks)
        nodes_cache = {}

        def node_hash(level: int, pos: int) -> bytes:
            """
            Return hash of node at `level` (0 = leaf level), position `pos`.
            Tree is virtually padded with zero chunks up to `depth`.
            """

            key = (level, pos)
            if key in nodes_cache:
                return nodes_cache[key]

            # This subtree starts beyond available leaves -> pure zero subtree.
            if (pos << level) >= n:
                return ZERO_HASHES[level]

            if level == 0:
                h = chunks[pos]
            else:
                left = node_hash(level - 1, pos * 2)
                right = node_hash(level - 1, pos * 2 + 1)
                h = hash_concat(left, right)

            nodes_cache[key] = h
            return h

        proof = []
        for level in range(depth):
            sibling_pos = (index >> level) ^ 1
            proof.append(node_hash(level, sibling_pos))

        return proof
