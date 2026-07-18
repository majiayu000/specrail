# Tech Spec

## Linked Issue

GH-141

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":141,"complete":true,"paths":["checks/rejection_items.py","checks/route_gate.py","checks/review_json_gate.py","checks/pr_review_contract.py","checks/pr_gate.py","tests/test_rejection_items.py","tests/test_route_gate.py","tests/test_review_json_gate.py","tests/test_pr_gate.py"],"spec_refs":["specs/GH141/product.md","specs/GH141/tech.md","specs/GH141/tasks.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| route_gate 结果组装 | `checks/route_gate.py:434` | `evaluate_route()` 返回 dict，`missing`/`reasons` 为自由文本字符串列表（`checks/route_gate.py:159`），已做全量收集但无 id/类别/expected-found | `rejection_items` 在此从收集过程同步构造 |
| route_gate 早退路径 | `checks/route_gate.py:454` | `blocked_result()` 只带 reasons，`missing` 恒为空；config 错误分支 `checks/route_gate.py:170` 同样无结构化条目 | B-010：早退路径也要输出 rejection_items |
| route_gate 退出码 | `checks/route_gate.py:557` | blocked→1，needs_human+required→1，其余 0 | B-007：退出码语义保持不变 |
| review_json_gate 汇总 | `checks/review_json_gate.py:541` | `evaluate_review_gate()` 聚合各 validator 的 reasons/missing，`checks/review_json_gate.py:583` 以 `reasons or missing` 判 blocked，排序去重后输出 | 已是全量枚举，只缺结构化条目与跨轮比对 |
| review_json_gate main | `checks/review_json_gate.py:615` | `--review`/`--diff` 必填；load 失败走 `checks/review_json_gate.py:630` 的单 reason blocked 结果 | `--prior-rejection` 参数与 B-010 同型的单项错误结构化 |
| review contract 汇总 | `checks/pr_review_contract.py:396` | `evaluate_review_contract()` 串行跑 `_github_review_items`/`_thread_items`(`checks/pr_review_contract.py:117`)/`_self_review_items`(`checks/pr_review_contract.py:169`) 等 checker，返回三元组字符串列表 | 三元组是 rejection item 的唯一上游来源；由 pr_gate（`checks/pr_gate.py:261`）消费 |
| 跨轮 prior findings 先例 | `skills/specrail-review-pr/SKILL.md:50` | `resumed`/`diff_only` 轮已有 `prior_findings[]` 状态复核先例 | repeat_rejection 的设计对齐既有跨轮复核心智模型 |

## Proposed Design

- 新增共享模块 `checks/rejection_items.py`：
  - `RejectionItem` 构造函数 `make_item(category, subject, expected, found)`；`item_id = f"{category}:{subject}"`（subject 为确定性 slug，如 artifact 名、evidence 字段路径、checker 规则名），生成时校验四字段非空且 category 属闭集，`expected`/`found` 拒绝空串与占位值（B-002/B-009），违规抛 `RejectionItemError`。
  - `finalize_items(items)`：按 `item_id` 去重（B-004）、按 `item_id` 排序（B-003），返回 list[dict]。
  - `load_prior_rejection(path)`：读取上一轮 payload，缺失/非法/缺 `rejection_items` 时返回一条 `config_error` item（B-006）。
  - `repeat_rejection(current, prior)`：返回 `item_id+expected+found` 三元组完全一致的 item_id 列表（B-005）。
