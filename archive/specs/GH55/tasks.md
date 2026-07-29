# Task Plan

## Linked Issue

GH-55

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP55-T001` Owner: schemas | Done when: `schemas/duplicate_work_evidence.schema.json` 存在,只用 `validate_instance` 支持的关键字,`validate_json_schemas` 通过 | Verify: `python3 checks/check_workflow.py --repo .`
- [ ] `SP55-T002` Owner: checks | Done when: `checks/duplicate_work_gate.py` 实现决策矩阵五种情形(引用 PR→blocked、契约分支→needs_human、证据非法→blocked、证据缺失→needs_human、干净→allowed),离线无网络调用 | Verify: `python3 -m pytest -q tests/test_duplicate_work_gate.py`
- [ ] `SP55-T003` Owner: checks | Done when: `checks/github_duplicate_evidence.py` 采集 open PR 与远端分支并输出符合 schema 的证据 JSON,`references_issue` 判定为纯函数且有单测 | Verify: `python3 -m pytest -q tests/test_github_duplicate_evidence.py`
- [ ] `SP55-T004` Owner: workflow | Done when: `workflow.yaml` artifacts 段含 `impl_branch` 模板,`check_workflow.py` 校验 `{issue_number}` 占位符,缺失即 fail | Verify: `python3 -m pytest -q tests/test_check_workflow.py`
- [ ] `SP55-T005` Owner: route_gate | Done when: `implement` 路由支持 `--duplicate-evidence`,决策按更严格者合并,未提供证据时结论上限为 `needs_human` | Verify: `python3 -m pytest -q tests/test_route_gate.py`
- [ ] `SP55-T006` Owner: docs | Done when: `skills/specrail-implement-queue/SKILL.md` 与 `AGENT_USAGE.md` 增补开工前查重步骤,`skills-lock.json` 哈希同步 | Verify: `python3 checks/check_workflow.py --repo .`

## 并行拆分

- Gate lane: `checks/duplicate_work_gate.py`、`schemas/duplicate_work_evidence.schema.json`、`tests/test_duplicate_work_gate.py`。
- Collector lane: `checks/github_duplicate_evidence.py`、`tests/test_github_duplicate_evidence.py`。
- Contract lane: `workflow.yaml`、`checks/check_workflow.py`、`tests/test_check_workflow.py`。
- Route lane: `checks/route_gate.py`、`tests/test_route_gate.py`(依赖 Gate lane 完成后集成)。
- Docs lane: `skills/specrail-implement-queue/SKILL.md`、`AGENT_USAGE.md`、`skills-lock.json`。
- Gate/Collector/Contract 三条 lane 文件不重叠可并行;Route lane 串行于
  Gate lane;lockfile 由 Docs lane 独占。

## 验证

- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 -m pytest -q`
- 手工:构造"已有 open PR 引用 GH-55"的证据 fixture,确认 gate 输出
  `blocked` 且 reasons 含 PR 编号。
