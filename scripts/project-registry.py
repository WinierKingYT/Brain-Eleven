#!/usr/bin/env python3
"""Command-line administration for the vault-local project registry."""

import argparse
import json
from pathlib import Path

from project_registry import ProjectRegistry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manage Brain-Eleven project identities")
    parser.add_argument("--vault", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(command_handler=lambda registry, args: registry.list_projects())

    register = subparsers.add_parser("register")
    register.add_argument("root")
    register.add_argument("--label", default=None)
    register.add_argument(
        "--proactive",
        action="store_true",
        help="Enable proactive capture for this active project",
    )
    register.set_defaults(
        command_handler=lambda registry, args: registry.register(
            args.root,
            args.label,
            proactive_capture=args.proactive,
        )
    )

    relocate = subparsers.add_parser("relocate")
    relocate.add_argument("project_id")
    relocate.add_argument("root")
    relocate.set_defaults(command_handler=lambda registry, args: registry.relocate(args.project_id, args.root))

    rename = subparsers.add_parser("rename")
    rename.add_argument("project_id")
    rename.add_argument("label")
    rename.set_defaults(command_handler=lambda registry, args: registry.rename(args.project_id, args.label))

    status = subparsers.add_parser("status")
    status.add_argument("project_id")
    status.add_argument("value", choices=("active", "archived"))
    status.set_defaults(command_handler=lambda registry, args: registry.set_status(args.project_id, args.value))

    proactive = subparsers.add_parser("proactive")
    proactive.add_argument("project_id")
    proactive.add_argument("value", choices=("on", "off"))
    proactive.set_defaults(
        command_handler=lambda registry, args: registry.set_proactive_capture(
            args.project_id, args.value == "on"
        )
    )

    migrate_legacy = subparsers.add_parser("migrate-legacy-opt-in")
    migrate_legacy.add_argument("--config", required=True)
    migrate_legacy.set_defaults(
        command_handler=lambda registry, args: registry.migrate_legacy_opt_in_config(args.config)
    )

    args = parser.parse_args(argv)
    result = args.command_handler(ProjectRegistry(Path(args.vault)), args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
