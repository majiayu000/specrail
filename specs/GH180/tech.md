# Tech Spec

## Linked Issue

GH-180

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":180,"complete":true,"paths":["AGENT_USAGE.md","checks/check_workflow.py","checks/github_issue_evidence.py","checks/route_gate.py","schemas/issue_evidence.schema.json","skills-lock.json","skills/specrail-implement-queue/SKILL.md","skills/specrail-plan-tasks/SKILL.md","skills/specrail-workflow/SKILL.md","tests/test_check_workflow.py","tests/test_check_workflow_paths.py","tests/test_evaluate.py","tests/test_issue_evidence_freshness.py","tests/test_route_gate.py"],"spec_refs":["specs/GH180/bootstrap-evidence.json","specs/GH180/product.md","specs/GH180/tech.md","specs/GH180/tasks.md"]}
-->

## Product Spec

见 `specs/GH180/product.md`。本设计把 packet 的 artifact shape 与 GitHub readiness
拆成两个正交维度：离线 validator 可接受 `staged`，但只有可信生命周期和 route evidence
才能进入 task planning；生产代码仍要求有效 `tasks.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| packet validator | `checks/check_workflow.py:260-342` | product/tech 必须存在；`tasks.md` 缺失被无条件加入 errors | 这是 product/tech-only spec PR 无法通过 CI 的直接根因 |
| CLI aggregation | `checks/check_workflow.py:463-515` | `--all-specs` 只汇总 errors，成功时不报告 packet shape | 需要稳定区分 `staged` / `complete`，且不能暗示 readiness |
| validator unit tests | `tests/test_evaluate.py:56-67`、`tests/test_check_workflow_paths.py:407-585` | 明确断言缺 `tasks.md` 必须失败，并覆盖 packet/file identity 与 task 内容失败 | 必须翻转缺文件正例，同时保留存在但无效 task 的全部 fail-closed 负例 |
| CLI integration tests | `tests/test_check_workflow.py:214-272` | 覆盖 configured root 与 `--all-specs`，尚无 staged/complete 输出断言 | 可证明全量发现、稳定排序与 additive shape audit |
| issue evidence | `checks/github_issue_evidence.py:174-233`、`schemas/issue_evidence.schema.json` | label 来源可标为 trusted，但 evidence 没有必填采集时间或稳定内容摘要 | 无法拒绝过期 evidence，也无法把 route 结果绑定到确切 issue snapshot |
| route gate | `checks/route_gate.py:240-405` | readiness route 可接受 CLI `--state`；artifact 只检查文件存在 | 自报状态可绕过可信 label，且旧 route success 可被错误复用于改变后的 packet |
| agent contract | `AGENT_USAGE.md:86-130` | Basic Flow 列出三种 artifact，却未说明 write_spec 与 implement 的分阶段所有权 | agent 容易把 validator 的完整性要求误读为提前生成 tasks |
| route router | `skills/specrail-workflow/SKILL.md:16-45` | 路由到 product、tech、tasks focused skill，但未明示 staged packet 的交接条件 | 需声明 product/tech 完成后等待真实 `ready_to_implement`，不能靠 shape 跳状态 |
| task planning | `skills/specrail-plan-tasks/SKILL.md:12-29` | 读取 product/tech，运行 implement gate，再创建 tasks | 已是无循环顺序；只需明确 staged validation 不等于可写 tasks |
| queue coverage | `skills/specrail-implement-queue/SKILL.md:48-70` | `needs_tasks` 与 `complete` 已分开，只有 complete 可进入生产实现候选 | 作为生产代码前的 deterministic enforcement，与新的结构 validator 对齐 |
| distributed skills | `skills-lock.json:21-73` | 三个将修改的 skill 都由内容 hash 锁定 | 文档变化后必须只更新对应 hash，保持分发完整性 |

## 设计方案

### 1. 纯 artifact shape 分类

在 `checks/check_workflow.py` 新增只读 helper：

```text
spec_packet_shape(spec_dir) -> invalid | staged | complete
```

- product 或 tech 文件任一缺失时返回 `invalid`；后续 validator 继续报告具体缺失项。
- product 与 tech 均存在、tasks 不存在时返回 `staged`。
- 三文件均存在时返回 `complete`；即使 tasks 内容无效，shape 仍是 `complete`，同时
  validation 失败，禁止把坏 task 静默降级成 staged。

shape 只描述当前 artifact presence，不读取 label、不接触 GitHub、不产生 readiness 或授权。
相同文件 snapshot 的分类稳定且幂等。

### 2. staged-aware 内容校验

保留 `validate_spec_packet(spec_dir) -> list[str]` 公共签名，避免改变所有调用方：

- product/tech 的 identity、linked issue、非空与 planned-changes manifest 规则逐字保留；
- tasks 不存在时不再产生 `missing tasks.md` error；
- tasks 存在时仍执行 identity/symlink/非空、稳定 task ID、Owner/Done when/Verify 和重复 ID
  全部现有校验；任何错误都使整体命令非零；
- product/tech 任一缺失或无效时仍失败，不因 tasks 是否存在而降级。

`main()` 对显式或 `--all-specs` 选择出的 packet 按现有稳定路径顺序记录 shape，并在结果中
输出 `Spec packet <path>: shape=<staged|complete|invalid>; readiness=unproven`。该行在成功和失败
路径都输出；最终 `SpecRail check passed/failed` 与 exit code 保持兼容。离线命令没有 GitHub
evidence，因此 readiness 固定为 `unproven`，不会把三文件齐全冒充 implementation-ready。

### 3. 可信 readiness 与 snapshot-bound route gate

保持 `workflow.yaml` 的 action policy 不变，并收紧 `github_issue_evidence` 与 `route_gate`：

- issue evidence schema 新增必填 UTC `collected_at`；collector 在完成同一次 issue query 后写入，
  route gate 对 readiness-sensitive route 使用显式、可配置且有安全默认值的最大年龄，拒绝缺失、
  无效、未来或超窗时间；
- 当 route 含 `readiness_label` human gate 时，只接受 `--evidence` 中
  `state_source=label`、`state_trusted=true` 且 issue 一致的状态；`--state` 只可用于不依赖
  readiness label 的 route/诊断，不能自报 `ready_to_spec` 或 `ready_to_implement` 获准；
- 对 route 实际发现的 product/tech/tasks 逐一计算 sha256，以稳定路径排序后生成
  `packet_snapshot_sha256`；同时对规范化 issue evidence 生成 `issue_evidence_sha256`，并在 JSON
  结果中返回 hashes、采集时间与 freshness 判定；
- route 在计算 snapshot 前调用 staged-aware packet validator，确保 product/tech 内容有效，
  已存在的 tasks 也有效；implement 入场允许 tasks 缺失，但 tasks 创建后必须重跑 route；
- `route_gate --verify-result <saved-route.json>` 作为确定性 consumer gate，重算当前 packet
  摘要并校验 saved result 的 issue、route、evidence 摘要、采集时间与 decision；queue 在生产
  代码 lane 前必须调用该模式。任何文件、evidence 或 freshness 状态改变都使旧结果失效，
  不允许把单独 validator success 与另一 snapshot 的 route success 拼接成授权。

对应交接顺序为：

1. `ready_to_spec` + allowed write_spec → 写 product/tech → staged validator pass；
2. 经过配置的 spec review/approval，取得可信 `ready_to_implement`；
3. fresh issue + duplicate evidence 令 implement route 对 staged snapshot allowed；
4. `specrail-plan-tasks` 创建并验证 tasks，packet 变为 complete；
5. 对 complete snapshot 重跑 implement route，并立即用 `--verify-result` 对当前文件验证结果；
6. `specrail-implement-queue` 只有在 `spec_status=complete` 且 consumer gate 通过时才允许生产代码 lane。

因此 implement route 入场不循环要求它将创建的 tasks，但生产代码也不能从 staged packet
开始。ready_to_implement 后 tasks 被删除或损坏时，queue coverage 重新分类为 `needs_tasks`，
旧 readiness/验证不可继续授权代码。

### 4. GH-180 bootstrap 与在途纠偏

GH-180 修复前的 validator 仍要求三文件，因此本 issue 使用一次性、真实状态的两阶段
bootstrap：

- 以已落盘的 live `ready_to_spec` / trusted label / `write_spec: allowed` evidence 写 product/tech；
- 主 agent 记录本次 `auth_mode: auto` 对 spec approval 的 waiver，并将 live issue 从
  `ready_to_spec` 真正迁移为 `ready_to_implement`；
- 重新采集 current issue/duplicate evidence并运行 implement gate；只有 `allowed` 后才写
  GH-180 tasks，使旧 CI 可验证完整 packet；把两阶段状态、route decision、duplicate 摘要、
  auto waiver 和 product/tech 哈希持久化为 tracked `specs/GH180/bootstrap-evidence.json`，
  这一 spec PR 不包含生产实现。该历史证据只审计 bootstrap，不充当未来 route 授权。

实现 PR 合并后，PR #179 仍在原分支删除提前生成的 `specs/GH165/tasks.md`，其 product/tech
以 staged 形态通过新 validator。GH-180 bootstrap evidence 不可复制到其它 issue；后续
ready_to_spec packet 一律走 staged 路径。

### 5. 文档、分发与审计一致性

`AGENT_USAGE.md`、router、task-planning skill 与 queue skill 使用相同术语：shape 是
`staged|complete|invalid`，queue spec status 是 `needs_tasks|complete|needs_spec`，readiness
来自可信 GitHub evidence。三个 skill 修改后只更新其 `skills-lock.json` hash；不修改集合、
顺序、路径或其它 skill hash。

审计由同一当前 packet 上的两份互补证据组成：`check_workflow` 输出 artifact
shape/validation/snapshot，`route_gate` 输出 linked issue、trusted state source、采集时间、
evidence 与 packet 摘要、decision、missing/reasons。消费者必须用 `--verify-result` 重算匹配，
不得拼接不同 snapshot 的成功结果声称 implementation-ready。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-010 | shape helper、staged-aware validator、CLI audit | staged/complete fixtures 分别 exit 0，输出对应 shape 与 `readiness=unproven` |
| B-003 | CLI wording、AGENT_USAGE、三个 skill | 文档一致性断言禁止 shape 被表述为 readiness/approval |
| B-004 | product/tech 现有校验 | 缺失、空、bad issue token、bad manifest fixtures 继续非零 |
| B-005 | present-task validation | 无效 task fixture 输出 `shape=complete` 且非零，绝不输出 staged success |
| B-006 | workflow/router docs + write_spec regression | 现有 write_spec route tests 保持 required artifacts 仅 product/tech |
| B-007 B-013 | route gate、plan-tasks 与 queue coverage | staged=`needs_tasks`，可信 implement gate 可用于规划；tasks 后重跑并匹配 snapshot 才能进入生产实现 |
| B-008 B-009 | issue evidence schema/collector、route gate | CLI state、body hint、过期/未来 evidence、错误 issue/冲突 label 全部 fail closed；fresh trusted label 才通过 |
| B-011 | all existing packets + full suite | `--all-specs` 中既有三文件 packet 全部 `complete`，无需迁移 |
| B-012 | PR #179 follow-up fixture/verification | 删除 GH165 tasks 后新 validator 报 staged 且 CI 绿，issue 仍非 implementation-ready |
| B-014 B-015 | validator/route snapshot hashes + `--verify-result` | 相同输入摘要一致；artifact 或 issue evidence 改变后旧 route 结果被确定性拒绝 |
| B-016 B-017 | tracked bootstrap evidence | 两阶段 route evidence 均绑定 issue #180 与 product/tech hash；缺任一步时不创建 tasks |
| B-018 | CLI + route evidence pair | shape 行含 path/shape/readiness/snapshot，route JSON 含 issue/state/source/time/hashes/decision/reasons |
| B-019 | partial-file fixtures | 半写/空 product 或 tech 失败；中断后只按当前文件重新分类 |

## 数据流

Git tree 中的 packet paths → `spec_packet_shape` → `validate_spec_packet` 内容错误集合 →
`check_workflow` 稳定 shape/validation/snapshot 输出。live GitHub issue evidence（含采集时间）→
route gate 校验 freshness、可信 label 和 packet 内容 → 带 evidence/packet 摘要的 decision JSON。
queue 在 task planning 前校验 staged snapshot，tasks 写入后再用 validator、route gate 和 spec
coverage 重跑，再用 `--verify-result` 匹配 complete snapshot；生产实现只消费 fresh 且摘要匹配的结果。

## 备选方案

- 继续要求所有 spec PR 提前写 tasks：拒绝；它越过 workflow 的 route/readiness 所有权。
- 让 implement route 入场前要求 tasks：拒绝；会形成“进入 route 前先有该 route 产物”的循环。
- 从 workflow 把 task_plan 移到 write_spec：拒绝；会把任务规划提前到未批准设计，扩大 issue 范围。
- 用 issue label 传给 `check_workflow --all-specs`：拒绝；CI 的离线结构校验不应依赖网络或可变状态。
- 删除 task 内容校验：拒绝；只允许文件缺失代表 staged，存在但无效必须 fail closed。

## 风险

- Security: shape 输出不得被当作权限；readiness 始终由可信 label/route evidence控制。
- Compatibility: CLI 新增确定性 shape 行但保留既有最终消息与 exit code；旧完整 packet 无需改写。
- Race: route JSON 显式绑定 issue evidence 与 packet 内容摘要；生产操作前必须重算匹配，
  不得复用旧 shape/readiness 组合。freshness 是 bounded staleness，不宣称消除 GitHub 查询后的瞬时竞态。
- Maintenance: `validate_spec_packet` 保持 list 返回值，新增 helper 避免大规模 API 迁移；修改后
  `checks/check_workflow.py` 与所有 touched files 仍须 `<800` 行。

## 测试计划

- [ ] Unit: `/usr/bin/python3 -m pytest -q tests/test_evaluate.py tests/test_check_workflow_paths.py`，
  覆盖 staged/complete/invalid shape、present-invalid tasks、symlink/identity 与 partial files。
- [ ] CLI: `/usr/bin/python3 -m pytest -q tests/test_check_workflow.py`，覆盖显式与 all-specs 的
  稳定 shape 行、配置 root、成功/失败 exit code和 readiness=unproven。
- [ ] Workflow/skill regression: 现有 route gate 与 queue coverage tests 全绿，skill lock 只更新
  三个目标 hash。
- [ ] Evidence/route: `/usr/bin/python3 -m pytest -q tests/test_issue_evidence_freshness.py tests/test_route_gate.py`，
  覆盖 collector 时间戳、CLI self-report、缺失/未来/超窗 evidence、错误 issue、内容摘要与 artifact 漂移。
- [ ] Submission: `/usr/bin/python3 -m pytest -q`、
  `/usr/bin/python3 checks/check_workflow.py --repo . --all-specs`、
  `/usr/bin/python3 tools/spec_depth_audit.py --spec-dir specs/GH180 --gate`、`git diff --check`、
  touched-file `<800`；修改前已为 799 行的 queue skill 必须通过删减重复文字保持在上限内。

## 回滚方案

回滚 `spec_packet_shape`、optional-tasks validator 分支、CLI shape 行、对应测试/文档/skill hash，
即可恢复旧的三文件强制合同；无数据迁移。回滚后 product/tech-only spec PR 会重新 CI 失败，
必须同时重新开放 GH-180，而不能以提前写 tasks 或跳过 CI 作为替代。
