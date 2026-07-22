# Tech Spec

## Linked Issue

GH-165

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":165,"complete":true,"paths":["checks/check_workflow.py","skills-lock.json","skills/specrail-diagnose-ci/SKILL.md","skills/specrail-implement/SKILL.md","skills/specrail-plan-tasks/SKILL.md","skills/specrail-release-note/SKILL.md","skills/specrail-triage-issue/SKILL.md","skills/specrail-workflow/SKILL.md","skills/specrail-write-product-spec/SKILL.md","skills/specrail-write-tech-spec/SKILL.md","tests/test_check_workflow.py"],"spec_refs":["specs/GH165/product.md","specs/GH165/tech.md","specs/GH165/tasks.md"]}
-->

## Product Spec

见 `specs/GH165/product.md`。本设计实现其中 B-001..B-018：把 mandatory
`route_gate.py` 从条件式建议收紧为可验证的 Gate Availability 契约，并保留明确、
限域且不可冒充 gate 成功的人工降级路径。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 工作流总检查 | `checks/check_workflow.py:140`, `checks/check_workflow.py:158`, `checks/check_workflow.py:500` | 已有 required-file、token、skill lock 等确定性检查，`main()` 聚合错误后一次性报告；尚未校验使用 route gate 的 skill 是否完整声明可用性契约。 | 新增 `validate_skill_gate_availability(repo)` 并接入现有错误聚合，无需新增检查器或运行时依赖。 |
| 检查器测试 | `tests/test_check_workflow.py:12`, `tests/test_check_workflow.py:24`, `tests/test_check_workflow.py:262` | 测试直接导入检查函数，也通过临时仓库和 CLI 验证整包行为。 | 可同时覆盖函数级全量报错、动态发现、兼容基线和 CLI fail-closed。 |
| 分发清单 | `skills-lock.json:4`, `skills-lock.json:16`, `skills-lock.json:61` | `skills-lock.json` 列出 repo-distributed skill 及内容哈希；八个目标 skill 均已被分发。 | 修改 skill 后必须更新对应八项哈希；既有 lock 校验继续负责路径/哈希/集合完整性。 |
| 路由器入口 | `skills/specrail-workflow/SKILL.md:23` | 路由器仅在仓库包含 gate 时运行，未规定缺失、执行错误或专用授权。 | 路由器必须在分派叶子 skill 前先按同一契约判定，防止未验证前提向下游传播。 |
| 实现与任务规划 | `skills/specrail-implement/SKILL.md:13`, `skills/specrail-plan-tasks/SKILL.md:15` | 两个 `implement` 路径均把 gate 写为 “when available”。 | 直接调用时也必须 fail closed，且不能借用另一路由或历史运行的 gate 结果。 |
| 规格编写 | `skills/specrail-write-product-spec/SKILL.md:16`, `skills/specrail-write-tech-spec/SKILL.md:15` | 产品规格与技术规格入口均允许条件式跳过 gate。 | `write_spec` 的两个叶子入口必须对缺失和失败给出一致、可审计的停止或降级结果。 |
| 分诊、CI 与发布 | `skills/specrail-triage-issue/SKILL.md:18`, `skills/specrail-diagnose-ci/SKILL.md:14`, `skills/specrail-release-note/SKILL.md:14` | 三条 route 均只有可选措辞；已有 rejection persistence 只处理 gate 已返回的拒绝 decision。 | Gate Availability 必须先处理 gate 根本不存在或没有产生有效 decision 的情况，再进入现有拒绝持久化流程。 |
| 兼容基线 | `skills/specrail-review-pr/SKILL.md:46` | review skill 已区分 exists、absent、command error 与显式人工降级，并要求稳定 unavailable 标记。 | 检查规则以其语义作为正向兼容基线；本 issue 不修改该文件，也不把规则局限为八个硬编码文件名。 |

## 设计方案

### 1. 动态发现 repo-distributed gate consumers

