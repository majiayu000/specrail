# Product Spec

## 关联 Issue

GH-160

## 用户问题

SpecRail 已声明 soft、hard、critical 三档 context watermark，但 runtime checkpoint
只记录配置比例，没有记录每回合真实上下文。`runtime_ledger_gate.py` 因而无法区分
健康会话与持续运行在 219K+ token 的会话。一次 24 小时生产 drain 中，头部会话
运行 2,600–3,400 回合、每回合上下文 p50 达 219K，却仍表现为 context budget
正常。

## 目标

- 从 Codex `token_count` telemetry 收集每回合 context 使用量，不暴露原始会话内容。
- 在 checkpoint 中记录 latest、maximum、p50、有效/无效观测数及 runtime context
  window，并由 gate 使用可信分母重新计算比例。
- 达到 soft stop 的第一个 checkpoint 必须结束当前会话并交接到 fresh session；
  不允许只结束 tranche 后在同一高上下文会话继续。
- 保持 GH-137 的 compaction/硬维度预算和 GH-159 的 turn batching 行为。
- 输出 tranche p50，使真实生产 drain 可验证 `<130K` 目标；本地测试不得伪造该结论。

## 非目标

- 不新增平行 gate 或第二种 checkpoint 格式；只扩展既有 `context_budget`。
- 不让 gate 自动发现或读取 Codex session JSONL；collector 只读取显式传入路径。
- 不更改模型 context window、compaction threshold、计费或 Codex token 算法。
- 不把单元测试当成 `<130K` 生产目标已达成的证据。
- 不在本 issue 中完成 #174 所要求的 queue skill 全面压缩；只抽取 GH-160 所需的
  Context Budget 协议，使主 `SKILL.md` 回到硬上限内。

## Behavior Invariants

1. B-001 当 tranche window 内的 `token_count` event 同时包含
   `info.last_token_usage.input_tokens` 与 `info.model_context_window` 时，read-only
   collector 必须从这两个字段生成 context observation；不得重复累加 cached input，
   也不得使用累计 `total_token_usage` 代替当前 context。
2. B-002 同一 tranche 有多个有效 observation 时，telemetry 必须输出 latest、maximum、
   observation count、p50 与 observed model context window；event 顺序和既有
   `tranche_start_offset` 定义观测窗口。偶数样本 p50 使用排序后的 lower median，
   即索引 `(n - 1) // 2`，保证结果始终为整数且跨平台确定。
3. B-003 缺失、null、boolean、非整数、负数或内部不一致的 token 字段必须跳过并计入
   `invalid_context_observation_count`。没有有效 observation 时，latest/max/p50/ratio
   字段必须省略，不能写入可信零；无效计数仍保留为审计证据。
4. B-004 checkpoint `context_budget` 必须记录 telemetry provenance、
   `observed_model_context_window` 与观测值。gate 必须先验证 runtime window 等于
   `window_tokens`，再用该分母重新计算 ratio；不一致、跨 event window 冲突或调用方
   自报 ratio 与重算值不符时均 fail closed。
5. B-005 latest 或 maximum ratio 达到 `soft_stop_ratio` 时，下一个 checkpoint 只能记录
   `handoff` convergence action，且顶层 `status` 必须为 `handoff`。`planning`、
   `running`、`complete`、`blocked` 或 `end_tranche` 都不能授权当前会话继续。
6. B-006 handoff evidence 必须包含时间、触发 observation、非空 `resume_prompt` 与 next
   action；trigger token 必须等于 gate 观测到的 high watermark，防止复用旧 action。
7. B-007 soft stop 以下 convergence evidence 可选；没有声明新 context observation 的
   version 1–3 checkpoint 保持既有判定。只要声明任一新字段，缺失或部分证据就 fail
   closed。
8. B-008 hard stop 继续要求 handoff；critical stop 还必须声明剩余动作仅限 checkpoint
   与 resume instructions。任何 unrelated budget override 都不能降低 context stop。
9. B-009 collector 与 gate 必须 read-only、无网络调用、不返回 raw event，只检查显式
   session path 与 tranche window。
10. B-010 runtime 暴露 `token_count` 时，queue skill 必须在 spawn 新 lane 或开始 broad
    action 前按 collect → checkpoint → gate → converge 顺序执行；达到 soft stop 即结束
    当前会话，即使 Codex Goal 仍为 active。
11. B-011 context telemetry 必须与 GH-137 叠加，不能改变 compaction、wall-clock、
    tool-call、review round、full-test、item-cap 和逐维 override 行为。
12. B-012 collector 可报告 tranche p50，queue runner 可报告 token/PR，但实现 PR 只能
    `Refs #160`。在真实 post-rollout bounded drain 把 p50 与 token/PR 证据附到 issue 前，
    不得声称 `<130K` 已达成，也不得关闭 GH-160。

## 验收标准

- [ ] telemetry fixtures 覆盖合法 `token_count`、latest/max/lower-median p50、offset、
      无效计数、window 冲突及无数据省略。
- [ ] runtime-ledger fixtures 覆盖可信分母相等、ratio 重算、soft/hard/critical handoff、
      stale action 与 legacy compatibility。
- [ ] schema 与中英文 checkpoint template 暴露完整 observation/convergence 字段，
      不增加平行 gate。
- [ ] queue skill 使用可执行的 collect/check/handoff 协议；Context Budget 细节进入
      reference 后，主 `skills/specrail-implement-queue/SKILL.md` 不超过 800 行。
- [ ] targeted tests、完整 Python tests、`python3 checks/check_workflow.py --repo .`
      与 `git diff --check` 全部通过。
- [ ] post-merge owner 运行一次真实 bounded drain；没有样本时 issue 保持 open，状态
      明确为 rollout evidence pending。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-007 |
| 错误与失败路径 | covered: B-003 B-004 B-006 |
| 授权/权限 | covered: B-005 B-008；override 不能授权高上下文继续 |
| 并发/竞态 | covered: B-002 B-004 B-006；event 顺序、window 一致性与 trigger 绑定防止 stale evidence |
| 重试/幂等 | covered: B-002 B-009；同一 snapshot 的收集与 gate 判定确定且只读 |
| 非法状态转换 | covered: B-005 B-006 B-008 |
| 兼容/迁移 | covered: B-007 B-011 |
| 降级/回退 | covered: B-003 B-004 B-007；不可用/冲突 telemetry 不伪装为可信零 |
| 证据与审计完整性 | covered: B-003 B-004 B-006 B-012 |
| 取消/中断 | covered: B-005 B-008 B-010 |

## 发布说明

这是 heavy runtime-ledger contract。先合并 spec PR，再用独立 implementation PR 实现；
implementation PR 使用 `Refs #160`。合并后的首个 bounded drain 负责提供真实
p50/token-per-PR，并在证据附加后再决定是否关闭 issue。