- `checks/route_gate.py`：在现有 `missing.append(...)` / `reasons.append(...)` 各点同步 `items.append(make_item(...))`；`evaluate_route()` 与 `blocked_result()` 的返回 dict 增加 `"rejection_items"`（allowed 时为空数组，B-008/B-010）；`main()` 增加可选 `--prior-rejection`，命中重复时输出 `"repeat_rejection"` 段。
- `checks/review_json_gate.py`：`evaluate_review_gate()` 从既有 reasons/missing 收集点构造 items 并入结果；`main()` 增加 `--prior-rejection`；load 失败分支同样产出单条 `config_error` item。
- `checks/pr_review_contract.py`：`evaluate_review_contract()` 返回值扩展为附带 items（新增第四返回位或伴生函数，保持三元组既有调用不破坏由实现者按 pr_gate 消费面选择）；`checks/pr_gate.py` 将其并入 gate 输出。
- decision 判定、退出码、既有字段的内容与排序全部不动（B-007）；全程只读（B-011），无跨进程状态（B-012）。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | 三个 gate 的收集点全量转 items | `test_rejection_items_enumerate_all_failures`（多缺失 fixture，断言 items 数 == 独立缺陷数） |
| B-002 | `make_item` 校验 | `test_make_item_rejects_bad_category_and_empty_fields` |
| B-003 | `finalize_items` 排序 | `test_rejection_items_deterministic_across_runs`（同输入两次运行输出逐字节一致） |
| B-004 | `finalize_items` 去重 | `test_duplicate_items_deduped_by_id` |
| B-005 | `repeat_rejection` + `--prior-rejection` | `test_repeat_rejection_lists_identical_items` |
| B-006 | `load_prior_rejection` fail-closed | `test_bad_prior_rejection_file_becomes_config_error_item` |
| B-007 | 既有字段不动 | `python3 -m pytest -q tests/test_route_gate.py tests/test_review_json_gate.py tests/test_pr_gate.py`（既有用例零改动全绿） |
| B-008 | allowed 分支 | `test_allowed_result_has_empty_rejection_items` |
| B-009 | `make_item` 占位值拒绝 | `test_placeholder_expected_found_rejected` |
| B-010 | `blocked_result` 与 config 错误分支 | `test_early_exit_paths_emit_structured_items` |
| B-011 | 全程无写文件 | `test_gate_read_only_with_rejection_items`（运行前后仓库快照一致） |
| B-012 | 无状态设计 | `test_rerun_after_interrupt_matches_full_run`（复用 B-003 断言于中断模拟后） |

## Data Flow

输入：gate CLI 参数 + evidence JSON +（可选）上一轮 rejection payload → 各 checker 产出 (satisfied, missing, reasons, items) → `finalize_items` 去重排序 → 结果 dict（新增 `rejection_items`，可选 `repeat_rejection`）→ stdout JSON/human，退出码不变。无持久化、无网络调用。

## Alternatives Considered

- 用自由文本 `missing` 字符串做跨轮 diff：被否。字符串含路径/数值易漂移，无法稳定判定"同一项"，正是 W-02 循环的现状根因。
- 把 repeat_rejection 升级为自动改判 decision（如强制 needs_human）：被否。信号与判定分离，避免改变既有 gate 语义（非目标）；编排方消费信号后自行升级。
- 在 skills 文档层约定清单格式而不动 checks：被否。无机器校验的约定不可执行，07-16 循环已证明。

## Risks

- Security: 无新输入面；`--prior-rejection` 仅读 JSON，沿用既有 `_load_json` 式错误处理。
- Compatibility: 下游若严格校验输出 schema 需容忍新增键；本 repo 内消费方以宽松读取为准，B-007 回归护住既有键。
- Performance: 条目构造为 O(现有 append 数)，可忽略。
- Maintenance: checker 新增失败点时需同步产出 item；`make_item` 的非空校验把遗漏暴露为测试失败而非静默缺项。

## Test Plan

- [ ] Unit tests: `tests/test_rejection_items.py` 覆盖 B-002/B-003/B-004/B-005/B-006/B-009。
- [ ] Integration tests: `tests/test_route_gate.py`、`tests/test_review_json_gate.py`、`tests/test_pr_gate.py` 新增 B-001/B-008/B-010/B-011 用例，既有用例零改动。
- [ ] Manual verification: 构造多缺失 fixture，跑两轮验证"一轮补齐、二轮通过、无重复驳回"。

## Rollback Plan

回滚删除 `checks/rejection_items.py` 与各 gate 的 items 构造/输出行即可；既有字段与退出码从未改动，无数据迁移。
