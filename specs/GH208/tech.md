# Tech Spec

## Linked Issue

GH-208

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":208,"complete":true,"paths":["AGENTS.md","AGENT_USAGE.md","checks/skill_size_gate.py","docs/GATE_AUDIT_2026-07-27.evidence.json","docs/GATE_AUDIT_2026-07-27.md","integrations/fastlane_observation_provider.md","schemas/gate_audit_evidence.schema.json","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement/SKILL.md","skills/specrail-pr-gate/SKILL.md","specs/GH208/product.md","specs/GH208/tech.md","tests/test_fastlane_startup_measurement.py","tests/test_gate_audit_inventory.py","tests/test_github_gate_audit_evidence.py","tests/test_skill_size_gate.py","tools/fastlane_startup_measurement.py","tools/gate_audit_inventory.py","tools/github_gate_audit_evidence.py"],"spec_refs":["specs/GH208/product.md","specs/GH208/tech.md"]}
-->

## Product Spec

见 `specs/GH208/product.md`。本设计仅覆盖 GH-208 剩余的 A/C/D，即
B-001..B-018；PR #210 已完成的 B/E 不进入本 planned-changes manifest。

## Codebase Context

以下锚点均在写作基线
`6b6e1f702a2098325ba34dd81f5f0c565f3c0134` 上核实。

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| stale audit totals | `docs/GATE_AUDIT_2026-07-27.md:3`、`docs/GATE_AUDIT_2026-07-27.md:25`、`docs/GATE_AUDIT_2026-07-27.md:66` | 报告声明 36/36、14,779 行，并以自由文本事故/安全依据支持处置。 | PR #210 unresolved thread 已证明 inventory 漏项；PR #215 round-1 又证明非空 prose 不能建立 B-011 的 evidence truth。 |
| omitted tier module | `checks/github_tier_evidence.py:1`、`checks/github_tier_evidence.py:219` | 当前模块共 219 行，承载 trusted current-head tier evidence；未进入审计表。 | 它是必须补入 C 组的第 37 个模块。 |
| fastlane read-set gate | `checks/skill_size_gate.py:22`、`checks/skill_size_gate.py:24`、`checks/skill_size_gate.py:32` | `FASTLANE_READ_SET` 固定为 `AGENTS.md`、`AGENT_USAGE.md`、三份 YAML 与 `implx`，共六文件，只检查 30 KiB。 | B-014/B-015 要求三文件数量和字节双门禁。 |
| read-set regression | `tests/test_skill_size_gate.py:32`、`tests/test_skill_size_gate.py:33`、`tests/test_skill_size_gate.py:43` | 测试精确锁定六文件集合并仅重算 byte total。 | 现有测试把验收漂移固化成“绿色”；需要三文件 exact/+1 负例。 |
| implx read contract | `skills/implx/SKILL.md:12`、`skills/implx/SKILL.md:14`、`skills/implx/SKILL.md:18` | 文本把六文件称为 measured bootstrap，implement/review/pr-gate 作为后置 phase load。 | 必须与 GH-208 原始三文件 fastlane startup 定义收敛。 |
| generic load contract | `AGENT_USAGE.md:7`、`AGENT_USAGE.md:9`、`AGENT_USAGE.md:18` | 通用 SpecRail flow 要求在创建 specs/PR/review 前读取七类入口。 | 若不声明 fastlane 专用边界，真实运行会读取第四个文件而违反 B-014。 |
| contract budget | `AGENTS.md:26`、`AGENTS.md:28`、`AGENTS.md:31` | 已定义 Skill 行数、fastlane 30KB 和 full-drain 60KB，但没有三文件数量门禁。 | 需要记录三文件闭集和显式 human revision 边界。 |
| current measurements | `checks/skill_size_gate.py:62`、`checks/skill_size_gate.py:78` | evaluator 输出实际 read-set files/bytes；当前树实测 fastlane 六文件 30,710 bytes，full-drain 八文件 55,414 bytes。 | 已有 evaluator 可扩展为 count+bytes 双门禁；六文件结果必须从 allowed 变 blocked。 |
| focused implementation contract | `skills/specrail-implement/SKILL.md:10`、`skills/specrail-implement/SKILL.md:25`、`skills/specrail-implement/SKILL.md:32` | 负责 scoped route、focused verification 与 exact-head PR 收口。 | 它是 B-014 的第二个具名 startup 文件，也定义 B-001 的启动终点。 |
| PR evidence contract | `skills/specrail-pr-gate/SKILL.md:10`、`skills/specrail-pr-gate/SKILL.md:30`、`skills/specrail-pr-gate/SKILL.md:36` | 定义 current PR evidence 与离线 gate。 | 它是 B-014 的第三个具名 startup 文件，并约束 B-005..B-008 的真实证据。 |

