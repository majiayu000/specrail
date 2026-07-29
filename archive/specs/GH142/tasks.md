# Task Plan

## Linked Issue

GH-142

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Implementation Tasks

- [ ] `SP142-T1` 为 `tools/spec_depth_audit.py` 增加 legacy 态：`LEGACY_RE` + `is_legacy()`（Linked Issue 小节限定，镜像 `is_trivial`）、`gate_failures()` legacy 豁免且优先于 trivial、`run_gate()` 独立 legacy 名单 + 二态计数行；非 gate 输出保持兼容。Covers: B-001 B-002 B-003 B-004 B-011 B-012. Owner: agent. Done when: Product-to-Test Mapping 中 B-001/B-002/B-003/B-004/B-011/B-012 对应测试全部通过且既有用例零回归. Verify: `python3 -m pytest -q tests/test_spec_depth_audit.py` 且 `python3 tools/spec_depth_audit.py --spec-dir specs/GH142 --gate` 退出码 0
- [ ] `SP142-T2` 在 `checks/specrail_lib.py` 新增 `spec_is_legacy()`（读取失败抛 `SpecRailError`），`checks/route_gate.py` implement 分支对 legacy spec 追加 missing `non_legacy_spec` 并给出 needs_spec 重写理由；含 unreadable fail-closed 用例。Covers: B-005 B-006 B-007. Owner: agent. Done when: legacy spec 的 implement 路由判 blocked、非 legacy 路径既有测试全绿. Verify: `python3 -m pytest -q tests/test_route_gate.py tests/test_route_gate_sensitive.py`
- [ ] `SP142-T3` legacy 标记 sweep：目标集合由审计输出机械枚举——`python3 tools/spec_depth_audit.py --repo . --gate 2>&1 | awk '/^FAIL /{sub(":","",$2); print $2}'` 得到 FAIL 全集（本 spec 写作时为 35 个），减去 backfill 白名单 {GH1, GH95, GH97, GH100, GH104, GH106, GH111} 后得 28 个老区段 spec（GH5,GH7,GH9,GH13,GH16,GH17,GH18,GH19,GH20,GH22,GH23,GH24,GH28,GH30,GH34,GH35,GH37,GH38,GH39,GH40,GH55,GH57,GH58,GH59,GH60,GH61,GH62,GH63）；实现时重跑该命令，若集合漂移（新合入 spec）按同规则重算，禁止手工挑选；对每个目标 `product.md` 的 Linked Issue 小节追加一行 `status: legacy`；其中 4 个老格式 spec（GH5、GH7、GH9、GH13）无 Linked Issue 小节，按 B-010 在文件末尾追加最小小节（`## Linked Issue` 标题行 + `GitHub issue: #<n>` 行 + `status: legacy` 行，+3 行 0 删除），其余 24 个每文件 +1 行 0 删除，全部纯追加；PR 附枚举命令输出。Covers: B-009 B-010. Owner: agent. Done when: 枚举输出减白名单与实际标记文件集合 diff 为空，`git diff --numstat` 显示 GH5/GH7/GH9/GH13 四个文件 +3/-0、其余 24 个 +1/-0. Verify: `python3 tools/spec_depth_audit.py --repo . --gate 2>&1 | awk '/^FAIL /{sub(":","",$2); print $2}' | grep -vE '^GH(1|95|97|100|104|106|111)$' | sort > /tmp/gh142-sweep.txt && git diff --name-only origin/main -- 'specs/*/product.md' | sed 's#specs/##;s#/product.md##' | sort | diff -u /tmp/gh142-sweep.txt - && git diff --numstat origin/main -- 'specs/*/product.md' | awk '{n=$3; gsub("specs/|/product.md","",n); old=(n=="GH5"||n=="GH7"||n=="GH9"||n=="GH13"); if (old && ($1!=3||$2!=0)) exit 1; if (!old && ($1!=1||$2!=0)) exit 1}'`
- [ ] `SP142-T4` backfill 7 个活跃 spec 至默认阈值 8/8/5：GH1（补 Boundary Checklist）、GH95（补 invariants）、GH97（补边界+锚点）、GH100/GH104/GH106/GH111（补 invariants+边界+锚点）；锚点须按 anchor discipline 用 Read/grep 现场核实，禁止加 `complexity: trivial` 或 `status: legacy` 规避。Covers: B-008. Owner: agent. Done when: 7 个目录逐一通过 gate 默认阈值. Verify: `for d in GH1 GH95 GH97 GH100 GH104 GH106 GH111; do python3 tools/spec_depth_audit.py --spec-dir specs/$d --gate || exit 1; done`
- [ ] `SP142-T5` 全库二态验收：全库 gate 通过、二态计数等式成立（pass+trivial+legacy=46+，无第三态）、workflow 校验与全量测试通过。Covers: B-003 B-011. Owner: agent. Done when: 三条验证命令全部退出码 0 且 gate 汇总含二态计数行. Verify: `python3 tools/spec_depth_audit.py --repo . --gate && python3 checks/check_workflow.py --repo . --all-specs && python3 -m pytest -q`

## Parallelization

- T1（`tools/spec_depth_audit.py` + `tests/test_spec_depth_audit.py`）与 T2（`checks/specrail_lib.py`、`checks/route_gate.py` + `tests/test_route_gate*.py`）文件互不相交，可并行。
- T3（28 个老区段 `specs/GH*/product.md`）与 T4（7 个 backfill spec 目录）文件互不相交，可在 T1 合入后并行；T3 的枚举依赖 T1 的 legacy 态输出。
- T5 串行收尾，依赖 T1–T4。

## Verification

- [ ] `SP142-T6` 逐任务 Verify 命令全部通过后，重跑 `python3 tools/spec_depth_audit.py --repo . --gate` 并把 gate 段（legacy 名单 + 二态计数）贴进 PR 描述。Covers: B-011. Owner: agent. Done when: PR 描述含 gate 段证据. Verify: `python3 tools/spec_depth_audit.py --repo . --gate`

## Handoff Notes

- 处置决策：混合方案已定——backfill 白名单 = {GH1, GH95, GH97, GH100, GH104, GH106, GH111}（GH1 为 workflow 奠基 spec 且被 umbrella 引用，GH95+ 为仍被当前 gate/queue 工作引用的活跃区段）；其余 FAIL 一律 legacy。不要在实现期重开该决策。
- `SPEC_STATUSES` 闭集不扩（`checks/specrail_lib.py:26`）；legacy 是 spec 文件属性，阻断发生在 route_gate implement 分支。
- GH108/GH117/GH120/GH124/GH127/GH93 现为 trivial 豁免，不在处置范围。
