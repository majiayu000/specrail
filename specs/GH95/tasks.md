# Task Plan

## Linked Issue

GH-95

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP95-T1` Covers: B-001, B-002. Owner: workflow validator. Depends on: none. 将 pack asset validation 绑定到执行 checkout 的可信 helper，并增加 target no-op helper + missing owned schema 负例。Done when: 外部 validator 非零退出并报告缺失 schema，target helper 未被执行。Verify: `python3 -m pytest -q tests/test_check_workflow.py -k trusted_pack_asset`。
- [ ] `SP95-T2` Covers: B-003. Owner: route gate. Depends on: none. 让 required spec artifacts 与 provided evidence 都复用 shared normalized path contract，并增加配置侧/evidence 侧 `./specs/...` 回归测试。Done when: 两侧等价路径均通过，真实不同或非法路径仍被阻断。Verify: `python3 -m pytest -q tests/test_route_gate.py -k normalized_configured_artifact`。
- [ ] `SP95-T3` Covers: B-004, B-005. Owner: workflow discovery. Depends on: none. 对 missing/non-directory configured root 抛出明确 `SpecRailError` 并增加 CLI 负例。Done when: 两种 root 均非零退出、无 traceback，合法空目录兼容。Verify: `python3 -m pytest -q tests/test_check_workflow.py -k configured_root_is_unusable`。
- [ ] `SP95-T4` Covers: B-001, B-002, B-003, B-004, B-005. Owner: coordinator. Depends on: SP95-T1, SP95-T2, SP95-T3. 执行 focused/full/pack 验证并复核白名单 diff。Done when: 所有验证新鲜通过且变更仅包含 GH95 packet、两个 checks 与对应 tests。Verify: `python3 -m pytest -q && python3 checks/check_workflow.py --repo . --all-specs && python3 checks/check_workflow.py --repo . --spec-dir specs/GH95 && python3 -m compileall -q checks && git diff --check`。

## 并行拆分

本次由单一 implementation lane 串行修改。三个生产修复很小但共享验证与行为契约，
不创建重叠 writable lane；独立 reviewer 只读复核完整 diff。

## 验证

- `python3 -m pytest -q tests/test_check_workflow.py tests/test_route_gate.py`
- `python3 -m pytest -q`
- `python3 checks/check_workflow.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 checks/check_workflow.py --repo . --spec-dir specs/GH95`
- `python3 -m compileall -q checks`
- `git diff --check`

## Handoff Notes

- 用户已授权本 bounded tranche 的修复与通过 fresh gate 后的合并；持久化
  `auth_mode` 保持 `review`。
- 合并前必须由独立 reviewer 覆盖 current head，并处理 #92 的三个关联 threads。
- 上游合并后，VibeGuard #594 必须更新精确 pin、复制修复并重新收集全部 evidence。