Search-first 已确认仓库没有现成的 gate-audit inventory/evidence validator 或真实
GH-208 performance measurement helper；已有 `tools/spec_depth_audit.py` 只审规格深度，
不能验证 `checks/*.py` 与 Markdown 审计表的一一对应。为避免增加会被自己纳入审计的
runtime gate，本设计把 inventory、fresh GitHub evidence collector 与 one-shot startup
measurement runner 都放在 `tools/`，不新增 `checks/*.py`。仓库也没有能完整中介
agent context 注入与整个 session 文件读取的 trusted provider 合同；新增
`integrations/fastlane_observation_provider.md` 只定义宿主 runtime 必须提供的能力与
attestation 形状，不把仓库内 adapter 或 Python runner 宣称为信任根。

## 设计方案

### 1. A：真实 fastlane measurement

运行 owner 选择一个当前 main 上满足 GH-203 complete/non-legacy/decidable/non-heavy
资格的真实 open issue。measurement 在任何仓库合同读取或 GitHub qualification query
前写入 `measurement_id` 和单调开始时间，随后按真实 single-issue fastlane 路径执行：

```text
measurement start
  -> read exact agent-facing fastlane contract set
  -> fresh issue/PR/branch duplicate-work mapping
  -> packet + done-when + risk qualification
  -> isolated fixed-validator implement route decision
  -> implementation-ready boundary
measurement stop
```

终态 evidence 采用 issue comment 中的闭合字段表，不新增 schema：

- `measurement_id`、`repository`、`base_sha`、`head_sha`、`issue`、可选 `pr`；
- `started_at`、`completed_at`、`elapsed_seconds_monotonic`；
- executor/tool versions；
- trusted provider attestation、`read_events[]` 与 `context_events[]`，事件至少包含
  `{path, bytes, reader_principal, command_digest, session_identity, pid, parent_pid,
  phase}`，以及从事件确定性派生的
  `agent_contract_read_set` / `validator_dependency_read_set` 与各自合计；
- route/duplicate/qualification command 的 exit status 和 artifact link；
- `outcome: passed | failed | incomplete` 与失败原因。

只有 `outcome=passed` 且 `elapsed_seconds_monotonic <= 600`、身份闭合、read set 满足
B-014/B-015、route gate 真实完成且没有 unknown/unclassified read event 时才满足
fastlane 实测。`integrations/fastlane_observation_provider.md` 定义 executor/runtime
控制、独立于 caller、agent、adapter、validator 和 repository code 的
`trusted_observation_provider`。它建立并拥有封闭 measurement session namespace，
通过 provider-owned read broker/repository mount 与 context broker 强制中介：

1. 首次 prompt attachment、Skill load、resume context 与 tool/validator output 中所有
   repository-derived bytes 进入 agent/model context 的事件；
2. agent、validator/import、所有 descendant 以及同 session sibling tool process 对
   repository 的 open/read 事件。

被测进程不能持有绕过 broker 的 repository FD/mount 或 context channel；provider 以
session namespace/security principal 而非仅 PID ancestry 确定覆盖范围。无法记录事件、
queue overflow/drop、provider 不可用、process escape、unmediated repository access 或
context bypass 时，provider 必须拒绝相应访问、关闭 session 并直接向 verifier 返回
`incomplete`，不得 fallback 到 adapter ledger。

provider 向 runner/verifier 直接交付签名或等价宿主 attested 的 closed envelope：
`provider_id`、provider executable/image digest、policy digest、coverage roots、
measurement ID/run nonce、session/sandbox/namespace identity、repository immutable
ID/ref/tree、repository mount identity、context broker identity、started/completed
boundary、`complete`/`overflow`、event count、canonical event-stream digest 和递增
sequence。caller/agent/adapter 只能消费该 envelope，不能提供、删除、改写或重排事件；
runner 校验 attestation、coverage 与 immutable ref，并把 adapter view 与 provider
direct stream 做 exact-set comparison。nonce、hash chain、PID 和 adapter stream
自洽只证明其内部一致，不能证明完整性。

