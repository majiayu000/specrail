# Tech Spec

## Linked Issue

GH-208

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":208,"complete":true,"paths":["AGENTS.md","AGENT_USAGE.md","checks/skill_size_gate.py","docs/GATE_AUDIT_2026-07-27.md","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement/SKILL.md","skills/specrail-pr-gate/SKILL.md","specs/GH208/product.md","specs/GH208/tech.md","tests/test_gate_audit_inventory.py","tests/test_skill_size_gate.py","tools/gate_audit_inventory.py"],"spec_refs":["specs/GH208/product.md","specs/GH208/tech.md"]}
-->

## Product Spec

见 `specs/GH208/product.md`。本设计仅覆盖 GH-208 剩余的 A/C/D，即
B-001..B-018；PR #210 已完成的 B/E 不进入本 planned-changes manifest。

## Codebase Context

以下锚点均在写作基线
`6b6e1f702a2098325ba34dd81f5f0c565f3c0134` 上核实。

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| stale audit totals | `docs/GATE_AUDIT_2026-07-27.md:3`、`docs/GATE_AUDIT_2026-07-27.md:25`、`docs/GATE_AUDIT_2026-07-27.md:66` | 报告声明 36/36、14,779 行，并用手写表自证完整。 | PR #210 unresolved thread 已证明该结论漏项；B-009..B-013 要求固定 ref 的动态闭合。 |
| omitted tier module | `checks/github_tier_evidence.py:1`、`checks/github_tier_evidence.py:219` | 当前模块共 219 行，承载 trusted current-head tier evidence；未进入审计表。 | 它是必须补入 C 组的第 37 个模块。 |
| fastlane read-set gate | `checks/skill_size_gate.py:22`、`checks/skill_size_gate.py:24`、`checks/skill_size_gate.py:32` | `FASTLANE_READ_SET` 固定为 `AGENTS.md`、`AGENT_USAGE.md`、三份 YAML 与 `implx`，共六文件，只检查 30 KiB。 | B-014/B-015 要求三文件数量和字节双门禁。 |
| read-set regression | `tests/test_skill_size_gate.py:32`、`tests/test_skill_size_gate.py:33`、`tests/test_skill_size_gate.py:43` | 测试精确锁定六文件集合并仅重算 byte total。 | 现有测试把验收漂移固化成“绿色”；需要三文件 exact/+1 负例。 |
| implx read contract | `skills/implx/SKILL.md:12`、`skills/implx/SKILL.md:14`、`skills/implx/SKILL.md:18` | 文本把六文件称为 measured bootstrap，implement/review/pr-gate 作为后置 phase load。 | 必须与 GH-208 原始三文件 fastlane startup 定义收敛。 |
| generic load contract | `AGENT_USAGE.md:7`、`AGENT_USAGE.md:9`、`AGENT_USAGE.md:18` | 通用 SpecRail flow 要求在创建 specs/PR/review 前读取七类入口。 | 若不声明 fastlane 专用边界，真实运行会读取第四个文件而违反 B-014。 |
| contract budget | `AGENTS.md:26`、`AGENTS.md:28`、`AGENTS.md:31` | 已定义 Skill 行数、fastlane 30KB 和 full-drain 60KB，但没有三文件数量门禁。 | 需要记录三文件闭集和显式 human revision 边界。 |
| current measurements | `checks/skill_size_gate.py:62`、`checks/skill_size_gate.py:78` | evaluator 输出实际 read-set files/bytes；当前树实测 fastlane 六文件 30,710 bytes，full-drain 八文件 55,414 bytes。 | 已有 evaluator 可扩展为 count+bytes 双门禁；六文件结果必须从 allowed 变 blocked。 |
| focused implementation contract | `skills/specrail-implement/SKILL.md:10`、`skills/specrail-implement/SKILL.md:25`、`skills/specrail-implement/SKILL.md:32` | 负责 scoped route、focused verification 与 exact-head PR 收口。 | 它是 B-014 的第二个具名 startup 文件，也定义 B-001 的启动终点。 |
| PR evidence contract | `skills/specrail-pr-gate/SKILL.md:10`、`skills/specrail-pr-gate/SKILL.md:30`、`skills/specrail-pr-gate/SKILL.md:36` | 定义 current PR evidence 与离线 gate。 | 它是 B-014 的第三个具名 startup 文件，并约束 B-005..B-008 的真实证据。 |

