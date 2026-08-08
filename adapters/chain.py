"""Talking to Monad.

Anchoring happens inline on every ingest rather than in a nightly batch. That is
a deliberate use of the chain we are on: at 0.3s blocks and 0.6s finality,
waiting for a receipt costs less than a database round trip used to, so the
commitment can be to *the moment* rather than to the day. Batch it and you have
proved that a root existed sometime on Tuesday, which is a much weaker claim and
exactly the one a backfiller needs.

When no key is configured the client still computes and stores roots, and marks
them unanchored. A missing chain should degrade the proof, not break the app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from adapters.config import settings

ABI_PATH = Path(__file__).parent / "abi" / "TrackRecordRegistry.json"


@lru_cache
def registry_abi() -> list[dict]:
    return json.loads(ABI_PATH.read_text())


@dataclass(frozen=True, slots=True)
class AnchorReceipt:
    status: str  # "confirmed" | "skipped" | "failed"
    tx_hash: str | None = None
    block_number: int | None = None
    seq: int | None = None
    confirmed_at: datetime | None = None
    error: str | None = None

    @property
    def anchored(self) -> bool:
        return self.status == "confirmed"


@dataclass(frozen=True, slots=True)
class ChainHead:
    root: str
    seq: int
    ts: int

    @property
    def exists(self) -> bool:
        return self.seq > 0


class ChainClient(Protocol):
    def anchor(self, record_key: str, root: str) -> AnchorReceipt: ...

    def head(self, record_key: str) -> ChainHead: ...

    def log_access(
        self, record_key: str, viewer_commitment: str, profile: int
    ) -> AnchorReceipt: ...


def _hexstr(value) -> str:
    """Always `0x`-prefixed.

    `HexBytes.hex()` stopped prefixing in hexbytes 1.0, and an unprefixed hash
    is silently wrong in two places at once: viem rejects it as a bytes32
    argument, and explorer links 404.
    """
    raw = value.hex() if hasattr(value, "hex") else str(value)
    return raw if raw.startswith("0x") else "0x" + raw


def record_key(slug: str) -> str:
    """The bytes32 a record is keyed by on-chain."""
    from web3 import Web3

    return _hexstr(Web3.keccak(text=slug))


def viewer_commitment(viewer_id: str, salt: str) -> str:
    """keccak(viewerId ‖ salt).

    The chain shows that a view happened and when, without publishing who. The
    salt is disclosed to the record owner alone, so they can reconstruct the
    identities and nobody else can.
    """
    from web3 import Web3

    return _hexstr(Web3.keccak(text=f"{viewer_id}|{salt}"))


def _hexbytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("0x"))


class DisabledChainClient:
    """No key, no contract, no anchoring — and the app says so plainly rather
    than pretending a root was committed."""

    reason = "no registry address or signing key configured"

    def anchor(self, record_key: str, root: str) -> AnchorReceipt:
        return AnchorReceipt(status="skipped", error=self.reason)

    def head(self, record_key: str) -> ChainHead:
        return ChainHead(root="0x" + "00" * 32, seq=0, ts=0)

    def log_access(
        self, record_key: str, viewer_commitment: str, profile: int
    ) -> AnchorReceipt:
        return AnchorReceipt(status="skipped", error=self.reason)


class MonadChainClient:
    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
        registry_address: str,
        private_key: str,
        *,
        timeout: int = 30,
    ) -> None:
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.chain_id = chain_id
        self.account = self.w3.eth.account.from_key(private_key)
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(registry_address), abi=registry_abi()
        )
        self.timeout = timeout

    @property
    def address(self) -> str:
        return self.account.address

    def _send(self, function) -> AnchorReceipt:
        try:
            tx = function.build_transaction(
                {
                    "from": self.account.address,
                    "nonce": self.w3.eth.get_transaction_count(
                        self.account.address, "pending"
                    ),
                    "chainId": self.chain_id,
                }
            )
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self.timeout
            )
        except Exception as exc:
            return AnchorReceipt(status="failed", error=f"{type(exc).__name__}: {exc}")

        if receipt["status"] != 1:
            return AnchorReceipt(
                status="failed",
                tx_hash=_hexstr(receipt["transactionHash"]),
                error="transaction reverted",
            )
        return AnchorReceipt(
            status="confirmed",
            tx_hash=_hexstr(receipt["transactionHash"]),
            block_number=receipt["blockNumber"],
            confirmed_at=datetime.now(timezone.utc),
        )

    def anchor(self, record_key: str, root: str) -> AnchorReceipt:
        receipt = self._send(
            self.contract.functions.anchor(_hexbytes(record_key), _hexbytes(root))
        )
        if receipt.anchored:
            # Read the sequence back from state rather than trusting what we
            # think we sent. A gap in this number is the whole anti-backfill
            # signal, so it is worth one extra call to be sure of it.
            head = self.head(record_key)
            return AnchorReceipt(
                status=receipt.status,
                tx_hash=receipt.tx_hash,
                block_number=receipt.block_number,
                seq=head.seq,
                confirmed_at=receipt.confirmed_at,
            )
        return receipt

    def log_access(
        self, record_key: str, viewer_commitment: str, profile: int
    ) -> AnchorReceipt:
        return self._send(
            self.contract.functions.logAccess(
                _hexbytes(record_key), _hexbytes(viewer_commitment), profile
            )
        )

    def head(self, record_key: str) -> ChainHead:
        root, seq, ts = self.contract.functions.head(_hexbytes(record_key)).call()
        return ChainHead(root=_hexstr(root), seq=int(seq), ts=int(ts))


_client: ChainClient | None = None


def chain_client() -> ChainClient:
    global _client
    if _client is None:
        config = settings()
        if not config.anchoring_enabled:
            _client = DisabledChainClient()
        else:
            _client = MonadChainClient(
                config.rpc_url,
                config.chain_id,
                config.registry_address or "",
                config.anchor_private_key or "",
            )
    return _client


def reset_chain_client() -> None:
    global _client
    _client = None
