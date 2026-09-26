"""The committed fixtures are exactly what the anonymisation rule produces.

The fixed-point test is the guard that matters: a fixture refreshed from the
real source brings real names back, and `anonymise()` of such a file differs
from the file itself -- without this repository ever having to spell a real
name out in a denylist.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

from scripts.anonymise_fixtures import (
    AREA_NAMES,
    FIXTURES,
    SYNTHETIC_MEMBERS,
    _dump,
    anonymise,
)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_committed_fixture_is_a_fixed_point_of_the_rule(path) -> None:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert _dump(payload) == raw, "the fixture must round-trip, or the script refuses it"
    assert anonymise(copy.deepcopy(payload)) == payload


def test_synthetic_members_stay_unambiguous_to_substring_resolution() -> None:
    # `constraint_service._resolve_member` substring-matches a token against
    # both the member name and the GUID contact_id.
    first_names = [name.split()[0] for name in SYNTHETIC_MEMBERS]
    assert len(set(first_names)) == len(first_names)
    for name in SYNTHETIC_MEMBERS:
        others = [other for other in SYNTHETIC_MEMBERS if other != name]
        assert not any(name.lower() in other.lower() for other in others), name
    assert not any(re.fullmatch(r"[0-9a-f]+", first.lower()) for first in first_names)


def test_area_initials_are_unique_so_task_codes_cannot_collide() -> None:
    initials = [name[0] for name in AREA_NAMES.values()]
    assert len(set(initials)) == len(initials)


def test_an_unknown_area_fails_with_the_offending_id() -> None:
    payload = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
    payload["Task"][0]["AreaID"] = "UNKNOWN-AREA"

    with pytest.raises(ValueError, match="UNKNOWN-AREA"):
        anonymise(payload)
