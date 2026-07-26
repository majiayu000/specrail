# Tech Spec

## Linked Issue

GH-174

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":174,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/installed_skill_integrity.py","checks/skill_reference_graph.py","skills-lock.json","tools/check_installed_codex_skills.py","tools/install_codex_skills.py","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-implement-queue/references/evidence-and-recovery.md","skills/specrail-implement-queue/references/planning-and-runtime.md","skills/specrail-implement-queue/references/review-and-merge.md","tests/test_check_workflow.py","tests/test_install_codex_skills.py","tests/test_skill_reference_graph.py"],"spec_refs":["specs/GH174/product.md","specs/GH174/tech.md","specs/GH174/tasks.md"]}
-->

## Product Spec

见 `specs/GH174/product.md`。本设计实现 B-001..B-016，并以 GH-172 合并为实现前置。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue entry | `skills/specrail-implement-queue/SKILL.md:11-249` | Startup、spec gate、tier 与 planning 全在主文件。 | 保留不可绕过摘要，阶段细节可移到 planning reference。 |
| runtime controls | `skills/specrail-implement-queue/SKILL.md:250-606` | 编排、review、budget、breaker、wait、checkpoint、Goal 混在主文件。 | 需要压缩主合同并按 planning/runtime、review/merge 路由详细步骤。 |
| implementation/merge | `skills/specrail-implement-queue/SKILL.md:607-799` | 实现、review、授权、merge、输出和 rejection 全在主文件。 | merge/authorization 摘要留主文件，证据与恢复细节按需加载。 |
| implx router | `skills/implx/SKILL.md:13-29`, `skills/implx/SKILL.md:224-227` | 直接委托 queue 主 Skill 并引用其中多个章节。 | 拆分后必须只指向主入口，不自行猜引用路径。 |
| current lock | `skills-lock.json:21-23` | queue 只锁 `SKILL.md`。 | GH-172 完成后为三个引用加入多文件 hash 闭集。 |
| installer | `tools/install_codex_skills.py:61-101` | 复制整个目录但只验证入口 hash。 | 由 GH-172 改为按同一 manifest post-check 全部引用。 |
| pack check | `checks/check_workflow.py:485-512` | 校验 required files、pack 与 lock，没有 phase/reference graph。 | 接入独立确定性引用图检查。 |

## 设计方案

### 1. 主文件合同与 phase manifest

主文件保留 frontmatter、入口条件、所有不可绕过合同的短版和一个
`specrail-phase-references-v1` JSON marker：

```json
{
  "version": 1,
  "phases": [
    {"phase": "startup_planning", "references": ["references/planning-and-runtime.md"]},
    {"phase": "runtime_handoff", "references": ["references/planning-and-runtime.md", "references/evidence-and-recovery.md"]},
    {"phase": "review_merge", "references": ["references/review-and-merge.md"]},
    {"phase": "retry_recovery", "references": ["references/evidence-and-recovery.md"]}
  ]
}
```

`phases` 用**数组**而不是对象：JSON 对象的重复键会被普通 parser 静默折叠成一个值，
B-008 要求的"重复 phase 声明必须被拒绝并报告"就无法实现（重复的
`startup_planning` 会隐形并悄悄改变路由）。数组形态让重复 `phase` 值可被确定性检出；
实现禁止改回对象形态，也不得依赖 pair-preserving parser 之外的隐式行为。

允许同一引用服务多个 phase，但**每个 phase 内**路径必须唯一、稳定排序；跨 phase 重复
同一路径是上述 canonical manifest 的合法复用，validator 不得用全局 path uniqueness
拒绝。主文件对每个 phase 明确“何时加载”和“在首个什么动作前加载”。implx 只加载 queue
主入口，queue 再按当前 phase 路由；禁止 implx 预读全部引用。

主文件必须保留稳定关键 marker：

- startup/readiness/skip labels/Done-When；
- reviewer lane required/failure；
- Same-Issue Circuit Breaker trip/no-auto-continue；
- bounded tranche stop；
- wait contract；
- authorization/merge gate/human boundary；
- checkpoint/Goal 不替代 GitHub truth；
- rejection repeat stop。

### 2. 三个单层引用

