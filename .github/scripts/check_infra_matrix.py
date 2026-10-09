#!/usr/bin/env python3
"""Fail if a Terraform directory with tests is missing from infra.yml's matrix.

Story 6.2 D13a. Each `terraform test` directory runs only because a matrix
entry names it; a new module whose tests nobody added would never run, and the
build would stay green. The reverse (a matrix entry whose directory has no
tests) is reported too, because `assert_counts.py` would then be asserting a
floor on a suite that cannot exist.

Usage: check_infra_matrix.py [--workflow PATH] [--root PATH]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_MATRIX_DIR = re.compile(r"^\s+dir: (infra/terraform/\S+)\s*$", re.MULTILINE)


def matrix_dirs(workflow: str) -> set[str]:
    return set(_MATRIX_DIR.findall(workflow))


def test_dirs(root: Path) -> set[str]:
    return {
        path.parent.parent.relative_to(root).as_posix()
        for path in (root / "infra" / "terraform").rglob("tests/*.tftest.hcl")
        if ".terraform" not in path.parts
    }


def problems(in_matrix: set[str], with_tests: set[str]) -> list[str]:
    found: list[str] = []
    if not with_tests:
        found.append("no tests/*.tftest.hcl found; the check would prove nothing")
    found += [f"missing from the matrix: {d}" for d in sorted(with_tests - in_matrix)]
    found += [f"in the matrix without tests: {d}" for d in sorted(in_matrix - with_tests)]
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", default=".github/workflows/infra.yml")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    in_matrix = matrix_dirs((root / args.workflow).read_text(encoding="utf-8"))
    with_tests = test_dirs(root)
    print(f"test directories: {sorted(with_tests)}")
    print(f"matrix:           {sorted(in_matrix)}")
    found = problems(in_matrix, with_tests)
    for problem in found:
        print(f"FAIL {problem}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