在 `checks/check_workflow.py` 新增纯读取函数
`validate_skill_gate_availability(repo: Path) -> list[str]`。函数遍历
`skills/*/SKILL.md`；只有正文引用精确路径 `checks/route_gate.py` 的 skill 才是候选。
`validate_skills_lock(repo)` 已负责确保该目录与 `skills-lock.json` 的路径、集合与哈希一致，
因此这里不复制 lock 解析或安装逻辑，也不维护八文件 allowlist。未来新增的 repo-distributed
route-gate consumer 会自动进入同一检查。

发现结果按仓库相对路径排序，函数收集所有错误后统一返回，不在第一个缺陷处提前退出。
这样一次运行能暴露全部目标 skill 的缺陷，并保持稳定输出顺序。

### 2. 确定性的 Gate Availability 文本契约

对每个候选 skill，验证器检查一个 `## Gate Availability` 段落。检查采用小而明确的
语义标记组合，不用 LLM、不执行 skill 中的命令，也不尝试推断自然语言同义词：

- gate exists：明确要求存在时执行 `checks/route_gate.py`，且只有真实 `allowed`
  decision 可以作为通过；
- gate absent：明确停止当前 SpecRail route、报告未接入，并禁止投机运行不存在的命令；
- gate error：解释器、权限、依赖、退出码或无效输出未产生 decision 时，按 unavailable
  处理而非 `allowed`，并保留错误；
- explicit degraded authorization：只有获知影响后的当前人工显式授权可继续；授权必须绑定
  当前 repository、route 与 task/run，普通执行授权、`implx auto`、历史或推断授权均无效；
- degraded evidence：要求 `gate_status: "unavailable"`、非空授权内容或引用，以及稳定用户
  可见标记 `SpecRail gate status: unavailable`；同时禁止声称 SpecRail-gated、verified、
  gate passed 或 merge-ready。

验证器还拒绝候选 skill 中仅以 `when available` 指示 mandatory route gate 的入口措辞。
它只约束 `checks/route_gate.py` consumer，不把 reviewer lane、外部 adapter、threads 等其他
可选集成的同名短语误判为 route-gate 缺陷。段落内可以有更严格规则，但缺少上述任一组
语义时都按路径列出错误。

`specrail-review-pr` 当前的 Gate Availability 段落是兼容性基线：它已有 named route、
repository gate、exists/absent/error 三分支、显式人工继续、结果内
`gate_authorization` 和稳定 unavailable 标记。验证器允许这种“命名 route + 当前结果内
授权证据”的等价限域表达，不要求为了通过检查而机械改写该未在本 issue 范围内的 skill。

### 3. 八个 skill 的同构契约

在八个目标 `SKILL.md` 中移除入口的 optional-only 表述，并增加同构
`## Gate Availability` 段落。每个段落写明该 skill 的实际 route 和 gate command，保持
route-specific 状态、参数与现有 decision 处理不变：

- `specrail-workflow` 在选路、分派前执行；上游结果不可替代叶子 skill 自检；
- `specrail-implement` 与 `specrail-plan-tasks` 使用 `implement`；
- `specrail-write-product-spec` 与 `specrail-write-tech-spec` 使用 `write_spec`；
- `specrail-triage-issue`、`specrail-diagnose-ci`、`specrail-release-note` 分别使用
  `triage_issue`、`fix_ci`、`draft_release_note`。

所有段落共同声明：不存在时默认停止；命令错误等价于 unavailable；只有当前人工的专用
gate-unavailable 授权才能开始 degraded operation；输出必须披露稳定标记、route、gate、
原因和授权证据。降级产物只能交给人工复核，不能满足后续 gate。恢复、重试或并发调用时
重新以当前 repository/route/task/run 判定，并保留既有 rejection persistence 的审计记录。

### 4. 接入整包校验与更新分发哈希

`main()` 在 `validate_skills_lock(repo)` 后调用
`validate_skill_gate_availability(repo)`。先由 lock 校验报告丢失、越界或哈希问题，再由新
验证器报告内容契约缺陷；两者都只读并进入现有统一错误列表。

