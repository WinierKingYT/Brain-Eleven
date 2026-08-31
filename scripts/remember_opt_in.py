#!/usr/bin/env python3
"""Small fail-closed CLI gate for proactive cross-project capture."""

import argparse
import json
import sys
from pathlib import Path

from remember import proactive_capture_policy


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check Brain-Eleven proactive-capture opt-in")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--vault", required=True)
    args = parser.parse_args(argv)

    policy = proactive_capture_policy(args.project_root, args.vault)
    print(json.dumps({"opted_in": policy["allowed"], **policy}))
    return 0 if policy["allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
