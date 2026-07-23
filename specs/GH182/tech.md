# Tech Spec

## Linked Issue

GH-182

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":182,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/skill_wait_contract.py","integrations/threads.md","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","tests/test_check_workflow.py","tests/test_skill_wait_contract.py"],"spec_refs":["specs/GH182/product.md","specs/GH182/tech.md","specs/GH182/tasks.md"]}
-->

## Product Spec

见 `specs/GH182/product.md`。本设计覆盖 B-001..B-018，且明确不修改 GH-160。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue batching | `skills/specrail-implement-queue/SKILL.md:497-512` | 已说明 turn 重发完整历史、批量收集证据并禁止 no-op turn。 | 保留成本模型与 batching 原则，只纠正其后的等待调用形态。 |
| queue waiting | `skills/specrail-implement-queue/SKILL.md:514-537` | 正确禁止模型轮询，但错误要求 direct exec 使用配置最大 yield，并允许需要时指数增加多个 wait。 | 这是本 issue 的直接合同缺陷。 |
| implx entry | `skills/implx/SKILL.md:224-227` | 只要求单次阻塞等待并跳转到 queue 的 Waiting Discipline。 | 需要给入口一个简短、不会被错误引用解释覆盖的硬边界。 |
| threads integration | `integrations/threads.md:115-123` | 列出 reviewer lanes、CI polling、closure audit 与 context firewall，但没有 exact wait 调用合同。 | subagent 路径需要固定一次长 `wait_agent` 和 timeout 后动作。 |
| pack validation | `checks/check_workflow.py:32-86`, `checks/check_workflow.py:485-512` | required assets 与各类 validator 在普通 workflow check 中聚合；没有 wait-contract validator。 | 新校验必须接入既有单一入口并保持纯仓库、确定性。 |
| lock entries | `skills-lock.json:6-8`, `skills-lock.json:21-23` | implx 与 queue 入口由 `computedHash` 绑定。 | Skill 字节变更后必须在最后刷新哈希。 |
| workflow tests | `tests/test_check_workflow.py:1-372` | 覆盖 required files、pack validation 与主流程结果。 | 增加 checker wiring 回归，但具体规则放在独立测试文件。 |
| file ceiling | `skills/specrail-implement-queue/SKILL.md` | 当前 799 行，距离 800 行硬上限只剩一行。 | 修改必须压缩/替换现有段落，最终不能超过 799 行。 |

## 设计方案

### 1. 唯一等待状态机

在 queue Skill 的 `Waiting Discipline` 中用一个简短状态机替换
`skills/specrail-implement-queue/SKILL.md:533-537`：

```text
start
  └─ exec_command(yield=30000)
       ├─ completed → return result
       └─ session_id
            └─ write_stdin(chars="", yield=1800000) exactly once
                 ├─ terminal → return result
                 └─ non-terminal/error → stop; no second empty poll
```

对于 code-mode，示例必须把外层调用预算与内层工具参数分开：

```javascript
// @exec: {"yield_time_ms": 1800000}
const result = await tools.exec_command({cmd, yield_time_ms: 30000});
if (result.session_id) {
  const done = await tools.write_stdin({
    session_id: result.session_id,
    chars: "",
    yield_time_ms: 1800000
  });
}
```

示例只描述调用形态，不允许拼接用户输入为 shell 命令，也不建议用 shell
`while/sleep` 轮询替代工具等待。direct `exec_command` 路径同样是首次
30000 ms，返回 session 后最多一次 1800000 ms 空续等。

### 2. subagent 与 CI 等待

`integrations/threads.md` 与 queue Skill 使用同一规则：

- reviewer/subagent：一次 `wait_agent(timeout_ms=1800000)`；
- timeout 后读取一次状态，没有可信进展则 interrupt/stop-and-return；
- 不在 wait 前后调用 `list_agents` 作为 polling；
- PR CI 使用 `gh pr checks --watch --fail-fast`；
- run CI 使用 `gh run watch --exit-status`。

`skills/implx/SKILL.md` 只保留简短入口断言与 queue reference，避免复制整段状态机。

### 3. 确定性等待合同校验

新增 `checks/skill_wait_contract.py`，提供：

```text
validate_skill_wait_contract(repo: Path) -> list[str]
```

校验器只读取以下仓库文件：

- `skills/specrail-implement-queue/SKILL.md`
- `skills/implx/SKILL.md`
- `integrations/threads.md`

规则分两类：

1. 必需 marker：direct cap 30000、blocking wait 1800000、最多一次
   `write_stdin`、一次 `wait_agent`、禁止 `list_agents` polling、CI watch；
2. 禁止 marker：`exec_command` 使用 30000 以上 yield、`maximum yield each
   time`、`grow the yield exponentially`、允许多个 empty wait 的措辞。

校验不解析用户 session，也不尝试证明 agent 已遵守合同。错误按固定文件/规则顺序
聚合，并只输出相对路径和规则 ID。`checks/check_workflow.py` 将 checker 文件加入
`REQUIRED_FILES` 并在 lock 校验旁调用该函数。

