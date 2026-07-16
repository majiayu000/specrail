#!/usr/bin/env python3
"""Read-only depth audit of SpecRail spec packets.

Measures per-spec: product/tech line counts, numbered behavior-invariant count,
EARS-style conditional ratio, boundary-category coverage, and verified-style
file:line anchor count in tech.md. Metric semantics v3 align boundary coverage
with the current template's 10 verdict rows, count only conditional EARS
triggers, and include code-formatted or conventional extensionless file
anchors. Recomputed at GH-86 baseline commit ac66dbb (30 specs): 60% had
exactly 5 invariants, 28/30 had zero anchors, boundary coverage averaged
0.6/10, and EARS coverage was 24%.

Historical v1 numbers are retained for provenance only and are not comparable
with v2: the 2026-07-13 baseline reported 3.1/10 boundary coverage and 38% EARS;
the GH58/GH60/GH62 blind A/B rerun reported 9/14/14 invariants, 37/46/17
anchors, 7.0 average boundary coverage, and 76% EARS.

Usage:
    python3 tools/spec_depth_audit.py                     # audit <repo>/specs/GH*/
    python3 tools/spec_depth_audit.py --repo PATH         # other repo root
    python3 tools/spec_depth_audit.py --spec-dir DIR ...  # audit explicit spec dirs only
"""
from __future__ import annotations

import argparse
from collections import Counter
import re
from pathlib import Path

METRIC_SEMANTICS_VERSION = 3

INVARIANT_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:[A-Z]{1,3}[-_ ]?)?\d{1,3}[.)：:]\s+")
EARS_RE = re.compile(
    r"\b(WHEN|WHILE|IF|WHERE|UNLESS|AFTER|BEFORE|GIVEN)\b|"
    r"(当|在.+期间|如果|若|对于|除非|之前|之后)",
    re.IGNORECASE,
)
FILE_LINE_RE = re.compile(r"(?:[A-Za-z0-9_.\-/]+\.[A-Za-z0-9_+\-]+)(?::|#L)\d+")
EXTENSIONLESS_FILE_LINE_RE = re.compile(
    r"`(?:[A-Za-z0-9_.+\-]+/)*[A-Za-z0-9_+\-]*[A-Za-z]"
    r"[A-Za-z0-9_+\-]*(?::|#L)\d+`"
)
FILE_RANGE_RE = re.compile(r"[A-Za-z0-9_.\-/]+\.[A-Za-z0-9_+\-]+\s*\(\d+[-–]\d+\)")

BOUNDARY_CATEGORIES = {
    "empty": ["empty", "missing input", "空", "缺失输入"],
    "error": ["error", "failure", "错误", "失败"],
    "permission": ["permission", "unauthorized", "forbidden", "auth", "权限", "未授权", "禁止"],
    "concurrency": ["concurrent", "race", "simultaneous", "并发", "竞态", "同时"],
    "retry_idempotency": ["retry", "idempotency", "重试", "幂等"],
    "illegal_state": ["illegal state", "state transition", "非法状态", "状态转换"],
    "compatibility": ["backward compat", "migration", "rollback", "兼容", "迁移", "回滚"],
    "degradation": ["degradation", "fallback", "降级", "回退"],
    "evidence_audit": ["evidence", "audit integrity", "证据", "审计完整"],
    "cancellation": ["cancel", "abort", "interrupt", "取消", "中断"],
}


