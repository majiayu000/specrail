# Task Plan

## Linked Issue

GitHub issue: `#19`

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP19-T001` Owner: `p3-worker` | Done when: focused skills and `skills-lock.json` exist | Verify: `python3 checks/check_workflow.py --repo .`
- [ ] `SP19-T002` Owner: `coordinator` | Done when: lock validation is wired into pack check | Verify: targeted unit test for hash mismatch |
- [ ] `SP19-T003` Owner: `coordinator` | Done when: docs mention split skills | Verify: `rg "skills-lock|specrail-review-pr" README.md AGENT_USAGE.md PLAN.md`

## 并行拆分

P3 worker owns skill files and lockfile. Coordinator owns validator/docs.

## 验证

- `uvx pytest -q`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH19`

## Handoff Notes

Do not install repo skills into user home.