`tools/fastlane_startup_measurement.py` 先生成 measurement ID/nonce，再要求宿主 provider
启动 session 和 executor adapter；CLI 不提供 `--ledger`、`--read-set` 或
`--provider-attestation` caller input。runner 从 provider direct stream 重算 sequence、
hash chain、read-set 分类并核对 closed envelope；断链、重复/跨 run event、caller JSON、
adapter identity 漂移、provider/adapter event 差异或 provider coverage 不完整均
incomplete。取消、head drift 或部分采集生成新的 `measurement_id` 重跑；旧证据保留，
不修改为成功。

可实现的正例边界是：agent context 只加载三份具名 Skill；`route_gate.py` 在新鲜、隔离
且 argv/digest 固定的 validator child 中执行，child 自身读取三份 YAML 与 Python imports。
这些依赖读取全部由 provider 留在 ledger 和 600 秒 elapsed 中，但不作为 agent-facing contract
bytes。validator 输出只允许 closed route decision/evidence fields；若输出仓库原文、
agent 另行打开 YAML/module，或 provider 无法证明 reader/session identity，来源文件
同时进入 `agent_contract_read_set` 或直接使 measurement incomplete。这样 route
completion 不再与三文件目标冲突，也不能靠 phase 改名、adapter 漏报或 sibling process
隐藏真实读取。

### 2. A：真实 multi-lane PR measurement

选择一个实际触发多个 implementation/reviewer lane 的真实 PR，记录 lane roster、
dispatch/completion、exact head、review manifest/artifacts 和每轮 findings。轮数从通过
manifest semantics 的 terminal artifacts 派生，不接受调用者自报。

- 首轮无 code/spec finding且 terminal artifact 在同一 head 收敛：目标
  `review_rounds=1`。
- 仅 JSON/manifest 表示修复且 head/reviewer conclusion 未变：重生成 artifact，不增加
  round，沿用 GH-200 合同。
- 出现真实 finding、head 变化或范围不足：如实进入 bounded re-review；该样本不满足
  “无 finding 时一轮”正例，必须另取样本或取得 B-007 的 maintainer revision。

两类 measurement 都只把有界摘要与 durable artifact/link 附到 GH-208；原始大输出留在
artifact，不复制进 issue comment。

### 3. C：immutable-ref dynamic audit inventory

新增 `tools/gate_audit_inventory.py`，输入 `--repo`、`--ref` 和 `--audit`。helper 使用
git object database 对目标 ref 动态枚举排序后的 `checks/*.py`，读取每个 blob 计算
line count，并派生：

```json
{
  "version": 1,
  "ref": "<resolved 40-char sha>",
  "module_count": 37,
  "total_lines": 15158,
  "modules": [{"path": "checks/check_workflow.py", "lines": 526}],
  "inventory_sha256": "<sha256 of canonical path+line rows>",
  "decision": "allowed|blocked",
  "errors": []
}
```

`docs/GATE_AUDIT_2026-07-27.md` 固定审计 ref 为
`6b6e1f702a2098325ba34dd81f5f0c565f3c0134`，补齐
`checks/github_tier_evidence.py` 及其它因漏项导致的行数/摘要差异。Markdown 表保留
每模块的 `basis_id` 与处置；closed sidecar
`docs/GATE_AUDIT_2026-07-27.evidence.json` 绑定 resolved ref、repo immutable ID、
inventory digest 和每个模块唯一 evidence entry。新增
`schemas/gate_audit_evidence.schema.json`，entry 的 `basis` 只能是：

```text
incident:
  refs[] = typed same-repository GitHub issue/comment/PR review-thread/
           merged-PR or provider-bound hosted CI/publication event
  occurred_at = authoritative provider timestamp of the exact source event
  collected_at = fresh collector timestamp, distinct from occurred_at
  immutable_refs[] = optional rejection artifact/fix commit content binding
security_property:
  property_id + immutable contract_ref(path/blob/anchor)
              + negative_test_ref(path/blob/pytest node id)
no_record:
  exact 2026-06-28..2026-07-27 window + module-derived canonical queries
  + fresh provider and immutable-ref repository negative-search snapshots
disposition:
  retain | consolidate | downgrade_warning | needs_confirmation
  | converge_existing_issue | park | delete
```

