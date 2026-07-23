# Tech Spec

## Linked Issue

GH-180

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":180,"complete":true,"paths":["AGENT_USAGE.md","README.md","checks/check_workflow.py","checks/duplicate_work_gate.py","checks/github_approved_spec_evidence.py","checks/github_duplicate_evidence.py","checks/github_issue_evidence.py","checks/route_gate.py","evaluate.py","examples/fixtures/issue-body-hint-ready-to-implement.json","examples/fixtures/issue-ready-to-implement.json","examples/fixtures/issue-ready-to-spec.json","examples/fixtures/issue-reserved-internal.json","labels.yaml","schemas/duplicate_work_evidence.schema.json","schemas/issue_evidence.schema.json","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-implement/SKILL.md","skills/specrail-plan-tasks/SKILL.md","skills/specrail-workflow/SKILL.md","skills/specrail-write-product-spec/SKILL.md","skills/specrail-write-tech-spec/SKILL.md","templates/pull_request.md","templates/zh-CN/pull_request.md","tests/route_gate_test_support.py","tests/test_check_workflow.py","tests/test_check_workflow_paths.py","tests/test_configured_spec_path_review_regressions.py","tests/test_duplicate_work_gate.py","tests/test_evaluate.py","tests/test_github_duplicate_evidence.py","tests/test_github_issue_evidence.py","tests/test_github_issue_route_evidence.py","tests/test_issue_evidence_freshness.py","tests/test_route_gate.py"],"spec_refs":["specs/GH180/bootstrap-evidence.json","specs/GH180/product.md","specs/GH180/tech.md","specs/GH180/tasks.md"]}
-->

## Product Spec