八个 skill 修改后，重新计算并更新 `skills-lock.json` 中对应 `computedHash`。不修改
`tools/install_codex_skills.py` 或 `checks/specrail_lib.py`：安装器继续消费经过整包检查的
lock，通用库继续负责既有 lock 完整性，无需引入共享片段或第二套分发源。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | 八个目标 skill 的入口措辞与 Gate Availability 段落；内容验证器 | 参数化删除段落或保留 optional-only 入口，断言每个目标 skill 均被拒绝。 |
| B-002 | `specrail-workflow` 的分派前检查与不可传递声明 | 检查路由器文本包含分派前判定和叶子独立复核；运行目标 skill 契约参数化测试。 |
| B-003 | exists 分支与真实 decision 处理 | 对 exists/`allowed` 标记做正例；逐项删除 run/decision 语义做反例。 |
| B-004 | absent 分支 | 删除 absent、stop 或禁止投机命令任一语义，断言 `validate_skill_gate_availability` 返回对应路径错误。 |
| B-005 | error/unavailable 分支 | 删除 error 或 “not allowed/unavailable” 语义，断言检查失败；保留错误披露的完整段落通过。 |
| B-006 | 显式且限域的 degraded authorization | 参数化缺失 human explicit、repository、route、task/run 或等价结果内授权证据，断言 fail closed。 |
| B-007 | 普通/auto/历史授权排除 | 检查八个段落明确排除普通执行、`implx auto`、历史和推断授权；缺失排除声明时验证失败。 |
| B-008 | degraded evidence 与稳定标记 | 分别删除 `gate_status`, 授权字段/引用和 `SpecRail gate status: unavailable`，断言所有缺口一次性列出。 |
| B-009 | 降级结果禁止成功声明 | 检查段落包含 gated/verified/gate passed/merge-ready 禁止项；缺失时拒绝。 |
| B-010 | 完整性组合 | 构造半完整 Gate Availability 段落，断言不因单个标记存在而通过，并返回全部缺失项。 |
| B-011 | 动态发现与叶子自检 | 在临时仓库增加并锁定一个引用 `checks/route_gate.py` 的新 skill，断言无需更新 allowlist 即被发现；八个叶子 skill 分别通过。 |
| B-012 | 调用限域 | 检查 repository/route/task/run 或等价 result-local evidence 组合；并发描述缺失时拒绝目标 skill。 |
| B-013 | 重试与审计 | 复核八个 skill 保留现有 Rejection Persistence And Retry，且 Gate Availability 要求重试重评、不得覆盖先前失败。 |
| B-014 | 状态机兼容 | 断言现有 route 命令、state 和 non-`allowed` decision 文本未改变；Gate Availability 不声明绕过状态。 |
| B-015 | 已接入仓库兼容 | 以当前完整仓库和未修改的 `specrail-review-pr` 作为正例，运行函数测试与整包检查。 |
| B-016 | 未接入仓库默认停止 | 临时移除 gate 存在语义并保留普通替代说明，断言仍失败；完整 absent/普通非 SpecRail 说明通过。 |
| B-017 | 取消/中断恢复 | 检查目标段落要求中断后重新判定当前调用且不保留成功结论；删除恢复语义时拒绝。 |
| B-018 | 动态全量确定性校验 | 同时破坏八个目标 skill，断言单次调用按路径稳定返回八组错误；CLI 返回非零并列出全部路径。 |

## 数据流

1. `check_workflow.py` 解析仓库根并执行既有 pack/lock 校验。
2. `validate_skill_gate_availability(repo)` 按路径遍历 `skills/*/SKILL.md`，读取文本并筛选
   `checks/route_gate.py` consumer。
3. 对每个候选提取 Gate Availability 段落，检查 optional-only 入口与 exists、absent、
   error、authorization、evidence、marker、禁止成功声明及恢复语义。
