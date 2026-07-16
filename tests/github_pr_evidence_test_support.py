from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "checks"
sys.path.insert(0, str(CHECKS))


def pr_payload() -> dict[str, object]:
    return {
        "number": 10,
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": "e36d97517d8d0b27faca1abe5e5c63f9f88684d9",
        "mergeStateStatus": "CLEAN",
        "body": "Closes #9",
        "closingIssuesReferences": [{"number": 9}],
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "workflow-check",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "detailsUrl": "https://github.com/example/specrail/actions/runs/1",
            },
            {
                "__typename": "StatusContext",
                "context": "lint",
                "state": "SUCCESS",
                "targetUrl": "https://ci.example.invalid/lint",
            },
        ],
        "reviews": [
            {"author": {"login": "reviewer"}, "state": "CHANGES_REQUESTED"},
            {"author": {"login": "reviewer"}, "state": "APPROVED"},
            {"author": {"login": "bot"}, "state": "COMMENTED"},
        ],
    }


def threads_payload() -> dict[str, object]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "PRRT_kwDOExample",
                                "isResolved": True,
                                "isOutdated": False,
                                "resolvedBy": {"login": "reviewer"},
                                "resolverRole": "reviewer_lane",
                                "comments": {
                                    "nodes": [
                                        {
                                            "id": "PRRC_kwDOExampleRoot",
                                            "url": "https://github.com/example/specrail/pull/10#discussion_r1",
                                            "author": {"login": "reviewer"},
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                }
            }
        }
    }


def clean_review_evidence() -> dict[str, object]:
    head_sha = "e36d97517d8d0b27faca1abe5e5c63f9f88684d9"
    artifact = {
        "artifact_id": "pr10-head1-reviewer1",
        "pr": 10,
        "reviewer_lane": "reviewer-1",
        "producer_identity": "reviewer",
        "review_source": "independent_lane",
        "head_sha": head_sha,
        "review_started_at": "2026-07-15T23:57:00Z",
        "review_completed_at": "2026-07-15T23:58:00Z",
        "status": "completed",
        "verdict": "clean",
        "human_final_review_required": False,
        "findings": [],
        "prior_findings": [],
        "body": "## Summary\nTerminal review.\n\n## Verdict\nclean",
        "comments": [],
    }
    return {
        "manifest_path": "examples/fixtures/review-manifest-pr10.json",
        "manifest_sha256": "a" * 64,
        "pr": 10,
        "head_sha": head_sha,
        "review_source": "independent_lane",
        "review_completed_at": "2026-07-15T23:58:00Z",
        "human_final_review_required": False,
        "lane_roster": [
            {"lane_id": "reviewer-1", "producer_identity": "reviewer"}
        ],
        "artifacts": [artifact],
        "current_artifact_ids": ["pr10-head1-reviewer1"],
        "errors": [],
        "blocking_reasons": [],
    }


def reviewer_resolver_roles() -> dict[str, dict[str, str]]:
    return {
        "reviewer": {
            "resolver_role": "reviewer_lane",
            "lane_id": "reviewer-1",
        }
    }


def base_sha() -> str:
    return "b" * 40


def file_snapshot(paths: list[str], *, head_sha: str | None = None) -> dict[str, object]:
    normalized = sorted(paths)
    return {
        "head_sha": head_sha or str(pr_payload()["headRefOid"]),
        "base_ref": "main",
        "base_sha": base_sha(),
        "default_base_ref": "main",
        "default_base_sha": base_sha(),
        "path_count": len(normalized),
        "paths": normalized,
        "paths_sha256": __import__("hashlib").sha256(
            json.dumps(normalized, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def approval_query_payload() -> dict[str, object]:
    return {
        "data": {
            "repository": {
                "defaultBranchRef": {"name": "main", "target": {"oid": base_sha()}},
                "issue": {
                    "state": "OPEN",
                    "labels": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [{"name": "ready_to_implement"}],
                    },
                    "timelineItems": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "createdAt": "2026-07-14T00:00:00Z",
                                "actor": {"login": "maintainer"},
                                "label": {"name": "ready_to_implement"},
                            }
                        ]
                    },
                },
            }
        }
    }


def snapshot_page(
    paths: list[str],
    *,
    total: int,
    has_next: bool,
    cursor: str | None,
) -> dict[str, object]:
    return {
        "data": {
            "repository": {
                "defaultBranchRef": {"name": "main", "target": {"oid": base_sha()}},
                "pullRequest": {
                    "headRefOid": str(pr_payload()["headRefOid"]),
                    "baseRefName": "main",
                    "baseRefOid": base_sha(),
                    "changedFiles": total,
                    "files": {
                        "totalCount": total,
                        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                        "nodes": [{"path": path} for path in paths],
                    },
                },
            }
        }
    }
