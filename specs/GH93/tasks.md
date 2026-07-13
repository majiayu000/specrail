# Task Plan

## Linked Issue

GH-93

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP93-T1` 入库 `tools/spec_depth_audit.py`:argparse(`--repo`/`--spec-dir`)、只读审计、空结果非零退出、docstring 记录基线。Covers: B-001 B-002 B-003。Owner: agent. Done when: 三条 invariant 的验证命令全部通过. Verify: `python3 tools/spec_depth_audit.py` 输出 30+ 份明细与汇总

## 并行拆分

单任务,无并行。

## 验证

- [ ] `SP93-T2` 全量回归。Covers: none(仓库级回归,非本 issue invariant)。Owner: agent. Done when: 两条命令全绿. Verify: `python3 checks/check_workflow.py --repo . --all-specs && python3 -m pytest -q`

## Handoff Notes

2026-07-13 基线与 A/B 数字已写入脚本 docstring 与 issue #93;EARS 正则对英文措辞低估是已知测量误差,若未来做深度门禁(Phase 2)需先修正。
