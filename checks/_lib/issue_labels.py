"""Shared validation for mutually exclusive SpecRail issue labels."""

from __future__ import annotations

from specrail_lib import ISSUE_STATES, PackConfig, SpecRailError, label_groups, state_map


DEFAULT_OUTCOMES = {"duplicate", "abandoned", "security_private"}


def validate_issue_labels(
    config: PackConfig | None,
    labels: list[str],
) -> tuple[str | None, list[str]]:
    """Return the single workflow state and outcomes, rejecting conflicts."""

    if config is None:
        state_labels = set(ISSUE_STATES)
        outcome_labels = DEFAULT_OUTCOMES
    else:
        groups = label_groups(config)
        states = state_map(config)
        terminal = {
            name
            for name, body in states.items()
            if isinstance(body, dict) and body.get("terminal") is True
        }
        state_labels = (
            set(groups.get("readiness", []))
            | set(groups.get("lifecycle", []))
            | terminal
            | ({"parked"} if "parked" in states else set())
        )
        outcome_labels = set(groups.get("outcome", []))

    state_matches = sorted(set(labels) & state_labels)
    outcome_matches = sorted(set(labels) & outcome_labels)
    if len(state_matches) > 1:
        raise SpecRailError(
            f"conflicting state labels: {', '.join(state_matches)}"
        )
    if len(outcome_matches) > 1:
        raise SpecRailError(
            f"conflicting outcome labels: {', '.join(outcome_matches)}"
        )
    if state_matches and outcome_matches:
        combined = sorted(set(state_matches) | set(outcome_matches))
        raise SpecRailError(
            f"conflicting terminal/readiness labels: {', '.join(combined)}"
        )
    return (state_matches[0] if state_matches else None), outcome_matches
