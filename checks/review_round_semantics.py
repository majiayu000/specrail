"""Bounded review-round semantics shared by review evidence consumers."""

from __future__ import annotations

from typing import Any


ROUND_POLICY = "bounded_diff_v1"
ROUND_CAP = 3


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_bounded_rounds(
    manifest: dict[str, Any], artifacts: list[dict[str, Any]], errors: list[str]
) -> dict[str, Any] | None:
    policy, rounds = manifest.get("round_policy"), manifest.get("rounds")
    if policy != {"name": ROUND_POLICY, "cap": ROUND_CAP}:
        errors.append("review manifest v2 round_policy must be bounded_diff_v1 with cap 3")
    if not isinstance(rounds, list) or not rounds:
        errors.append("review manifest v2 rounds must be a non-empty list")
        return None
    fields = {
        "artifact_id", "review_round", "review_mode", "base_head_sha",
        "head_sha", "diff_sha256", "escalation_authorization_id",
    }
    by_id = {
        item.get("artifact_id"): item
        for item in artifacts
        if _nonempty(item.get("artifact_id"))
    }
    if len(rounds) != len(artifacts):
        errors.append(
            "review manifest v2 rounds must cover every loaded artifact exactly once"
        )
    all_ids, seen_ids, seen_heads = set(by_id), set(), set()
    unresolved: set[tuple[str, str]] = set()
    definitions: set[tuple[str, str]] = set()
    audit_rounds: list[dict[str, Any]] = []
    for index, declared in enumerate(rounds, start=1):
        label = f"review manifest rounds[{index - 1}]"
        if not isinstance(declared, dict) or set(declared) != fields:
            errors.append(f"{label} must contain exactly the bounded round fields")
            continue
        artifact_id = declared.get("artifact_id")
        artifact = by_id.get(artifact_id)
        if artifact is None:
            errors.append(f"{label}.artifact_id does not reference a loaded artifact")
            continue
        if artifact.get("round_policy_version") != 1:
            errors.append(f"{label} artifact round_policy_version must be 1")
        if artifact_id in seen_ids:
            errors.append(f"duplicate bounded review artifact: {artifact_id}")
        seen_ids.add(artifact_id)
        escalation = artifact.get("round_cap_escalation")
        authorization_id = (
            escalation.get("authorization_id")
            if isinstance(escalation, dict)
            else None
        )
        derived = {
            "artifact_id": artifact_id,
            "review_round": artifact.get("review_round"),
            "review_mode": artifact.get("review_mode"),
            "base_head_sha": artifact.get("base_head_sha"),
            "head_sha": artifact.get("head_sha"),
            "diff_sha256": artifact.get("diff_sha256"),
            "escalation_authorization_id": authorization_id,
        }
        if declared != derived:
            errors.append(f"{label} does not match its loaded artifact")
        if derived["review_round"] != index:
            errors.append(f"bounded review rounds must be exactly 1..N; expected {index}")
        if index >= 2 and derived["review_mode"] not in {"resumed", "diff_only"}:
            errors.append(f"bounded review round {index} must be resumed or diff_only")
        if index == 1 and (
            derived["base_head_sha"] is not None
            or derived["diff_sha256"] is not None
        ):
            errors.append(
                "bounded review round 1 base_head_sha and diff_sha256 must be null"
            )
        if index >= 2 and (
            not audit_rounds
            or derived["base_head_sha"] != audit_rounds[-1]["head_sha"]
        ):
            errors.append(
                f"bounded review round {index} base_head_sha must equal prior round head_sha"
            )
        if derived["head_sha"] in seen_heads:
            errors.append(f"bounded review head_sha must be unique: {derived['head_sha']}")
        seen_heads.add(derived["head_sha"])

        prior = (
            artifact.get("prior_findings")
            if isinstance(artifact.get("prior_findings"), list)
            else []
        )
        prior_map: dict[tuple[str, str], dict[str, Any]] = {}
        for item in prior:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("source_artifact_id", "")),
                str(item.get("finding_id", "")),
            )
            if key in prior_map:
                errors.append(f"duplicate compact prior finding key: {key[0]}/{key[1]}")
            prior_map[key] = item
            if key not in definitions:
                errors.append(
                    f"compact prior finding has no source definition: {key[0]}/{key[1]}"
                )
            pointer = item.get("evidence_pointer")
            if (
                isinstance(pointer, dict)
                and pointer.get("kind") == "artifact"
                and pointer.get("value") not in all_ids
            ):
                errors.append(
                    "compact prior finding references unknown evidence artifact: "
                    f"{pointer.get('value')}"
                )
        for key in sorted(unresolved - set(prior_map)):
            errors.append(
                f"missing compact prior finding carry-forward: {key[0]}/{key[1]}"
            )
        for key in sorted(set(prior_map) - unresolved):
            errors.append(
                f"compact prior finding is not currently unresolved: {key[0]}/{key[1]}"
            )
        still_unresolved = {
            key for key, item in prior_map.items()
            if item.get("status") == "unresolved"
        }
        current_keys: set[tuple[str, str]] = set()
        actionable: set[tuple[str, str]] = set()
        for finding in artifact.get("findings", []):
            if isinstance(finding, dict) and _nonempty(finding.get("id")):
                key = (str(artifact_id), str(finding["id"]))
                current_keys.add(key)
                if (
                    finding.get("severity") in {"critical", "important"}
                    or finding.get("actionable") is True
                ):
                    actionable.add(key)
        definitions.update(current_keys)
        expected_escalation = still_unresolved | actionable
        if index <= ROUND_CAP and escalation is not None:
            errors.append(
                f"bounded review round {index} must not declare round_cap_escalation"
            )
        if index > ROUND_CAP:
            supplied = (
                escalation.get("unresolved_findings")
                if isinstance(escalation, dict)
                else None
            )
            supplied_keys = {
                (
                    str(item.get("source_artifact_id", "")),
                    str(item.get("finding_id", "")),
                )
                for item in supplied or []
                if isinstance(item, dict)
            }
            if not _nonempty(authorization_id):
                errors.append(
                    f"bounded review round {index} requires "
                    "round_cap_escalation authorization_id"
                )
            if (
                not isinstance(supplied, list)
                or supplied_keys != expected_escalation
                or len(supplied_keys) != len(supplied)
            ):
                errors.append(
                    f"bounded review round {index} escalation findings must exactly "
                    "match unresolved/actionable findings"
                )
        unresolved = still_unresolved | current_keys
        audit_rounds.append(derived)
    if seen_ids != all_ids:
        errors.append("review manifest v2 rounds omit or duplicate loaded artifacts")
    return {
        "policy": ROUND_POLICY,
        "cap": ROUND_CAP,
        "total_rounds": len(rounds),
        "rounds": audit_rounds,
    }
