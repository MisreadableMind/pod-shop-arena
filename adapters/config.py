"""Configuration. Everything that varies between a laptop and Render.

Note what is *not* here: the institution allow-list. Which domains we will
believe a signature from is a security decision, so it lives in code, in version
control, next to a test — not in an environment variable somebody can widen at
three in the morning.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Monad Testnet, per docs.monad.xyz/developer-essentials.
MONAD_TESTNET_CHAIN_ID = 10143
MONAD_TESTNET_RPC = "https://testnet-rpc.monad.xyz"
MONAD_TESTNET_EXPLORER = "https://testnet.monadvision.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="PODARENA_", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://podarena:podarena@localhost:5432/podarena"

    # Raw documents are content-addressed and write-once. They never go in the
    # database — a multi-megabyte blob in a row is a slow way to lose both.
    blob_dir: Path = Path("var/blobs")
    # Where the synthetic corpus is written on first generation, so that fresh
    # keys are not minted on every boot.
    fixture_dir: Path = Path("var/fixtures")
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # Chain
    rpc_url: str = MONAD_TESTNET_RPC
    chain_id: int = MONAD_TESTNET_CHAIN_ID
    explorer_url: str = MONAD_TESTNET_EXPLORER
    registry_address: str | None = None
    anchor_private_key: str | None = None

    # DNS lookups during ingest. Kept short: a slow resolver should degrade the
    # verdict to "no key captured", not hang the request.
    dns_timeout_seconds: float = 5.0

    # Runs the synthetic corpus. Adds a plainly fake demo domain to the DKIM
    # allow-list, so it must never be on for a deployment holding real records.
    demo_fixtures: bool = True

    admin_token: str | None = None
    public_base_url: str = "http://localhost:8000"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Render hands out `postgres://`, which SQLAlchemy 2 does not accept.

        Rewriting it here beats making every deployment remember to, and beats
        the alternative of a confusing boot failure ten seconds into a deploy.
        """
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def anchoring_enabled(self) -> bool:
        return bool(self.registry_address and self.anchor_private_key)

    @property
    def uses_s3(self) -> bool:
        return bool(self.s3_bucket)

    def explorer_tx(self, tx_hash: str) -> str:
        return f"{self.explorer_url.rstrip('/')}/tx/{tx_hash}"

    def explorer_address(self, address: str) -> str:
        return f"{self.explorer_url.rstrip('/')}/address/{address}"


@lru_cache
def settings() -> Settings:
    return Settings()
