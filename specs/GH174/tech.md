# Tech Spec

## Linked Issue

GH-174

<!-- specrail-requires-planned-changes-v1 -->
<!-- specrail-planned-changes
{"version":1,"issue":174,"complete":true,"paths":["AGENT_USAGE.md","CHANGELOG.md","checks/check_workflow.py","checks/skill_reference_graph.py","skills-lock.json","skills/implx/SKILL.md","skills/specrail-implement-queue/SKILL.md","skills/specrail-implement-queue/references/evidence-and-recovery.md","skills/specrail-implement-queue/references/planning-and-runtime.md","skills/specrail-implement-queue/references/review-and-merge.md","tests/test_check_workflow.py","tests/test_install_codex_skills.py","tests/test_skill_reference_graph.py"],"spec_refs":["specs/GH174/product.md","specs/GH174/tech.md","specs/GH174/tasks.md"]}
-->

## Product Spec

见 `specs/GH174/product.md`。本设计实现 B-001..B-016，并以 GH-172 合并为实现前置。

## Codebase Context

| Area | Files | Current behavior | Why relevant |
| --- | --- | --- | --- |
| queue entry | `skills/specrail-implement-queue/SKILL.md:11-249` | Startup、spec gate、tier 与 planning 全在主文件。 | 保留不可绕过摘要，阶段细节可移到 planning reference。 |
| runtime controls | `skills/specrail-implement-queue/SKILL.md:250-606` | 编排、review、budget、breaker、wait、checkpoint、Goal 混在主文件。 | 需要压缩主合同并按 planning/runtime、review/merge 路由详细步骤。 |
| implementation/merge | `skills/specrail-implement-queue/SKILL.md:607-799` | 实现、review、授权、merge、输出和 rejection 全在主文件。 | merge/authorization 摘要留主文件，证据与恢复细节按需加载。 |
| implx router | `skills/implx/SKILL.md:13-29`, `skills/implx/SKILL.md:224-227` | 直接委托 queue 主 Skill 并引用其中多个章节。 | 拆分后必须只指向主入口，不自行猜引用路径。 |
| current lock | `skills-lock.json:21-23` | queue 只锁 `SKILL.md`。 | GH-172 完成后为三个引用加入多文件 hash 闭集。 |
| installer | `tools/install_codex_skills.py:61-101` | 复制整个目录但只验证入口 hash。 | 由 GH-172 改为按同一 manifest post-check 全部引用。 |
| pack check | `checks/check_workflow.py:485-512` | 校验 required files、pack 与 lock，没有 phase/reference graph。 | 接入独立确定性引用图检查。 |

## 设计方案

### 1. 主文件合同与 phase manifest

主文件保留 frontmatter、入口条件、所有不可绕过合同的短版和一个
`specrail-phase-references-v1` JSON marker：

```json
{
  "version": 1,
  "phases": {
    "startup_planning": ["references/planning-and-runtime.md"],
    "runtime_handoff": ["references/planning-and-runtime.md", "references/evidence-and-recovery.md"],
    "review_merge": ["references/review-and-merge.md"],
    "retry_recovery": ["references/evidence-and-recovery.md"]
  }
}
```

允许同一引用服务多个 phase，但每个 phase 路径必须唯一、稳定排序。主文件对每个 phase
明确“何时加载”和“在首个什么动作前加载”。implx 只加载 queue 主入口，queue 再按
当前 phase 路由；禁止 implx 预读全部引用。

主文件必须保留稳定关键 marker：

- startup/readiness/skip labels/Done-When；
- reviewer lane required/failure；
- Same-Issue Circuit Breaker trip/no-auto-continue；
- bounded tranche stop；
- wait contract；
- authorization/merge gate/human boundary；
- checkpoint/Goal 不替代 GitHub truth；
- rejection repeat stop。

### 2. 三个单层引用

- `planning-and-runtime.md`：tier 细节、queue ledger、spec/impl mix、context/runtime
  budget、checkpoint/Goal 字段与操作顺序。
- `review-and-merge.md`：bounded review artifact、reviewer failure、CI/PR gate、
  graded reconfirmation 与 safe merge 的详细步骤。
- `evidence-and-recovery.md`：output firewall、验证层次、handoff、closure audit、
  rejection persistence 与 retry evidence。

引用不含 frontmatter，不声明其他引用，不出现 `../` 或绝对路径。每个引用开头声明
`Reference only; the main SKILL.md contract wins`，并列出自己服务的 phase ID。
normative summary 只在主文件定义；引用给出步骤/字段/示例，不得出现降低 MUST 的
fallback 语句。

