# Product Spec

## Linked Issue

GitHub issue: `#17`
status: legacy

## 用户问题

Agent review 目前只有 advisory checklist，缺少可验证的 review artifact。Maintainer 无法稳定判断 comment 是否绑定真实 diff line，也无法自动拒绝越权的 final approval / merge 语言。

## 目标

- 定义 `review_result` JSON artifact。
- 提供本地 `checks/review_json_gate.py`。
- 让 review evidence 可在 PR gate 前独立验证。

## 非目标

- 不自动提交 GitHub review。
- 不自动 approve 或 merge。
- 不替代 human final review。

## Behavior Invariants

1. 有效 review artifact 必须包含 advisory `verdict`、body 和可选 inline comments。
2. 每条 comment 必须指向 diff 中存在的 path/line/side。
3. severity 必须来自固定集合：`critical`、`important`、`suggestion`、`nit`。
4. review body/comment 不得包含授予 final approval 或 merge 权限的语言。
5. spec drift 必须在 `spec_alignment` 或 comments/body 中显式表达，不能静默通过。

## 验收标准

- [ ] 新增 schema、gate、fixtures、tests。
- [ ] gate 输出稳定 decision JSON。
- [ ] docs/review guide 说明 artifact contract。

## 边界情况

- LEFT/RIGHT line 的 diff 语义不同。
- advisory `verdict: APPROVE` 不能等同 human final approval。

## 发布说明

这是本地 artifact validator，可用于 CI 或 agent preflight。
