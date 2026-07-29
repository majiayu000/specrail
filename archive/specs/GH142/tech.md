# Tech Spec

## Linked Issue

GH-142

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":142,"complete":true,"paths":["tools/spec_depth_audit.py","checks/specrail_lib.py","checks/route_gate.py","tests/test_spec_depth_audit.py","tests/test_route_gate.py","specs/GH5/product.md","specs/GH7/product.md","specs/GH9/product.md","specs/GH13/product.md","specs/GH16/product.md","specs/GH17/product.md","specs/GH18/product.md","specs/GH19/product.md","specs/GH20/product.md","specs/GH22/product.md","specs/GH23/product.md","specs/GH24/product.md","specs/GH28/product.md","specs/GH30/product.md","specs/GH34/product.md","specs/GH35/product.md","specs/GH37/product.md","specs/GH38/product.md","specs/GH39/product.md","specs/GH40/product.md","specs/GH55/product.md","specs/GH57/product.md","specs/GH58/product.md","specs/GH59/product.md","specs/GH60/product.md","specs/GH61/product.md","specs/GH62/product.md","specs/GH63/product.md","specs/GH1/product.md","specs/GH1/tech.md","specs/GH95/product.md","specs/GH95/tech.md","specs/GH97/product.md","specs/GH97/tech.md","specs/GH100/product.md","specs/GH100/tech.md","specs/GH104/product.md","specs/GH104/tech.md","specs/GH106/product.md","specs/GH106/tech.md","specs/GH111/product.md","specs/GH111/tech.md"],"spec_refs":["specs/GH142/product.md","specs/GH142/tech.md"]}
-->

## Product Spec

见 `product.md`。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| trivial 声明先例 | `tools/spec_depth_audit.py:57`、`tools/spec_depth_audit.py:154` | `TRIVIAL_RE` 按行匹配，`is_trivial()` 限定只在 Linked Issue 小节内生效 | `status: legacy` 复用同一模式：`LEGACY_RE` + `is_legacy()`（B-001/B-002） |
| gate 判定 | `tools/spec_depth_audit.py:186`、`tools/spec_depth_audit.py:216` | `gate_failures()` 对 trivial 返回空；`run_gate()` 打印 exempt 名单与 FAIL 行，失败 `SystemExit(1)` | legacy 走同类豁免分支但输出独立名单（B-001/B-003/B-004）；汇总二态计数在 `run_gate()` 末尾追加（B-011） |
| CLI 入口/默认阈值 | `tools/spec_depth_audit.py:238`、`tools/spec_depth_audit.py:41-43` | `main()` 解析参数；默认阈值 8/8/5 | 阈值不变（非目标）；无 `--gate` 路径不动（B-006/B-012） |
| implement 路由 | `checks/route_gate.py:316`、`checks/route_gate.py:125` | `evaluate_route()` 在 `route == "implement"` 分支做 sensitive/duplicate 判定，artifact 齐备即 satisfied | 在该分支新增 legacy 检查：legacy → missing `non_legacy_spec`、decision blocked（B-005/B-007） |
| spec 状态词汇 | `checks/specrail_lib.py:26` | `SPEC_STATUSES` 含 `complete`/`needs_spec` 等闭集，供 runtime ledger 校验 | 闭集不扩：legacy 不是 spec_status 取值，而是 spec 文件属性，映射到"不得 complete、须 needs_spec"（B-005） |
| spec_status 校验 | `checks/runtime_ledger_gate.py:307`、`checks/runtime_ledger_gate.py:488` | `_validate_spec_status()` 校验闭集；terminal state 与 needs_spec/needs_tasks 的组合约束 | 佐证 legacy 不改此处：route_gate 上游阻断后，ledger 侧无需新词汇 |
| spec packet 校验 | `checks/check_workflow.py:260` | `validate_spec_packet()` 校验三件套、issue token、manifest | legacy 追加行不影响任何既有校验项（B-010 追加式） |
| 回归测试 | `tests/test_spec_depth_audit.py:1`、`tests/test_route_gate.py:1` | audit 用单元 + subprocess CLI 风格；route_gate 用 fixture 风格 | legacy 用例分别落在这两个文件 |

## Proposed Design

