#!/usr/bin/env python3
"""Small fail-closed CLI gate for proactive cross-project capture."""

import argparse
import json
import sys
from pathlib import Path

from remember import is_project_opted_in, normalize_project_root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check Brain-Eleven proactive-capture opt-in")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)

    allowed = is_project_opted_in(args.project_root, args.config)
    print(json.dumps({"opted_in": allowed, "project_root": normalize_project_root(args.project_root)}))
    return 0 if allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
