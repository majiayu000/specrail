# Tech Spec

## Linked Issue

GH-172

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":172,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","README.md","checks/check_workflow.py","checks/specrail_lib.py","skills-lock.json","skills/specrail-implement-queue/SKILL.md","skills/specrail-install/SKILL.md","tests/test_check_workflow.py","tests/test_install_codex_skills.py","tools/install_codex_skills.py"],"spec_refs":["specs/GH172/product.md","specs/GH172/tech.md","specs/GH172/tasks.md"]}
-->

## Product Spec

见 `specs/GH172/product.md`。本设计实现 B-001..B-020：新增显式只读
installed-skill doctor，普通 pack/CI check 保持只依赖仓库内容，并让
queue/install entrypoints 在使用已安装副本前消费 doctor 证据。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 普通 pack check | `checks/check_workflow.py:463-500` | CLI 只有 repo/spec 选择；`main()` 总是校验 repo lock，但没有 installed-skill opt-in 或 target 参数。 | 新增显式 doctor flags，并确保未启用时不解析安装 target。 |
| spec packet validator | `checks/check_workflow.py:260-341` | product/tech 被校验后仍无条件要求 `tasks.md`。 | 解释本轮为何不能用旧 `--spec-dir/--all-specs` 获得全绿，也不能提前创建 tasks。 |
| repo lock validator | `checks/specrail_lib.py:559-655` | `_sha256_file` 与 `validate_skills_lock` 只读取 repo 内 `skills/<name>/SKILL.md`，并聚合 lock 结构/frontmatter/hash 错误。 | installed validator 必须复用此信任前提，并增加 target 解析与逐项状态。 |
| path safety primitive | `checks/specrail_lib.py:369-401` | `resolve_path` 可解析现存前缀和缺失后缀；`resolve_repo_path` 拒绝 repo escape。 | installed path 检查复用相同 fail-closed 思路，但以 resolved target root 为边界。 |
| installer target | `tools/install_codex_skills.py:35-58` | `default_codex_skills_dir` 在 installer 内独占 `CODEX_HOME`/home 解析；installer 再次读取 lock。 | 把 target resolution 提取为共享 helper，避免 doctor 与 installer 漂移。 |
| installer write/verify | `tools/install_codex_skills.py:72-100` | 无 `--apply` 时只列计划；apply 时替换 skill 目录并在写后核对 hash。 | 保留写路径和授权边界；doctor 只读且不能调用此路径。 |
| installer CLI | `tools/install_codex_skills.py:104-146` | `--target-dir` override 已存在，默认 dry-run，输出明确 target。 | shared resolver 接入后保持现有 CLI 兼容。 |
| installer tests | `tests/test_install_codex_skills.py:51-106` | 覆盖 dry-run 无写入、apply sync 与 unsafe source target。 | 扩展 target precedence/共享 resolver 回归，保留已有断言。 |
| pack-check tests | `tests/test_check_workflow.py:24-38`, `tests/test_check_workflow.py:262-273` | 已测试 required assets 与 main 的普通成功路径，尚无安装目录状态矩阵。 | 增加普通 check 隔离测试和显式 doctor 正反例。 |
| install entrypoint | `skills/specrail-install/SKILL.md:11-51` | 已有 `doctor` route，但只运行 installer dry-run + 普通 pack check；安装后 hash 核对仍是自然语言要求。 | 改为先运行显式 installed check，并按结果控制报告/修复建议。 |
| queue entrypoint | `skills/specrail-implement-queue/SKILL.md:11-37` | startup 读取 repo contract、remote truth 与 skip labels，但不验证当前加载的安装副本。 | 在任何 implementation lane 前加入 doctor preflight 和 fail-closed 分支。 |
| 用户文档 | `AGENT_USAGE.md:61-81`, `README.md:210-237` | 只说明 preview/apply 与 restart 提示，没有独立 runtime integrity 命令或状态语义。 | 记录显式 doctor、无写入边界、skip 与 failure 的区别。 |
| lock entry | `skills-lock.json:31-33` | `specrail-install` 自身被 lock；queue skill 也在同一 lock 中。 | 修改两个 entrypoint 后必须刷新对应 `computedHash`。 |
| 外部 label 边界 | `AGENT_USAGE.md:296-305` | 当前明确没有 automatic issue label checks。 | `parked` provisioning 作为独立依赖，不由本 doctor 假装解决。 |
| route artifact ownership | `workflow.yaml:69-112` | `write_spec` 创建 product/tech；`implement` 才创建 task plan。 | 本轮只提交 product/tech，并把完整 packet 验证标记为 blocked by GH180。 |

