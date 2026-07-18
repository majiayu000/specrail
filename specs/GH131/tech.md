# Tech Spec

## Linked Issue

GH-131

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| 自审授权校验 | `checks/runtime_gate_rules.py:159` | `_validate_self_review_authorization` 只要求 `lane_failures` 非空 + scope/marker 非空 | 双 lane 断言在此新增 |
| lane 失败解析 | `checks/runtime_gate_rules.py:66` | `_validate_lane_failures` 已校验 `lane_id` 必填并返回 id 列表 | 复用其字段约定；空白 lane_id 不计数（B-005） |
| merge-ready 调用点 | `checks/runtime_ledger_gate.py:556` | 仅在 merge-ready 证据路径调用自审校验 | B-007 的触发边界由此保证；需向下传 `auth_mode` |
| 契约文本 | `skills/specrail-implement-queue/SKILL.md:496` | Auto-mode exception 段定义"two distinct independent reviewer lanes have failed" | 断言语义的唯一来源，不改文本 |
| 既有回归 | `tests/test_runtime_ledger_review.py:88` | `runtime-self-review-merged-unauthorized.json` fixture 无 `auth_mode`、单条 lane 失败 | B-001 兼容性的直接证据 |

## Proposed Design

- `_validate_self_review_authorization(raw_item, label, errors, *, auth_mode="")` 增加仅关键字参数；结尾新增：`auth_mode` 归一化后等于 `auto` 时，统计 `lane_failures` 中非空白 `lane_id` 的去重数，少于 2 则追加错误（含实际数目）。
- `runtime_ledger_gate.py` 调用点传 `auth_mode=str(data.get("auth_mode") or "")`；归一化（strip + lower）在校验函数内做（B-006）。
- 不改 `_validate_lane_failure_outcome` 的非 merge-ready 早退路径（B-007 非目标边界）。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | 校验函数默认参数 | 既有 `test_runtime_ledger_gate_allows_authorized_self_review_merge` 等全绿 |
| B-002 | 新增 auto 分支 | `test_auto_self_review_blocks_single_lane_failure` |
| B-003 | 同上 | `test_auto_self_review_allows_two_distinct_lane_failures` |
| B-004 | 去重计数 | `test_auto_self_review_blocks_duplicate_lane_ids` |
| B-005 | 非空白过滤 | `test_auto_self_review_ignores_blank_lane_ids` |
| B-006 | 归一化 | `test_auto_self_review_auth_mode_is_case_insensitive` |
| B-007 | 调用点位置不变 | `test_auto_single_lane_failure_non_merge_state_not_gated` |
| B-008 | 错误文案 | `test_auto_self_review_blocks_single_lane_failure`（断言含 found 计数） |

## Data Flow

输入：checkpoint JSON（顶层 `auth_mode`、item 的 `lane_failures[]`/`review.review_source`）→ merge-ready 路径触发校验 → errors 列表 → gate decision。无持久化、无网络。

## Alternatives Considered

- 对 `self_review_authorization.source`/`conversation_marker` 做文本启发式（识别"implx auto"引用）：被否。自由文本判定误报面大，且 #107 已把 auto 例外的结构条件定义为"两条不同 lane 失败"，结构断言即足够（非目标）。
- 把断言放进 `pr_review_contract.py`：被否。契约条件依赖 checkpoint 顶层 `auth_mode`，PR 证据层拿不到该字段。
- 无条件要求两条 lane（含 review 模式）：被否。契约明确允许 review 模式下人工在单条失败后显式授权自审（"fresh explicit self-review authorization after reporting the failure"）。
