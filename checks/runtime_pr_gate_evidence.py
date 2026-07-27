"""Load and bind local PR-gate evidence to runtime checkpoint items.

Motivating incident: GH-208 / PR #210 review found that trusted tier evidence
could be reused after a PR base retarget or rewrite while the head stayed
unchanged. This module intercepts that drift by requiring tier-authorized
runtime items to copy the current allowed PR-gate tier evidence, including its
base-bound diff identity, exactly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pr_gate import evaluate_pr_gate
from runtime_tier_authorization import FASTLANE_SELF_REVIEW_BASIS
from specrail_lib import PackConfig


def resolve_local_evidence_path(reference: Any) -> Path | None:
    if not isinstance(reference, str) or not reference.strip():
        return None
    normalized = reference.strip()
    if normalized.startswith(("https://", "http://")):
        return None
    return Path(normalized).expanduser()


def load_local_json(
    path: Path,
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label}: evidence file does not exist: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{label}: cannot read evidence file {path}: {exc}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: evidence file is not valid JSON {path}: {exc.msg}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label}: evidence file JSON must be an object: {path}")
        return None
    return payload


def validate_pr_gate_artifact(
    raw_item: dict[str, Any],
    evidence: Any,
    label: str,
    errors: list[str],
    repo: Path | None,
    config: PackConfig | None,
) -> dict[str, Any] | None:
    authorization = raw_item.get("self_review_authorization")
    fastlane_self_review = (
        isinstance(authorization, dict)
        and authorization.get("basis") == FASTLANE_SELF_REVIEW_BASIS
    )
    tier_authorized = raw_item.get("authorization_tier") == "standard_auto"
    path = resolve_local_evidence_path(evidence)
    if path is None:
        if (
            raw_item.get("enforcement_sensitive") is True
            or fastlane_self_review
            or tier_authorized
        ):
            errors.append(
                f"{label}: sensitive or tier-authorized item requires "
                "local machine-readable pr_gate evidence"
            )
        return None
    payload = load_local_json(path, f"{label}: pr_gate", errors)
    if payload is None:
        return None

    # specs/GH202 B-009: a recorded `allowed` decision must not survive drift in
    # the sensitive-path registry. A decision-only artifact carries no raw
    # classification inputs, so tier-authorized items must supply raw evidence
    # and be re-evaluated against the current repository configuration.
    tier_trusted = fastlane_self_review or tier_authorized
    # Re-evaluation is only meaningful against a loaded sensitive-path registry.
    # Without repo/config the classification would silently be the config-less
    # one, which is exactly the drift this check exists to catch.
    if tier_trusted and (repo is None or config is None):
        errors.append(
            f"{label}: tier-authorized item requires repository context "
            "(pass --repo) so pr_gate evidence is re-evaluated against the "
            "current sensitive-path registry"
        )
        return None
    if "decision" in payload:
        if tier_trusted:
            errors.append(
                f"{label}: tier-authorized item requires raw pr_gate evidence so "
                "the decision is re-evaluated against the current sensitive-path "
                "registry; a recorded decision is not accepted"
            )
            return None
        result = payload
    else:
        result = evaluate_pr_gate(payload, repo=repo, config=config)
    if result.get("decision") != "allowed":
        reasons = result.get("reasons")
        detail = f": {reasons}" if reasons else ""
        errors.append(f"{label}: pr_gate evidence decision must be allowed{detail}")

    for key, message in [("pr", "pr"), ("head_sha", "head_sha")]:
        item_value = raw_item.get(key)
        result_value = result.get(key)
        if tier_trusted and not (item_value and result_value):
            errors.append(
                f"{label}: tier-authorized item requires pr_gate evidence {message} "
                "identity on both the item and the evidence"
            )
        elif item_value and result_value and result_value != item_value:
            errors.append(
                f"{label}: pr_gate evidence {message} must match item {message}"
            )

    binding_keys = [
        "content_binding_version",
        "snapshot",
        "content_hashes",
        "reused_components",
    ]
    result_has_binding = (
        result.get("content_binding_version") == 1
        or any(result.get(key) is not None for key in binding_keys[1:])
    )
    if result_has_binding or any(key in raw_item for key in binding_keys):
        for key in binding_keys:
            if key not in raw_item or raw_item.get(key) != result.get(key):
                errors.append(
                    f"{label}: runtime item must copy current pr_gate {key} exactly"
                )

    if fastlane_self_review or tier_authorized:
        tier_keys = ["pr_tier", "pr_tier_evidence", "enforcement_sensitive"]
        if fastlane_self_review:
            tier_keys.insert(0, "review_source")
        for key in tier_keys:
            if key not in raw_item or raw_item.get(key) != result.get(key):
                errors.append(
                    f"{label}: tier-authorized runtime item must copy current pr_gate "
                    f"{key} exactly"
                )
    elif raw_item.get("enforcement_sensitive") is True and result.get(
        "enforcement_sensitive"
    ) is not True:
        errors.append(
            f"{label}: sensitive item requires enforcement-sensitive pr_gate evidence"
        )
    return result
