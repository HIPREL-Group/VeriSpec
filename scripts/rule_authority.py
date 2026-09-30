#!/usr/bin/env python3
"""Load and validate explicit authority resolutions for unlabelled rules."""

from __future__ import annotations

import json
import re
from pathlib import Path

AUTHORITY = {"root", "system", "developer", "user", "guideline"}
RULE_ID = re.compile(r"^\w{4}$")
OVERRIDES_FILE = "authority_overrides.json"


def load_authority_overrides(spec_dir: Path) -> dict[str, str]:
    """Return marker-id -> authority mappings from an optional spec sidecar.

    Each entry must include a non-empty reason so an inferred authority remains
    reviewable rather than becoming an unexplained hard-coded exception.
    """
    path = spec_dir / OVERRIDES_FILE
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc

    if not isinstance(payload, dict) or set(payload) != {"overrides"}:
        raise ValueError(f"{path} must be an object containing only 'overrides'")
    entries = payload["overrides"]
    if not isinstance(entries, dict):
        raise ValueError(f"{path}: 'overrides' must be an object")

    overrides: dict[str, str] = {}
    for rid, entry in entries.items():
        if not isinstance(rid, str) or not RULE_ID.fullmatch(rid):
            raise ValueError(f"{path}: invalid rule id {rid!r}")
        if not isinstance(entry, dict) or set(entry) != {"authority", "reason"}:
            raise ValueError(
                f"{path}: override {rid} must contain exactly 'authority' and 'reason'"
            )
        authority = entry["authority"]
        reason = entry["reason"]
        if authority not in AUTHORITY:
            raise ValueError(f"{path}: override {rid} has invalid authority {authority!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{path}: override {rid} must have a non-empty reason")
        overrides[rid] = authority
    return overrides


def resolve_authorities(
    marker_authorities: dict[str, str | None], overrides: dict[str, str]
) -> dict[str, str | None]:
    """Apply overrides only to known markers that lack structural authority."""
    unknown = sorted(set(overrides) - set(marker_authorities))
    if unknown:
        raise ValueError("authority override(s) reference unknown marker(s): " + ", ".join(unknown))

    redundant = sorted(rid for rid in overrides if marker_authorities.get(rid) is not None)
    if redundant:
        raise ValueError(
            "authority override(s) conflict with explicit/inherited authority: "
            + ", ".join(redundant)
        )

    resolved = dict(marker_authorities)
    resolved.update(overrides)
    return resolved
