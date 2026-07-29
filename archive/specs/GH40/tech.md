# Tech Spec

## Linked Issue

GH-40

## Product Spec

`specs/GH40/product.md`

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| schema | `schemas/runtime_checkpoint.schema.json` | items 仅 required `state`/`next_action`,顶层契约弱于 gate | 需收紧到与 gate 结构要求一致 |
| gate | `checks/runtime_ledger_gate.py` | 结构 + 语义契约的实际权威 | 对账的行为侧 |
| lib | `checks/specrail_lib.py` | `validate_json_schemas` 只做元校验 | 最小实例校验器落点 |
| fixtures | `examples/fixtures/`、`tests/test_runtime_ledger_gate.py` 内联样例 | gate 测试输入 | 实例校验的数据源 |
| docs | `README.md`、`SPEC.md`、`specs/GH34/tech.md` | GH34 自述"故意重复约束" | 契约权威声明落点 |

## 设计方案

1. 在 `checks/specrail_lib.py` 新增 `validate_instance(schema, data, path)`:
   递归实现 `type` / `required` / `properties` / `items` / `enum` /
   `additionalProperties`;遇到未实现的 schema 关键字(如 `oneOf`、
   `pattern`)抛 `SpecRailError`,提示"校验器不支持该特性,请扩展或
   简化 schema"。约 80-120 行,含清晰的错误路径输出
   (如 `items[2].pr_gate.head_sha: missing required field`)。
2. 收紧 `runtime_checkpoint.schema.json`:把 gate 实际强制的结构字段
   (顶层 `tranche_id`/`repo`/`scope`/`status`/`resume_prompt`,item 的
   证据字段结构)补进 required/properties。语义规则(值相等、分级
   逻辑)不进 schema。
3. 新增测试 `test_schema_instance_validation`:
   - 校验器自身单测:每种支持特性的正例与负例、不支持特性报错。
   - 遍历"合法 checkpoint 样例集"(fixtures + 测试内联的 gate-pass
     样例),逐一 `validate_instance` 断言通过。
   - 一致性负例:删除样例中的 `resume_prompt` 后,gate 与 schema 必须
     同时拒绝(防单侧漂移)。
4. 文档:在 SPEC.md 增加"契约权威"小节(gate = 行为权威,
   schema = 结构权威,测试对账);README 的 runtime checkpoint 段落链接
   过去;更新 `specs/GH34/tech.md` 不动(历史记录),但 CHANGELOG 注明
   升级。

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 | `specrail_lib.validate_instance` | 校验器单测(正/负例、不支持特性) |
| P2 | fixtures 实例校验测试 | `pytest -k schema_instance` |
| P3 | schema required 收紧 | 删字段负例复现失败 |
| P4 | SPEC.md 契约权威小节 | 文档审查 + `check_workflow` |

## 数据流

测试期:fixtures/内联样例 JSON → `validate_instance(schema, data)` →
断言。运行时数据流不变;gate 不调用实例校验器(保持 gate 独立决策,
避免 schema 文件损坏影响 gate 可用性)。

## 备选方案

- 引入 `jsonschema` 库:被否——违反零依赖原则(U-06;仓库明确声明
  全新 checkout 可校验)。
- 降级路线(schema 仅文档):被否——仓库哲学是确定性检查优先,schema
  已被 GH34/GH37 当作契约引用,降级是倒退;且最小校验器成本可控。
- gate 运行时调用实例校验器:被否——gate 需在 schema 缺失时独立工作,
  测试期对账已足够防漂移。

## 风险

- Security: 校验器是纯函数、无 IO,无新增面。
- Compatibility: schema 收紧对外部消费者是破坏性变化(若其此前依赖
  宽松 schema);CHANGELOG 注明,版本按 MINOR 处理(schema 是文档性
  契约,gate 行为未变)。
- Performance: 测试期少量递归,可忽略。
- Maintenance: 自研校验器需随 schema 特性增长维护;"不支持即报错"
  保证不会静默漏检。

## 测试计划

- [ ] Unit tests: `validate_instance` 六种特性正/负例;不支持特性报错。
- [ ] Integration tests: 合法样例全量实例校验;删字段双侧拒绝负例;
      `python3 checks/check_workflow.py --repo . --all-specs`。
- [ ] Manual verification: 用 GH-37 时期的历史 checkpoint 样例跑一次
      `validate_instance`,确认无误伤。

## 回滚方案

两步回滚:还原 schema required 收紧(独立 commit),删除校验器与测试
(独立 commit)。gate 行为全程未变,回滚无运行时影响。
