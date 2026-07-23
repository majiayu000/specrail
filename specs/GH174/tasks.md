# Task Plan

## Linked Issue

GH-174

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP174-T1` Owner: reference-contract | Depends on: approved spec, GH-172 merged | Done when: section/critical-marker inventory、phase enum、manifest parser、500 行/28 KiB 边界和单层图规则均由确定性 checker 测试锁住 | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py` | Covers: B-001 B-002 B-003 B-007 B-008 B-009 B-010 B-012 B-015 | 新增 `checks/skill_reference_graph.py` 与测试，不先移动 Skill 内容。
- [ ] `SP174-T2` Owner: skill-split | Depends on: SP174-T1 | Done when: 主文件保留关键合同与 phase 路由，三个 reference 只承载声明阶段的细节，主文件 ≤500 行且 ≤28672 bytes，各引用 <500 行 | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py && test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 500 && test "$(wc -c < skills/specrail-implement-queue/SKILL.md)" -le 28672` | Covers: B-001 B-002 B-003 B-004 B-007 B-009 B-010 B-011 B-015 | 逐 section 人工迁移并每段核对 inventory，禁止脚本批量重写语义。
- [ ] `SP174-T3` Owner: integrity-integration | Depends on: SP174-T2 | Done when: queue 多文件集合进入 GH-172 normalized lock、installer 和 installed doctor，缺失/漂移/越界/循环/取消均 fail closed | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py tests/test_install_codex_skills.py -k "reference or multifile"` | Covers: B-005 B-006 B-013 B-014 | 接入最新 GH-172 API，不复制 manifest/path/hash 逻辑。
- [ ] `SP174-T4` Owner: entry-docs | Depends on: SP174-T2 SP174-T3 | Done when: implx 只路由主入口，AGENT_USAGE/CHANGELOG 说明 phase loading 与安装升级，最终 implx/queue hash 匹配 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-003 B-004 B-006 B-011 B-012 B-016 | 更新入口、文档、workflow wiring 与 lock 收口。

## 并行拆分

- 固定顺序 `SP174-T1 → SP174-T2 → SP174-T3 → SP174-T4`；queue、reference graph、
  lock 与 installer 都是共享接口，不并行写。
- 只读 inventory/reviewer 可并行，但不得修改 manifest 路径。
- GH-172 未合并前保持 blocked；若 GH-182 已合并，必须保留其 wait-contract marker。

## 验证

- [ ] `SP174-T5` Owner: verification-owner | Depends on: SP174-T1 SP174-T2 SP174-T3 SP174-T4 | Done when: exact-head focused/full/pack/depth/diff/size/hash/forward-use 全绿，无 GH-160 diff，startup/review/recovery 三 phase 仅加载声明引用 | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py tests/test_install_codex_skills.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH174 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 | 交付结构与行为证据。
- [ ] `SP174-T6` Owner: observation-owner | Depends on: merged implementation, comparable implx run | Done when: 独立报告 queue 主/引用读取次数、注入 bytes 与 phase 分布，不以未达固定降幅重开结构 PR | Verify: 人工复核汇总指标与 cohort 窗口 | Covers: B-016 | 不读取/发布 session 正文。

## Handoff Notes

- 当前只允许 write_spec；spec 合并并转 `ready_to_implement` 前不得实现。
- 实现固定等待 GH-172；不得并行修改 queue、lock、installer 或 doctor。
- manifest 限定 tech spec 的 13 个路径，不含 GH-160。
- GH-182 若先实现，wait-contract-v1 必须在拆分后保持唯一、可校验。
