"""RFC 8785 hashing plus live idempotent/conflicting fixture import tests."""
from __future__ import annotations

import json
import math
import struct
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from application.contracts.canonical import canonicalize_json, contract_digest
from adapters.postgres.fixture_history import (
    FixtureVersionConflictError,
    PostgresFixtureHistoryAdapter,
)
from adapters.postgres.schema import scenario_version
from settings import default_settings


def test_rfc8785_canonicalizes_the_published_sample() -> None:
    payload = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
        "string": "€$" + chr(0x0F) + "\nA'B" + '"' + "\\\\" + '"/',
        "literals": [None, True, False],
    }
    expected = bytes.fromhex(
        "7b226c69746572616c73223a5b6e756c6c2c747275652c66616c73655d2c"
        "226e756d62657273223a5b3333333333333333332e333333333333332c31"
        "652b33302c342e352c302e3030322c31652d32375d2c22737472696e6722"
        "3a22e282ac245c75303030665c6e4127425c225c5c5c5c5c222f227d"
    )

    assert canonicalize_json(payload) == expected


def test_rfc8785_sorts_object_keys_as_utf16_code_units() -> None:
    payload = {
        "€": "Euro Sign",
        "\r": "Carriage Return",
        "דּ": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "😀": "Emoji: Grinning Face",
        "\x80": "Control",
        "ö": "Latin Small Letter O With Diaeresis",
    }

    pairs = json.loads(
        canonicalize_json(payload).decode("utf-8"),
        object_pairs_hook=lambda values: values,
    )
    assert [value for _, value in pairs] == [
        "Carriage Return",
        "One",
        "Control",
        "Latin Small Letter O With Diaeresis",
        "Euro Sign",
        "Emoji: Grinning Face",
        "Hebrew Letter Dalet With Dagesh",
    ]


@pytest.mark.parametrize(
    ("ieee754", "expected"),
    [
        ("0000000000000000", "0"),
        ("8000000000000000", "0"),
        ("0000000000000001", "5e-324"),
        ("8000000000000001", "-5e-324"),
        ("7fefffffffffffff", "1.7976931348623157e+308"),
        ("ffefffffffffffff", "-1.7976931348623157e+308"),
        ("4340000000000000", "9007199254740992"),
        ("c340000000000000", "-9007199254740992"),
        ("4430000000000000", "295147905179352830000"),
        ("44b52d02c7e14af5", "9.999999999999997e+22"),
        ("44b52d02c7e14af6", "1e+23"),
        ("44b52d02c7e14af7", "1.0000000000000001e+23"),
        ("444b1ae4d6e2ef4e", "999999999999999700000"),
        ("444b1ae4d6e2ef4f", "999999999999999900000"),
        ("444b1ae4d6e2ef50", "1e+21"),
        ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
        ("3eb0c6f7a0b5ed8d", "0.000001"),
        ("41b3de4355555553", "333333333.3333332"),
        ("41b3de4355555554", "333333333.33333325"),
        ("41b3de4355555555", "333333333.3333333"),
        ("41b3de4355555556", "333333333.3333334"),
        ("41b3de4355555557", "333333333.33333343"),
        ("becbf647612f3696", "-0.0000033333333333333333"),
        ("43143ff3c1cb0959", "1424953923781206.2"),
    ],
)
def test_rfc8785_number_serialization_vectors(
    ieee754: str,
    expected: str,
) -> None:
    value = struct.unpack(">d", bytes.fromhex(ieee754))[0]

    assert canonicalize_json(value) == expected.encode("ascii")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_rfc8785_rejects_non_json_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonicalize_json(value)


def test_rfc8785_rejects_lone_surrogates() -> None:
    with pytest.raises(ValueError, match="surrogate"):
        canonicalize_json("\udead")


def test_rfc8785_rejects_integers_that_would_silently_lose_precision() -> None:
    with pytest.raises(ValueError, match="lose precision"):
        canonicalize_json(2**53 + 1)


def test_contract_digest_declares_the_governed_rfc8785_shape() -> None:
    assert contract_digest({"b": 2, "a": 1}) == (
        "sha256",
        "rfc8785-v1",
        "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777",
    )


@pytest.fixture(scope="module")
def postgres_engine(governed_postgres_engine):
    return governed_postgres_engine


@pytest.mark.postgres
def test_same_fixture_import_returns_existing_semantic_result(
    postgres_engine,
) -> None:
    adapter = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=postgres_engine,
    )
    suffix = uuid4().hex
    site_id = adapter.ensure_seed_site(f"Organization {suffix}", f"Site {suffix}")
    payload = {"z": 1, "nested": {"b": True, "a": None}}

    first = adapter.import_fixture(
        site_id=site_id,
        fixture_id=f"fixture-{suffix}",
        version="v1",
        payload=payload,
        source_package="tests",
        source_path="fixture.json",
    )
    second = adapter.import_fixture(
        site_id=site_id,
        fixture_id=f"fixture-{suffix}",
        version="v1",
        payload={"nested": {"a": None, "b": True}, "z": 1},
        source_package="tests",
        source_path="fixture.json",
    )

    assert first.created is True
    assert second.created is False
    assert second.scenario_version_id == first.scenario_version_id
    assert second.checksum_digest == first.checksum_digest
    with postgres_engine.connect() as connection:
        count = connection.execute(
            select(func.count())
            .select_from(scenario_version)
            .where(
                scenario_version.c.site_id == site_id,
                scenario_version.c.fixture_id == f"fixture-{suffix}",
                scenario_version.c.version == "v1",
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.postgres
def test_conflicting_fixture_version_rolls_back_without_history_change(
    postgres_engine,
) -> None:
    adapter = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=postgres_engine,
    )
    suffix = uuid4().hex
    fixture_id = f"fixture-{suffix}"
    site_id = adapter.ensure_seed_site(f"Organization {suffix}", f"Site {suffix}")
    original = adapter.import_fixture(
        site_id=site_id,
        fixture_id=fixture_id,
        version="v1",
        payload={"value": "original"},
        source_package="tests",
        source_path="fixture.json",
    )

    with pytest.raises(FixtureVersionConflictError, match="different checksum"):
        adapter.import_fixture(
            site_id=site_id,
            fixture_id=fixture_id,
            version="v1",
            payload={"value": "mutated"},
            source_package="tests",
            source_path="fixture.json",
        )

    with postgres_engine.connect() as connection:
        rows = connection.execute(
            select(
                scenario_version.c.id,
                scenario_version.c.checksum_digest,
            ).where(
                scenario_version.c.site_id == site_id,
                scenario_version.c.fixture_id == fixture_id,
                scenario_version.c.version == "v1",
            )
        ).all()
    assert rows == [(original.scenario_version_id, original.checksum_digest)]
