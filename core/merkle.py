"""A Merkle tree over sorted leaves, with proofs a browser can re-fold.

Two details that matter more than they look:

Leaves and internal nodes are hashed under different prefixes. Without that, an
attacker can present an internal node as if it were a leaf and prove membership
of something that was never committed.

An odd node is *promoted* to the next level rather than hashed against a copy of
itself. Duplicating the last leaf is the classic construction and the classic
bug: it lets two different leaf sets fold to the same root.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Literal

_NODE_PREFIX = b"\x01"

Side = Literal["left", "right"]


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


@dataclass(frozen=True, slots=True)
class ProofStep:
    sibling: bytes
    side: Side  # which side the *sibling* sits on

    def as_dict(self) -> dict[str, str]:
        return {"sibling": self.sibling.hex(), "side": self.side}


@dataclass(frozen=True, slots=True)
class MerkleProof:
    leaf: bytes
    steps: tuple[ProofStep, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "leaf": self.leaf.hex(),
            "steps": [s.as_dict() for s in self.steps],
        }


class EmptyTree(ValueError):
    """Nothing was committed. An empty root would be a commitment to nothing
    that still looks like a commitment, so we refuse to build one."""


class MerkleTree:
    """Leaves are sorted before folding, so the root depends on the *set* of
    evidence and not on the order our pipeline happened to emit it."""

    __slots__ = ("_leaves", "_levels")

    def __init__(self, leaves: Iterable[bytes]) -> None:
        materialized = sorted(bytes(leaf) for leaf in leaves)
        if not materialized:
            raise EmptyTree("refusing to build a Merkle tree over zero leaves")
        for leaf in materialized:
            if len(leaf) != 32:
                raise ValueError(f"leaf must be a 32-byte digest, got {len(leaf)} bytes")
        self._leaves: tuple[bytes, ...] = tuple(materialized)
        self._levels: tuple[tuple[bytes, ...], ...] = self._fold(self._leaves)

    @staticmethod
    def _fold(leaves: tuple[bytes, ...]) -> tuple[tuple[bytes, ...], ...]:
        levels = [leaves]
        current = leaves
        while len(current) > 1:
            nxt: list[bytes] = []
            for i in range(0, len(current) - 1, 2):
                nxt.append(_node(current[i], current[i + 1]))
            if len(current) % 2:
                nxt.append(current[-1])  # promoted, not duplicated
            current = tuple(nxt)
            levels.append(current)
        return tuple(levels)

    @property
    def leaves(self) -> tuple[bytes, ...]:
        return self._leaves

    @property
    def root(self) -> bytes:
        return self._levels[-1][0]

    def __len__(self) -> int:
        return len(self._leaves)

    def __contains__(self, leaf: bytes) -> bool:
        return bytes(leaf) in self._leaves

    def proof_for(self, leaf: bytes) -> MerkleProof:
        leaf = bytes(leaf)
        try:
            index = self._leaves.index(leaf)
        except ValueError:
            raise KeyError("leaf is not in this tree") from None

        steps: list[ProofStep] = []
        for level in self._levels[:-1]:
            if index % 2 == 0:
                if index + 1 < len(level):
                    steps.append(ProofStep(level[index + 1], "right"))
                # else: promoted, no sibling at this level
            else:
                steps.append(ProofStep(level[index - 1], "left"))
            index //= 2
        return MerkleProof(leaf, tuple(steps))


def verify_proof(proof: MerkleProof, root: bytes) -> bool:
    """Re-fold a leaf to a root. The browser runs the same walk in TypeScript;
    if the two ever disagree, one of them is wrong and the UI says so."""
    current = proof.leaf
    for step in proof.steps:
        if step.side == "right":
            current = _node(current, step.sibling)
        elif step.side == "left":
            current = _node(step.sibling, current)
        else:  # pragma: no cover - guarded by the Side literal
            raise ValueError(f"bad proof step side: {step.side!r}")
    return current == bytes(root)
