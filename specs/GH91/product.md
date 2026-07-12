# Product Spec

## Linked Issue

GH-91

## 用户问题

SpecRail 允许消费仓库在 `workflow.yaml` 的 `artifacts` 中声明 spec packet
位置，但 `check_workflow.py --all-specs`、GitHub issue evidence 和 route gate
验证提示仍固定使用 `specs/GH<number>`。采用 `docs/specs/GH<number>` 的仓库会
得到互相矛盾的结果：配置看似有效，运行时却漏检或指向不存在的文件。

## 目标

- 让 spec packet 发现、issue evidence 和 route gate 命令服从同一 artifact contract。
- 保持默认 pack 的 `specs/GH<number>` 行为兼容。
- 对缺失、不可发现或逃逸仓库的 spec packet template 明确失败。

## 非目标

- 不迁移消费仓库已有 spec 文件。
- 不改变 readiness label、human gate、merge 或 authorization 语义。
- 不增加网络写入或自动化 label 行为。
- 不把任意目录结构放宽为 spec packet；packet 目录仍必须是 `GH<number>`。

## Behavior Invariants

1. B-001 `--all-specs` 必须从 `workflow.yaml` 的 `artifacts.spec_packet` 推导
   packet 父目录，并按数字顺序发现其中所有 `GH<number>` 目录。
2. B-002 显式 `--spec-dir` 继续验证调用方给出的目录，且与 `--all-specs`
   组合时保持去重和排序行为。
3. B-003 `github_issue_evidence.py` 的 CLI 必须从所选 `--repo` pack 渲染
   `product_spec`、`tech_spec` 和 `task_plan`；三者必须位于对应 packet 且保持
   固定文件名，CLI issue 与 GitHub payload issue 必须一致。
4. B-004 route gate 返回的单 packet 验证命令必须使用配置后的
   `artifacts.spec_packet` 路径，并安全 quote repo-controlled 参数。
5. B-005 默认 artifact templates 下，现有发现顺序、evidence 字段和值保持不变。
6. B-006 缺失 `artifacts.spec_packet`、issue-dependent packet parent、渲染后
   目录不是 `GH<number>`、POSIX/Windows 绝对或 drive 路径、反斜杠、`..`、
   resolved symlink 逃逸、packet/file identity 重定向、symlink loop 或未解析
   placeholder 必须 fail closed，不得回退到 `specs/`。
7. B-007 GitHub adapter 仍为只读 collector，offline gates 仍不执行网络写入。
8. B-008 任何配置读取或 artifact 渲染错误必须输出明确错误并返回非零状态。
9. B-009 adopted repo 自有的 schema/template 不得被误判为 SpecRail pack 资产；
   SpecRail 自有资产缺失或非法仍必须失败。

## 验收标准

- [x] `docs/specs/GH{issue_number}/` 配置能通过 `--all-specs` 发现测试。
- [x] 自定义配置的 issue evidence 和 route gate 命令测试通过。
- [x] 默认路径兼容、非法 template 和逃逸路径负例测试通过。
- [x] 消费仓库自有 schema/template coexistence 测试通过。
- [x] focused tests、完整 pytest、pack check、all-specs check 和 diff check 通过。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-006, B-008 |
| 错误与失败路径 | covered: B-006, B-008 |
| 授权/权限 | covered: B-007；不改变现有授权边界 |
| 并发/竞态 | N/A：本变更只做本地确定性配置读取与只读 evidence 采集 |
| 重试/幂等 | covered: B-001, B-005；相同配置重复运行得到相同目录与路径 |
| 非法状态转换 | N/A：不修改状态机 |
| 兼容/迁移 | covered: B-002, B-005 |
| 降级/回退 | covered: B-006；禁止静默回退默认目录 |
| 证据与审计完整性 | covered: B-003, B-004, B-007 |
| 取消/中断 | N/A：命令为一次性本地检查，中断后完整重跑 |

## 发布说明

这是向后兼容的 workflow artifact contract 修复。采用自定义 spec 根目录的仓库
无需迁移文件；升级 pack 后，检查与 evidence 会按已有配置工作。
