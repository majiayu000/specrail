from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from runtime_ledger_test_support import ROOT  # noqa: E402
from session_telemetry import collect  # noqa: E402


def _event(event_type: str, timestamp: str, **payload_extra: object) -> str:
    return json.dumps(
        {
            "timestamp": timestamp,
            "type": "event_msg",
            "payload": {"type": event_type, **payload_extra},
        }
    )


def _write_session(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_collect_counts_context_compacted_exactly(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [
            _event("function_call", "2026-07-17T01:00:00Z"),
            _event("context_compacted", "2026-07-17T01:10:00Z", window_id="w-1"),
            _event("agent_message", "2026-07-17T01:20:00Z"),
            _event("context_compacted", "2026-07-17T01:30:00Z", window_id="w-2"),
            _event("context_compacted", "2026-07-17T01:40:00Z", window_id="w-3"),
        ],
    )

    result = collect(session)

    assert result["telemetry_source"] == "session_log"
    assert result["observed_compaction_count"] == 3
    assert result["last_compaction_window_id"] == "w-3"


def test_collect_counts_top_level_compacted_events(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [json.dumps({"type": "compacted", "timestamp": "2026-07-17T01:00:00Z"})],
    )

    result = collect(session)

    assert result["observed_compaction_count"] == 1


def test_collect_missing_file_returns_unavailable(tmp_path: Path) -> None:
    result = collect(tmp_path / "missing.jsonl")

    assert result["telemetry_source"] == "unavailable"
    assert "observed_compaction_count" not in result
    assert "observed_tool_calls" not in result


def test_collect_all_unparseable_lines_treated_as_unreadable(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(session, ["not json", "{broken", "also not json"])

    result = collect(session)

    assert result["telemetry_source"] == "unavailable"
    assert "observed_compaction_count" not in result


def test_collect_skips_corrupt_lines_but_counts_parseable(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [
            _event("context_compacted", "2026-07-17T01:00:00Z"),
            "{corrupt line",
            _event("context_compacted", "2026-07-17T01:30:00Z"),
        ],
    )

    result = collect(session)

    assert result["telemetry_source"] == "session_log"
    assert result["observed_compaction_count"] == 2
    assert result["skipped_lines"] == 1


def test_collect_respects_tranche_start_offset(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [
            _event("context_compacted", "2026-07-17T01:00:00Z", window_id="old-1"),
            _event("context_compacted", "2026-07-17T02:00:00Z", window_id="old-2"),
            _event("agent_message", "2026-07-17T05:00:00Z"),
            _event("context_compacted", "2026-07-17T05:30:00Z", window_id="new-1"),
        ],
    )

    result = collect(session, tranche_start_offset=2)

    assert result["observed_compaction_count"] == 1
    assert result["last_compaction_window_id"] == "new-1"
    assert result["tranche_window"] == {"start_line": 2, "end_line": 4}


def test_collect_counts_tool_calls_and_wall_clock(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [
            _event("function_call", "2026-07-17T01:00:00Z"),
            _event("local_shell_call", "2026-07-17T01:04:00Z"),
            _event("agent_message", "2026-07-17T01:10:00Z"),
        ],
    )

    result = collect(session)

    assert result["observed_tool_calls"] == 2
    assert result["observed_wall_clock_minutes"] == 10


def test_telemetry_collect_is_read_only(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(session, [_event("context_compacted", "2026-07-17T01:00:00Z")])
    before_bytes = session.read_bytes()
    before_mtime = session.stat().st_mtime_ns

    collect(session)
    collect(session)

    assert session.read_bytes() == before_bytes
    assert session.stat().st_mtime_ns == before_mtime


def test_collect_rejects_negative_offset(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(session, [_event("agent_message", "2026-07-17T01:00:00Z")])

    with pytest.raises(ValueError):
        collect(session, tranche_start_offset=-1)


def test_cli_outputs_json(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [
            _event("context_compacted", "2026-07-17T01:00:00Z"),
            _event("context_compacted", "2026-07-17T01:30:00Z"),
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "checks.session_telemetry",
            str(session),
            "--tranche-start-offset",
            "1",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["observed_compaction_count"] == 1
    assert payload["telemetry_source"] == "session_log"
    assert payload["tranche_window"] == {"start_line": 1, "end_line": 2}


def test_collect_offset_beyond_session_length_is_unavailable(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [_event("context_compacted", "2026-07-17T01:00:00Z", window_id="w-1")],
    )

    result = collect(session, tranche_start_offset=999)

    assert result["telemetry_source"] == "unavailable"
    assert "beyond the session length" in result["reason"]
    assert "observed_compaction_count" not in result
    assert "tranche_window" not in result


def test_collect_offset_equal_to_session_length_is_empty_window(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [_event("context_compacted", "2026-07-17T01:00:00Z", window_id="w-1")],
    )

    result = collect(session, tranche_start_offset=1)

    assert result["telemetry_source"] == "session_log"
    assert result["observed_compaction_count"] == 0
    assert result["tranche_window"] == {"start_line": 1, "end_line": 1}
