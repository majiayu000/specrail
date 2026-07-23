# Product Spec

## Linked Issue

GH-188

## 用户问题

queue 要求在 adopted repo 执行 `checks/runtime_ledger_gate.py`，但 adoption/Skill
安装不分发该 checker 的依赖闭集。目标仓库缺文件时，最新 runtime 合同实际上无法执行。

## 目标

- 定义可版本化、可哈希的 consumer runtime enforcement bundle。
- 提供只读 doctor 与 dry-run-first adoption installer。
- queue 在 lane/checkpoint/远端写前验证 bundle 完整匹配。

## 非目标

- 不自动写 consumer repo、HOME 或 GitHub。
- 不替代 GH-165 unavailable gate 或 GH-172 installed Skill integrity。
- 不处理 GH-160。

## Behavior Invariants

1. B-001 当构建 bundle 时，manifest 必须闭集列出 checker、Python 依赖、schema、
   template 与每个内容哈希。
2. B-002 当文件缺失、额外、漂移、重复、符号链接或路径逃逸时，validator 必须失败。
3. B-003 当显式 consumer target 未采用 bundle 时，doctor 必须返回 `not_adopted`，
   不得冒充 match。
4. B-004 当 target 存在但任一资产缺失/漂移时，doctor 必须一次报告全部缺陷并非零退出。
5. B-005 当且仅当闭集全部安全且 hash 匹配时，doctor 才返回 match。
6. B-006 当 installer 未收到 `--apply` 时，只显示完整计划且不得写文件。
7. B-007 当 apply 被授权时，只能写 manifest 声明路径，并在写后重新 doctor；post-check
   非 match 不得成功。
8. B-008 当 source/target 重叠、权限失败、检查中变化或取消时，必须 fail closed 且
   不声明采用完成。
9. B-009 当 queue 启动时，bundle unavailable/not_adopted/drift/error 必须在 lane、
   checkpoint 与 remote write 前阻断。
10. B-010 当普通 SpecRail pack CI 运行时，不得访问真实 consumer 或 HOME。
11. B-011 当 bundle 版本升级时，旧 consumer 必须报告 version drift 并通过显式
    dry-run/apply 迁移，不得从其他 checkout fallback。
12. B-012 当静态输入不变时，doctor/manifest 输出、顺序和退出码必须稳定且不泄露正文、
    secret 或非声明路径。

## 验收标准

- [ ] manifest/doctor/installer 对完整、缺失、漂移、不安全、未采用均有测试。
- [ ] queue preflight fail closed，普通 CI 不读 consumer。
- [ ] 两个临时 consumer 完成 install/upgrade/漂移 forward test。
- [ ] full suite 全绿且不含 GH-160 diff。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-001 B-003 B-004 |
| 错误与失败路径 | covered: B-002 B-004 B-008 B-009 |
| 授权/权限 | covered: B-006 B-007 B-008 |
| 并发/竞态 | covered: B-008 |
| 重试/幂等 | covered: B-007 B-011 B-012 |
| 非法状态转换 | covered: B-003 B-005 B-009 |
| 兼容/迁移 | covered: B-011 |
| 降级/回退 | covered: B-003 B-008 B-009 B-011 |
| 证据与审计完整性 | covered: B-001 B-002 B-005 B-012 |
| 取消/中断 | covered: B-008 |

## 发布说明

adopted repo 可显式安装并验证 runtime bundle；doctor 只读，安装仍需人工 `--apply`。