`tools/github_gate_audit_evidence.py` 是 read-only fresh provider collector：
GitHub ref 必须属于同一 repository immutable ID，按 node/URL 取回且 source body、
review path 或关联 commit 必须包含目标 module path/stable audit ID；collector 在
validation invocation 内前后双读，输出 provider timestamp、node/database identity、
canonical payload digest 与 module binding。`no_record` query 由 module path/audit ID
和固定 `2026-06-28..2026-07-27` 窗口确定性派生；collector 返回 GitHub 每条 query 的
完整 result node IDs，inventory helper 从目标 ref/history 重算 tracked rejection/
review artifacts 与 fix commits 的结果。只有两类 search 都为空且窗口/query exact
匹配才成立，调用者自报空数组不参与判定。
repo artifact/commit、security contract/test 均从目标 immutable git ref 读取 blob，
validator 校验 path/blob/anchor 或 pytest node 确实存在并与 module entry 匹配。
调用者自报 URL/commit、只匹配 URL 格式、跨仓库 evidence、current-worktree 文件、
无法绑定 module 的真实事件均不能建立 basis。

`incident` 必须至少有一个 module-bound source event 的权威 `occurred_at` 落在固定
inclusive UTC 窗口
`2026-06-28T00:00:00Z <= occurred_at <= 2026-07-27T23:59:59Z`。GitHub
issue/comment/review-thread 使用准确 report/finding event 的 immutable provider
`createdAt`；merged PR 使用 provider `mergedAt`。fix commit/blob 可交叉绑定 incident
内容，但 author/committer timestamp 可由作者设置，不能单独证明发生时间。仓库 rejection
或 review artifact 必须再绑定 hosted CI run、GitHub comment/review 等 trusted
publication/run event，并采用该事件的 provider timestamp；artifact 自报时间不参与
窗口资格。`collected_at` 只证明本次采集新鲜度，不能把旧 incident 变成窗口内事件。
缺失/无法解析/越界 `occurred_at`、只给 commit author date、source event 与 module
binding 不一致时 block；窗口外引用可以保留为 context，但不计入合格 incident。

`docs/...evidence.json` 是 durable audit record，不是 provider 信任根。
`tools/gate_audit_inventory.py` 必须在同一 validation invocation 内调用 fresh collector
并将双读结果与 sidecar exact compare；provider unavailable/drift 时 block。随后解析
Markdown path/line/basis_id/disposition columns，与动态 inventory/evidence exact-set
一一比较，并验证：

- 表 path 集合与 git ref 完全相等、无重复；
- 每行 line count、37/15,158 totals 和 inventory digest 一致；
- 每行 basis_id 唯一且解析到同 module 的 verified typed basis，free text 不参与判定；
- `incident` 必须通过 fresh provider 验证准确 source event/module binding，且至少一个
  权威 `occurred_at` 位于固定窗口；immutable object 只能辅助内容绑定；
  `security_property` 必须同时解析 contract 与 executable negative test；
- `no_record` 必须具有 fixed-window fresh negative-search snapshot，只允许
  downgrade/warning/confirm/delete/park dispositions，不得支持 incident/security retain；
- `consolidate` 必须绑定目标 ref 中存在的 target module，`converge_existing_issue`
  必须绑定 fresh same-repository open issue；Markdown disposition 必须与 evidence entry
  exact match，任意其它处置 prose 拒绝；
- 处置摘要计数恰好覆盖全部 37 行。

所有 errors 稳定按 category/path 排序并一次性输出。`tests/test_gate_audit_inventory.py`
覆盖遗漏 `github_tier_evidence.py`、重复/额外 path、错行数、错总数、unknown/duplicate/
cross-module basis_id、自由文本 basis、伪造/过期/非空搜索结果、`no_record + retain`、
unknown/mismatched disposition、合并/收敛缺 target、缺 contract/test anchor、
摘要不闭合，以及另一个 ref 新增/删除模块的重枚举；incident 时间负例覆盖 fresh
collection + old occurrence、缺 `occurred_at`、commit author timestamp、起止边界前后
一秒，正例覆盖两个 inclusive 边界；
`tests/test_github_gate_audit_evidence.py` 覆盖不存在/跨仓库/未绑定 module/漂移的
GitHub ref、provider 双读不一致，以及准确 source-event provider timestamp 绑定。
helper 只做历史审计的确定性验证，不进入 runtime route，也不扩张 agent authority。

### 4. D：exact three-file fastlane startup

`checks/skill_size_gate.py` 把 agent-facing fastlane contract 的静态闭集改为：

