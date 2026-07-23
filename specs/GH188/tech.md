# Tech Spec

## Linked Issue

GH-188

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":188,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/runtime_bundle.py","runtime-bundle-lock.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","skills/specrail-install/SKILL.md","tools/check_runtime_bundle.py","tools/install_runtime_bundle.py","tests/test_check_workflow.py","tests/test_runtime_bundle.py"],"spec_refs":["specs/GH188/product.md","specs/GH188/tech.md","specs/GH188/tasks.md"]}
-->

## Product Spec

见 `product.md`，实现 B-001..B-012。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue call | `skills/specrail-implement-queue/SKILL.md:545-573` | 假设 repo-relative gate 存在。 | 加 bundle preflight。 |
| checker | `checks/runtime_ledger_gate.py:1-35` | 依赖多个本地模块/schema。 | 必须按闭集分发。 |
| pack assets | `checks/check_workflow.py:32-86` | 只保证 SpecRail 源 pack 资产。 | 不证明 consumer adoption。 |
| adoption | `skills/specrail-install/SKILL.md:40-60` | 计划 files to copy，无版本化 installer。 | 接入 doctor/dry-run/apply。 |
| docs | `AGENT_USAGE.md:183-193` | 直接展示 consumer 命令。 | 先验证 bundle availability。 |

## 设计方案

新增 `runtime-bundle-lock.json`，以 version 和排序 files[] 绑定 runtime gate 的 checker、
依赖 Python、schema/template。`checks/runtime_bundle.py` 共享 manifest/path/hash/稳定快照
逻辑，拒绝额外文件、symlink、越界与检查中变化。

CLI：

- `tools/check_runtime_bundle.py --repo . --target <consumer> [--json] [--require-adopted]`
- `tools/install_runtime_bundle.py --repo . --target <consumer> [--apply]`

doctor 只读并返回 `match | not_adopted | drift | invalid`；默认 not_adopted 可用于 adoption
规划，queue 使用 `--require-adopted`，只接受 match。installer 默认 dry-run，apply
使用 staging + per-file atomic replace，写后运行同一 doctor。不得删除 manifest 外文件。

queue 在写 `.specrail/runtime`、开 lane 或远端动作前检查。普通 `check_workflow` 只验证
源 manifest 与工具资产，不读取 consumer。GH-165 提供 unavailable fail-closed，GH-172
保证调用这些命令的 installed Skill 自身匹配。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-011 | manifest validator | `python3 -m pytest -q tests/test_runtime_bundle.py -k manifest` |
| B-003 B-004 B-005 B-012 | doctor | `python3 -m pytest -q tests/test_runtime_bundle.py -k doctor` |
| B-006 B-007 B-008 | installer | `python3 -m pytest -q tests/test_runtime_bundle.py -k install` |
| B-009 | queue preflight | `python3 -m pytest -q tests/test_runtime_bundle.py -k queue` |
| B-010 | pack isolation | `python3 -m pytest -q tests/test_check_workflow.py -k runtime_bundle` |

## 数据流

`source manifest → doctor(target) → dry-run plan → authorized apply → post-doctor → queue gate`

## 备选方案

- 从任意 SpecRail checkout fallback：版本不可证明，拒绝。
- 只复制入口 checker：依赖/schema 可漂移，拒绝。
- queue 自动 apply：越过用户写授权，拒绝。

## 风险

- Security: 只允许声明相对路径、普通文件与原子写，不输出正文。
- Compatibility: 旧 consumer 显式 not_adopted，需人工迁移。
- Performance: startup 哈希小型闭集，无网络。
- Maintenance: bundle lock 与 pack required assets 由测试对账。

## 测试计划

- [ ] Unit: manifest/path/hash/snapshot/status。
- [ ] Integration: dry-run/apply/post-check/queue/CI isolation。
- [ ] Full: pytest、all-specs、depth/diff/hash 与双 consumer forward test。

## 回滚方案

回滚 bundle library/CLIs/Skill/wiring/tests/docs/locks；已复制 consumer 文件不自动删除，
由用户根据 dry-run 反向计划决定。