4. 每个缺陷形成带仓库相对 skill 路径的确定性错误；函数返回完整列表，`main()` 与其他
   pack 错误合并输出。检查器不写文件、不执行 route gate、不持久化授权。
5. 运行时由 skill 指令先探测目标 gate：存在则执行并消费当前 decision；缺失或执行错误则
   停止。仅在获得当前人工专用授权后产生明确标记的 degraded 结果，其证据绑定当前调用，
   不成为任何下游 gate 的输入成功证据。
6. 八个 skill 内容变化通过更新后的 `skills-lock.json` 哈希进入既有分发流程；安装行为和
   dry-run 默认值不变。

## 备选方案

- 为八个文件维护硬编码 allowlist：拒绝。它会漏掉未来新增的 route-gate consumer，违背
  B-018 的全 skill 集约束。
- 新建共享 Markdown fragment 并在安装时拼接：拒绝。当前分发单位是独立 `SKILL.md`，
  拼接会引入第二套运行时组装与哈希语义；本 issue 先用机械检查保证副本同构。
- 把检查放入 `checks/specrail_lib.py` 或修改安装器：拒绝。该契约属于工作流资产静态检查，
  不需要扩大公共库或安装写路径。
- 缺失 gate 时自动安装、复制或直接继续：拒绝。会扩大权限并把未验证路径误报为
  SpecRail 成功。
- 只替换八处 “when available” 文案：拒绝。无法证明 absent、error、专用授权、审计标记
  与恢复语义完整，也无法防止未来回归。

## 风险

- Security: 人工授权文本可能含敏感信息；skill 只要求保存非空内容或可追溯引用，不要求
  将秘密写入公共产物。自动安装、权限提升、命令猜测均不在范围内。
- Compatibility: 依赖静默跳过 gate 的调用将变为显式停止，这是预期的 fail-closed 收紧。
  已有完整 gate 和有效 decision 的 route 命令、state 与业务决策保持不变；review skill
  作为正向基线防止规则过窄。
- Performance: 校验仅顺序读取少量 Markdown 文件，复杂度与分发 skill 总字节数线性相关，
  不产生网络或子进程开销。
- Maintenance: 自然语言 token 检查可能被无意义堆词规避；通过要求同一 Gate Availability
  段落内的组合语义、反例测试和稳定输出降低风险。若未来需要机器可读 schema，应另开
  issue，不在本次偷偷扩大范围。
- False positives: `when available` 只在引用 `checks/route_gate.py` 的候选中按 mandatory
  gate 入口语义检查；其他可选集成不受影响。

## 测试计划

- [ ] Unit tests: `/usr/bin/python3 -m pytest -q tests/test_check_workflow.py`；覆盖动态发现、
  当前仓库正例、review 兼容基线、optional-only 拒绝、每组缺失语义、全量错误、非候选不误报。
- [ ] Integration tests: `/usr/bin/python3 checks/check_workflow.py --repo . --all-specs`；证明
  新检查已接入 CLI，skill lock 哈希与所有规格包仍有效。
- [ ] Spec depth: `/usr/bin/python3 tools/spec_depth_audit.py --spec-dir specs/GH165 --gate`；
  证明 B-001..B-018 均有技术与验证映射。
- [ ] Manual verification: `rg -n "when available|## Gate Availability|SpecRail gate status: unavailable" skills/specrail-*`，逐项确认八个目标文件不再以 optional-only 方式进入 route gate，且未修改的 review 基线仍被接受。

## 回滚方案

回滚 `checks/check_workflow.py` 的新函数及 `main()` 接线、对应测试、八个 skill 的
Gate Availability 文本和 `skills-lock.json` 八项哈希即可恢复原行为。回滚不需要迁移数据、
撤销 schema 或清理持久化状态，因为本变更不改变 gate 输出格式、不写运行时数据，也不安装
任何文件。若只需紧急解除静态检查，可整体回滚这 11 个路径；不得仅删除检查器而保留失配
哈希，或仅恢复 optional-only 文案却继续声称整包通过。
