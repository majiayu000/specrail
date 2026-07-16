# Tech Spec

## Linked Issue

GH-111

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 队列 skill 触发 | `skills/specrail-implement-queue/SKILL.md` frontmatter | description 按工作内容描述触发（"implementing or draining a queue"） | 隐式接管的入口，B-001 |
| 单件 skills 触发 | 其余 12 个 `skills/specrail-*/SKILL.md` frontmatter | 同为内容描述式触发 | B-002 |
| 路由 | `skills/specrail-workflow/SKILL.md:45-49` | "multiple approved specs" 即路由到队列 skill | 隐式接管的第二入口，B-003 |
| implx 入口 | `skills/implx/SKILL.md` | 已是 explicit-invocation（说 implx 才触发） | 保持不变，B-004 |
| Skill hash lock | `skills-lock.json` | 记录每个 SKILL.md sha256 | B-005 |

## 设计方案

### 1. 队列 skill description（B-001）

在 description 开头加限定："Use ONLY when explicitly delegated by the
implx skill or when the user names this skill (specrail-implement-queue)
directly. Do not activate from descriptive language about optimizing a
repository, finishing issues, or draining work…"，其余内容保留。

### 2. 单件 skills description（B-002）

12 个 skill 的 description 末尾统一追加一句："Explicit invocation only:
use when the user names this skill or a SpecRail skill/workflow route
explicitly delegates to it; do not self-activate from descriptive
language."（保持各自原有语义描述不变，便于人类查阅。）

### 3. workflow 路由（B-003）

`specrail-workflow/SKILL.md:45` 的路由条目改为：仅当用户点名 implx 或
specrail-implement-queue 时路由到队列 skill；多 spec 落地但用户未点名时，
按单 issue 逐个走 `specrail-implement`，或提示用户可用 implx。

### 4. 锁文件（B-005）

刷新全部改动 SKILL.md 的 hash。

## 风险与兼容

- SpecRail skill 间显式委派链（implx → queue → implement / write-spec /
  pr-gate…）不受影响：委派是"explicit delegation"。
- 消费仓库 AGENTS.md 若自行写了"遇到队列工作用 implement-queue"之类的
  引导，仍构成显式委派——那是仓库 owner 的选择，不属于本次修复范围。
- 文本变更；验证以 pack 校验 + 全量 pytest + hash 一致性为准。
