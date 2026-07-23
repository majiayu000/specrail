# Task Plan

## Linked Issue

GH-182

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP182-T1` Owner: contract-checker | Depends on: approved spec, GH-172 merged | Done when: `checks/skill_wait_contract.py` 对 wait-contract-v1 的必需 marker、exact 调用形态、禁止文本、重复/缺失/非法值和稳定错误顺序全部有测试 | Verify: `python3 -m pytest -q tests/test_skill_wait_contract.py` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-011 B-012 B-014 | 新增纯仓库等待合同 validator 与单元测试，不访问 session、HOME、GitHub 或网络。
- [ ] `SP182-T2` Owner: wait-contract | Depends on: SP182-T1 | Done when: queue、implx 与 threads 文档使用 direct 30000 + 单次 1800000 continuation、一次长 wait_agent、无 list_agents polling 和 CI watch 的唯一合同，且 queue 低于 800 行 | Verify: `python3 -m pytest -q tests/test_skill_wait_contract.py && test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -lt 800` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-013 B-015 | 用紧凑状态机替换错误的最大 yield/指数 wait 指导，不新增 shell polling。
- [ ] `SP182-T3` Owner: workflow-wiring | Depends on: SP182-T1 SP182-T2 | Done when: checker 成为 required asset 并由普通 workflow check 调用，正确 repo 通过、缺失 checker 或篡改合同失败，且 check 不读取用户目录 | Verify: `python3 -m pytest -q tests/test_skill_wait_contract.py tests/test_check_workflow.py -k "wait_contract or required_files"` | Covers: B-011 B-012 B-013 B-014 | 接入 `checks/check_workflow.py` 并扩展 wiring 回归。
- [ ] `SP182-T4` Owner: integration-owner | Depends on: SP182-T2 SP182-T3 | Done when: 文档说明静态/运行验收边界，implx/queue 最终字节与最新 GH-172 lock schema 下的哈希一致，CHANGELOG 记录纠错 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-010 B-011 B-015 B-016 B-017 B-018 | 更新 `AGENT_USAGE.md`、`CHANGELOG.md` 和 `skills-lock.json`，不修改 GH-160。

## 并行拆分

- 固定串行顺序 `SP182-T1 → SP182-T2 → SP182-T3 → SP182-T4`；Skill、checker
  wiring 和 lock 都是共享收口面，不并行写。
- 若只读 reviewer lane 与实现并行，它不得修改任何 manifest 路径，只返回
  `file:line` 证据。
- GH-172 未合并时所有实现任务保持 blocked；本 spec PR 本身不修改 queue/lock。

## 验证

- [ ] `SP182-T5` Owner: verification-owner | Depends on: SP182-T1 SP182-T2 SP182-T3 SP182-T4 | Done when: 本轮 exact head 的 focused/full/pack/depth/diff/line/hash 检查全绿，无 GH-160 文件进入 diff；静态 PR 可报告 ready，但 issue 保持 open 等 cohort | Verify: `python3 -m pytest -q tests/test_skill_wait_contract.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH182 --gate && git diff --check && test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -lt 800` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-018 | 产出静态合同完成证据。
- [ ] `SP182-T6` Owner: cohort-owner | Depends on: SP182-T5, merged implementation, one comparable implx run | Done when: 独立 post-policy cohort 报告 `wait_cell + write_stdin < 5%`、pure poll `< 10%`、同等工作量 turn 数至少减半；任一未满足则 issue 不关闭 | Verify: 人工复核 cohort cutoff、样本量、root-session 去重和逐项指标 | Covers: B-016 B-017 | 只消费汇总指标，不把 session 正文或 GH-160 context baseline 带入 issue。

## Handoff Notes

- 当前 route 只允许 `write_spec`；spec PR 合并并切到 `ready_to_implement` 前不得实现。
- 实现必须等待 GH-172 合并并基于其最新 lock schema；不得覆盖并行 GH-174 工作。
- implementation manifest 严格限定 tech spec 的 10 个路径，不含 GH-160 或 `/tmp` 脚本。
- 静态门禁通过不等于性能验收通过；T6 cohort 完成前 GH-182 保持 open。
