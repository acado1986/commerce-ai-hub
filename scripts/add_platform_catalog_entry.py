#!/usr/bin/env python3
"""Add or update a platform/profile entry in config/platform_catalog.yaml.

This helper keeps the catalog structure consistent when onboarding new platforms.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "platform_catalog.yaml"
)


def _load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Catalog file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Catalog root must be a mapping.")

    for key in ("platforms", "profiles", "capabilities"):
        value = payload.get(key)
        if not isinstance(value, dict):
            raise SystemExit(f"Catalog key '{key}' must be a mapping.")
    return payload


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _build_profile(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "label": args.label,
        "platform": args.platform_id,
        "setup_command": args.setup_command,
        "skills_setup_command": args.skills_setup_command,
        "requires_specialized_skills": bool(args.requires_specialized_skills),
        "skills": _dedupe(args.skill),
        "project_commands": _dedupe(args.project_command),
        "triggers": _dedupe(args.trigger),
        "source_documents": _dedupe(args.source_document),
        "architecture_notes": _dedupe(args.architecture_note),
    }


def _update_platform_mapping(catalog: dict[str, Any], args: argparse.Namespace) -> None:
    platforms: dict[str, Any] = catalog["platforms"]
    platform = platforms.get(args.platform_id)
    if platform is None:
        platforms[args.platform_id] = {
            "profile_ids": [args.profile_id],
            "default_profile_id": args.profile_id,
        }
        return

    profile_ids = platform.get("profile_ids")
    if not isinstance(profile_ids, list):
        raise SystemExit(f"platforms.{args.platform_id}.profile_ids must be a list")
    if args.profile_id not in profile_ids:
        profile_ids.append(args.profile_id)

    default_profile_id = platform.get("default_profile_id")
    if not isinstance(default_profile_id, str) or args.set_default_profile:
        platform["default_profile_id"] = args.profile_id


def _write_catalog(path: Path, catalog: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-path", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--platform-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--label", required=True)

    parser.add_argument("--setup-command", default=None)
    parser.add_argument("--skills-setup-command", default=None)
    parser.add_argument("--requires-specialized-skills", action="store_true")

    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--project-command", action="append", default=[])
    parser.add_argument("--trigger", action="append", default=[])
    parser.add_argument("--source-document", action="append", default=[])
    parser.add_argument("--architecture-note", action="append", default=[])

    parser.add_argument("--set-default-profile", action="store_true")
    parser.add_argument("--overwrite-profile", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    catalog_path = Path(args.catalog_path).expanduser().resolve()
    catalog = _load_catalog(catalog_path)

    profiles: dict[str, Any] = catalog["profiles"]
    if args.profile_id in profiles and not args.overwrite_profile:
        raise SystemExit(
            f"Profile '{args.profile_id}' already exists. Use --overwrite-profile to replace it."
        )

    profiles[args.profile_id] = _build_profile(args)
    _update_platform_mapping(catalog, args)

    if args.dry_run:
        print(yaml.safe_dump(catalog, sort_keys=False, allow_unicode=False))
        return 0

    _write_catalog(catalog_path, catalog)
    print(f"Updated catalog: {catalog_path}")
    print(f"Platform: {args.platform_id}")
    print(f"Profile: {args.profile_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
