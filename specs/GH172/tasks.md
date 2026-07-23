# Task Plan

## Linked Issue

GH-172

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP172-T1` Owner: lock-contract | Depends on: approved spec | Done when: 单文件 fixture 零改动通过，多文件 fixture 完整通过，任一集合/路径/哈希缺陷一次性报错 | Verify: `python3 -m pytest -q tests/test_evaluate.py -k skills_lock` | Covers: B-001 B-008 B-014 B-015 B-020 | 扩展共享 lock manifest：在 `checks/specrail_lib.py` 支持每个 skill 可选的目录内 `files[]` 闭集，保持现有 `path`/`computedHash` 单文件条目兼容，拒绝未锁定文件、重复、绝对/越界/反斜线路径、符号链接和非普通文件；在 `tests/test_evaluate.py` 添加正反例。
- [ ] `SP172-T2` Owner: integrity-library | Depends on: SP172-T1 | Done when: 所有状态、混合缺陷、目标优先级、符号链接/逃逸、检查中变化、重复运行与无写入均有测试，新增代码行覆盖率至少 80%，安全路径和决策分支 100% | Verify: `python3 -m pytest -q tests/test_installed_skill_integrity.py` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-016 B-017 B-018 B-019 B-020 | 新增 `checks/installed_skill_integrity.py` 与 `tests/test_installed_skill_integrity.py`：实现 explicit → `$CODEX_HOME/skills` → `~/.codex/skills` 目标解析、逐锁定文件稳定快照、`match | drift | missing | unsafe | unstable` 结果、整体 `match | not_installed | invalid` 聚合、只读/有界输出和稳定排序。
- [ ] `SP172-T3` Owner: doctor-cli | Depends on: SP172-T2 | Done when: 默认 `not_installed` 明确 skipped 且退出 0，`--require-installed` 仅在完整 match 时退出 0，普通 workflow check 不访问目标目录 | Verify: `python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_check_workflow.py -k "installed or required_files"` | Covers: B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-012 B-013 B-017 B-018 B-019 | 新增 `tools/check_installed_codex_skills.py`，提供 `--repo`、`--target-dir`、`--json`、`--require-installed`；将 checker/library 加入 `checks/check_workflow.py` 的 pack required files，但普通 workflow 主流程不得调用 installed inspect；补充 CLI 与 CI-no-home 测试。
- [ ] `SP172-T4` Owner: installer | Depends on: SP172-T1 SP172-T2 | Done when: dry-run 不写，已有 drift/missing 显式非零但打印完整计划，授权 apply 可修复并只在 post-check 全 match 时成功 | Verify: `python3 -m pytest -q tests/test_install_codex_skills.py` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-014 B-015 B-016 B-017 B-019 B-020 | 重构 `tools/install_codex_skills.py` 使用共享 manifest、目标解析和 pre/post integrity inspect；保留 dry-run 默认和显式 `--apply`，apply 后验证所有锁定文件；扩展 `tests/test_install_codex_skills.py` 覆盖未安装、匹配、混合 drift/missing、多文件复制、apply 修复、post-check 失败、source-target 与 no-write。
- [ ] `SP172-T5` Owner: skill-integration | Depends on: SP172-T3 SP172-T4 | Done when: install/queue 两条路径消费同一 checker，不自动 apply，不把 unavailable/drift 降级为 warning，lock 哈希与最终 skill 字节一致 | Verify: `python3 checks/check_workflow.py --repo . && python3 -m pytest -q tests/test_check_workflow.py` | Covers: B-003 B-010 B-011 B-012 B-013 B-018 B-020 | 更新 `skills/specrail-install/SKILL.md`、`skills/implx/SKILL.md` 与 `skills/specrail-implement-queue/SKILL.md`：安装 doctor 使用新 CLI，queue 在 lane/checkpoint/远端写入前要求 `--require-installed` match，checker 缺失或错误 fail closed；同步 `AGENT_USAGE.md`、`CHANGELOG.md` 和三个入口 `computedHash`。

## 并行拆分

- 固定串行顺序 `SP172-T1 → SP172-T2 → SP172-T3/SP172-T4 → SP172-T5`。
- `SP172-T3` 与 `SP172-T4` 在 T1/T2 接口冻结后可并行：T3 独占
  `tools/check_installed_codex_skills.py`、`checks/check_workflow.py`、
  `tests/test_check_workflow.py`；T4 独占 installer 与其测试。
- `SP172-T5` 必须最后串行执行，因为三个 Skill 与 `skills-lock.json` 是共享收口面。
- 任一并行 lane 不得修改另一个 lane 的 writable files；集成 owner 负责最终哈希。

## 验证

- [ ] `SP172-T6` Owner: verification-owner | Depends on: SP172-T1 SP172-T2 SP172-T3 SP172-T4 SP172-T5 | Done when: 所有命令本轮全绿、doctor 前后目标快照相同、无 GH-160 文件进入 diff、所有新增/修改 Python 与 Skill 文件低于 800 行 | Verify: `python3 -m pytest -q tests/test_installed_skill_integrity.py tests/test_install_codex_skills.py tests/test_evaluate.py tests/test_check_workflow.py && python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 tools/spec_depth_audit.py --spec-dir specs/GH172 --gate && git diff --check` | Covers: B-001 B-002 B-003 B-004 B-005 B-006 B-007 B-008 B-009 B-010 B-011 B-012 B-013 B-014 B-015 B-016 B-017 B-018 B-019 B-020 | 在 exact head 运行 focused、full 和 pack checks，并做只读安全复核。

## Handoff Notes

- 当前 issue 只有 `ready_to_spec`；本 spec PR 合并并由维护者切换到
  `ready_to_implement` 前，不得执行以上实现任务。
- 实现 manifest 严格限定 tech spec 声明的 15 个路径；不得修改 GH-160、自动安装本机
  skill、重启会话、创建标签或把 doctor 结果写成 checkpoint。
- GH-174 依赖本 issue 的多文件 lock/installer/doctor 合同；GH-172 合并前不得并行修改
  `skills/specrail-implement-queue` 或 `skills-lock.json`。
- 本 issue 只验证“安装的 Skill 资产是否匹配”；把 runtime gate/checker 作为全局可执行
  依赖分发是后续独立 issue，不得在实现时偷偷扩大范围。