Search-first 已确认仓库没有现成的 gate-audit inventory validator 或真实 GH-208
performance measurement helper；已有 `tools/spec_depth_audit.py` 只审规格深度，不能验证
`checks/*.py` 与 Markdown 审计表的一一对应。为避免增加一个会被自己纳入审计的新 gate，
本设计新增 `tools/gate_audit_inventory.py`，不新增 `checks/*.py`。

## 设计方案

### 1. A：真实 fastlane measurement

运行 owner 选择一个当前 main 上满足 GH-203 complete/non-legacy/decidable/non-heavy
资格的真实 open issue。measurement 在任何仓库合同读取或 GitHub qualification query
前写入 `measurement_id` 和单调开始时间，随后按真实 single-issue fastlane 路径执行：

```text
measurement start
  -> read exact fastlane startup set
  -> fresh issue/PR/branch duplicate-work mapping
  -> packet + done-when + risk qualification
  -> write_spec/implement route decision
  -> implementation-ready boundary
measurement stop
```

终态 evidence 采用 issue comment 中的闭合字段表，不新增 schema：

- `measurement_id`、`repository`、`base_sha`、`head_sha`、`issue`、可选 `pr`；
- `started_at`、`completed_at`、`elapsed_seconds_monotonic`；
- executor/tool versions；
- `read_set[] = {path, bytes, phase}` 与合计；
- route/duplicate/qualification command 的 exit status 和 artifact link；
- `outcome: passed | failed | incomplete` 与失败原因。

只有 `outcome=passed` 且 `elapsed_seconds_monotonic <= 600`、身份闭合、read set 满足
B-014/B-015 时才满足 fastlane 实测。取消、head drift 或部分采集生成新的
`measurement_id` 重跑；旧证据保留，不修改为成功。

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
每模块的事故/安全依据和处置；helper 解析 path/line columns，与动态 inventory
一一比较，并验证：

- 表 path 集合与 git ref 完全相等、无重复；
- 每行 line count、37/15,158 totals 和 inventory digest 一致；
- 每行 basis/disposition 非空；无证据必须显式“无记录”；
- 处置摘要计数恰好覆盖全部 37 行。

所有 errors 稳定按 category/path 排序并一次性输出。`tests/test_gate_audit_inventory.py`
覆盖遗漏 `github_tier_evidence.py`、重复/额外 path、错行数、错总数、空依据/处置、
摘要不闭合，以及另一个 ref 新增/删除模块的重枚举。该 helper 是历史审计的确定性
validator，不进入 runtime route，也不扩张 agent authority。

### 4. D：exact three-file fastlane startup

`checks/skill_size_gate.py` 把 fastlane 的闭集改为：

```text
skills/implx/SKILL.md
skills/specrail-implement/SKILL.md
skills/specrail-pr-gate/SKILL.md
```

gate 同时断言 `file_count <= 3`、exact set 和 total bytes `<=30 * 1024`。测试必须覆盖：

- exact three-set + 30 KiB 通过；
- 任意第四文件，即使总字节低于 30 KiB，阻断；
- exact set 中缺文件、替换文件或同义路径，阻断；
- 三文件总计 30 KiB 通过、30 KiB + 1 阻断；
- current six-file set 明确阻断；
- full-drain 60 KiB/60 KiB + 1 边界保持。

