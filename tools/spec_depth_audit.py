#!/usr/bin/env python3
"""Read-only depth audit of SpecRail spec packets.

Measures per-spec: product/tech line counts, numbered behavior-invariant count,
EARS-style conditional ratio, boundary-category coverage, and verified-style
file:line anchor count in tech.md. Used as the regression baseline for the
GH-86 deep-spec-authoring method (baseline measured 2026-07-13: 60% of specs
had exactly 5 invariants, 28/30 had zero anchors).

Usage:
    python3 tools/spec_depth_audit.py                     # audit <repo>/specs/GH*/
    python3 tools/spec_depth_audit.py --repo PATH         # other repo root
    python3 tools/spec_depth_audit.py --spec-dir DIR ...  # audit explicit spec dirs only
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

INVARIANT_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:[A-Z]{1,3}[-_ ]?)?\d{1,3}[.)：:]\s+")
EARS_RE = re.compile(
    r"\b(WHEN|WHILE|IF|WHERE|UNLESS|AFTER|BEFORE|GIVEN|SHALL)\b|"
    r"(当|在.+期间|如果|若|对于|除非|之前|之后|应|须)",
    re.IGNORECASE,
)
FILE_LINE_RE = re.compile(r"(?:[A-Za-z0-9_.\-/]+\.[A-Za-z0-9_+\-]+)(?::|#L)\d+")
FILE_RANGE_RE = re.compile(r"[A-Za-z0-9_.\-/]+\.[A-Za-z0-9_+\-]+\s*\(\d+[-–]\d+\)")

BOUNDARY_CATEGORIES = {
    "empty": ["empty", "no data", "missing", "空", "无数据", "缺失"],
    "error": ["error", "failure", "invalid", "错误", "失败", "非法", "无效"],
    "loading": ["loading", "pending", "progress", "加载", "处理中", "等待"],
    "permission": ["permission", "unauthorized", "forbidden", "auth", "权限", "未授权", "禁止"],
    "timeout_offline": ["timeout", "offline", "network", "超时", "离线", "网络"],
    "concurrency": ["concurrent", "race", "simultaneous", "并发", "竞态", "同时"],
    "stale_cache": ["stale", "outdated", "cache", "过期", "旧数据", "缓存"],
    "cancellation": ["cancel", "abort", "interrupt", "取消", "中断"],
    "accessibility": ["keyboard", "focus", "screen reader", "a11y", "键盘", "焦点", "无障碍"],
    "compatibility": ["backward compat", "migration", "rollback", "兼容", "迁移", "回滚"],
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
    low = text.lower()
    return {c for c, ws in BOUNDARY_CATEGORIES.items() if any(w.lower() in low for w in ws)}


def audit_dir(d: Path):
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
    anchors = len(FILE_LINE_RE.findall(ttext)) + len(FILE_RANGE_RE.findall(ttext))
    return (
        d.name,
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

    dirs = args.spec_dir if args.spec_dir else sorted(args.repo.glob("specs/GH*/"))
    rows = [r for d in dirs if (r := audit_dir(Path(d))) is not None]
    if not rows:
        raise SystemExit("no spec dirs with product.md found")

    hdr = ("spec", "P行", "T行", "inv数", "EARS%", "边界类", "锚点", "覆盖的边界类别")
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))]

    def fmt(r):
        return "  ".join(str(r[i]).ljust(w[i]) for i in range(len(r)))

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