见 `specs/GH180/product.md`。本设计把 packet 的 artifact shape 与 GitHub readiness
拆成两个正交维度：离线 validator 可接受 `staged`，但只有可信生命周期和 route evidence
才能进入 task planning；生产代码仍要求有效 `tasks.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| packet validator | `checks/check_workflow.py:260-342` | product/tech 必须存在；`tasks.md` 缺失被无条件加入 errors | 这是 product/tech-only spec PR 无法通过 CI 的直接根因 |
| standalone evaluator | `evaluate.py:84-126`、`tests/test_evaluate.py:56-67` | `evaluate_spec()` 独立把缺 `tasks.md` 记为 `spec.tasks_present` failure | 只修 workflow checker 会让公开 evaluator 与 staged 合同继续冲突 |
| CLI aggregation | `checks/check_workflow.py:463-515` | `--all-specs` 只汇总 errors，成功时不报告 packet shape | 需要稳定区分 `staged` / `complete`，且不能暗示 readiness |
| validator unit tests | `tests/test_check_workflow_paths.py:407-585` | 明确断言缺 `tasks.md` 必须失败，并覆盖 packet/file identity 与 task 内容失败 | 必须翻转缺文件正例，同时保留存在但无效 task 的全部 fail-closed 负例 |
| CLI integration tests | `tests/test_check_workflow.py:214-272` | 覆盖 configured root 与 `--all-specs`，尚无 staged/complete 输出断言 | 可证明全量发现、稳定排序与 additive shape audit |
| issue evidence | `checks/github_issue_evidence.py:174-233`、`schemas/issue_evidence.schema.json` | label 来源可标为 trusted，但 evidence 没有必填采集时间或稳定内容摘要；非 sensitive implement 不采 spec approval | 无法拒绝过期 evidence，也会让仅有 readiness label 的普通 issue 绕过 workflow `spec_approval` human gate |
| lifecycle approval | `checks/github_approved_spec_evidence.py:151-315`、`labels.yaml`、`workflow.yaml:87-96` | 已有 helper 能查权限/label event，exact-head sensitive 流程也认识 spec lifecycle label，但普通 implement 没有通用的有序 lifecycle evidence；默认 label catalog 未声明三种 lifecycle label | 应复用既有 GitHub 查询与权限判定，为所有 implement route 验证 `spec_pr_open → spec_review → spec_approved`，而非只保护 sensitive route |
| duplicate-work evidence | `checks/github_duplicate_evidence.py`、`checks/duplicate_work_gate.py`、`schemas/duplicate_work_evidence.schema.json` | collector/gate 能验证 open PR/remote branch 完整性，但 saved route consumer 不要求 fresh duplicate evidence，gate 也不限制 evidence 年龄 | saved result 后出现新 PR/branch 时，旧 duplicate success 仍可能被消费 |
| route gate | `checks/route_gate.py:240-405` | readiness route 可接受 CLI `--state`，CLI `--label` 又在推断前并入 labels；artifact 只检查文件存在 | 两种自报入口都可绕过可信 label，且旧 route success 可被错误复用于改变后的 packet 或 duplicate snapshot |
| evidence regressions | `tests/test_github_issue_evidence.py:245-760`、`tests/route_gate_test_support.py:142-181`、`tests/test_configured_spec_path_review_regressions.py:155-345`、`examples/fixtures/issue-*.json` | 既有断言允许 readiness CLI state，trusted helper/fixtures 没有采集时间；主测试文件 851 行 | freshness 收紧会影响现有全量回归，必须纳入 manifest，并把超限文件按现有 route-evidence 模块拆分 |
| agent contract | `AGENT_USAGE.md:86-130` | Basic Flow 列出三种 artifact，却未说明 write_spec 与 implement 的分阶段所有权 | agent 容易把 validator 的完整性要求误读为提前生成 tasks |
| route router | `skills/specrail-workflow/SKILL.md:16-45` | 路由到 product、tech、tasks focused skill，但未明示 staged packet 的交接条件 | 需声明 product/tech 完成后等待真实 `ready_to_implement`，不能靠 shape 跳状态 |
| focused write/implement | `skills/specrail-write-product-spec/SKILL.md:12-23`、`skills/specrail-write-tech-spec/SKILL.md:12-21`、`skills/specrail-implement/SKILL.md:12-21` | focused skills 仍以 CLI `--state` 自报；direct implement 预读 tasks 且未定义缺 tasks 的交还顺序 | 新 route policy 会让真实入口自阻塞或绕过 staged handoff |
| task planning | `skills/specrail-plan-tasks/SKILL.md:12-29` | 读取 product/tech，运行 implement gate，再创建 tasks | 需改为 fresh issue evidence 入场，并明确 tasks 后重跑 complete snapshot |
| queue coverage | `skills/specrail-implement-queue/SKILL.md:48-70` | `needs_tasks` 与 `complete` 已分开，只有 complete 可进入生产实现候选 | 作为生产代码前的 deterministic enforcement，与新的结构 validator 对齐 |
| implx auto entrypoint | `skills/implx/SKILL.md:83-109`、`skills/specrail-implement-queue/SKILL.md:101-123` | shorthand 允许同轮 draft/implement，但没有完整写出 staged 后重采 evidence、tasks 后重验的顺序 | 顶层入口不能让 auto waiver 被误读为 freshness 或 snapshot waiver |
| public docs/templates | `README.md:89-101`、`templates/pull_request.md:10-14`、`templates/zh-CN/pull_request.md:10-14` | README 示例仍使用 CLI `--state`；PR 模板对 staged spec PR 也要求 `ready_to_implement` | 公开入口必须区分 spec PR 与 implementation PR readiness |
| distributed skills | `skills-lock.json:5-73` | 七个将修改的 skill 都由内容 hash 锁定 | 文档变化后必须只更新对应 hash，保持分发完整性 |

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

保留 `validate_spec_packet(spec_dir) -> list[str]` 公共签名，避免改变所有调用方，并让
standalone `evaluate.py` 使用同一 staged/complete 语义：

- product/tech 的 identity、linked issue、非空与 planned-changes manifest 规则逐字保留；
- tasks 不存在时不再产生 `missing tasks.md` error；
- tasks 存在时仍执行 identity/symlink/非空、稳定 task ID、Owner/Done when/Verify 和重复 ID
  全部现有校验；任何错误都使整体命令非零；
- product/tech 任一缺失或无效时仍失败，不因 tasks 是否存在而降级。
- `evaluate_spec()` 对缺 tasks 输出可审计的 staged/optional 结果而非
  `spec.tasks_present` failure；tasks 存在时继续执行全部 task format checks。

`main()` 对显式或 `--all-specs` 选择出的 packet 按现有稳定路径顺序记录 shape，并在结果中
输出 `Spec packet <path>: shape=<staged|complete|invalid>; readiness=unproven`。该行在成功和失败
路径都输出；最终 `SpecRail check passed/failed` 与 exit code 保持兼容。离线命令没有 GitHub
evidence，因此 readiness 固定为 `unproven`，不会把三文件齐全冒充 implementation-ready。

### 3. 可信 lifecycle/readiness 与 snapshot-bound route gate

保持 `workflow.yaml` 的 action policy 不变，并收紧 issue/lifecycle/duplicate collectors 与
`route_gate`：

- issue evidence schema 新增必填 UTC `collected_at`；collector 在完成同一次 issue query 后写入，
  route gate 对 readiness-sensitive route 使用显式、可配置且有安全默认值的最大年龄，拒绝缺失、
  无效、未来或超窗时间；
- 当 route 含 `readiness_label` human gate 时，只接受 `--evidence` 中
  `state_source=label`、`state_trusted=true` 且 issue 一致的状态；`--state` 只可用于不依赖
  readiness label 的 route/诊断，`--state ready_to_*` 与
  `--label ready_to_spec|ready_to_implement` 都必须明确拒绝，不能在 state inference 前注入可信状态；
- 在 `labels.yaml` 声明 `spec_pr_open`、`spec_review`、`spec_approved` lifecycle labels。
  `github_approved_spec_evidence.py` 复用现有 label timeline、default-base 与 permission 查询，
  为所有 trusted `ready_to_implement` issue 收集闭合的 `spec_lifecycle_approval`：
  三个 transition 必须属于同一 issue、按时间有序、终态为当前/latest `spec_approved`，approval
  actor 的 repository permission 必须满足现有 maintainer policy，且 snapshot 前后 issue
  identity/labels 不得漂移。`github_issue_evidence.py` 无论 sensitive registry 是否启用都必须
  嵌入该对象；schema 禁止开放字段；
- 当 route 的 human gates 含 `spec_approval` 时，`route_gate` 必须离线重验上述完整对象与
  evidence digest，再接受随后的 fresh trusted `ready_to_implement`；当前 readiness label
  不能代替 lifecycle approval。sensitive route 原有 exact-head `approved_spec` 仍是额外约束，
  不替代也不放宽这个普通 human gate；
- 对 route 实际发现的 product/tech/tasks 逐一计算 sha256，以稳定路径排序后生成
  `packet_snapshot_sha256`；同时对规范化 issue evidence 生成 `issue_evidence_sha256`，并在 JSON
  结果中返回 hashes、采集时间与 freshness 判定；
- route 在计算 snapshot 前调用 staged-aware packet validator，确保 product/tech 内容有效，
  已存在的 tasks 也有效；implement 入场允许 tasks 缺失，但 tasks 创建后必须重跑 route；
- duplicate evidence schema 将 `collected_at` 收紧为可解析 UTC 时间；`duplicate_work_gate`
  使用与 issue evidence 同样显式、可配置且有安全默认值的最大年龄，重新验证 issue/repository、
  complete open-PR query、open PR refs 与 matching remote branches。collector 测试固定顺序和
  canonical JSON，route result 记录 `duplicate_work_evidence_sha256`、采集时间和 decision；
- `route_gate --verify-result <saved-route.json> --evidence <fresh-issue-evidence.json>
  --duplicate-evidence <fresh-duplicate-evidence.json>` 作为确定性 consumer gate：先对 fresh
  issue/lifecycle evidence 重做 identity/source/trust/freshness/permission 校验，再把 fresh
  duplicate evidence 交给 duplicate gate 重做 freshness、open PR 与 branch 检查，然后重算
  当前 packet 摘要，最后同时匹配 saved result 的 issue、route、三类 evidence/packet 摘要与
  allowed decision。不得把 saved hash 与 saved result 自身比较。queue 在生产代码 lane 前必须
  调用该模式；新 PR/branch、文件、label/lifecycle 或 freshness 状态变化都使旧结果失效。
- 更新四个 shipped issue fixtures，使其结构包含 `repository` 与 `collected_at`；固定时间 fixture
  只作为 schema/陈旧证据样本。需要 allowed 结果的测试必须复制 fixture 后注入测试时钟对应的
  current timestamp，不能扩大 production freshness 窗口掩盖陈旧输入。
- 将 `tests/test_github_issue_evidence.py` 中 route/fixture 集成回归迁移到已有的
  `tests/test_github_issue_route_evidence.py`，并同步 `route_gate_test_support.py` 与 configured-path
  回归；两个修改后的测试文件都必须 `<800`，不得删除覆盖或弱化断言。

对应交接顺序为：

1. `ready_to_spec` + allowed write_spec → 写 product/tech → staged validator pass；
2. 经过配置的 spec review/approval，采集有权限 actor 的有序
   `spec_pr_open → spec_review → spec_approved` lifecycle evidence，再取得可信
   `ready_to_implement`；
3. fresh issue/lifecycle + fresh duplicate evidence 令 implement route 对 staged snapshot allowed；
4. `specrail-plan-tasks` 创建并验证 tasks，packet 变为 complete；
5. 对 complete snapshot 重跑 implement route，并立即用
   `--verify-result <result> --evidence <fresh-evidence>
   --duplicate-evidence <fresh-duplicate-evidence>` 对当前文件、fresh issue/lifecycle 与
   fresh duplicate snapshot 验证结果；
6. `specrail-implement-queue` 只有在 `spec_status=complete` 且 consumer gate 通过时才允许生产代码 lane。

因此 implement route 入场不循环要求它将创建的 tasks，但生产代码也不能从 staged packet
开始。ready_to_implement 后 tasks 被删除或损坏时，queue coverage 重新分类为 `needs_tasks`，
旧 readiness/验证不可继续授权代码。

### 4. GH-180 bootstrap 与在途纠偏

GH-180 修复前的 validator 仍要求三文件，因此本 issue 历史上使用一次性
`auth_mode: auto` old-validator bootstrap exception：

- live `ready_to_spec` label 可观察；coordinator 报告 `write_spec: allowed` 后写
  product/tech，但原 issue-evidence runtime 文件未 tracked，不能称为可独立恢复的证据；
- 主 agent 记录本次 `auth_mode: auto` waiver，maintainer 把 live label 直接从
  `ready_to_spec` 切到 `ready_to_implement`；该 transition 没有经过正常的
  `spec_pr_open → spec_review → spec_approved`，不得描述为 B-008 正常链；
- coordinator 报告重新采集 issue/duplicate evidence 且 implement gate 为 `allowed` 后写
  GH-180 tasks，使旧 CI 可验证完整 packet；但原 issue-evidence runtime 文件不在 tracked
  checkout，`collected_at`/hash 无法恢复，因此 tracked JSON 将这部分和 normal lifecycle
  明确标成 `unproven`，不得从 duplicate timestamp、label timeline 或文件名推断。

tracked `specs/GH180/bootstrap-evidence.json` 只审计 observed direct transition、reported
decisions 与证据缺口；它的 `authorization_effect` 为 `none`，不充当未来 route 授权。这一
spec PR 不包含生产实现。

实现 PR 合并后，PR #179 仍在原分支删除提前生成的 `specs/GH165/tasks.md`，其 product/tech
以 staged 形态通过新 validator。GH-180 bootstrap evidence 不可复制到其它 issue；后续
ready_to_spec packet 一律走 staged 路径。

### 5. 文档、分发与审计一致性

`AGENT_USAGE.md`、`README.md`、两份 PR template、implx、router、两个 focused write skill、
task-planning、direct implement 与 queue skill 使用相同术语：shape 是
`staged|complete|invalid`，queue spec status 是 `needs_tasks|complete|needs_spec`，readiness
来自 fresh trusted GitHub evidence，spec approval 来自有序且有权限 actor 的 lifecycle
evidence。staged 写作完成后必须等待或在 auto 合同下真实完成 lifecycle/readiness 并重新采集；
tasks 完成后必须重跑 route 与 consumer gate。七个 skill 修改后只更新其
`skills-lock.json` hash；不修改 skill 集合、顺序、路径或其它 hash。

审计由同一当前 packet 上的两份互补证据组成：`check_workflow` 输出 artifact
shape/validation/snapshot，`route_gate` 输出 linked issue、trusted state source、采集时间、
issue/lifecycle/duplicate evidence 与 packet 摘要、decision、missing/reasons。消费者必须用
`--verify-result <result> --evidence <fresh-evidence>
--duplicate-evidence <fresh-duplicate-evidence>` 重算所有摘要并重跑 duplicate gate，不得拼接
不同 snapshot 的成功结果或把 saved hash 自比较后声称 implementation-ready。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-010 | shape helper、staged-aware validator、standalone evaluator、CLI audit | 两个 CLI 对 staged/complete fixtures 分别成功，check_workflow 输出对应 shape 与 `readiness=unproven` |
| B-003 | CLI wording、public docs/templates、七个 skill | 文档一致性断言禁止 shape 被表述为 readiness/approval |
| B-004 | product/tech 现有校验 | 缺失、空、bad issue token、bad manifest fixtures 继续非零 |
| B-005 | present-task validation | 无效 task fixture 输出 `shape=complete` 且非零，绝不输出 staged success |
| B-006 | workflow/router/focused write docs + write_spec regression | write_spec route 只要求 product/tech，focused skills 使用 fresh label evidence |
| B-007 B-013 | route gate、plan-tasks、direct implement、implx 与 queue coverage | staged=`needs_tasks`；tasks 后以 fresh issue/lifecycle/duplicate evidence 重跑并匹配 complete snapshot 才能进入生产实现 |
| B-008 B-009 | issue/lifecycle evidence schema/collector、label catalog、route gate、既有 fixtures/tests | 普通 implement 必须同时满足 ordered human lifecycle approval 与 fresh trusted readiness；CLI state/readiness label、body hint、过期/未来 evidence、错误 issue/冲突 label 全部 fail closed |
| B-011 | all existing packets + full suite | `--all-specs` 中既有三文件 packet 全部 `complete`，无需迁移 |
| B-012 | PR #179 follow-up fixture/verification | 删除 GH165 tasks 后新 validator 报 staged 且 CI 绿，issue 仍非 implementation-ready |
| B-014 B-015 | validator/route snapshot hashes + `--verify-result` + fresh issue/duplicate evidence | 相同输入摘要一致；label/lifecycle/duplicate/artifact 任一漂移或新 PR/branch 出现后旧 result 被确定性拒绝 |
| B-016 B-017 | tracked bootstrap evidence | direct transition、reported decisions 与 unproven collected_at/hash 分栏；authorization_effect=none |
| B-018 | CLI + route evidence pair | shape 行含 path/shape/readiness/snapshot，route JSON 含 issue/state/source/time/hashes/decision/reasons |
| B-019 | partial-file fixtures | 半写/空 product 或 tech 失败；中断后只按当前文件重新分类 |

## 数据流

Git tree 中的 packet paths → `spec_packet_shape` → `validate_spec_packet` 内容错误集合 →
`check_workflow` 稳定 shape/validation/snapshot 输出。live GitHub issue/lifecycle evidence
与 duplicate-work evidence（均含采集时间）→ route gate 校验 freshness、可信 label、有序人类
approval、open PR/branch snapshot 和 packet 内容 → 带三类 evidence/packet 摘要的 decision JSON。
queue 在 task planning 前校验 staged snapshot，tasks 写入后再用 validator、route gate 和 spec
coverage 重跑，再用 `--verify-result` 与 fresh issue/duplicate evidence 同时匹配 complete
snapshot；生产实现只消费 fresh 且全部摘要、human gates 和 duplicate gate 均匹配的结果。

## 备选方案

- 继续要求所有 spec PR 提前写 tasks：拒绝；它越过 workflow 的 route/readiness 所有权。
- 让 implement route 入场前要求 tasks：拒绝；会形成“进入 route 前先有该 route 产物”的循环。
- 从 workflow 把 task_plan 移到 write_spec：拒绝；会把任务规划提前到未批准设计，扩大 issue 范围。
- 用 issue label 传给 `check_workflow --all-specs`：拒绝；CI 的离线结构校验不应依赖网络或可变状态。
- 删除 task 内容校验：拒绝；只允许文件缺失代表 staged，存在但无效必须 fail closed。

## 风险

- Security: shape 与 readiness label 都不得被当作 spec approval；implement 同时验证有权限人类
  lifecycle approval、可信 readiness 与 route evidence。
- Compatibility: CLI 新增确定性 shape 行但保留既有最终消息与 exit code；旧完整 packet 无需改写。
- Race: route JSON 显式绑定 issue/lifecycle/duplicate evidence 与 packet 内容摘要；生产操作前
  必须重采并重算匹配，不得复用旧 shape/readiness 或旧“无重复工作”结论。freshness 是 bounded
  staleness，不宣称消除 GitHub 查询后的瞬时竞态。
- Maintenance: `validate_spec_packet` 保持 list 返回值，新增 helper 避免大规模 API 迁移；修改后
  `checks/check_workflow.py` 与所有 touched files 仍须 `<800` 行。

## 测试计划

- [ ] Unit: `/usr/bin/python3 -m pytest -q tests/test_evaluate.py tests/test_check_workflow_paths.py`，
  覆盖 standalone evaluator 与 workflow validator 的 staged/complete/invalid、present-invalid
  tasks、symlink/identity 与 partial files。
- [ ] CLI: `/usr/bin/python3 -m pytest -q tests/test_check_workflow.py`，覆盖显式与 all-specs 的
  稳定 shape 行、配置 root、成功/失败 exit code和 readiness=unproven。
- [ ] Workflow/skill regression: README、双语 PR template、implx、focused write/plan/direct
  implement/queue 入口均不再自报 readiness，skill lock 只更新七个目标 hash。
- [ ] Evidence/route: `/usr/bin/python3 -m pytest -q tests/test_issue_evidence_freshness.py
  tests/test_route_gate.py tests/test_duplicate_work_gate.py tests/test_github_duplicate_evidence.py`，
  覆盖 collector 时间戳、ordered lifecycle/human permission、CLI state/readiness label self-report、
  缺失/未来/超窗 issue/duplicate evidence、错误 issue、新 PR/branch、内容摘要与 artifact 漂移。
- [ ] Regression migration: `/usr/bin/python3 -m pytest -q tests/test_github_issue_evidence.py tests/test_github_issue_route_evidence.py tests/test_configured_spec_path_review_regressions.py tests/test_route_gate_sensitive.py`，覆盖拆分后的原有断言、shipped fixtures、configured paths 与 sensitive route helper；所有修改文件 `<800`。
- [ ] Submission: `/usr/bin/python3 -m pytest -q`、
  `/usr/bin/python3 checks/check_workflow.py --repo . --all-specs`、
  `/usr/bin/python3 tools/spec_depth_audit.py --spec-dir specs/GH180 --gate`、`git diff --check`、
  touched-file `<800`；修改前已为 799 行的 queue skill 必须通过删减重复文字保持在上限内。

## 回滚方案

回滚 `spec_packet_shape`、optional-tasks validator 分支、CLI shape 行、对应测试/文档/skill hash，
即可恢复旧的三文件强制合同；无数据迁移。回滚后 product/tech-only spec PR 会重新 CI 失败，
必须同时重新开放 GH-180，而不能以提前写 tasks 或跳过 CI 作为替代。
