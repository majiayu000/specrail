# Tech Spec

## Linked Issue

GH-55

## 设计概览

沿用 SpecRail 既有的"采集与评估分离"模式(参照 `pr_gate.py` 与
`github_pr_evidence.py` 的分工):

```
gh pr list / git ls-remote          checks/duplicate_work_gate.py
        │                                     │
        ▼                                     ▼
duplicate_work_evidence.json  ──────►  decision: allowed | needs_human | blocked
```

新增三个构件,修改一个构件:

1. `schemas/duplicate_work_evidence.schema.json` — 证据契约。
2. `checks/github_duplicate_evidence.py` — 采集器,包装
   `gh pr list --json number,headRefName,body,state` 与
   `git ls-remote --heads`,输出证据 JSON。采集器允许网络,gate 不允许。
3. `checks/duplicate_work_gate.py` — 离线评估器。
4. `workflow.yaml` — `artifacts` 段新增
   `impl_branch: "{agent}/gh{issue_number}-{slug}"`;
   `checks/check_workflow.py` 增加占位符校验。

## 证据 Schema(要点)

顶层必填字段:

- `issue`(正整数):目标 issue 编号。
- `collected_at`(非空字符串):采集时间戳。
- `open_prs`(数组):每项含 `number`、`head_ref`、`references_issue`
  (布尔,采集器根据 PR body/标题/分支名中的 `GH-N`/`#N` token 判定)。
- `remote_branches`(字符串数组):远端分支名列表。

Schema 使用 `specrail_lib.validate_instance` 支持的关键字子集
(`type`/`required`/`properties`/`items`/`enum`/`minimum`/
`additionalProperties`),不引入新关键字。

## 决策矩阵

| 证据情形 | 决策 | 说明 |
| --- | --- | --- |
| 存在 `references_issue: true` 的 open PR | `blocked` | reasons 列出 PR 编号 |
| 无引用 PR,但存在匹配 `gh{N}` 契约的远端分支 | `needs_human` | 人裁决接管或废弃 |
| 证据 JSON 非法(缺必填/类型错) | `blocked` | 与 schema 校验失败同路径 |
| 证据文件缺失 | `needs_human` | 与 `pr_gate` 缺 `human_authorization` 同语义 |
| 以上皆无 | `allowed` | |

分支匹配规则:从 `workflow.yaml` 的 `impl_branch` 模板取
`gh{issue_number}` 段,对 `remote_branches` 做大小写不敏感的子串段匹配
(按 `/` 与 `-` 分段,避免 `gh5` 误中 `gh55`)。

## route_gate 集成

`implement` 路由新增可选参数 `--duplicate-evidence <path>`:

- 提供且 gate 结论为 `blocked`/`needs_human` 时,合并进 route_gate 决策
  (取更严格者)。
- 未提供时,route_gate 结论降级上限为 `needs_human`,reasons 提示缺少
  查重证据 —— 与现有"deterministic missing"处理一致,不静默放行。

`main()`/`_load_json`/退出码沿用各 gate 现行样板。

## check_workflow 集成

`REQUIRED_FILES` 增补新 schema 与两个 checks 脚本;新增校验:
`artifacts.impl_branch` 存在且含 `{issue_number}` 占位符,否则 fail。

## 测试计划

- `tests/test_duplicate_work_gate.py`:决策矩阵五行各至少一例;分支段
  匹配的 `gh5`/`gh55` 边界例;schema 一致性(fixture 证据通过
  `validate_instance`)。
- `tests/test_route_gate.py`:补 `implement` 路由带/不带查重证据的决策
  合并例。
- `tests/test_check_workflow.py`:`impl_branch` 缺失/缺占位符 fail 例。

## 风险与取舍

- 采集与评估之间存在 TOCTOU 窗口(采集后别人开了 PR)。接受:窗口远小
  于现状(完全无检查),且 merge 阶段仍有 pr_gate 兜底。
- `references_issue` 判定放在采集器,gate 只信任布尔值。取舍理由:token
  匹配需要 PR body 全文,放进证据会让 fixture 臃肿;采集器判定逻辑用
  纯函数实现并单测。
- 不复用 runtime checkpoint 作为查重来源:checkpoint 是可选本地文件,
  跨会话不可靠;GitHub open PR 列表是此问题域的最近真源。