```text
skills/implx/SKILL.md
skills/specrail-implement/SKILL.md
skills/specrail-pr-gate/SKILL.md
```

size gate 同时断言 `file_count <= 3`、exact set 和 total bytes `<=30 * 1024`；
one-shot measurement runner 再以 executor ledger 证明真实运行没有额外 agent contract
read。测试必须覆盖：

- exact three-set + 30 KiB 通过；
- 任意第四文件，即使总字节低于 30 KiB，阻断；
- exact set 中缺文件、替换文件或同义路径，阻断；
- 三文件总计 30 KiB 通过、30 KiB + 1 阻断；
- current six-file set 明确阻断；
- agent 直接读取 YAML/module、validator 转发仓库原文、伪造 phase、unknown PID 或漏掉
  validator dependency 明确阻断；
- 调用者注入 ledger、事件断链/重复、跨 measurement 重放或 executor identity 漂移阻断；
- adapter 省略第四个 context injection/agent read 但提交 nonce、sequence、hash 与 PID
  自洽的三文件 ledger，因 provider direct stream exact-set mismatch 阻断；
- sibling/descendant read、context bypass、process/session escape、provider
  identity/policy/coverage mismatch、event overflow/drop/unavailable 明确产生
  `incomplete`，不得回退 self-report；
- 三 YAML 与 Python imports 由 fixed route-gate child 读取时单独列入
  `validator_dependency_read_set`，route 可完成且总 elapsed 包含这些读取；
- full-drain 60 KiB/60 KiB + 1 边界保持。

`skills/implx/SKILL.md`、`skills/specrail-implement/SKILL.md` 和
`skills/specrail-pr-gate/SKILL.md` 收敛为 fastlane 启动的三份自包含合同；
`AGENTS.md`/`AGENT_USAGE.md` 明确这是显式 implx single-issue fastlane 的窄路径，
其它 SpecRail route 仍走通用加载合同。fastlane 所需 locale、human-gate 和 route
事实必须在三文件内可得、由 authenticated invocation input 提供，或由 fixed validator
以 closed decision 输出；不得由 agent 实际打开通用配置后改称 validator dependency。

三份 Skill 都遵守现有 150/200 行上限和 one-in-one-out，最终字节确定后只刷新对应
`skills-lock.json` hashes。若无法在不丢行为合同的情况下实现三文件启动，route 保持
blocked，并请求 B-016 的显式 maintainer revision；不得恢复六文件 allowed。

### 5. Human revision 与 evidence ordering

任何替代三文件集合的授权必须来自 GH-208 或实现 PR 的 fresh maintainer comment/review，
并记录 actor、source URL、target revision、exact replacement set/count/budget 和理由。
实现者自报、普通 spec approval、merge authorization 或旧 PR #210 body 不满足。

验证顺序固定为：

```text
fixed-ref audit inventory
  -> exact read-set/count/bytes gate
  -> focused tests
  -> packet/workflow/depth checks
  -> real fastlane measurement
  -> real multi-lane measurement
  -> attach evidence to GH-208
```

