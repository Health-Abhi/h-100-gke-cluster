#!/usr/bin/env python3
"""Update the lifecycle status in a cluster request document."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import yaml


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("phase")
    parser.add_argument("--condition", default="Reconciled")
    parser.add_argument("--status", choices=["True", "False", "Unknown"], default="True")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    document = yaml.safe_load(args.request.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit("Request must be a YAML mapping")
    status = document.setdefault("status", {})
    status["phase"] = args.phase
    conditions = status.setdefault("conditions", [])
    conditions[:] = [item for item in conditions if item.get("type") != args.condition]
    condition = {
        "type": args.condition,
        "status": args.status,
        "last_transition_time": now(),
    }
    if args.message:
        condition["message"] = args.message
    conditions.append(condition)
    args.request.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
