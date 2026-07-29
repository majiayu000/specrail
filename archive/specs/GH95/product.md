# Product Spec

## Linked Issue

GH-95

complexity: small

## 用户问题

GH91 已让 spec packet 路径服从 `workflow.yaml`，但合并后审计发现三个会破坏
确定性 gate 的遗漏：外部 validator 会执行目标仓库自己的资产 helper、等价的
规范化路径会被 route gate 错误拒绝、配置的 spec root 为普通文件时
`--all-specs` 会错误通过。这些行为使损坏的采用包看起来有效，或让 adapter 产生
的合法 evidence 无法通过 offline gate。

## 目标

- 恢复 pack asset validation 的可信执行边界。
- 让 adapter 与 route gate 对等价 repo-relative POSIX 路径使用同一规范形式。
- 让缺失或非目录的 configured spec root 明确失败。
- 用三个独立负例锁定合并后审计发现的行为。

## 非目标

- 不改变 artifact template、readiness、authorization、merge 或 GitHub 写入语义。
- 不新增 schema、template、workflow state 或 fallback spec root。
- 不接受 `..`、绝对路径、反斜杠或 symlink identity redirect。
- 不扩大 #91 已声明的 configured artifact contract。

## Behavior Invariants

1. B-001 当 validator 的执行 checkout 与 `--repo` 目标不同，pack asset validation
   必须使用执行 checkout 中的可信 helper 逻辑检查目标资产；目标仓库内同名 helper
   不得改变、跳过或替换这些检查。
2. B-002 即使目标仓库 helper 返回空错误，任何 SpecRail-owned schema 或 template
   缺失、不可读或非法时，workflow check 仍必须非零退出并报告对应资产。
3. B-003 route gate 比较 spec artifact evidence 与配置路径前必须使用和
   `spec_packet_artifact_paths` 相同的规范化 repo-relative POSIX 表示；例如
   `./specs/GH95/product.md` 与 `specs/GH95/product.md` 必须视为同一路径，而真实
   不同的路径仍必须阻断。
4. B-004 `--all-specs` 使用的 configured spec root 缺失或不是目录时必须非零退出；
   不得把该状态降级为空 packet 集合或默认 root。
5. B-005 上述失败必须是确定性、可重跑的本地结果，输出明确错误且不泄露
   traceback；默认 `specs/GH<number>` 与合法自定义 root 的现有成功行为保持兼容。
6. B-006 当执行 checkout 自身缺失 `checks/pack_asset_validation.py` 或该模块
   无法加载时，workflow check 必须报告明确的 "cannot load trusted pack asset
   validation" 错误并非零退出；不得静默跳过资产检查或回退到目标仓库 helper。
7. B-007 当 configured spec root 是存在的合法空目录时，`--all-specs` 返回空
   packet 集合并成功——保留"当前没有 spec packet"与"配置根损坏"的语义区分；
   若 root 下发现的 `GH<number>` 条目解析为非目录，或经 symlink 解析到不同
   名称/路径，必须以 `SpecRailError` 失败而不是静默跳过该条目。
8. B-008 路径规范化不得放宽既有约束：当 provided evidence path 含反斜杠、
   绝对路径、Windows 盘符、`..` 上溯或未展开占位符时，必须以明确错误拒绝；
   等价规范化仅接受词法相同 repo-relative POSIX 路径的 `./` 前缀差异。

## 验收标准

- [ ] 外部 `check_workflow.py --repo <target>` 能拒绝被 no-op target helper 掩盖的
      缺失 SpecRail-owned asset。
- [ ] route gate 接受 adapter 对 `./specs/...` 产出的等价规范化路径，并继续拒绝
      非配置路径。
- [ ] `check_workflow.py --all-specs` 拒绝缺失 root 和 regular-file root。
- [ ] focused tests、完整 pytest、pack check、all-specs check 和 diff check 通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-002, B-004, B-006, B-007 |
| 错误与失败路径 | covered: B-002, B-004, B-005, B-006, B-008 |
| 授权/权限 | N/A：只修复本地只读 validator，不改变授权决策 |
| 并发/竞态 | N/A：输入是单次本地文件系统快照 |
| 重试/幂等 | covered: B-005 |
| 非法状态转换 | N/A：不修改 workflow state |
| 兼容/迁移 | covered: B-003, B-005 |
| 降级/回退 | covered: B-001, B-002, B-004 |
| 证据与审计完整性 | covered: B-001, B-002, B-003 |
| 取消/中断 | N/A：命令中断后完整重跑，不保存部分状态 |

## 发布说明

这是 #91 / #92 的 fail-closed 回归修复。消费仓库无需迁移；采用方应固定包含本
修复的精确 commit，并重新运行 workflow、route 和 adoption checks。