前四项只证明实现可进入 rollout；不能替代最后两项真实证据。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | real end-to-end timing boundary | manual durable check：GH-208 evidence 从首个 read/validator/query 前开始，含真实 route completion 且 `elapsed_seconds_monotonic <= 600` |
| B-002 | provider-mediated read/context ledger | `python3 -m pytest -q tests/test_fastlane_startup_measurement.py -k "provider or context or identity or ledger or sequence or hash_chain or partition or coverage"` |
| B-003 | provider-derived provenance/completeness | `python3 -m pytest -q tests/test_fastlane_startup_measurement.py -k "self_report or omitted or exact_set or injected or replay or unknown or missing or relayed or sibling or escape or overflow or dry_run"` |
| B-004 | incomplete/retry handling | negative rehearsal：取消或 head drift 产生 `incomplete` 与新 measurement ID，不改写旧记录 |
| B-005 | multi-lane terminal evidence | manual durable check：真实 PR lane roster + exact-head manifest/artifacts 派生 `review_rounds=1` |
| B-006 | artifact-only vs re-review split | `python3 -m pytest -q tests/test_review_contract_docs.py tests/test_review_result_semantics.py` |
| B-007 | true-finding exclusion | manual durable check：含真实 finding 的样本不标作 no-finding pass，或存在 exact maintainer revision |
| B-008 | GitHub durable evidence | `gh issue view 208 --repo majiayu000/specrail --comments` 人工核对 measurement links/IDs 与有界摘要 |
| B-009 | fixed main 37/15,158 baseline | `python3 tools/gate_audit_inventory.py --repo . --ref 6b6e1f702a2098325ba34dd81f5f0c565f3c0134 --audit docs/GATE_AUDIT_2026-07-27.md --json` |
| B-010 | dynamic git-ref enumeration | `python3 -m pytest -q tests/test_gate_audit_inventory.py -k "dynamic or ref or hardcoded"` |
| B-011 | verified typed basis + fixed incident occurrence window | `python3 -m pytest -q tests/test_gate_audit_inventory.py tests/test_github_gate_audit_evidence.py -k "incident or occurred_at or window_boundary or old_incident or commit_timestamp or security_property or no_record or negative_search or free_text or cross_module or provider"` |
| B-012 | inventory/table/summary failures | `python3 -m pytest -q tests/test_gate_audit_inventory.py -k "missing or duplicate or extra or lines or summary"` |
| B-013 | ref change regeneration | `python3 -m pytest -q tests/test_gate_audit_inventory.py -k "ref_change or added or removed"` |
| B-014 | provider-observed exact three-file context set + separate validator dependencies | `python3 -m pytest -q tests/test_skill_size_gate.py tests/test_fastlane_startup_measurement.py -k "fastlane and (read_set or fourth_file or validator_dependency or direct_read or omitted or context)"` |
| B-015 | count + bytes + anti-reclassification | `python3 -m pytest -q tests/test_skill_size_gate.py tests/test_fastlane_startup_measurement.py -k "fastlane and (byte or six_file or relayed or unknown)"` |
| B-016 | maintainer revision boundary | manual contract inspection of GH-208/implementation PR authorization evidence and negative self-authored fixtures |
| B-017 | full-drain principal-aware preservation | `python3 -m pytest -q tests/test_skill_size_gate.py tests/test_fastlane_startup_measurement.py -k "full_drain"` |
| B-018 | ref/reader/process drift and interruption freshness | negative rehearsal + `python3 -m pytest -q tests/test_fastlane_startup_measurement.py tests/test_gate_audit_inventory.py -k "drift or ancestry or interrupted"` |

## 数据流

```text
immutable main ref
  -> dynamic checks/*.py inventory
  -> fresh/immutable typed evidence resolution
  -> audit table/basis/disposition exact-set reconciliation
  -> deterministic audit decision

explicit implx single-issue invocation
  -> trusted provider sealed session + read/context mediation
  -> provider-observed exact three-file agent contract set
  -> provider-observed isolated route validator dependency set
  -> count + bytes gate
  -> fresh target/route qualification
  -> monotonic timing envelope
  -> real implementation-ready boundary
  -> durable GH-208 measurement evidence

real multi-lane PR
  -> lane roster + exact-head artifacts/manifest
  -> derived finding/round state
  -> durable GH-208 convergence evidence
```

审计 helper 只读 git objects/Markdown。measurement 对 GitHub 的唯一新写是经授权附加到
GH-208 的证据 comment；不修改 labels、不关闭 issue、不提供 merge/final approval。

## 备选方案

- 只把报告标题改为 37/15,158：表仍可能漏项且下一次新增模块会再次漂移，拒绝。
- 在 `checks/` 新增审计 gate：新 gate 会立即改变被审计集合并扩大 flywheel，采用
  `tools/` 下的离线 validator。
- 接受六文件 30KB 作为 D：违反 issue 原始“≤3 个文件”条件和当前任务明确约束，拒绝。
- 把六个通用 bootstrap 文件改名为 pre-startup 后不计：实际读取成本仍存在，违反
  B-003/B-015，拒绝。
- 把 route-gate YAML/Python dependencies 算入三份 agent contract：使每个真实 route
  completion 必然失败；采用 reader-principal 分区，但保留完整 ledger 与端到端 elapsed。
- 让调用者用 `phase: validator` 重分类第四个 agent read：不可审计；分类必须来自 fixed
  command identity 与 provider session identity，未知事件 fail closed。
- 把 adapter 的 nonce/hash/PID stream 当作完整性信任根：adapter 仍可删掉第四次读取并
  生成内部自洽 ledger；采用宿主强制中介 provider 的 direct stream 与 closed
  attestation，adapter view 只作 exact compare。
