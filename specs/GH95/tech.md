# Tech Spec

## Linked Issue

GH-95

## Product Spec

`specs/GH95/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| Pack asset validation dispatch | `checks/check_workflow.py:156-181` | 从 `--repo` 目标动态导入 helper，目标代码可弱化检查 | 需要把 validation 逻辑绑定到执行 checkout |
| Spec root discovery | `checks/check_workflow.py:316-324` | root 非目录时返回空列表 | `--all-specs` 因此把损坏 root 当成功 |
| Artifact path comparison | `checks/route_gate.py:105-112`, `checks/route_gate.py:269-284` | required path 使用 raw renderer，provided evidence 使用规范化路径 | 等价路径字符串不相等时误阻断 |
| Shared path contract | `checks/specrail_lib.py:388-415`, `checks/specrail_lib.py:442-476` | validated helper 已将 artifact 输出为规范化 POSIX path | route gate 应复用现有唯一解释器 |
| Regression coverage | `tests/test_check_workflow.py:301-380`, `tests/test_check_workflow.py:570-615`, `tests/test_route_gate.py:170-205` | 已覆盖 symlink/custom root 与 verification command，未覆盖三个审计负例 | 增加最小 targeted tests |

## 设计方案

### 1. 固定可信 helper 来源

`check_workflow.py` 从自身模块搜索路径导入 `pack_asset_validation` 的
`validate_json_schemas` 与 `validate_template_parity`，然后把 `--repo` 目标路径仅
作为被检查数据传入。保留目标 helper 为 `REQUIRED_FILES`，但不执行它。这样从可信
SpecRail checkout 检查消费仓库时，目标仓库无法通过 no-op helper 自证有效。

该边界与 validator 自身的信任模型一致：调用方负责选择可信的执行 checkout；
`--repo` 只是待验证 pack。若直接执行目标仓库的 validator，则该 checkout 本身仍是
调用方选定的信任根，本修复不声称对已被任意篡改的执行代码提供沙箱。

### 2. 复用规范化 artifact contract

`required_artifact_path` 对 `product_spec`、`tech_spec`、`task_plan` 且 issue 已知时，
从 `spec_packet_artifact_paths(config, issue)` 取路径；provided evidence 则先通过
`validated_repo_relative_path` 规范化，其他 artifact 保留现有 renderer。这使
required/provided 两侧都使用 `PurePosixPath.as_posix()` 结果，并继续经过现有
packet/filename 与 repo-relative 约束。不存在的文件仍由 `artifact_exists`
fail closed。

### 3. 拒绝不可用 spec root

`discover_spec_packet_dirs` 在解析 configured root 后区分：不存在和不是目录均抛出
`SpecRailError`，不返回空列表。合法的空目录仍返回空 packet 集合；这保留“当前没有
spec packet”和“配置根损坏”之间的语义差异。主 CLI 捕获错误并打印无 traceback 的
非零结果。

### 4. 回归测试

- 从 source checkout 运行 validator 指向临时 target；目标 helper no-op 且缺 schema，
  断言 missing asset。
- 使用带 `./` 的完整 spec artifact templates 和 adapter-style normalized evidence，
  断言 implement route 不因路径字符串差异阻断。
- 对 missing root 与 regular-file root 调用 discovery/CLI，断言明确失败。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 trusted helper boundary | `checks/check_workflow.py` import/dispatch | `python3 -m pytest -q tests/test_check_workflow.py -k trusted_pack_asset` |
| B-002 target no-op 不能掩盖缺失资产 | `checks/check_workflow.py`, trusted helper test fixture | `python3 -m pytest -q tests/test_check_workflow.py -k trusted_pack_asset` |
| B-003 normalized evidence path comparison | `checks/route_gate.py` | `python3 -m pytest -q tests/test_route_gate.py -k normalized_configured_artifact` |
| B-004 missing/non-directory root fail closed | `checks/check_workflow.py` discovery | `python3 -m pytest -q tests/test_check_workflow.py -k configured_root_is_unusable` |
| B-005 deterministic compatibility/error output | CLI regression tests and full suite | `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs` |

## 数据流

1. 可信 `check_workflow.py` 加载自身 helper，并读取目标 repo 的 schemas/templates。
2. `workflow.yaml` 经 shared validator 产生规范化 artifact paths；adapter evidence 与
   route gate 使用同一字符串表示。
3. configured root 解析为目标 repo 内 path；缺失/错误类型转为 `SpecRailError`。

没有数据库、持久化或网络写入。GitHub adapter 行为不变。

## 备选方案

- 继续动态导入 target helper 并校验其 hash：拒绝；没有声明的 target-specific hash
  真相，而且 target helper 不应成为自己的信任根。
- 只对 provided path 调用字符串 `lstrip("./")`：拒绝；会创建第二套不完整路径规则。
- 非目录 root 返回空列表并增加 warning：拒绝；deterministic gate 必须 fail closed。

## 风险

- Security: trusted validator checkout 决定检查逻辑；目标 pack 只能提供数据。
- Compatibility: 等价 lexical path 新增成功行为；非法/错误 root 从错误成功改为失败。
- Performance: 只减少一次动态 import，并增加常数级 path/type 检查。
- Maintenance: 复用既有 `spec_packet_artifact_paths`，避免新增 renderer。

## 测试计划

- [ ] Unit tests: 三个 targeted regression tests。
- [ ] Integration tests: source validator 对临时 target 的 no-op helper 场景。
- [ ] Full verification: pytest、pack、all-specs、GH95 packet、compileall、diff check。

## 回滚方案

回滚本 issue 的单个修复 commit 即可。若回滚，必须重新阻断下游采用，因为三个已知
fail-closed 缺口会恢复；不得通过删除负例测试或放宽 gate 来回滚。
