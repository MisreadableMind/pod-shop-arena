"""Test fixtures.

The environment has to be set before anything imports `adapters.config`,
because settings are cached for the life of the process — so this runs first,
at import time, on purpose.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="podarena-tests-"))

os.environ["PODARENA_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["PODARENA_BLOB_DIR"] = str(_TMP / "blobs")
os.environ["PODARENA_DEMO_FIXTURES"] = "true"
os.environ["PODARENA_REGISTRY_ADDRESS"] = ""
os.environ["PODARENA_ANCHOR_PRIVATE_KEY"] = ""

import pytest  # noqa: E402

from adapters import db  # noqa: E402
from demo.corpus import Corpus, build_corpus, demo_institutions  # noqa: E402
from worker import pipeline  # noqa: E402


@pytest.fixture(scope="session")
def corpus() -> Corpus:
    """One signed corpus for the whole session.

    Generating three 2048-bit RSA keys per test would dominate the runtime, and
    the corpus is immutable, so a session fixture is both faster and honest.
    """
    built = build_corpus()
    pipeline.set_fixture_dns(built.captured_dns)
    return built


@pytest.fixture(scope="session")
def institutions():
    return demo_institutions()


@pytest.fixture()
def session(corpus):
    db.Base.metadata.drop_all(db.engine())
    db.create_all()
    db_session = db.SessionLocal()
    try:
        yield db_session
    finally:
        db_session.rollback()
        db_session.close()


@pytest.fixture()
def record(session):
    from adapters.chain import record_key

    entity = db.Entity(name="Test Fund")
    session.add(entity)
    session.flush()
    row = db.Record(
        entity_id=entity.id,
        slug="test-fund",
        name="Test Fund",
        chain_key=record_key("test-fund"),
        viewer_salt="test-salt",
    )
    session.add(row)
    session.flush()
    return row
