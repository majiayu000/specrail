# Product Spec

## Linked Issue

GH-174

## 用户问题

`specrail-implement-queue/SKILL.md` 当前为 799 行、40,985 bytes，是 implx
运行中最大的 Skill 注入源。它同时承载入口合同、阶段细节、证据说明和恢复示例，
导致 agent 为确认某一阶段规则而整篇重读。简单拆文件又会引入漏读、引用漂移或
“主文件与引用互相冲突”的新风险。

用户需要一个小而完整的主入口，以及确定性的按阶段引用机制；未加载引用时也不能绕过
readiness、review、authorization、merge 或 fail-closed 合同。

## 目标

- 将 queue 主 Skill 收缩到不超过 500 行且不超过 28 KiB。
- 在主文件保留所有运行时关键合同和 phase-to-reference 路由。
- 将阶段细节移到单层、受锁定、按需加载的引用文件。
- 用确定性检查保证引用闭集、路径安全、无循环、无冲突并可安装。

## 非目标

- 不改变 queue 的 readiness、route、review、authorization、merge 或 fail-closed 语义。
- 不读取原始 Codex session JSONL，也不承诺固定 token 降幅或读取次数。
- 不修改 GH-160 的 context budget 行为。
- 不在 GH-172 合并前修改 queue、installer、doctor 或 `skills-lock.json`。

## Behavior Invariants

1. B-001 当 agent 加载 queue Skill 时，主 `SKILL.md` 必须不超过 500 行且不超过
   28 KiB；任一上限超出均使 pack check 失败。
2. B-002 当 agent 只读取主文件时，仍必须看到 Startup、skip labels、Done-When、
   Same-Issue Circuit Breaker、停止条件、reviewer lane、authorization、merge gate
   和 fail-closed 的不可绕过摘要。
3. B-003 当某一 queue phase 需要详细步骤时，主文件必须通过稳定 phase ID 将该阶段
   映射到且只映射到一个或多个明确相对引用路径。
4. B-004 当 phase 未发生时，agent 不得被要求预读该 phase 的引用；当 phase 发生时，
   必须在执行该阶段首个动作前加载全部映射引用。
5. B-005 当引用文件缺失、未锁定、hash 漂移、非普通文件、符号链接或路径逃逸时，
   workflow/installed doctor/queue preflight 必须 fail closed，不能 warning 后继续。
6. B-006 当 queue Skill 目录新增、删除或修改引用时，GH-172 定义的 lock、installer
   与 installed doctor 必须消费同一完整文件闭集。
7. B-007 当引用 A 指向引用 B、指回主文件或形成任何多跳/循环图时，确定性引用检查
   必须拒绝；所有引用只能由主文件一跳到达。
8. B-008 当主文件声明未知 phase、重复 phase、重复路径、空路由或未使用引用时，
   检查必须一次报告全部缺陷并稳定排序。
9. B-009 当主文件与引用出现冲突的 normative contract 时，检查必须失败；引用不得
   放宽主文件的 MUST/禁止项或声明自己具有更高优先级。
10. B-010 当现有 queue 行为测试运行时，拆分前的 readiness、planning、review、
    CI、authorization、merge、checkpoint 与 rejection 语义必须保持通过。
11. B-011 当 queue/implx 入口引用已拆分资产时，入口不得递归整篇重读 queue 主文件；
    compaction/resume 只重读主文件与当前 phase 的引用。
12. B-012 当相同仓库重复运行引用图校验时，phase 路由、错误顺序、hash 与退出码必须一致。
13. B-013 当安装目标不存在时，doctor 按 GH-172 返回 not-installed；当目标存在但
    任一引用缺失时，必须是完整性失败而非 skipped。
14. B-014 当安装 apply 在复制过程中失败或被取消时，不得报告成功；post-check 必须
    覆盖主文件与每个引用。
15. B-015 当 GH-182 等后续 issue 修改等待合同时，`wait-contract-v1` 语义必须在
    拆分后仍有唯一规范位置并由主入口路由，不得因移动而失去静态校验。
16. B-016 当合并后观测真实运行指标时，读取次数/token 注入仅作为独立观测；结构、
    完整性与行为门禁全绿即可完成本 issue。

## 验收标准

- [ ] 主 Skill 同时满足 ≤500 行与 ≤28 KiB。
- [ ] 关键运行合同全部保留在主文件，阶段细节按稳定 phase ID 一跳加载。
- [ ] 引用图检查拒绝缺失、未锁定、漂移、越界、循环、未使用与冲突引用。
- [ ] lock、installer、installed doctor 对多文件闭集语义一致。
- [ ] 现有行为测试与全量测试全绿，且不含 GH-160 diff。
- [ ] 合并后的真实注入指标单独记录，不作为关闭硬门。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-005 B-008 B-013 |
| 错误与失败路径 | covered: B-005 B-008 B-009 B-014 |
| 授权/权限 | covered: B-002 B-009 B-010 |
| 并发/竞态 | covered: B-014 |
| 重试/幂等 | covered: B-011 B-012 B-014 |
| 非法状态转换 | covered: B-004 B-005 B-010 |
| 兼容/迁移 | covered: B-002 B-006 B-010 B-015 |
| 降级/回退 | covered: B-005 B-009 B-013 B-014 |
| 证据与审计完整性 | covered: B-006 B-008 B-012 B-016 |
| 取消/中断 | covered: B-014 |

## 发布说明

queue 的入口和行为保持不变，详细规则改为按 phase 一跳加载。安装旧单文件副本的用户
必须在 GH-172 多文件完整性能力可用后显式更新；活动会话可能需要重启。真实 token
改善作为合并后观测，不替代结构和行为验证。
