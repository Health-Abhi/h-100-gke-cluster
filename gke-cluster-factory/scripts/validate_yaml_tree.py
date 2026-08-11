#!/usr/bin/env python3
"""Parse every YAML document below one or more paths."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def files_under(path: Path):
    if path.is_file():
        yield path
        return
    for pattern in ("*.yaml", "*.yml"):
        for candidate in path.rglob(pattern):
            if "templates" in candidate.parts or candidate.suffix == ".tpl":
                continue
            yield candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    count = 0
    for base in args.paths:
        for path in files_under(base):
            count += 1
            try:
                list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            except (OSError, yaml.YAMLError) as exc:
                print(f"ERROR: {path}: {exc}", file=sys.stderr)
                failed = True
    if not failed:
        print(f"Parsed {count} YAML files")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
