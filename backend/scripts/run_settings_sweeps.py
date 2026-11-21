"""Run settings/numbering sweeps synchronously for operations and CI."""
from __future__ import annotations

import argparse
import json

from app.tasks.settings_sweeps import TASKS, run_sweep


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", choices=sorted(TASKS), help="sweep task name")
    group.add_argument("--all", action="store_true", help="run every sweep in registration order")
    parser.add_argument("--compact", action="store_true", help="emit single-line JSON")
    args = parser.parse_args()

    names = sorted(TASKS) if args.all else [args.task]
    results = {name: run_sweep(name) for name in names}
    print(json.dumps(results, indent=None if args.compact else 2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