为避免脆弱的自然语言全文匹配，Skill 段落加入稳定、唯一的 marker：

```text
wait-contract-v1
direct_exec_yield_ms=30000
blocking_wait_ms=1800000
empty_write_stdin_max=1
wait_agent_max=1
list_agents_polling=forbidden
```

validator 校验 marker、示例关键调用和已知禁止文本；普通说明可在不破坏合同的情况下
重写。重复 marker、非法整数或相互冲突的文本均失败。

### 4. 行数与 lock 收口

queue Skill 已有 799 行。实现先删除错误的五行和可被状态机替代的重复说明，再加入
marker/示例；最终必须 `wc -l < 800`。不得通过把合同藏入超长单行规避可读性。

所有 Skill 文本与文档完成后再刷新 `skills-lock.json` 中 implx/queue 的
`computedHash`。GH-172 尚未合并时不开始本实现；合并后必须基于最新 lock schema
重放变更与测试，避免覆盖其多文件 manifest。

### 5. 效果证据边界

静态门禁只证明合同资产正确。关闭 GH-182 还需要独立 post-policy cohort：

- cutoff 不早于包含修复后 Skill 的会话启动时间；
- 不把父/子 rollout 复刻历史重复计数；
- 分别报告三类 poll 和总 turn；
- 对比等价工作量，披露样本量和窗口；
- 不把 GH-160 的 context baseline 指标混入本 issue。

分析脚本不在本 manifest 中；如果需要把 `/tmp` 脚本产品化，应另开 issue，经
search-first 与 spec gate 后实现。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 B-002 B-003 B-004 | queue wait state machine/markers | `python3 -m pytest -q tests/test_skill_wait_contract.py -k exec` |
| B-005 B-006 | single continuation rule | `python3 -m pytest -q tests/test_skill_wait_contract.py -k write_stdin` |
| B-007 B-008 | threads/subagent rule | `python3 -m pytest -q tests/test_skill_wait_contract.py -k agent` |
| B-009 | CI watch rule | `python3 -m pytest -q tests/test_skill_wait_contract.py -k ci` |
| B-010 | output firewall wording | `python3 -m pytest -q tests/test_skill_wait_contract.py -k output` |
| B-011 B-012 B-014 | deterministic checker and wiring | `python3 -m pytest -q tests/test_skill_wait_contract.py tests/test_check_workflow.py -k "wait_contract or required_files"` |
| B-013 | cancellation/error wording | `python3 -m pytest -q tests/test_skill_wait_contract.py -k terminal` |
| B-015 | queue file ceiling | `test "$(wc -l < skills/specrail-implement-queue/SKILL.md)" -lt 800` |
| B-016 B-017 | post-policy cohort evidence | 人工复核独立 cohort 报告、窗口和三项阈值 |
| B-018 | dependency and diff scope | `git merge-base --is-ancestor <GH172-merge-sha> HEAD && git diff --name-only <base>...HEAD` |

## 数据流

```text
repo Skill/docs bytes
  → skill_wait_contract parser
  → stable marker + forbidden-pattern results
  → check_workflow aggregated errors / exit code

long command
  → exec_command(30000)
  → completed OR one session_id
  → at most one write_stdin("", 1800000)
  → terminal evidence OR explicit stop
```

校验无持久化和外部调用。运行时等待由 Codex 工具完成；Skill 只约束调用策略。

## 备选方案

- 只改自然语言、不加 checker：无法防止错误的“最大 direct yield”再次回归，拒绝。
- 只依赖系统 developer instructions：安装的 Skill 仍会向模型提供冲突指导，拒绝。
- 把等待逻辑写成 shell `while sleep`：仍是轮询，且增加进程/注入风险，拒绝。
- 立即修改 `/tmp/final.py`：临时文件不可分发、不可审查，也不是当前 implementation
  manifest，留给独立 issue。

## 风险

- Security: 示例必须使用结构化工具参数，不拼接不可信 shell 输入或读取 session 正文。
- Compatibility: 工具常量未来可能变化；marker 版本升级必须走新的 spec，而不是静默改值。
- Performance: 单次长 wait 会降低中途可见性，但不会增加实际命令执行时间；完成时会提前返回。
- Maintenance: queue 已接近行数上限，后续 GH-174 拆分需要保留 `wait-contract-v1` 语义。

## 测试计划

- [ ] Unit tests: 正向 marker、各禁止文本、重复/缺失/非法值和稳定错误顺序。
- [ ] Integration tests: `check_workflow.py` 在正确资产通过、篡改 fixture 时失败。
- [ ] Regression: 全量 pytest、all-specs、depth audit、diff check、Skill 行数和 lock hash。
- [ ] Manual verification: 实现后跑一轮独立 implx cohort 并核对三项运行指标。

## 回滚方案

回滚 Skill、checker、wiring、测试、文档与 lock hash 的同一实现提交即可恢复旧行为。
若静态合同误报，可回滚 checker 接入，但不得声称等待性能已验证；不得单独回滚 lock
hash 或保留与 Skill 字节不一致的条目。