## 设计方案

### 1. 共享 target resolution

在 `checks/specrail_lib.py` 增加纯函数式 target resolver，输入为可选显式
target、environment mapping 与 home path，输出：

```text
InstalledSkillsTarget(path, source)
source = explicit | CODEX_HOME | default_home
```

优先级严格为 explicit → `CODEX_HOME/skills` → `<home>/.codex/skills`。
helper 不读取文件、不创建目录；调用方显式传入 environment/home，使测试
不修改真实进程环境或用户目录。

`tools/install_codex_skills.py` 删除私有的 target 解析重复实现，继续通过
现有 `--target-dir` 把 explicit 值传给共享 helper。其 dry-run/apply 分支、
复制范围、unsafe overlap 拒绝和写后 hash 校验保持不变。

### 2. installed-skill status model

在 `checks/specrail_lib.py` 增加只读结果类型：

```text
InstalledSkillRecord(
  name,
  status = match | drift | missing,
  expected_hash,
  actual_hash,
  path,
)

InstalledSkillsReport(
  decision = passed | failed | skipped,
  reason = all_match | runtime_mismatch | invalid_lock
           | unsafe_path | read_error | not_installed,
  target,
  target_source,
  locked_count,
  match_count,
  drift_count,
  missing_count,
  records,
  errors,
)
```

先运行现有 `validate_skills_lock(repo)`；有任何 repo/lock 错误时返回
`decision=failed, reason=invalid_lock`，不扫描 target。target root 不存在
时返回 `decision=skipped, reason=not_installed`，records 为空。target root
存在时按 lock 顺序检查全部条目：

1. 计算 lexical path `<target>/<name>/SKILL.md`；
2. 解析 target root 与 candidate；
3. candidate 必须保留该 lexical identity 并位于 resolved root 内；
4. 普通文件缺失记 `missing`；
5. 读取 bytes 一次并计算 `sha256:` digest；
6. hash 相等记 `match`，否则记 `drift`；
7. 路径逃逸、非普通文件、权限/读取错误进入 errors 并使总结果失败。

不接受“从 repo 回退读取”或“只比较存在项”。并发 install 若暴露 missing、
读取错误或 drift，会得到失败；下一次完整重跑再重新判断。

### 3. 显式 CLI 边界

`checks/check_workflow.py` 新增：

```sh
python3 checks/check_workflow.py --repo . --check-installed-skills
python3 checks/check_workflow.py --repo . \
  --check-installed-skills \
  --installed-skills-dir /explicit/target
```

- 没有 `--check-installed-skills`：不得调用 resolver/validator，保持当前
  pack/CI 行为。
- `--installed-skills-dir` 只能与 `--check-installed-skills` 同用。
- `match`：打印逐项记录与 summary，整体可成功。
- `not_installed`：打印 `status=not_installed`, `skipped=true` 与 target
  来源；不作为 pack error，但成功行不得写成“installed skills passed”。
- drift/missing/invalid/unsafe/read error：加入现有 errors 聚合，非零退出，
  同时保留全部 records 与 summary。

稳定文本字段为 `decision`、`reason`、`status`、`name`、`expected`、
`actual`、`path`、`target`、`target_source`、`locked`、`match`、
`drift`、`missing`、`skipped`。记录按 lock 顺序，errors 按记录顺序，
便于测试和审计。

### 4. entrypoint 消费

`specrail-install`：

1. `doctor` 先运行普通 pack check，再显式运行 installed check；
2. `match` 才能报告磁盘副本一致；
3. `not_installed` 报告未安装；
4. drift/missing 先报告完整证据，再展示 installer dry-run；
5. 只有当前用户明确授权才运行 `--apply`；
6. apply 后重跑 doctor，并保留 active-session restart 提示。

`specrail-implement-queue`：

1. startup 在 fetch/mapping/lane 之前运行显式 installed check；
2. 当前从 installed copy 启动且结果非 `match` 时，停止并写入
   `human_decisions`，不得打开 lane；
3. `not_installed` 只能说明没有安装副本；若从 repo-distributed skill
   运行，必须明确记录 `runtime_source: repo`，不得声称 installed verified。

两个 skill 变更后刷新 `skills-lock.json`。README、AGENT_USAGE 与 CHANGELOG
同步命令、状态语义和授权边界。

