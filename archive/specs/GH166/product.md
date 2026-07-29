# Product Spec

## Linked Issue

GH-166

## 用户问题

SpecRail 把昂贵的 CI 与独立 review 证据整体绑定到 PR exact head；只改 metadata 或一个独立类别也会让所有组件证据失效。remem #907/#908 的 markdown-only 规格 PR 因多次 head 变化重复运行 13–17 分钟的全量 CI，浪费约 1.5–2 小时。本 spec 将“可复用组件证据”按其真实输入类别绑定 content hash；当前 head 的 PR snapshot、threads、merge state、授权和 `pr_gate` 决策始终重新采集/评估，不复用旧 head 的最终 gate 决策。

## 目标

- 为每个 CI check/review artifact 声明实际覆盖类别与内容绑定；只有其覆盖的全部类别未变化时才可复用该组件。
- 规格、代码/base tree、metadata 独立建模；spec-aware CI/review 必须同时绑定 spec 类别。
- legacy evidence 保持 exact-head 语义；只有 opt-in 的新证据才要求 provenance/coverage/hash 字段。
- 当前 head 重新运行轻量 gate，复用只减少昂贵组件重跑，不跳过实时 threads/merge/auth/query freshness。

## 非目标

- 不复用旧 head 的最终 `pr_gate` decision、runtime merge-ready decision、thread snapshot、merge state 或授权。
- 不允许调用方自报 hash/coverage；字段由可信 collector 与 reviewer artifact schema 生成并验证。
- 不改变 human gates、enforcement-sensitive terminal review、CI 必须绿等要求。
- 不引入跨仓库缓存或远程 hash store。

## Behavior Invariants

1. B-001 collector 必须为当前稳定 snapshot 计算 `code_inputs_hash`、`spec_files_hash`、`pr_metadata_hash`；`code_inputs_hash` 包含可信 base tree OID 与规范化 code diff，base ref 前进或 rebase 必然改变绑定。
2. B-002 `spec_files_hash` 必须对规范化 repo-relative path 排序，并以 `path + NUL + byte_length + NUL + raw_content` 编码后计算 SHA-256；rename/split/order/边界拼接不能产生歧义。
3. B-003 每个可复用 CI check/review artifact 必须声明非空 `covered_categories` 与对应 `content_bindings`；复用要求所有覆盖类别的原 hash 与当前可信 hash 逐字一致，不能只比较 `code_inputs_hash`。
4. B-004 CI check 的覆盖类别由仓库可信配置/collector 推导；读取 spec packet 的 `workflow-check` 必须覆盖 `spec_files`，因此 spec 修改会让该 check 失效，即使 code hash 未变。
5. B-005 terminal review 的覆盖类别来自 schema-backed artifact。review 涵盖 spec packet 时必须绑定 `spec_files`；head 不同但所有 covered bindings 相同时，review 组件可复用，否则必须重审。
6. B-006 metadata-only 变化只在目标组件未声明覆盖 `pr_metadata` 时允许复用；审查 PR body/issue relation 的 artifact 若覆盖 metadata，则 metadata 变化会使其失效。
7. B-007 legacy evidence/checkpoint 未声明 `content_binding_version` 时继续 exact-head 严格校验，且不要求 `sha_provenance`；provenance/coverage/hash 仅对 opt-in v1 证据强制。
8. B-008 v1 机械字段与 hashes 必须携带 collector provenance、算法/规范化版本和 current snapshot identity；缺失、无法重算、不支持版本或 mismatch 均 fail closed，不得复用。
9. B-009 采集期间 head/base/files/relation 任一漂移时必须重启 current snapshot；所有 current hashes 必须来自同一 final head/base。可引用旧组件 artifact，但不得把不同 head 采集的类别 hash 拼成 current snapshot。
10. B-010 `schemas/pr_review_gate.schema.json`、`review_result.schema.json`、review manifest contract 与 runtime checkpoint schema 必须声明相同 v1 binding 闭集，拒绝 partial/unknown/mixed-version 字段。
11. B-011 runtime ledger 与 `pr_review_contract` 可接受 previous-head 组件 artifact，仅当其 schema-backed coverage bindings 与 current snapshot 全匹配；legacy/missing/category mismatch 仍要求 exact head。
12. B-012 当前 head 必须重新生成 PR evidence wrapper 并重新运行 `pr_gate`；runtime ledger 的 `item.pr_gate.head_sha` 与 loaded gate result 仍须等于 item current head。旧 gate decision 不可跨 head 复用，组件复用记录作为 current gate 的输入与审计。
13. B-013 enforcement-sensitive review 复用必须覆盖 `code_inputs` 与 `spec_files` 中实际存在的所有类别，并保留独立 terminal review；任一类别/base/hash/provenance 缺失即重审，不弱于 GH-97。
14. B-014 current gate/checkpoint 必须记录每个复用组件的 artifact ID、原 head、covered categories、original/current hashes、collector provenance 与复用原因；缺审计即 blocked。

## 验收标准

- [ ] base advance/rebase、spec path/content、metadata 三类变更分别使正确的组件失效；spec-aware CI 与 spec review 不会因 code hash相同而误复用（B-001..B-006）。
- [ ] legacy evidence 保持 exact-head 且不新增 provenance 要求；v1 partial/unsupported/mismatch 全部 fail closed（B-007 B-008 B-010）。
- [ ] previous-head review/CI 组件可在 coverage 全匹配时由 current-head `pr_gate` 使用，但旧 pr_gate/threads/merge/auth 决策永不复用（B-009 B-011 B-012 B-014）。
- [ ] enforcement-sensitive 路径覆盖所有实际类别且回归不弱化（B-013）。

## 边界情况清单

| 类别 | 判定（covered: B-xxx / N/A + 原因） |
| --- | --- |
| 空/缺失输入 | covered: B-003 B-007 B-008 B-010（v1 partial fail closed；legacy exact-head） |
| 错误与失败路径 | covered: B-008 B-009（无法重算/漂移重启 snapshot） |
| 授权/权限 | covered: B-012 B-013（当前 head 授权与敏感 review 不复用/不弱化） |
| 并发/竞态 | covered: B-001 B-009（base/head/file/relation drift 均重采） |
| 重试/幂等 | covered: B-003 B-014（相同 immutable bindings 得相同判定与审计） |
| 非法状态转换 | covered: B-010 B-012（mixed version、旧 gate decision 跨 head 均拒绝） |
| 兼容/迁移 | covered: B-007（无 v1 字段时严格 exact-head，零新增 provenance 要求） |
| 降级/回退 | covered: B-003 B-008 B-011（任何歧义回退重跑/重审） |
| 证据与审计完整性 | covered: B-002 B-008 B-010 B-014（无歧义编码、schema、provenance、audit） |
| 取消/中断 | covered: B-009（中断后重启 current snapshot，不混绑） |

## 发布说明

v1 为显式 opt-in；旧 evidence/checkpoint 不迁移，继续 exact-head。实现按 collector/schema→review contract→PR gate→runtime ledger 顺序落地，任何阶段不得让未消费/未验证的新字段产生复用。