与 GH-160 的顺序约束：GH-160 计划新增
`skills/specrail-implement-queue/references/context-budget.md`
（`specs/GH160/tasks.md:17`、`specs/GH160/tech.md:106-114`）。本设计把 context/runtime
budget 收进 `planning-and-runtime.md`，两者的闭集/lock 相等性检查会互相判错。因此显式
定序：**GH-174 先落地**，GH-160（当前 `parked`）在其之后实现，并在解除 parked 时按本
manifest 的引用集合调整——要么把 context budget 写进 `planning-and-runtime.md`，要么在
GH-160 自己的 manifest 里同时更新 phase manifest、lock 与闭集检查。若 GH-160 先合并，
本 issue 必须先把该文件纳入 phase manifest 与 planned paths 再实现，不得在 manifest
之外删改它。

- `planning-and-runtime.md`：tier 细节、queue ledger、spec/impl mix、context/runtime
  budget、checkpoint/Goal 字段与操作顺序。
- `review-and-merge.md`：bounded review artifact、reviewer failure、CI/PR gate、
  graded reconfirmation 与 safe merge 的详细步骤。
- `evidence-and-recovery.md`：output firewall、验证层次、handoff、closure audit、
  rejection persistence 与 retry evidence。

引用不含 frontmatter，不声明其他引用，不出现 `../` 或绝对路径。每个引用第一条非空行
必须逐字声明 `Reference only; the main SKILL.md contract wins`，并列出自己服务的 phase ID。
validator 仅对这条 exact required header 中的单个 bare `SKILL.md` token 做窄豁免；header
之外的裸 `SKILL.md`、`references/*.md` 或其它主/引用路径仍按二级路由拒绝，近似 header、
多次出现或在其它位置出现均不豁免。
normative summary 只在主文件定义；引用给出步骤/字段/示例，不得出现降低 MUST 的
fallback 语句。

### 3. 引用图 validator

新增 `checks/skill_reference_graph.py`：

```text
validate_skill_reference_graph(repo, skill_name) -> list[str]
```

处理顺序：

1. 解析主文件唯一 JSON marker；
2. 校验 closed phase enum、非空路由、POSIX 相对路径与 skill-root containment；
3. 校验每个路径是普通文件且无 symlink component；
4. 扫描引用中的 Markdown link/marker **以及裸路径 token**（反引号或纯文本里的
   `SKILL.md`、`references/*.md` 等规范化路径），拒绝对主文件/其他引用的二级路由；
   唯一例外是步骤 6 验证通过的第一条 exact required header 中恰好一次 `SKILL.md`，
   scanner 必须按 line/occurrence 定位豁免，不能把该 token 加入全局 allowlist。
   只扫链接语法不够：这类 skill 文档习惯用反引号裸写可操作文件名，未加链接语法的
   `references/review-and-merge.md` 同样会诱导多跳重读；
5. 与 GH-172 normalized lock manifest 对账：声明集合必须等于 queue 的额外
   `files[]` 集合；
6. 检查每个引用的 exact required header、声明 phase 与反向路由一致；
7. 检查关键 marker 只在主文件存在，并按**结构化清单**判定冲突：每条不可绕过合同在
   主文件里有稳定语义 ID（`contract_id`），引用中若出现同一 `contract_id` 的规范性
   句子，必须逐字复用主文件的短版文本，否则报冲突。引用中其它强制步骤必须放在成对的
   `specrail-normative-v1:start/end` marker 内；仅这些 block 扫描显式、封闭的 weakening
   pattern 清单（如 "when available"、"optional"、"best effort"、"may skip"），示例、
   解释和 marker 外普通文本不扫描。这样当前合法的 “optional local runtime checkpoint”
   可保留在说明文本中，但若在 normative block 用 `optional` 放宽 gate 仍确定性失败。
   B-009 的判定范围随之收窄为「同 contract_id 文本不一致」或「显式 normative block
   命中清单」两类可判定情形——检查器不承诺检出其它自然语言矛盾；
8. 稳定聚合全部错误。

`checks/check_workflow.py` 把 checker 加入 required assets，并对 queue 调用。
installed doctor 继续负责安装字节/hash；reference graph 负责仓库结构/路由，两者都通过
才可启动 queue。

仅靠"某次 doctor 或 CI 跑过"不满足 B-005。preflight 先从实际加载的 main entrypoint
descriptor 与 canonical repo root 判定 `execution_origin = repo_copy | installed_copy`；
调用方不得用 flag 自报 origin。两条入口都必须在 fetch/list/map remote state、写
checkpoint 或 spawn lane 前执行：

```sh
python3 checks/skill_reference_graph.py --repo <specrail-source> --skill specrail-implement-queue --json
```

- `repo_copy`：graph checker 的 `<specrail-source>` 必须是当前加载 repo copy 所属
  canonical source root；`allowed` 即可继续，**不得**要求 `$CODEX_HOME`/`~/.codex`
  存在或运行 `--require-installed`。