### 5. `parked` 依赖

本实现不修改 `labels.yaml`、GitHub labels 或 provisioning 工具。doctor
的成功范围仅为“locked SKILL.md 磁盘一致”。在独立的 `parked` label
contract/provisioning 工作完成前，queue 必须继续报告该外部依赖，不能把
GH157 circuit breaker 宣称为端到端 operational。

### 6. GH180 生命周期阻塞

当前 `workflow.yaml` 正确声明 `write_spec` 只创建 product/tech，但
`validate_spec_packet` 仍无条件要求 tasks。本分支不得创建
`specs/GH172/tasks.md`。在 #180 / PR #181 的 staged-packet 实现合并前：

- depth audit、manifest 解析、普通 pack check 与 diff check 可以运行；
- `check_workflow --spec-dir specs/GH172` / `--all-specs` 预期只因
  `missing tasks.md` 失败；
- 不得把该预期失败改成测试豁免、提前 tasks 或伪造
  `ready_to_implement`。

GH172 的后续 implementation 还与 GH180 的 `checks/check_workflow.py`、
`skills-lock.json`、queue skill 和测试路径重叠；必须等待 GH180
implementation 合并，基于新 main 重取锚点、重跑 duplicate evidence 与
implement route gate 后再开始，不得从当前 base 并行实现。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 普通 pack check 不读安装目录 | `checks/check_workflow.py` opt-in 分支 | `pytest -q tests/test_check_workflow.py -k ordinary_check_ignores_installed_state` |
| B-002 target precedence | shared resolver + installer integration | `pytest -q tests/test_install_codex_skills.py -k target_precedence` |
| B-003 target/source 明示 | installed report renderer | `pytest -q tests/test_check_workflow.py -k installed_target_source` |
| B-004 root 缺失显式 skip | installed validator + CLI | `pytest -q tests/test_check_workflow.py -k installed_root_absent` |
| B-005 每个 lock 条目闭集状态 | installed validator | `pytest -q tests/test_check_workflow.py -k installed_records_cover_lock` |
| B-006 聚合全部 drift/missing | CLI errors aggregation | `pytest -q tests/test_check_workflow.py -k installed_reports_all_failures` |
| B-007 全匹配才成功 | installed validator + CLI | `pytest -q tests/test_check_workflow.py -k installed_all_match` |
| B-008 present root 缺项失败 | installed validator | `pytest -q tests/test_check_workflow.py -k installed_present_but_missing` |
| B-009 无效 repo lock 先失败 | existing lock validator + doctor ordering | `pytest -q tests/test_check_workflow.py -k installed_invalid_lock` |
| B-010 symlink/path escape 拒绝 | installed path resolver | `pytest -q tests/test_check_workflow.py -k installed_symlink_escape` |
| B-011 doctor 全状态无写入 | CLI integration tests | `pytest -q tests/test_check_workflow.py -k installed_no_write` |
| B-012 重复运行幂等 | report ordering | `pytest -q tests/test_check_workflow.py -k installed_idempotent` |
| B-013 并发替换 fail closed | read-error/replacement test double | `pytest -q tests/test_check_workflow.py -k installed_concurrent_replace` |
| B-014 queue 只接受 match 声明 | `skills/specrail-implement-queue/SKILL.md` + lock | `rg -n \"check-installed-skills|not_installed|runtime_source\" skills/specrail-implement-queue/SKILL.md && python3 checks/check_workflow.py --repo .` |
| B-015 install route 不自动 apply | `skills/specrail-install/SKILL.md` + installer | `pytest -q tests/test_install_codex_skills.py -k \"dry_run or apply\"` 并人工核对 doctor 分支 |
| B-016 summary 计数完整 | report renderer | `pytest -q tests/test_check_workflow.py -k installed_summary_counts` |
| B-017 active session restart 提示 | install skill + README/AGENT_USAGE | `rg -n \"restart|重启\" skills/specrail-install/SKILL.md AGENT_USAGE.md README.md` |
| B-018 match 不越权证明 parked | queue/install docs | `rg -n \"parked|operational|依赖\" skills/specrail-implement-queue/SKILL.md skills/specrail-install/SKILL.md AGENT_USAGE.md` |
| B-019 installer CLI 兼容 | installer + existing tests | `pytest -q tests/test_install_codex_skills.py` |
| B-020 中断无 partial 标记 | stateless validator + no-write tests | `pytest -q tests/test_check_workflow.py -k \"installed_no_write or installed_idempotent\"` |

