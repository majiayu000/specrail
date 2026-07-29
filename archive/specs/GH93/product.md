# Product Spec

## Linked Issue

GH-93

complexity: trivial

## 用户问题

GH-86 把深 spec 方法嵌入 write skills 后,深度是否退化只能靠人工翻阅判断。基线审计与 GH58/GH60/GH62 盲测 A/B 已经用一个临时脚本量化了四项深度指标(invariant 数、EARS 占比、边界覆盖、path:line 锚点),但脚本只存在于会话临时目录,基线数字无法复现。需要把它入库为可复用的回归对比工具。

## 目标

- 任何人可用一条命令复现 spec 深度基线,并对新产出的 spec 做 A/B 对比。

## 非目标

- 不接入 gate/CI 阻断逻辑(深度门禁属 Phase 2,另行立项)。
- 不修改 `checks/`、`workflow.yaml` 的任何行为。
- 指标启发式(正则与 checklist verdict 解析)不追求语义精确,仅在相同 `metric_semantics` 版本内作趋势对比。

## Behavior Invariants

1. B-001 当对仓库运行时,脚本应只读取 `specs/GH*/product.md` 与 `tech.md`,不得写入或修改任何仓库文件。
2. B-002 当传入 `--spec-dir`(可重复)时,脚本应只审计指定目录并忽略 `--repo` 的 glob,使仓库外的 A/B 产物可被同一套指标度量。
3. B-003 若指定目录集合中没有任何含 `product.md` 的目录,脚本应以非零退出并报错,不得输出空汇总冒充结果。

## Acceptance Criteria

- [ ] `python3 tools/spec_depth_audit.py` 输出存量 spec 的逐份明细与汇总(invariant/EARS/边界/锚点)。
- [ ] `python3 tools/spec_depth_audit.py --spec-dir <仓库外目录>` 可正常审计。
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` 与 `python3 -m pytest -q` 通过。

## Boundary Checklist

| Category | Verdict (covered: B-xxx / N/A + reason) |
| --- | --- |
| Empty / missing input | covered: B-003 |
| Error / failure paths | covered: B-003 |
| Authorization / permission | N/A:本地只读脚本,无权限面 |
| Concurrency / race | N/A:单进程只读,无共享可变状态 |
| Retry / idempotency | covered: B-001(只读,重跑天然幂等) |
| Illegal state transitions | N/A:无状态机 |
| Compatibility / migration | N/A:新增文件,不改既有行为 |
| Degradation / fallback | covered: B-003(无数据即报错,不静默输出空表) |
| Evidence / audit integrity | N/A:输出即证据,无持久化 |
| Cancellation / interruption | N/A:秒级只读命令,中断无副作用 |

## Rollout Notes

纯新增开发工具,无迁移;删除该文件即完全回滚。