- `installed_copy`：除 source graph `allowed` 外，还必须运行
  `python3 tools/check_installed_codex_skills.py --repo <specrail-source>
  --require-installed --json` 并得到 `match`，证明实际加载的 installed bytes 与同一
  manifest 一致；无法定位 source/loaded origin 或不匹配均停止。

正常 `implx` wrapper 当前在加载 queue 主 Skill 前就 fetch/map remote state，因此
`skills/implx/SKILL.md` 自己必须先执行上述 origin-aware bootstrap，再做任何远端读取，
随后才委派 queue。直接调用 `specrail-implement-queue` 时，queue Startup 第一步重复该
bootstrap，不能信任 wrapper 曾执行。两层都须 fail closed；repo copy 不依赖本机安装，
installed copy 不得跳过 doctor。

### 4. 机械等价与尺寸门禁

拆分前先建立 section inventory 和关键 marker fixture。移动每段时保留语义 ID，
测试对比拆分后主文件+引用的合同 inventory，禁止丢失或重复。新增尺寸校验直接按 UTF-8
bytes 和 `splitlines()` 计算，边界 500/28672 均测试 exact pass 与 +1 fail。

queue 主文件和引用单文件均低于 500 行；三引用不互相依赖。GH-172 合并后基于最新
manifest API 实现并最后刷新 queue/implx hash。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | size validator | `python3 -m pytest -q tests/test_skill_reference_graph.py -k size` |
| B-002 B-010 B-015 | critical marker inventory | `python3 -m pytest -q tests/test_skill_reference_graph.py -k contract` |
| B-003 B-004 B-011 | phase router + exact per-phase isolation | `python3 -m pytest -q tests/test_skill_reference_graph.py -k "phase or runtime_handoff or isolation"` |
| B-005 B-006 B-013 B-014 | origin-aware repo/installed preflight + GH-172 lock/installer/doctor | `python3 -m pytest -q tests/test_skill_reference_graph.py tests/test_install_codex_skills.py tests/test_check_workflow.py -k "repo_copy or installed_copy or outer_preflight or reference or multifile"` |
| B-007 B-008 B-009 | graph/safety/conflict rules | `python3 -m pytest -q tests/test_skill_reference_graph.py -k "cycle or path or conflict"` |
| B-012 | deterministic repeat | `python3 -m pytest -q tests/test_skill_reference_graph.py -k deterministic` |
| B-016 | post-merge observation boundary | 人工复核报告不作为结构 PR gate |

## 数据流

```text
main SKILL bytes → phase manifest → current phase → selected one-hop references
          └──────→ reference graph validator ← normalized GH-172 lock manifest
installed files  → GH-172 doctor ────────────┘
```

所有 pack checks 只读仓库；安装写入仍由显式 `--apply` 控制。

## 备选方案

- 只删文字：容易丢失合同且无法按 phase 扩展，拒绝。
- 每个 phase 独立 Skill：增加发现/安装/路由复杂度，当前无需，拒绝。
- 引用互相链接：形成隐式递归与漏读风险，拒绝。
- 把真实 token 降幅作为合并门：样本受任务/compaction 影响，本轮已明确非目标。

## 风险

- Security: 路径逃逸/symlink 必须在读取前拒绝，引用不得包含可执行自动化。
- Compatibility: 实现等待 GH-172；旧 installer/lock 不能安全分发引用。
- Performance: phase 路由减少默认注入，但当前阶段首次读取会增加一次小文件读取。
- Maintenance: critical marker inventory 与 phase enum 需测试，避免后续规则只写进引用。

## 测试计划

- [ ] Unit: 尺寸、manifest、phase 内重复/跨 phase 合法复用、required-header 窄豁免、
      normative-block weakening、闭集、循环、路径、冲突与稳定错误。
- [ ] Integration: workflow + GH-172 lock/installer/doctor 多文件 fixture。
- [ ] Regression: 全量 pytest、all-specs、depth audit、diff/hash/line/byte checks。
- [ ] Forward-use: 临时安装目录加载 startup_planning、runtime_handoff、review_merge、
  retry_recovery 四条 phase 路径（`runtime_handoff` 同时需要 planning 与 evidence 两个
  引用），并逐 phase 断言 exact isolation：startup 仅 planning、runtime_handoff 恰为
  planning+evidence、review 仅 review、recovery 仅 evidence。

## 回滚方案

回滚主 Skill、三个引用、checker/wiring、tests、docs 与 lock hash 的同一实现提交。
不得只删除引用而保留路由，或只回滚 lock 造成安装完整性漂移。
