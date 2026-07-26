# Task Plan

## Linked Issue

GH-174

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP174-T1` Owner: reference-contract | Depends on: approved spec, GH-172 merged | Done when: section/critical-marker inventory（含 main-only `output_firewall_v1`）、phase enum、**数组形态** manifest parser、同 phase duplicate 拒绝/跨 phase reuse 允许、required-header 窄豁免、contract_id 与 normative block 冲突检查、500 行/28 KiB 边界和单层图规则均由确定性 checker 测试锁住；pack/CI `validate_skill_reference_graph(repo, skill_name)` 明确不能授权 startup | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py -k "size or contract or phase or conflict or output_firewall"` | Covers: B-001 B-002 B-003 B-007 B-008 B-009 B-010 B-012 B-015 B-018 | 新增 checker/tests，不先移动 Skill 内容。
- [ ] `SP174-T2` Owner: skill-split | Depends on: SP174-T1 | Done when: 主文件保留关键合同、phase 路由与在第一条命令前生效的 artifact-first output firewall；`planning-and-runtime.md` 提供 startup artifact 目录/有界 summary/batched remote-query 细节，`evidence-and-recovery.md` 只保留 post-startup evidence/recovery 细节且不成为 firewall 唯一来源；主文件 ≤500 行且 ≤28672 bytes，各引用 <500 行 | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py -k "contract or output_firewall or startup_planning or isolation" && test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 500 && test "$(wc -c < skills/specrail-implement-queue/SKILL.md)" -le 28672` | Covers: B-001 B-002 B-003 B-004 B-007 B-009 B-010 B-011 B-015 B-018 | 逐 section 人工迁移并核对 inventory。
- [ ] `SP174-T3` Owner: integrity-integration | Depends on: SP174-T2, host `specrail.runtime.loaded-entrypoint.v1` available | Done when: queue 多文件集合进入 GH-172 normalized lock/installer/doctor；`bootstrap_loaded_skill()` 通过 fixed authenticated resolver 的 fresh challenge 取得 current-invocation attestation：direct queue 绑定 loaded queue entrypoint，implx outer 绑定 loaded implx + loader-resolved queue dependency descriptor；禁止 CLI/env/repo/checkpoint 提供 source/entrypoint/origin/descriptor/endpoint/root；checker 重算两级 path/bytes、验证 delegation/source-lock chain 并推导唯一 origin，repo copy 只要求 attested source graph，installed copy 才额外对同一 source-lock 运行 doctor `match`，resolver unavailable、stale/replay/spoof、dependency/path/digest/root/manifest drift 或歧义均在任何 remote read 前 fail closed | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py tests/test_install_codex_skills.py tests/test_check_workflow.py -k "loaded_entrypoint or delegated_entrypoint or attestation or repo_copy or installed_copy or stale or spoof or outer_preflight"` | Covers: B-005 B-006 B-013 B-014 B-017 | 接入最新 GH-172 API；host owner 管 resolver/loader registry/trust，repo client 不复制权威状态。
- [ ] `SP174-T4` Owner: entry-docs | Depends on: SP174-T2 SP174-T3 | Done when: `implx` 与 direct queue 都在任何 fetch/list/map、诊断大输出、checkpoint 或 lane 前启用 main output firewall 并执行 `--bootstrap-loaded`；两者不得使用 caller-selected source/origin，之后只按 phase 路由；AGENT_USAGE/CHANGELOG 说明 host resolver prerequisite、repo/installed 分支、firewall startup ordering 与安装升级，最终 implx/queue hash 匹配 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py tests/test_skill_reference_graph.py -k "implx or direct_queue or loaded_entrypoint or outer_preflight or output_firewall or large_output"` | Covers: B-003 B-004 B-005 B-006 B-011 B-012 B-016 B-017 B-018 | 更新入口、文档、workflow wiring 与 lock 收口。

## 并行拆分

- 固定顺序 `SP174-T1 → SP174-T2 → SP174-T3 → SP174-T4`；queue、reference graph、
  lock 与 installer 都是共享接口，不并行写。
- 只读 inventory/reviewer 可并行，但不得修改 manifest 路径。
- GH-172 未合并前保持 blocked；若 GH-182 已合并，必须保留其 wait-contract marker。

## 验证

- [ ] `SP174-T5` Owner: verification-owner | Depends on: SP174-T1 SP174-T2 SP174-T3 SP174-T4 | Done when: exact-head focused/full/pack/depth/range-diff/size/hash/forward-use 全绿；fresh loader binding 的 direct queue 与 implx→queue delegation、repo/installed 正例及 resolver unavailable/stale/replay/spoof/path/bytes/root/source-lock 负例齐全；implx outer/direct queue 均在 remote read 前完成 bootstrap；两份 main entrypoint 的 startup 大输出 fixture 证明 firewall 在 recovery reference 未加载时仍生效；四 phase exact isolation 保持 startup=planning、runtime_handoff=planning+evidence、review=review、recovery=evidence；manifest 为 16 unique paths、B-001..B-018 全覆盖、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py tests/test_install_codex_skills.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH174 --gate && test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 500 && test "$(wc -c < skills/specrail-implement-queue/SKILL.md)" -le 28672 && sed -n '9p' specs/GH174/tech.md | jq -e '(.paths|length)==16 and (.paths|unique|length)==16' && git diff --check "$(git merge-base origin/main HEAD)"..HEAD` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 | 交付结构与行为证据。

## 合并后非阻断观测

- `SP174-T6` Owner: observation-owner | Non-blocking: true | Depends on: merged implementation, comparable implx run | Outcome: 独立报告 queue 主/引用读取次数、注入 bytes 与 phase 分布，不以未达固定降幅重开结构 PR | Verify: 人工复核汇总指标与 cohort 窗口 | Covers: B-016 | 此 follow-up 不属于本 issue Done-When、spec approval、merge、关闭或实现 task 完整性 gate；不读取/发布 session 正文。

## Handoff Notes

- 当前只允许 write_spec；spec 合并并转 `ready_to_implement` 前不得实现。
- 实现固定等待 GH-172；不得并行修改 queue、lock、installer 或 doctor。
- manifest 限定 tech spec 的 16 个 unique paths，不含 GH-160。
- host loaded-entrypoint resolver 未部署时 implementation queue 保持 blocked；不得用 caller
  metadata 代替。output firewall 在 main startup 即生效，不等待 recovery reference。
- GH-182 若先实现，wait-contract-v1 必须在拆分后保持唯一、可校验。
