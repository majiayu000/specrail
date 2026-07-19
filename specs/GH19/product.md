# Product Spec

## Linked Issue

GitHub issue: `#19`
status: legacy

## 用户问题

`specrail-workflow` 是单个大入口 skill，职责太多，不利于能力审计、版本锁定和局部复用。SpecRail 需要从 workflow pack 进化到可分发的 agent workflow skill set。

## 目标

- 保留 `specrail-workflow` 作为 router。
- 新增 focused skills。
- 新增 `skills-lock.json`，锁定 repo-distributed skills。
- pack validation 能发现缺失/不匹配 skill lock。

## 非目标

- 不安装到 `$HOME`。
- 不删除现有入口 skill。
- 不引入自动 approval/merge。

## Behavior Invariants

1. Agent 仍可从 `specrail-workflow` 启动完整 SpecRail preflight。
2. 每个 focused skill 只覆盖一个窄 route 或 gate。
3. `skills-lock.json` 必须列出每个 repo skill path 和 hash。
4. check workflow 必须在 skill path 缺失或 hash 不匹配时失败。

## 验收标准

- [ ] 新 focused skills 存在且 frontmatter 有 `name`/`description`。
- [ ] `skills-lock.json` 覆盖所有 SpecRail skills。
- [ ] `checks/check_workflow.py` 校验 lockfile。
- [ ] `specrail-workflow` 指向 focused skills。

## 边界情况

- Lock hash 更新应 deterministic。
- 旧入口 skill 不应和 focused skills 冲突。

## 发布说明

这是 skill distribution 结构升级，consumer repos 可渐进采用。