- `tools/spec_depth_audit.py`：新增 `LEGACY_RE = re.compile(r"^\s*status:\s*legacy\s*$", re.IGNORECASE | re.MULTILINE)` 与 `is_legacy(ptext)`（`section(ptext, ["Linked Issue"])` 内匹配，镜像 `is_trivial` 的小节限定）。`audit_dir()` 记录 dict 增加 `legacy` 键。`gate_failures()` 开头增加 `if record["legacy"]: return []`，且 legacy 优先于 trivial 分类（B-004：先判 legacy 再判 trivial）。`run_gate()` 输出三段：`exempt (complexity: trivial): ...`、`legacy (status: legacy): ...`、FAIL 行；通过时追加二态计数行 `two-state: pass=<n> trivial=<n> legacy=<n> total=<n>`（B-011）。
- `checks/specrail_lib.py`：新增 `spec_is_legacy(repo, config, issue) -> bool`——用 `spec_packet_artifact_paths()` 定位 `product.md`，读取失败抛 `SpecRailError`（B-007），Linked Issue 小节内匹配 `status: legacy`。正则与 audit 侧刻意各自持有（tools/ 不 import checks/，保持 audit 零依赖；两处即容忍，第三处出现时抽公共模块）。
- `checks/route_gate.py`：`evaluate_route()` 的 implement 分支（`route_gate.py:316` 之后）调用 `spec_is_legacy`；legacy 时 `missing.append("non_legacy_spec")`、reasons 加 `spec packet specs/GH<n> is status: legacy; rewrite via write_spec (needs_spec) before implementing`，decision 走既有 missing→blocked 通道。`SpecRailError` 一律 blocked（B-007）。
- Sweep：28 个老区段 spec 的 `product.md` Linked Issue 小节追加一行 `status: legacy`（B-010，追加式）。其中 GH5、GH7、GH9、GH13 为老格式 header（`GitHub issue: \`#N\`` 直接置于标题下方，无 `## Linked Issue` 小节），`section(ptext, ["Linked Issue"])` 对它们返回空串，标记无法被识别；对这 4 个文件在末尾追加最小小节（`## Linked Issue` + `GitHub issue: #<n>` + `status: legacy`，+3 行 0 删除），追加后即为标准 Linked Issue 小节，`is_legacy()` 无需任何解析器改动即可识别。
- Backfill：GH1（补 Boundary Checklist）、GH95（补 invariants）、GH97（补边界+锚点）、GH100/GH104/GH106/GH111（补 invariants+边界+锚点），逐个达到 8/8/5（B-008）。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | `is_legacy` + `gate_failures` 豁免分支 | `test_gate_exempts_legacy_spec_in_legacy_list` |
| B-002 | `is_legacy` 小节限定 | `test_legacy_marker_outside_linked_issue_is_not_exempt`（含负例：文件完全没有 Linked Issue 小节、`status: legacy` 落在正文时不计） |
| B-003 | `run_gate` FAIL 路径（既有） | `test_gate_blocks_shallow_unmarked_spec`（第三态非零退出） |
| B-004 | legacy 先于 trivial 的分类顺序 | `test_legacy_wins_over_trivial_declaration` |
| B-005 | `route_gate.py` implement 分支 + `spec_is_legacy` | `test_implement_blocked_on_legacy_spec_with_non_legacy_spec_missing` |
| B-006 | 无 legacy 声明的原路径 | `python3 -m pytest -q tests/test_route_gate.py tests/test_spec_depth_audit.py`（既有用例全绿） |
| B-007 | `spec_is_legacy` 读取失败抛错 | `test_implement_blocked_when_product_md_unreadable` |
| B-008 | 7 个 backfill spec 文件 | 对每个目录 `python3 tools/spec_depth_audit.py --spec-dir specs/GH<n> --gate` 退出码 0 |
| B-009 | sweep 枚举流程 | 实现 PR 附 `python3 tools/spec_depth_audit.py --repo . --gate 2>&1 \| awk '/^FAIL /{sub(":","",$2); print $2}'` 输出与 28 个标记文件 diff 一致 |
| B-010 | sweep 的 diff 形态 | `git diff --numstat` 显示 24 个 product.md 为 +1/-0、老格式 4 个（GH5/GH7/GH9/GH13）为 +3/-0，全部 0 删除；摘除路径由 B-008 命令约束 |
| B-010（老格式追加小节） | 文件末尾追加的最小 Linked Issue 小节 | `test_legacy_recognized_in_appended_minimal_linked_issue_section`（正例：追加小节后 gate 判 legacy）+ B-002 负例（小节外标记不计） |
| B-011 | `run_gate` 二态计数行 | `test_gate_summary_reports_two_state_counts` |
| B-012 | 非 gate 输出路径 | `test_non_gate_output_unchanged_for_legacy_spec` |

## Data Flow

audit：spec 目录集合 → 逐目录读 `product.md`/`tech.md` → 记录（含 trivial/legacy 标记）→ 表格/汇总 →（`--gate`）exempt/legacy/FAIL 三段 + 二态计数 → 退出码。route_gate：evidence + `specs/GH<n>/product.md` → legacy 判定 → decision JSON。无持久化、无网络调用。

## Alternatives Considered

- 把 legacy 写成 YAML front-matter（`---` 块）：被否。存量 spec 首行是 `# Product Spec`，front-matter 需改写文件头，违背追加式（B-010）；Linked Issue 小节声明已有 `complexity: trivial` 先例与现成解析。
- 扩展 `SPEC_STATUSES` 加 `legacy` 取值：被否。`SPEC_STATUSES`（`checks/specrail_lib.py:26`）是 runtime ledger 的路由闭集，legacy 是 spec 文件的属性而非 issue 的路由状态；在 route_gate 上游阻断即可，闭集不动。
- 全量回填 35 个 FAIL spec：被否。GH5–GH63 的 issue 均已关闭、无开放引用，回填是回溯税且无人消费；GH59 实验已证明深度价值在事前而非事后。
- 全量标 legacy（含 GH95–GH111）：被否。GH95+ 区段与 GH1 仍被当前 gate/queue 工作引用，标 legacy 会把活跃依赖逼进 needs_spec 重写循环。

## Risks and Rollback

- 误标活跃 spec：sweep 集合由枚举命令生成并减去白名单，PR 附证据（B-009）；错标可单文件 revert（+1 行）。
- route_gate 回归：legacy 检查只在 implement 分支追加 missing 项，不触碰既有 sensitive/duplicate 逻辑；B-006 用既有测试全绿兜底。
- 回滚：tooling commit 与 sweep/backfill commit 分开，可分层 revert；摘除 legacy 标记本身不需要代码回滚。
