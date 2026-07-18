# Task Plan

## Linked Issue

GH-130

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP130-T1` 为 `tools/spec_depth_audit.py` 增加 `--gate` 硬判定：trivial 豁免（Linked Issue 小节内 `complexity: trivial`）、三项可配置阈值（默认 8/8/5）、逐项失败原因输出、EARS 不参与阻断；同步在 `templates/product_spec.md` 与 `templates/zh-CN/product_spec.md` 的 Behavior Invariants 小节补 EARS 条件式触发写作指引；回归测试覆盖 B-002…B-007、B-009、B-010。Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010。Owner: agent. Done when: Product-to-Test Mapping 中全部验证命令通过. Verify: `python3 -m pytest -q tests/test_spec_depth_audit.py` 且 `python3 tools/spec_depth_audit.py --spec-dir specs/GH130 --gate` 退出码 0

## 并行拆分

单任务无并行。
