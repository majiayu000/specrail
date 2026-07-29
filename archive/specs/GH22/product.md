# Product Spec

## Linked Issue

GitHub issue: `#22`
status: legacy

## 用户问题

SpecRail 已经持续新增 `specs/GH*` packet，但 CI workflow 仍然手写少数旧 packet。
当新 spec packet 没被加入硬编码列表时，CI 会漏掉 packet 完整性、linked issue token
和 task ID 校验，导致本地手动验证和远端 CI 结果不一致。

## 目标

- 提供 deterministic 的 all-specs validation 入口。
- 让 CI 自动覆盖所有 `specs/GH<number>` packet。
- 避免未来新增 spec packet 时必须同步维护 workflow hardcoded list。

## 非目标

- 不改变 spec packet 的文件格式。
- 不改变 adoption matrix 的独立 evaluator。
- 不扫描非 `specs/GH<number>` 目录。

## Behavior Invariants

1. 当运行 all-specs validation 时，validator 必须发现 repo 中所有 `specs/GH<number>` 目录。
2. 每个被发现的 spec packet 必须经过现有 `validate_spec_packet` 规则。
3. CI workflow 必须使用 all-specs validation，而不是列出固定 GH packet。
4. 当不存在 `specs/` 或不存在 matching packet 时，validator 必须给出稳定、可解释的结果。
5. 单个 `--spec-dir` 验证仍然保持兼容。

## 验收标准

- [ ] `checks/check_workflow.py` 提供 `--all-specs`。
- [ ] `.github/workflows/workflow-check.yml` 使用 `--all-specs`。
- [ ] tests 覆盖 all-specs discovery。
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` 覆盖现有 packet 并通过。

## 边界情况

- `specs/GHabc`、`specs/GH1.tmp` 等非规范目录不能被当作 packet。
- 显式 `--spec-dir` 和 `--all-specs` 可以共同使用时，不应重复校验同一路径。

## 发布说明

CI 将自动验证所有 spec packet；采用者新增 `specs/GH*` 后无需再手动改 workflow。