### 3. 引用图 validator

新增 `checks/skill_reference_graph.py`：

```text
validate_skill_reference_graph(repo, skill_name) -> list[str]
```

处理顺序：

1. 解析主文件唯一 JSON marker；
2. 校验 closed phase enum、非空路由、POSIX 相对路径与 skill-root containment；
3. 校验每个路径是普通文件且无 symlink component；
4. 扫描引用中的 Markdown link/marker，拒绝对主/其他引用的二级路由；
5. 与 GH-172 normalized lock manifest 对账：声明集合必须等于 queue 的额外
   `files[]` 集合；
6. 检查每个引用声明的 phase 与反向路由一致；
7. 检查关键 marker 只在主文件存在，禁止引用包含 known weakening patterns；
8. 稳定聚合全部错误。

`checks/check_workflow.py` 把 checker 加入 required assets，并对 queue 调用。
installed doctor 继续负责安装字节/hash；reference graph 负责仓库结构/路由，两者都通过
才可启动 queue。

### 4. 机械等价与尺寸门禁

拆分前先建立 section inventory 和关键 marker fixture。移动每段时保留语义 ID，
测试对比拆分后主文件+引用的合同 inventory，禁止丢失或重复。新增尺寸校验直接按 UTF-8
bytes 和 `splitlines()` 计算，边界 500/28672 均测试 exact pass 与 +1 fail。

queue 主文件和引用单文件均低于 500 行；三引用不互相依赖。GH-172 合并后基于最新
manifest API 实现并最后刷新 queue/implx hash。

## Product-to-Test Mapping

| Behavior invariant | Implementation area | Verification |
| --- | --- | --- |
| B-001 | size validator | `python3 -m pytest -q tests/test_skill_reference_graph.py -k size` |
| B-002 B-010 B-015 | critical marker inventory | `python3 -m pytest -q tests/test_skill_reference_graph.py -k contract` |
| B-003 B-004 B-011 | phase router | `python3 -m pytest -q tests/test_skill_reference_graph.py -k phase` |
| B-005 B-006 B-013 B-014 | GH-172 lock/installer/doctor | `python3 -m pytest -q tests/test_skill_reference_graph.py tests/test_install_codex_skills.py -k "reference or multifile"` |
| B-007 B-008 B-009 | graph/safety/conflict rules | `python3 -m pytest -q tests/test_skill_reference_graph.py -k "cycle or path or conflict"` |
| B-012 | deterministic repeat | `python3 -m pytest -q tests/test_skill_reference_graph.py -k deterministic` |
| B-016 | post-merge observation boundary | 人工复核报告不作为结构 PR gate |

## 数据流

```text
main SKILL bytes → phase manifest → current phase → selected one-hop references
          └──────→ reference graph validator ← normalized GH-172 lock manifest
installed files  → GH-172 doctor ────────────┘
```

所有 pack checks 只读仓库；安装写入仍由显式 `--apply` 控制。

## 备选方案

- 只删文字：容易丢失合同且无法按 phase 扩展，拒绝。
- 每个 phase 独立 Skill：增加发现/安装/路由复杂度，当前无需，拒绝。
- 引用互相链接：形成隐式递归与漏读风险，拒绝。
- 把真实 token 降幅作为合并门：样本受任务/compaction 影响，本轮已明确非目标。

## 风险

- Security: 路径逃逸/symlink 必须在读取前拒绝，引用不得包含可执行自动化。
- Compatibility: 实现等待 GH-172；旧 installer/lock 不能安全分发引用。
- Performance: phase 路由减少默认注入，但当前阶段首次读取会增加一次小文件读取。
- Maintenance: critical marker inventory 与 phase enum 需测试，避免后续规则只写进引用。

## 测试计划

- [ ] Unit: 尺寸、manifest、phase、闭集、循环、路径、冲突与稳定错误。
- [ ] Integration: workflow + GH-172 lock/installer/doctor 多文件 fixture。
- [ ] Regression: 全量 pytest、all-specs、depth audit、diff/hash/line/byte checks。
- [ ] Forward-use: 临时安装目录加载 startup、review、recovery 三条 phase 路径。

## 回滚方案

回滚主 Skill、三个引用、checker/wiring、tests、docs 与 lock hash 的同一实现提交。
不得只删除引用而保留路由，或只回滚 lock 造成安装完整性漂移。