## 数据流

```text
explicit CLI target? ─┐
CODEX_HOME? ──────────┼─> shared target resolver ─> target + source
home ─────────────────┘

repo/skills-lock.json
  └─> validate_skills_lock(repo)
        ├─ invalid ─> failed report; target is not scanned
        └─ valid ─> ordered locked entries
                     + resolved target
                     └─> per-entry path guard + byte hash
                           └─> records + counts + summary + exit decision
```

无持久化、无网络调用、无 installer 调用。GitHub label availability 不进入
该数据流，只作为 queue 的独立外部依赖报告。

## 备选方案

- 普通 `check_workflow` 默认读取 `$HOME`：拒绝。它会让同一 commit 在 CI、
  新用户机器和开发者机器上得到不同结果，并迫使开发者在 spec/skill PR
  尚未合并时安装工作副本。
- 只在 `install_codex_skills.py --apply` 后校验：拒绝。这正是当前缺口，
  无法发现安装后漂移。
- CI 自动安装到用户机器：拒绝。CI 无该机器权限，也违反显式安装授权。
- 新增独立网络服务或后台 watcher：拒绝。超出只读 doctor 范围，并引入
  长期状态与权限面。
- 将 `parked` label provisioning 合入本 PR：拒绝。它属于 GitHub adoption
  / label contract，必须独立授权和验证。

## 风险

- Security: installed paths 可能含 symlink 或权限异常；candidate 必须留在
  resolved target root 内，任何逃逸/读取错误 fail closed。doctor 不写入
  target，也不执行 skill 内容。
- Compatibility: 普通 pack check 与 installer CLI 保持原行为；只有显式
  doctor 增加本机状态。旧自动化无需新增 flags。
- Performance: 只读取 lock 中 14 个 `SKILL.md` 并各 hash 一次，成本线性且
  有界；不递归扫描整个 skills root。
- Maintenance: resolver 必须单一真源；修改两个 locked skill 后必须刷新
  lock。稳定输出字段形成新 CLI contract，后续改名需显式迁移。
- Race: concurrent apply 可能暴露瞬时 missing/drift；允许保守失败，不允许
  false match。操作者在安装完成后重跑 doctor。
- Lifecycle: #180 未实现前，合法 staged packet 会被旧 validator 判缺
  `tasks.md`；本 PR 只能局部验证并保持阻塞可见。

## 测试计划

- [ ] Unit tests:
  - shared resolver 的 explicit / `CODEX_HOME` / default home precedence；
  - root absent、present-empty、单/多 drift、全部 match、无效 lock；
  - unsafe descendant symlink、读取错误、并发替换、稳定排序和 summary；
  - no-write 与 idempotency。
- [ ] Integration tests:
  - 普通 `check_workflow` 在不同 installed fixtures 下结果不变；
  - 显式 doctor 的退出码、全部记录和 stable fields；
  - installer 继续通过 dry-run、apply sync、unsafe overlap 全套测试；
  - queue/install skill 与 lock hash 同步。
- [ ] Manual verification:
  - 对临时 target 运行显式 doctor，确认不创建不存在的 root；
  - 对 copy fixture 改动一个字节，确认只读 doctor 列出 drift 且非零；
  - 仅在另行获得安装授权时才可对真实 `~/.codex/skills` 执行 apply；
  - apply 后重跑 doctor并重启新会话验证实际加载，不能由本 spec PR执行。
- [ ] Repository checks after implementation:
  - `python3 -m pytest -q`
  - `python3 checks/check_workflow.py --repo . --all-specs`
  - `git diff --check`

当前 spec-only 分支可运行：

- `python3 tools/spec_depth_audit.py --spec-dir specs/GH172 --gate`
- manifest JSON/issue/path/spec_ref 静态解析
- `python3 checks/check_workflow.py --repo .`
- `git diff --check`

当前预期阻塞：

- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH172`
- `python3 checks/check_workflow.py --repo . --all-specs`

两条只应报告 `specs/GH172: missing tasks.md`；解除条件是 #180 / PR #181
的 staged-packet lifecycle 实现先合并，而不是本分支提前新增 tasks。

## 回滚方案

回滚 installed report/helper、check_workflow flags、两个 skill entrypoint 文案
及文档，再把 installer target resolution 恢复为当前私有实现，同时恢复
对应 `skills-lock.json` hash。回滚不触碰已安装目录，也不删除用户 skill；
普通 pack check 从始至终保持仓库内确定性。