`skills/implx/SKILL.md`、`skills/specrail-implement/SKILL.md` 和
`skills/specrail-pr-gate/SKILL.md` 收敛为 fastlane 启动的三份自包含合同；
`AGENTS.md`/`AGENT_USAGE.md` 明确这是显式 implx single-issue fastlane 的窄路径，
其它 SpecRail route 仍走通用加载合同。fastlane 所需 locale、human-gate 和 route
事实必须在三文件内可得或由 authenticated invocation input 提供；不得实际打开通用
配置后把它从 measurement 排除。

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
| B-001 | real fastlane timing boundary | manual durable check：GH-208 evidence 的 start/end events、route decision 与 `elapsed_seconds_monotonic <= 600` |
| B-002 | measurement identity envelope | manual durable check：repository/SHA/issue/time/tool/read-set 字段完整且互相绑定 |
| B-003 | real-run provenance | manual durable check：证据无 dry-run/mock/fixture/old-transcript，并列出计时区间内全部 reads/queries |
| B-004 | incomplete/retry handling | negative rehearsal：取消或 head drift 产生 `incomplete` 与新 measurement ID，不改写旧记录 |
| B-005 | multi-lane terminal evidence | manual durable check：真实 PR lane roster + exact-head manifest/artifacts 派生 `review_rounds=1` |
| B-006 | artifact-only vs re-review split | `python3 -m pytest -q tests/test_review_contract_docs.py tests/test_review_result_semantics.py` |
| B-007 | true-finding exclusion | manual durable check：含真实 finding 的样本不标作 no-finding pass，或存在 exact maintainer revision |
| B-008 | GitHub durable evidence | `gh issue view 208 --repo majiayu000/specrail --comments` 人工核对 measurement links/IDs 与有界摘要 |
| B-009 | fixed main 37/15,158 baseline | `python3 tools/gate_audit_inventory.py --repo . --ref 6b6e1f702a2098325ba34dd81f5f0c565f3c0134 --audit docs/GATE_AUDIT_2026-07-27.md --json` |
| B-010 | dynamic git-ref enumeration | `python3 -m pytest -q tests/test_gate_audit_inventory.py -k "dynamic or ref or hardcoded"` |
| B-011 | one complete row per module | `python3 -m pytest -q tests/test_gate_audit_inventory.py -k "basis or disposition or complete"` |
| B-012 | inventory/table/summary failures | `python3 -m pytest -q tests/test_gate_audit_inventory.py -k "missing or duplicate or extra or lines or summary"` |
| B-013 | ref change regeneration | `python3 -m pytest -q tests/test_gate_audit_inventory.py -k "ref_change or added or removed"` |
| B-014 | exact three-file set | `python3 -m pytest -q tests/test_skill_size_gate.py -k "fastlane and (read_set or fourth_file or replacement)"` |
| B-015 | count + byte dual gate | `python3 -m pytest -q tests/test_skill_size_gate.py -k "fastlane and (byte or fourth_file or six_file)"` |
| B-016 | maintainer revision boundary | manual contract inspection of GH-208/implementation PR authorization evidence and negative self-authored fixtures |
| B-017 | full-drain preservation | `python3 -m pytest -q tests/test_skill_size_gate.py -k "full_drain"` |
| B-018 | drift/interruption freshness | negative rehearsal + `python3 -m pytest -q tests/test_skill_size_gate.py tests/test_gate_audit_inventory.py -k "drift or ref or interrupted"` |

## 数据流

```text
immutable main ref
  -> dynamic checks/*.py inventory
  -> audit table/basis/disposition reconciliation
  -> deterministic audit decision

explicit implx single-issue invocation
  -> exact three-file startup read set
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
- 用 fixture timing 替代真实队列：只能证明测试速度，不能证明真实 ceremony 成本，
  拒绝。
- 把有 finding 的两轮 PR 统计成“首轮发现后即收敛”：改变了 B-005 前提，拒绝。

## 风险

- Security: 三文件自包含可能遗漏人类 gate；实现必须保留现有 authorization 边界，
  缺失即 blocked，不能用性能目标降级安全规则。
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
  `python3 -m pytest -q tests/test_gate_audit_inventory.py`。
- [ ] Focused read-set:
  `python3 -m pytest -q tests/test_skill_size_gate.py`。
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
  单位；历史 GH-208 evidence 保留并追加纠正，不删除旧证据。
- 若三文件入口造成行为缺失，先禁用 fastlane shortcut并回退到 blocked/full route；
  未取得 B-016 授权前不得把 PR #210 的六文件集合恢复为 GH-208 passed。
- 回滚 Skill 文本时同步回滚 `skills-lock.json` 对应 hashes；不回滚 B/E 的 size caps、
  CI gate 或单 reviewer 默认。
- 真实 measurement 一旦发布即追加式保留。发现边界错误时发布新的
  `supersedes_measurement_id` 纠正记录，GH-208 保持 open，禁止改写旧 comment 冒充
  原始通过。