def section(text: str, heading_words: list[str]) -> str:
    for h in heading_words:
        pat = re.compile(
            rf"^#+\s+{re.escape(h)}.*?$(?P<body>.*?)(?=^#+\s+|\Z)",
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        m = pat.search(text)
        if m:
            return m.group("body")
    return ""


def numbered_items(block: str) -> list[str]:
    lines = block.splitlines()
    starts = [i for i, ln in enumerate(lines) if INVARIANT_RE.search(ln)]
    items = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        items.append("\n".join(lines[s:e]).strip())
    return items


def boundary_cov(text: str) -> set[str]:
    block = section(
        text,
        ["Boundary Checklist", "边界情况清单", "Boundary Cases", "边界情况"],
    )
    if not block:
        return set()

    covered: set[str] = set()
    recognized_rows = 0
    for line in block.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        label, verdict = cells[:2]
        label_low = label.lower()
        category = next(
            (
                name
                for name, words in BOUNDARY_CATEGORIES.items()
                if any(word.lower() in label_low for word in words)
            ),
            None,
        )
        if category is None:
            continue
        recognized_rows += 1
        if verdict:
            covered.add(category)

    if recognized_rows:
        return covered

    low = block.lower()
    return {
        category
        for category, words in BOUNDARY_CATEGORIES.items()
        if any(word.lower() in low for word in words)
    }


def spec_labels(dirs: list[Path], *, explicit: bool) -> list[str]:
    names = Counter(path.name for path in dirs)
    return [
        str(path.resolve()) if explicit and names[path.name] > 1 else path.name
        for path in dirs
    ]


def anchor_count(text: str) -> int:
    return (
        len(FILE_LINE_RE.findall(text))
        + len(EXTENSIONLESS_FILE_LINE_RE.findall(text))
        + len(FILE_RANGE_RE.findall(text))
    )


def audit_dir(d: Path, *, label: str | None = None):
    prod = d / "product.md"
    tech = d / "tech.md"
    if not prod.is_file():
        return None
    ptext = prod.read_text(encoding="utf-8")
    ttext = tech.read_text(encoding="utf-8") if tech.is_file() else ""
    beh = section(ptext, ["Behavior Invariants", "行为不变式", "Behavior"])
    invs = numbered_items(beh)
    n_inv = len(invs)
    ears_hits = sum(1 for it in invs if EARS_RE.search(it))
    ears_ratio = (ears_hits / n_inv) if n_inv else 0.0
    cov = boundary_cov(ptext)
    anchors = anchor_count(ttext)
    return (
        label or d.name,
        len(ptext.splitlines()),
        len(ttext.splitlines()),
        n_inv,
        f"{ears_ratio:.0%}",
        len(cov),
        anchors,
        ",".join(sorted(cov)) or "-",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--spec-dir", type=Path, action="append", default=None,
                    help="audit only these spec dirs (repeatable); overrides --repo glob")
    args = ap.parse_args()

    dirs = [Path(d) for d in args.spec_dir] if args.spec_dir else sorted(args.repo.glob("specs/GH*/"))
    invalid_explicit = [d for d in dirs if args.spec_dir and not (d / "product.md").is_file()]
    if invalid_explicit:
        rendered = ", ".join(str(path) for path in invalid_explicit)
        raise SystemExit(f"spec dirs missing product.md: {rendered}")
    labels = spec_labels(dirs, explicit=args.spec_dir is not None)
    rows = [
        row
        for d, label in zip(dirs, labels)
        if (row := audit_dir(d, label=label)) is not None
    ]
    if not rows:
        raise SystemExit("no spec dirs with product.md found")

    hdr = ("spec", "P行", "T行", "inv数", "EARS%", "边界类", "锚点", "覆盖的边界类别")
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))]

    def fmt(r):
        return "  ".join(str(r[i]).ljust(w[i]) for i in range(len(r)))

    print(f"metric_semantics=v{METRIC_SEMANTICS_VERSION}")
    print(fmt(hdr))
    print("  ".join("-" * w[i] for i in range(len(hdr))))
    for r in rows:
        print(fmt(r))

    n = len(rows)
    print(f"\n=== 汇总 (n={n} specs) ===")
    print(f"product.md 行数:  min={min(r[1] for r in rows)} max={max(r[1] for r in rows)} 均值={sum(r[1] for r in rows)/n:.0f}")
    print(f"invariant 数:     min={min(r[3] for r in rows)} max={max(r[3] for r in rows)} 均值={sum(r[3] for r in rows)/n:.1f}")
    print(f"file:line 锚点:   总计={sum(r[6] for r in rows)}  有锚点的spec数={sum(1 for r in rows if r[6]>0)}/{n}")
    print(f"边界类覆盖:       均值={sum(r[5] for r in rows)/n:.1f}/10  覆盖>=5类的spec数={sum(1 for r in rows if r[5]>=5)}/{n}")
    ears_all = [int(r[4].rstrip("%")) for r in rows]
    print(f"EARS 占比:        均值={sum(ears_all)/n:.0f}%  >=60%的spec数={sum(1 for e in ears_all if e>=60)}/{n}")


if __name__ == "__main__":
    main()