- 接受调用者生成的 ledger、provider-shaped attestation 或另一 run 的完整 event
  stream：仍可删事件/重放通过；runner 必须先建 nonce，并只接受 provider 直接绑定该
  sealed session 的 evidence。
- 只要求 audit basis/disposition 非空或 URL 格式正确：可用任意 prose/假链接
  false-close；采用 fresh/immutable typed evidence 与 module cross-binding。
- 把 committed audit sidecar 当作 GitHub/no-record 信任根：sidecar 可由实现者自洽伪造；
  validation 必须 fresh 双读远端，并对 `no_record` 重跑 fixed-window derived query。
- 用本次 fresh `collected_at` 证明 incident 在 30 天内，或用 commit author date 代替
  provider source-event time：两者都不证明真实发生窗口；采用准确 event 的
  `createdAt`/`mergedAt` 并单独校验 `occurred_at`。
- 用 fixture timing 替代真实队列：只能证明测试速度，不能证明真实 ceremony 成本，
  拒绝。
- 把有 finding 的两轮 PR 统计成“首轮发现后即收敛”：改变了 B-005 前提，拒绝。

## 风险

- Security: 三文件自包含可能遗漏人类 gate；实现必须保留现有 authorization 边界，
  缺失即 blocked。validator 只返回 closed decision，若转发仓库原文则来源计入 agent
  contract；measurement provider 必须由宿主 runtime 控制并强制中介 repo/context
  access，仓库代码不得伪装 provider；incident/security basis 必须由 fresh provider
  验真，incident occurrence 还必须落在固定窗口。
- Compatibility: 通用 SpecRail route 继续读取通用配置；只有显式、合格的 implx
  single-issue fastlane 使用三文件窄入口。
- Performance: 真实测量本身产生一次运行成本；使用单次命名 measurement 和有界摘要，
  不建立常驻 telemetry。
- Audit integrity: 历史 ref 与工作树可能不同；validator 必须从指定 git object 读取，
  不能混用 current filesystem。
- Maintenance: 三个 Skill 都接近硬上限时必须 one-in-one-out；不得提高 cap。
- External evidence: GitHub comment 是外部可见写；执行前仍需当前授权，规格本身不授权。

## 测试计划

- [ ] Focused audit:
  `python3 -m pytest -q tests/test_gate_audit_inventory.py
  tests/test_github_gate_audit_evidence.py`。
- [ ] Focused read-set:
  `python3 -m pytest -q tests/test_skill_size_gate.py
  tests/test_fastlane_startup_measurement.py`。
- [ ] Existing review semantics:
  `python3 -m pytest -q tests/test_review_contract_docs.py tests/test_review_result_semantics.py`。
- [ ] Fixed-ref audit:
  `python3 tools/gate_audit_inventory.py --repo . --ref 6b6e1f702a2098325ba34dd81f5f0c565f3c0134 --audit docs/GATE_AUDIT_2026-07-27.md --json`。
- [ ] Pack:
  `python3 checks/check_workflow.py --repo . --spec-dir specs/GH208`。
- [ ] Depth:
  `python3 tools/spec_depth_audit.py --spec-dir specs/GH208 --gate`。
- [ ] Runtime rollout：完成 B-001..B-008 的两次真实 measurement 并附到 GH-208；
  focused tests 不能替代。

## 回滚方案

- 若 audit helper/report 有误，回滚 `tools/gate_audit_inventory.py`、对应测试与报告为同一
  单位；fresh provider sidecar/collector/schema 同步回滚，历史 GH-208 evidence 保留并
  追加纠正，不删除旧证据。
- 若三文件入口造成行为缺失，先禁用 fastlane shortcut并回退到 blocked/full route；
  未取得 B-016 授权前不得把 PR #210 的六文件集合恢复为 GH-208 passed。
- 若 executor 无法提供完整 reader/PID ledger，measurement 标记 incomplete；不得退回
  调用者或 adapter 自报 read set/ledger。若宿主没有受信 provider 能力、coverage
  attestation 不完整或发现 access bypass，fastlane measurement 保持 disabled/incomplete。
- 回滚 Skill 文本时同步回滚 `skills-lock.json` 对应 hashes；不回滚 B/E 的 size caps、
  CI gate 或单 reviewer 默认。
- 真实 measurement 一旦发布即追加式保留。发现边界错误时发布新的
  `supersedes_measurement_id` 纠正记录，GH-208 保持 open，禁止改写旧 comment 冒充
  原始通过。
