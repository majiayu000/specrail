from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))


def _auth_workflow(**overrides: object) -> dict[str, object]:
    workflow: dict[str, object] = {
        "automation_policy": {"auth_mode": "review"},
        "required_human_gates": [
            "readiness_label",
            "spec_approval",
            "final_pr_review",
            "security_decision",
            "merge",
            "release",
        ],
        "auth_modes": {
            "auto": {
                "waived_human_gates": ["spec_approval", "final_pr_review", "merge"],
            },
            "review": {"waived_human_gates": []},
        },
    }
    workflow.update(overrides)
    return workflow


def _config(workflow: dict[str, object]) -> object:
    class Config:
        pass

    config = Config()
    config.workflow = workflow
    return config


def _spec_config(**artifact_overrides: str) -> object:
    artifacts = {
        "spec_packet": "docs/specs/GH{issue_number}/",
        "product_spec": "docs/specs/GH{issue_number}/product.md",
        "tech_spec": "docs/specs/GH{issue_number}/tech.md",
        "task_plan": "docs/specs/GH{issue_number}/tasks.md",
    }
    artifacts.update(artifact_overrides)
    return _config({"artifacts": artifacts})
