# Product Spec

## Linked Issue

GH-40
status: legacy

## 用户问题

`schemas/runtime_checkpoint.schema.json` 当前是"假保证":schema 对 items
只要求 `state` 与 `next_action`,而真正的合并就绪契约(`truth_level: A`、
CI 证据、review_threads、`pr_gate.head_sha` 一致性)只存在于
`checks/runtime_ledger_gate.py`。`specrail_lib.validate_json_schemas` 只
检查 schema 文件本身可解析,从不用实际数据做实例校验。结果是:一个通过
标准 JSON-Schema 校验器的 checkpoint 可能被 gate 阻断,反之 gate 放行的
结构 schema 可能标记非法。消费者无法知道哪一侧才是权威契约。

## 目标

- 消除 schema 与 gate 的静默分歧:选择"强制路线",让 fixtures 中的样例
  checkpoint 在测试期逐一对 schema 做实例校验。
- 在文档一处明确契约权威顺序:gate 是行为权威,schema 是结构权威,
  两者由测试对账。
- 保持零第三方依赖。

## 非目标

- 不引入第三方 JSON-Schema 校验库。
- 不实现完整 JSON-Schema 规范,只实现本仓库 schema 实际用到的特性子集。
- 不放宽或收紧 gate 的现有阻断规则。
- 不要求最终用户在运行时执行 schema 校验(仍是测试期护栏)。

## Behavior Invariants

1. 存在一个 stdlib 实现的最小实例校验器,支持本仓库 schema 实际使用的
   特性(`type`、`required`、`properties`、`items`、`enum`、
   `additionalProperties`);遇到 schema 中使用但校验器不支持的特性时
   显式报错,不静默跳过。
2. 测试期,`tests/` 与 `examples/fixtures/` 中每个 runtime checkpoint
   样例(合法样例)都通过 schema 实例校验;gate 判定为结构合法但
   schema 拒绝(或反向)的样例会使测试失败。
3. schema 收紧到与 gate 的结构要求一致:gate 要求的必填字段
   (如 `tranche_id`、`repo`、`scope`、`status`、`resume_prompt`、item
   的合并就绪证据字段)在 schema 中同样标记为 required 或条件说明。
4. README 或 SPEC 中有一段唯一的契约权威声明,与实际实现一致。

## 验收标准

- [ ] 最小校验器存在,有直接单测(正例 + 每种特性的负例)。
- [ ] fixtures 实例校验测试存在并通过;删除 schema 中任一 required
      字段可复现测试失败。
- [ ] 契约权威声明在 README 或 SPEC 中存在且唯一。
- [ ] `python3 -m pytest -q tests/` 与
      `python3 checks/check_workflow.py --repo . --all-specs` 通过。

## 边界情况

- gate 的语义性规则(如 head_sha 相等、truth_level 分级)无法用
  JSON-Schema 表达:这些保留在 gate 中,契约权威声明需明确这个分工,
  schema 不承诺语义校验。
- fixtures 中的非法样例(用于测试 gate 阻断)不要求通过 schema 校验;
  测试需区分"合法样例集"与"非法样例集"。

## 发布说明

checkpoint 文件格式不变;schema 收紧后,此前依赖 schema 宽松性的外部
消费者(若有)可能需要补齐必填字段——CHANGELOG 需注明 schema 从
"宽松文档"升级为"与 gate 对账的结构契约"。
