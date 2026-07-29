# Tech Spec

## Linked Issue

GH-111

## Product Spec

Link to `product.md`.

## Codebase Context

锚点按当前实现现场核实（2026-07-19，`origin/main` c0be38f）。本 spec 已
实现；下表 "Current behavior" 描述实现后的现状。

| Area | Anchor | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 队列 skill 触发 | `skills/specrail-implement-queue/SKILL.md:3` | description 以 "Use ONLY when explicitly delegated by the implx skill or when the user names this skill … directly. Do not self-activate from descriptive language…" 开头，其余语义描述保留 | B-001 B-009 |
| 单件 skills 触发 | `skills/specrail-implement/SKILL.md:3`（其余 11 个 specrail-* SKILL.md 同款第 3 行） | 每个 description 末尾追加 "Explicit invocation only: use when the user names this skill or a SpecRail skill/workflow route explicitly delegates to it; do not self-activate from descriptive language." | B-002 B-009 |
| workflow 路由（队列） | `skills/specrail-workflow/SKILL.md:45-49` | 仅当用户点名 implx 或 specrail-implement-queue 才路由队列 skill；多 approved specs 就绪但未点名时逐 issue 走 `specrail-implement` 或提示 implx 可用 | B-003 |
| workflow 路由（implx） | `skills/specrail-workflow/SKILL.md:51-53` | implx 路由条目要求用户 explicitly asks for `implx` / `use implx` / `用 implx` | B-003 B-004 |
| workflow 自身限定 | `skills/specrail-workflow/SKILL.md:3` | router skill 的 description 同样带 explicit-invocation 限定语 | B-002 |
| implx 入口（不动） | `skills/implx/SKILL.md:3` | description 仍是 "Use when the user says implx…"，触发条件与被调用后行为逐字未变 | B-004 |
| Skill hash lock | `skills-lock.json:6-7`（implx 条目）、`skills-lock.json:21-22`（队列 skill 条目） | 记录每个 SKILL.md 的 path 与 sha256，安装校验以此为准 | B-005 |

## 设计方案

### 1. 队列 skill description（B-001，`specrail-implement-queue/SKILL.md:3`）

description 开头限定："Use ONLY when explicitly delegated by the
implx skill or when the user names this skill (specrail-implement-queue)
directly. Do not self-activate from descriptive language about optimizing a
repository, finishing issues, draining work…"，其余内容保留（B-009）。

### 2. 单件 skills description（B-002）

12 个 skill 的 description 末尾统一追加一句："Explicit invocation only:
use when the user names this skill or a SpecRail skill/workflow route
explicitly delegates to it; do not self-activate from descriptive
language."（保持各自原有语义描述不变，便于人类查阅。）

### 3. workflow 路由（B-003，`specrail-workflow/SKILL.md:45-53`）

路由条目：仅当用户点名 implx 或 specrail-implement-queue 时路由到队列
skill；多 spec 落地但用户未点名时，按单 issue 逐个走
`specrail-implement`，或提示用户可用 implx。

### 4. 锁文件（B-005，`skills-lock.json:6-7` 等条目）

刷新全部改动 SKILL.md 的 hash；hash 与内容不一致即安装校验失败。

## 风险与兼容

- SpecRail skill 间显式委派链（implx → queue → implement / write-spec /
  pr-gate…）不受影响：委派是 "explicit delegation"（B-002）。
- 消费仓库 AGENTS.md 若自行写了"遇到队列工作用 implement-queue"之类的
  引导，仍构成显式委派——那是仓库 owner 的选择，不属于本次修复范围
  （B-007）。
- 文本变更；验证以 pack 校验 + 全量 pytest + hash 一致性为准。
