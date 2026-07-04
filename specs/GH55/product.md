# Product Spec

## Linked Issue

GH-55

## 用户问题

SpecRail 队列执行中,同一 issue 会被并发会话或重试会话重复领取并重复开
PR,维护者需要人工识别并关闭重复方。真实样本:vibeguard #558 重复 #557、
#563 重复 #562,均为同一天同一功能的重复 PR。

根因是流程里缺少两个确定性构件:

1. `implement` 路由 gate 只校验状态标签与 spec 三件套,开工前没有任何
   检查回答"该 issue 是否已有 open PR 或在途分支"。
2. `workflow.yaml` 没有分支命名契约,分支名是自由文本,无法从分支反查
   某个 issue 是否已被领取。

## 目标

- 开工前存在一个确定性查重 gate:给定 open PR 与远端分支证据,重复即
  `blocked`,证据缺失即 `needs_human`,干净即 `allowed`。
- `workflow.yaml` 声明实现分支命名契约,使"该 issue 已有在途分支"成为
  一次机械模式匹配。
- `implement` 路由消费查重结论,重复工作在开工前而非 review 阶段被拦截。

## 非目标

- 不引入远端写操作、分布式锁或 GitHub 状态变更;gate 保持离线只读评估。
- 不解决标签回写与跨会话 checkpoint 对账(另行立项)。
- 不改变 `implement` 路由对 spec 三件套与 readiness 标签的现有要求。
- 不强制迁移或重命名历史分支。

## Behavior Invariants

1. 证据显示存在引用 `GH-N` 的 open PR 时,查重 gate 对 issue N 的
   `implement` 决策为 `blocked`,且 reasons 中列出重复 PR 编号。
2. 证据显示存在匹配分支契约 `gh{N}` 前缀的远端分支(且无对应 open PR)
   时,决策为 `needs_human`,由人裁决是接管分支还是废弃。
3. 证据文件缺失或格式非法时,决策为 `needs_human`/`blocked`(格式非法为
   `blocked`),绝不静默放行。
4. 证据干净时决策为 `allowed`,`implement` 路由行为与现状一致。
5. gate 全程无网络调用;证据采集与评估分离,与 `pr_gate.py` 同构。

## 验收标准

- [ ] `checks/duplicate_work_gate.py` 对 blocked/needs_human/allowed 三类
      证据给出上述决策,并有对应测试。
- [ ] `workflow.yaml` 含 `impl_branch` 模板且 `check_workflow.py` 校验
      占位符,缺失即 fail。
- [ ] 证据 JSON 有 `schemas/duplicate_work_evidence.schema.json` 且通过
      `validate_json_schemas`。
- [ ] `python3 -m pytest -q` 全绿。
