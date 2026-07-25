# Task Plan

## Linked Issue

GH-172

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP172-T1` Owner: lock-contract | Depends on: approved spec | Done when: 单文件 fixture（`version: 1`）零改动通过，多文件 fixture（`version: 2`，并有 v1 reader 对其 fail closed 的回归）完整通过；shared manifest 从声明文件路径精确派生 strict parent `structural_directories`，`files[]` 允许目录成分但拒绝目录条目本身；`skills/*/SKILL.md` 的全部顶层分发 skill 都进入 completeness 集合，`implx` 与新增无前缀 fixture 均不能绕过 lock，任一集合/路径/哈希缺陷一次性报错 | Verify: `python3 -m pytest -q tests/test_evaluate.py -k "skills_lock or structural_directories or unprefixed_skill"` | Covers: B-001 B-008 B-014 B-015 B-020 | 扩展共享 lock manifest：在 `checks/specrail_lib.py` 支持每个 skill 可选的目录内 `files[]` 闭集及不可由 caller 注入的 structural parents，保持现有 `path`/`computedHash` 单文件条目兼容；把顶层 discovery 从 `specrail-*` 改为所有直接子目录的普通 `SKILL.md`；拒绝未锁定 skill/file、重复、绝对/越界/反斜线路径、符号链接和非普通文件，并在 `tests/test_evaluate.py` 添加正反例。
- [ ] `SP172-T2` Owner: integrity-library | Depends on: SP172-T1 | Done when: 所有状态（含未声明文件导致的 `undeclared`/`invalid`）、混合缺陷、目标优先级、符号链接/逃逸、检查中变化、重复运行与无写入均有测试；nested locked file 的真实必要父目录被视为 structural entry 而通过，同级 stale/空目录仍为 undeclared；final component 以 `O_NOFOLLOW|O_NONBLOCK` 打开后立即 `fstat`，只有 regular file 才能 hash，symlink swap 与 FIFO/special-file swap 都快速 fail closed 而不阻塞/读取；标准输出固定报告 `undeclared_total`/`undeclared_omitted` 和最多 50 项、8192 UTF-8 bytes 的稳定样本；新增 integrity/CLI 总 branch coverage 至少 80%，其中 integrity library 为 100% | Verify: `python3 -m pip install --disable-pip-version-check coverage==7.15.2 && python3 -m coverage erase && python3 -m coverage run --branch --source=checks.installed_skill_integrity,tools.check_installed_codex_skills -m pytest -q tests/test_installed_skill_integrity.py && python3 -m coverage report --include='checks/installed_skill_integrity.py,tools/check_installed_codex_skills.py' --fail-under=80 && python3 -m coverage report --include='checks/installed_skill_integrity.py' --fail-under=100` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-016 B-017 B-018 B-019 B-020 | 新增 `checks/installed_skill_integrity.py` 与 `tests/test_installed_skill_integrity.py`：实现目标解析、structural-parent-aware namespace enumeration、逐锁定文件 nonblocking no-follow same-fd snapshot、整体聚合、只读/有界输出和稳定排序；测试名包含 `nested_parent`、`fifo_swap`、`symlink_swap` 与 `target_snapshot_no_write`，供 final gate 定点执行。
- [ ] `SP172-T3` Owner: doctor-cli | Depends on: SP172-T2 | Done when: 默认 `not_installed` 明确 skipped 且退出 0，`--require-installed` 仅在完整 match 时退出 0，普通 workflow check 不访问目标目录；只有显式 `--undeclared-artifact <new-file>` 才能以 `0600` create-only 方式导出完整稳定路径清单，拒绝覆盖、安装目标内 artifact 与 queue 使用；新增 CLI 在 branch coverage 模式下至少 80% | Verify: `python3 -m pip install --disable-pip-version-check coverage==7.15.2 && python3 -m coverage erase && python3 -m coverage run --branch --source=checks.installed_skill_integrity,tools.check_installed_codex_skills -m pytest -q tests/test_installed_skill_integrity.py tests/test_check_workflow.py -k "installed or required_files or undeclared_artifact" && python3 -m coverage report --include='tools/check_installed_codex_skills.py' --fail-under=80` | Covers: B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-012 B-013 B-017 B-018 B-019 | 新增 `tools/check_installed_codex_skills.py`，提供 `--repo`、`--target-dir`、`--json`、`--require-installed`、`--undeclared-artifact`；将 checker/library 加入 `checks/check_workflow.py` 的 pack required files，但普通 workflow 主流程不得调用 installed inspect；补充 CLI、bounded-output、artifact 与 CI-no-home 测试。
- [ ] `SP172-T4` Owner: installer | Depends on: SP172-T1 SP172-T2 | Done when: dry-run 不写，已有 drift/missing 显式非零但打印完整计划；授权 apply 只复制 manifest-declared files + derived structural directories，source 逐段 no-follow、final nonblocking open 后 immediate regular-file fstat，并从同一 fd 复制/哈希到 staging；source 在 validation/copy 间换成 symlink/FIFO/special file 或发生 snapshot/hash 变化时，在替换 destination 前失败且不读取/落盘 escape 内容；post-check 全 match 才成功 | Verify: `python3 -m pytest -q tests/test_install_codex_skills.py -k "dry_run or apply or source_race or symlink or fifo or special or post_check"` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-014 B-015 B-016 B-017 B-019 B-020 | 重构 `tools/install_codex_skills.py` 使用 shared manifest/structural parents、目标解析和 pre/post inspect；移除会跟随 source race 的 whole-directory `copytree`，以 verified same-fd staging copy 保留 dry-run 默认与显式 `--apply`；扩展 tests 覆盖多文件复制、source symlink/FIFO race、apply 修复、post-check 失败、source-target 与 no-write。
- [ ] `SP172-T5` Owner: skill-integration | Depends on: SP172-T3 SP172-T4 | Done when: install/queue 两条路径消费同一 checker，且在 installed queue skill 之外增加源侧 bootstrap（`AGENTS.md` Long Queue Guardrails 与 `skills/specrail-workflow/SKILL.md` 路由器在委派给已安装 queue skill 之前先跑 `--require-installed` doctor），不自动 apply，不把 unavailable/drift 降级为 warning，lock 哈希与最终 skill 字节一致 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-003 B-010 B-011 B-012 B-013 B-018 B-020 | 更新 `skills/specrail-install/SKILL.md`、`skills/implx/SKILL.md` 与 `skills/specrail-implement-queue/SKILL.md`：安装 doctor 使用新 CLI，queue 在 lane/checkpoint/远端写入前要求 `--require-installed` match，checker 缺失或错误 fail closed；同步 `AGENT_USAGE.md`、`CHANGELOG.md` 和三个入口 `computedHash`。

## 并行拆分

- 固定串行顺序 `SP172-T1 → SP172-T2 → SP172-T3/SP172-T4 → SP172-T5`。
- `SP172-T3` 与 `SP172-T4` 在 T1/T2 接口冻结后可并行：T3 独占
  `tools/check_installed_codex_skills.py`、`checks/check_workflow.py`、
  `tests/test_check_workflow.py`；T4 独占 installer 与其测试。
- `SP172-T5` 必须最后串行执行，因为三个 Skill 与 `skills-lock.json` 是共享收口面。
- 任一并行 lane 不得修改另一个 lane 的 writable files；集成 owner 负责最终哈希。

## 验证

- [ ] `SP172-T6` Owner: verification-owner | Depends on: SP172-T1 SP172-T2 SP172-T3 SP172-T4 SP172-T5 | Done when: 所有命令本轮全绿；T2 combined/library coverage 与 T3 CLI-only coverage 各自执行并达到 80%/100%/80% 强制阈值；`target_snapshot_no_write` 明确证明 doctor 前后路径/type/mode/mtime_ns/hash 闭合 snapshot 相同；manifest 为 17 个 unique paths 且不含 GH-160，PR diff 也无 `specs/GH160`；manifest 中所有新增/修改 Python 与 Skill 文件严格 `<800` 行 | Verify: `python3 -m pip install --disable-pip-version-check coverage==7.15.2 && python3 -m coverage erase && python3 -m coverage run --branch --source=checks.installed_skill_integrity,tools.check_installed_codex_skills -m pytest -q tests/test_installed_skill_integrity.py && python3 -m coverage report --include='checks/installed_skill_integrity.py,tools/check_installed_codex_skills.py' --fail-under=80 && python3 -m coverage report --include='checks/installed_skill_integrity.py' --fail-under=100 && python3 -m coverage erase && python3 -m coverage run --branch --source=checks.installed_skill_integrity,tools.check_installed_codex_skills -m pytest -q tests/test_installed_skill_integrity.py tests/test_check_workflow.py -k "installed or required_files or undeclared_artifact" && python3 -m coverage report --include='tools/check_installed_codex_skills.py' --fail-under=80 && python3 -m pytest -q tests/test_installed_skill_integrity.py -k "nested_parent or fifo_swap or symlink_swap or target_snapshot_no_write" && python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_install_codex_skills.py tests/test_evaluate.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH172 --gate && sed -n '9p' specs/GH172/tech.md | jq -e '(.paths|length)==17 and (.paths|unique|length)==17 and ([.paths[]|select(startswith("specs/GH160/"))]|length)==0' && test -z "$(git diff --name-only "$(git merge-base HEAD origin/main)"..HEAD -- specs/GH160)" && for path in $(sed -n '9p' specs/GH172/tech.md | jq -r '.paths[]|select(endswith(".py") or endswith("/SKILL.md"))'); do test "$(wc -l < "$path")" -lt 800 || exit 1; done && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 | exact-head final gate 不得以 library coverage 替代 CLI gate，也不得以普通 tests 隐含 no-write/scope/line-count 断言。

## Handoff Notes

- 当前 issue 只有 `ready_to_spec`；本 spec PR 合并并由维护者切换到
  `ready_to_implement` 前，不得执行以上实现任务。
- 实现 manifest 严格限定 tech spec 声明的 17 个路径；不得修改 GH-160、自动安装本机
  skill、重启会话、创建标签或把 doctor 结果写成 checkpoint。
- GH-160 与 GH-174 都依赖本 issue 的多文件 lock/installer/doctor 合同；GH-172 合并前
  两者均不得修改 `skills/specrail-implement-queue` 或 `skills-lock.json`。二者各自实现
  reference 时必须声明该 skill 的完整 `files[]` 并迁移为 v2 lock。
- 本 issue 只验证“安装的 Skill 资产是否匹配”；把 runtime gate/checker 作为全局可执行
  依赖分发是后续独立 issue，不得在实现时偷偷扩大范围。
