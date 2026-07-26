# Task Plan

## Linked Issue

GH-174

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP174-T1` Owner: reference-contract | Depends on: approved spec, GH-172 merged | Done when: section/critical-marker inventory（含 main-only `output_firewall_v1`）、五项 phase enum、**数组形态** manifest parser、同 phase duplicate 拒绝/跨 phase reuse 允许、required-header 窄豁免、contract_id 与 normative block 冲突检查、主文件 500 行/28 KiB、每引用 `<500` 行/`≤16384` UTF-8 bytes、invalid UTF-8 与单层图规则均由确定性 checker exact-boundary/+1 测试锁住；pack/CI `validate_skill_reference_graph(repo, skill_name)` 明确不能授权 startup；`post_merge_closure` 稳定映射到 evidence reference | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py -k "size or utf8 or reference_size or contract or phase or post_merge_closure or conflict or output_firewall"` | Covers: B-001 B-002 B-003 B-007 B-008 B-009 B-010 B-012 B-015 B-018 B-020 B-026 | 新增 checker/tests，不先移动 Skill 内容。
- [ ] `SP174-T2` Owner: skill-split | Depends on: SP174-T1 | Done when: 主文件保留关键合同、五 phase 路由与在第一条命令前生效的 artifact-first output firewall；firewall 对 parent 同时实施 150 lines、16384 total UTF-8 bytes、512 UTF-8 bytes/line、4096 current-tokenizer tokens，marker 计入上限且 raw excess 仅进 artifact，meter unavailable 只输出固定最小 status/path；`planning-and-runtime.md` 提供 startup artifact 目录/有界 summary/batched remote-query 细节，`evidence-and-recovery.md` 承载 post-startup evidence/recovery 与正常 `post_merge_closure` 的 closure-audit 细节且不成为 firewall 唯一来源；主文件 ≤500 行/≤28672 bytes，各引用 `<500` 行/`≤16384` UTF-8 bytes | Verify: `python3 -m pytest -q tests/test_skill_reference_graph.py tests/test_check_workflow.py -k "contract or output_firewall or line_limit or byte_limit or token_limit or startup_planning or post_merge_closure or isolation" && test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 500 && test "$(wc -c < skills/specrail-implement-queue/SKILL.md)" -le 28672` | Covers: B-001 B-002 B-003 B-004 B-007 B-009 B-010 B-011 B-015 B-018 B-020 B-025 B-026 | 逐 section 人工迁移并核对 inventory。
- [ ] `SP174-T3` Owner: runtime-integrity | Depends on: SP174-T2, host `specrail.runtime.skill-contract.v2` hook/parser sink deployed | Done when: queue 多文件集合及 `runtime/phase_loader.py`（v2 lock `0755`）进入 GH-172 normalized lock/installer/doctor；host 在 agent commands 前从 current-invocation registry 解析 client，stable-open 后验证 canonical path/mode/expected-size/digest/source-lock，并从同一 verified source bytes 加载 `bootstrap_current_invocation(authenticated_host_context)`，不得执行 consumer CWD 相对 checker；direct queue 绑定 loaded queue，implx outer 绑定 loaded implx + loader-resolved queue dependency/client，repo copy 无 installed copy 仍可启动，installed copy 精确绑定实际 loaded root；client 返回 opaque handle，`load_phase(handle, phase_id)` 从 startup-held root stable-open/read/verify 一次并将同一 immutable bytes buffer 交给 attested parser sink，closed receipt 绑定 invocation/phase/reference digests/parser/injection，caller 不得传 path/bytes/parser/reopen；installed branch 把 typed attested root 交给 internal doctor，receipt 回绑 canonical root/device/inode binding digest 与 source-lock；host/client/peer/handle/receipt unavailable、stale/replay/spoof、wrong-root、dependency/path/digest/root/manifest/parser/partial-injection drift、未知 skill ID、混链或歧义均 fail closed | Verify: `python3 -m pytest -q tests/test_phase_loader.py tests/test_skill_reference_graph.py tests/test_install_codex_skills.py tests/test_check_workflow.py -k "host_hook or runtime_client or consumer_checkout or repo_copy_without_install or loaded_entrypoint or delegated_entrypoint or canonical_skill_path or installed_root_binding or load_phase or same_buffer or parser_peer or partial_injection or replay or post_startup_drift"` | Covers: B-005 B-006 B-013 B-014 B-017 B-019 B-021 B-022 B-023 B-024 B-026 | host owner 管 pre-instruction hook/loader registry/client pre-exec verification/parser peer/trust；repo runtime-client owner 管 closed validation、origin/doctor dispatch、same-buffer phase handoff 与 tests，不复制 host 权威状态。
- [ ] `SP174-T4` Owner: entry-docs | Depends on: SP174-T2 SP174-T3 | Done when: `implx` 与 direct queue 都先验证 host-provided opaque bootstrap receipt，再在任何 fetch/list/map、诊断大输出、checkpoint 或 lane 前启用四重上限 main output firewall；两者不得运行相对 `checks/skill_reference_graph.py --bootstrap-loaded` 或使用 caller-selected source/origin/root/parser，之后只能调用 `load_phase(handle, phase_id)`；远端 merge 确认后无条件进入 `post_merge_closure` 并先通过 authenticated parser handoff 加载 closure-audit reference；AGENT_USAGE/CHANGELOG 说明 host v2 prerequisite、consumer/repo/installed 分支、attested-root doctor、same-buffer parser receipt、reference/output ceilings、closure phase与安装升级，最终 implx/queue/client hash 匹配 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py tests/test_phase_loader.py tests/test_skill_reference_graph.py -k "implx or direct_queue or host_hook or consumer_checkout or outer_preflight or canonical_skill_path or post_merge_closure or closure_audit or output_firewall or large_output"` | Covers: B-003 B-004 B-005 B-006 B-011 B-012 B-016 B-017 B-018 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 | 更新入口、文档、workflow wiring 与 lock 收口。

## 并行拆分

- 固定顺序 `SP174-T1 → SP174-T2 → SP174-T3 → SP174-T4`；queue、reference graph、
  lock 与 installer 都是共享接口，不并行写。
- 只读 inventory/reviewer 可并行，但不得修改 manifest 路径。
- GH-172 未合并前保持 blocked；若 GH-182 已合并，必须保留其 wait-contract marker。

## 验证

- [ ] `SP174-T5` Owner: verification-owner | Depends on: SP174-T1 SP174-T2 SP174-T3 SP174-T4 | Done when: exact-head focused/full/pack/depth/range-diff/size/hash/forward-use 全绿；fresh host hook/client binding 的 direct queue 与 implx→queue delegation、consumer repo-copy without install、installed 正例及 hook/client/resolver unavailable、stale/replay/spoof/path/bytes/root/source-lock/wrong-doctor-root/parser-peer/partial-injection 负例齐全；repo-copy fixture 分别校验 direct queue canonical path 和同 source/root/lock 下的 implx+delegated queue 双 canonical paths；startup 后漂移 fixture 在五个 phase 的首项动作前失败且无漂移只向 attested parser 注入同一 verified bytes；implx outer/direct queue 均在 remote read 前取得 host bootstrap handle；两份 main entrypoint 的 startup 大输出 fixture 对 150 lines/16384 total bytes/512 bytes per line/4096 tokens 逐项 exact/+1，证明 recovery reference 未加载时仍生效且 raw excess 仅进 artifact；每引用 `<500` lines/`≤16384` UTF-8 bytes 的 exact/+1/invalid-UTF-8 在 graph/lock/install/load 一致；五 phase exact isolation 保持 startup=planning、runtime_handoff=planning+evidence、review=review、post-merge closure=evidence、recovery=evidence，正常 merge success 不经 handoff/retry 仍加载 closure-audit reference；manifest 为 18 unique paths、B-001..B-026 全覆盖、无 GH-160 diff | Verify: `python3 -m pytest -q tests/test_phase_loader.py tests/test_skill_reference_graph.py tests/test_install_codex_skills.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH174 --gate && test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -le 500 && test "$(wc -c < skills/specrail-implement-queue/SKILL.md)" -le 28672 && sed -n '9p' specs/GH174/tech.md | jq -e '(.paths|length)==18 and (.paths|unique|length)==18' && git diff --check "$(git merge-base origin/main HEAD)"..HEAD` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 B-021 B-022 B-023 B-024 B-025 B-026 | 交付结构与行为证据。

## 合并后非阻断观测

- `SP174-T6` Owner: observation-owner | Non-blocking: true | Depends on: merged implementation, comparable implx run | Outcome: 独立报告 queue 主/引用读取次数、注入 bytes 与 phase 分布，不以未达固定降幅重开结构 PR | Verify: 人工复核汇总指标与 cohort 窗口 | Covers: B-016 | 此 follow-up 不属于本 issue Done-When、spec approval、merge、关闭或实现 task 完整性 gate；不读取/发布 session 正文。

## Handoff Notes

- 当前只允许 write_spec；spec 合并并转 `ready_to_implement` 前不得实现。
- 实现固定等待 GH-172；不得并行修改 queue、lock、installer 或 doctor。
- manifest 限定 tech spec 的 18 个 unique paths，不含 GH-160。
- host `specrail.runtime.skill-contract.v2` hook/parser sink 未部署时 implementation queue
  保持 blocked；不得用 caller metadata、consumer CWD checker 或 parser reopen 代替。
  repo-copy 的 implx/queue canonical paths 必须分别校验并同链，repo copy 不要求本机安装；
  installed doctor 精确检查 attested loaded root；phase 引用通过 opaque handle 在 load-time
  对 startup-pinned root/lock/digest 重校验并向认证 parser 消费同一 bytes。output firewall
  在 main startup 即以 line/total-byte/per-line/token 四重上限生效，每引用另有 UTF-8 byte
  ceiling；正常 merge 后由 `post_merge_closure` 加载 closure-audit reference。
- GH-182 若先实现，wait-contract-v1 必须在拆分后保持唯一、可校验。
