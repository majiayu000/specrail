# Task Plan

## Linked Issue

GitHub issue: `#18`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP18-T001` Owner: `coordinator` | Done when: product templates use `Behavior Invariants` | Verify: `rg "Behavior Invariants" templates`
- [ ] `SP18-T002` Owner: `coordinator` | Done when: tech templates include codebase/test mapping tables | Verify: `rg "Codebase Context|Product-to-Test Mapping" templates`

## 并行拆分

Coordinator only; templates are shared workflow assets.

## 验证

- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH18`

## Handoff Notes

Keep stable machine tokens English.
