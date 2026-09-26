"""Rewrite the governed fixtures' name-like fields with synthetic values.

The fixtures were cut from a real site, so their member names, employee
numbers, agreement names and task names identified real people and a real
business. This script replaces them by rule, and only them: every GUID,
number, time, rate and volume is left byte-identical, so the solver sees the
same problem.

Run from the repository root; running it twice changes nothing:
    uv run --directory backend python scripts/anonymise_fixtures.py

Rules
-----
* Area names come from `AREA_NAMES`, keyed by AreaID.
* Task names follow `{Area} {Function} | {Activity} {Code}`: the area name,
  the function label, the activity that function performs, and a code of the
  area's initial plus a two-digit ordinal within that area in Task order --
  e.g. `Chiller Putaway | Forklift C01`.
* Members take `SYNTHETIC_MEMBERS[i]` and SAPID `998000{i+1:02}` by the order
  in which their ContactID first appears in `Team Member`. A ContactID with
  two rows is one person and gets one name. Rows already named
  `Test Member NN` are synthetic and kept as they are.
* Agreements take `AGREEMENT_NAMES`, keyed by EBAID.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = (
    REPO_ROOT / "data" / "sample_tiny_input.json",
    REPO_ROOT / "data" / "sample_tiny_input_more_tm.json",
)

AREA_NAMES = {
    "587561A7-9E3C-487F-A8E6-0DE9268481C1": "Chiller",
    "99AD3050-7864-4456-8848-680BD6488EC3": "Freezer",
    "DB02EC2E-FC8D-4FC6-ACAA-6F5119D8C4E2": "Main",
}

#: Function name -> (label used in the task name, activity it performs).
FUNCTION_RULES = {
    "Receiving": ("Receive", "Unloader"),
    "Putaways": ("Putaway", "Forklift"),
    "Despatch": ("Despatch", "Loader"),
    "Pick": ("Pick", "Order Picker"),
}

#: Unique first names, none a substring of another and none made only of hex
#: letters -- member resolution also substring-matches the GUID contact_id.
SYNTHETIC_MEMBERS = (
    "Mika Tane",
    "Arjun Patel",
    "Lena Ortiz",
    "Owen Hale",
    "Priya Nair",
    "Nina Brooks",
    "Theo Marsh-Walker",
    "Felix Van Dijk",
    "Hana Sato",
    "Ravi Kumar",
)

AGREEMENT_NAMES = {
    "30958F3A-DF00-4DFA-A600-0BE8811755F8": ("Agency Agreement", "AGENCY"),
    "F3936C24-1272-4067-8D27-E1E8E81C4474": ("Site Agreement", "SITE"),
}

_ALREADY_SYNTHETIC = re.compile(r"^Test Member \d+$")


def _dump(payload: dict) -> str:
    # The committed fixtures are json.dumps(indent=1) with no trailing newline.
    return json.dumps(payload, indent=1)


def _rule(table: dict, key: str, what: str):
    # A fixture refreshed from the source can carry an ID the rules have never
    # seen; say which one instead of failing with a bare KeyError.
    try:
        return table[key]
    except KeyError:
        raise ValueError(f"no anonymisation rule for {what} {key!r}") from None


def _task_names(payload: dict) -> dict[str, str]:
    functions = {row["FunctionID"]: row["Name"] for row in payload["Function"]}
    ordinals: dict[str, int] = {}
    names: dict[str, str] = {}
    for task in payload["Task"]:
        area = _rule(AREA_NAMES, task["AreaID"], "AreaID")
        function = _rule(functions, task["FunctionID"], "FunctionID")
        label, activity = _rule(FUNCTION_RULES, function, "function")
        ordinals[area] = ordinals.get(area, 0) + 1
        names[task["TaskID"]] = f"{area} {label} | {activity} {area[0]}{ordinals[area]:02}"
    return names


def _member_identities(payload: dict) -> dict[str, tuple[str, str]]:
    identities: dict[str, tuple[str, str]] = {}
    for row in payload["Team Member"]:
        contact_id = row["ContactID"]
        if contact_id in identities or _ALREADY_SYNTHETIC.match(row["Team Member"]):
            continue
        index = len(identities)
        if index == len(SYNTHETIC_MEMBERS):
            raise ValueError(
                f"more than {len(SYNTHETIC_MEMBERS)} real members; extend SYNTHETIC_MEMBERS"
            )
        identities[contact_id] = (SYNTHETIC_MEMBERS[index], f"998000{index + 1:02}")
    return identities


def anonymise(payload: dict) -> dict:
    """Return `payload` with every name-like field rewritten by the rules above."""
    for area in payload["Area"]:
        area["Name"] = area["Code"] = _rule(AREA_NAMES, area["AreaID"], "AreaID")

    agreements = {}
    for eba in payload["EBA"]:
        eba["Name"], eba["Code"] = _rule(AGREEMENT_NAMES, eba["EBAID"], "EBAID")
        agreements[eba["EBAID"]] = eba["Name"]

    task_names = _task_names(payload)
    for task in payload["Task"]:
        task["Task"] = task_names[task["TaskID"]]

    identities = _member_identities(payload)
    for row in payload["Team Member"]:
        row["EBA"] = _rule(agreements, row["EBAID"], "EBAID")
        if row["ContactID"] in identities:
            row["Team Member"], row["SAPID"] = identities[row["ContactID"]]

    synthetic = {row["ContactID"]: row["Team Member"] for row in payload["Team Member"]}
    for table in ("Roster Profile", "Availability"):
        for row in payload[table]:
            row["Team Member"] = _rule(synthetic, row["ContactID"], f"{table} ContactID")
    return payload


def _identities(payload: dict) -> dict[tuple[str, str], str]:
    """Every rewritten value keyed by the stable ID it belongs to."""
    found = {("TaskID", t["TaskID"]): t["Task"] for t in payload["Task"]}
    for row in payload["Team Member"]:
        found[("ContactID", row["ContactID"])] = row["Team Member"]
        found[("SAPID of", row["ContactID"])] = row["SAPID"]
    return found


def main() -> None:
    # Everything is computed and checked before anything is written, so a
    # failure can never leave one fixture rewritten and the other not.
    rewritten: list[tuple[Path, str]] = []
    seen: dict[tuple[str, str], str] = {}
    for path in FIXTURES:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if _dump(payload) != raw:
            sys.exit(f"{path.name} does not round-trip through json.dumps; not rewriting it")
        try:
            anonymised = anonymise(payload)
        except ValueError as exc:
            sys.exit(f"{path.name}: {exc}")
        for key, value in _identities(anonymised).items():
            if seen.setdefault(key, value) != value:
                sys.exit(f"{key[0]} {key[1]} would be named differently in different fixtures")
        rewritten.append((path, _dump(anonymised)))
    for path, text in rewritten:
        path.write_text(text, encoding="utf-8", newline="\n")
        print(path.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
