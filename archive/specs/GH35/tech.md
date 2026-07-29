# Tech Spec

## Linked Issue

GH-35

## Product Spec

Link to `product.md`.

## Codebase Context

| Area | Files | Current behavior | Change |
| --- | --- | --- | --- |
| Setup skill | `skills/specrail-install/SKILL.md` | No focused setup route exists | Add route for doctor, local skill install, global guidance, and repo adoption |
| Installer | `tools/install_codex_skills.py` | No deterministic local skill installer exists | Add dry-run-first installer based on `skills-lock.json` |
| Tests | `tests/test_install_codex_skills.py` | Installer behavior is untested | Add dry-run, apply, and unsafe-target tests |
| Router skill | `skills/specrail-workflow/SKILL.md` | Routes issue/spec/implementation work | Route setup requests to `specrail-install` and document autonomous SpecRail mode |
| Docs | `README.md`, `AGENT_USAGE.md`, `PLAN.md`, `CHANGELOG.md` | Setup guidance is spread across human instructions | Document agent-first setup and explicit authorization boundaries |
| Validator | `checks/check_workflow.py` | Does not require installer helper | Add `tools/install_codex_skills.py` to required files |
| Skill lock | `skills-lock.json` | Pins existing skills | Add `specrail-install` and refresh changed hashes |

## 设计方案

Add a focused setup skill instead of making humans memorize installer commands.
The skill owns route selection and authorization boundaries; the installer is a
deterministic helper the selected route may run.

`tools/install_codex_skills.py` loads `skills-lock.json`, validates it through
the existing lock validator, derives each locked skill directory, previews copy
operations by default, and writes only with `--apply`. After writes, it verifies
installed `SKILL.md` hashes against the lockfile.

The installer targets `$CODEX_HOME/skills` when `CODEX_HOME` is set or
`~/.codex/skills` otherwise. It refuses to install over the source skill
directory, inside a source skill directory, or into a source parent path.

## Product-to-Test Mapping

| Product invariant | Implementation area | Verification |
| --- | --- | --- |
| P1 setup routes through a skill | `skills/specrail-install/SKILL.md`, `skills/specrail-workflow/SKILL.md` | inspection and skill lock validation |
| P2 dry-run by default | `tools/install_codex_skills.py` | `test_install_codex_skills_dry_run_writes_nothing` |
| P3 explicit apply syncs locked skill | installer copy path | `test_install_codex_skills_apply_syncs_locked_skill` |
| P4 unsafe target refusal | `ensure_safe_destination` | `test_install_codex_skills_refuses_source_target` |
| P5 lockfile and installed hashes align | installer validation and `skills-lock.json` | `python3 checks/check_workflow.py --repo . --all-specs` |

## 数据流

Input is the repository root and `skills-lock.json`. Output is a dry-run plan or
an applied local skill directory sync. The command writes only to the selected
target directory when `--apply` is present. It does not write global
`AGENTS.md`, target repository pack files, GitHub issues, PRs, labels, reviews,
or merges.

## 备选方案

- Document manual copy commands only: rejected because the user asked for an
  agent-facing installation path.
- Make installation automatic during repo adoption: rejected because local skill
  install and repo adoption are separate layers.
- Put setup guidance only in `specrail-workflow`: rejected because setup is not
  an issue/spec workflow route.

## 风险

- Security: No credentials are handled; the installer copies local skill files
  only and refuses unsafe overlap.
- Compatibility: Local installation is optional; existing repo-distributed skill
  usage keeps working.
- Performance: The installer copies a small locked skill set.
- Maintenance: `skills-lock.json` must be refreshed when skill text changes.

## 测试计划

- `python3 tools/install_codex_skills.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 -m pytest -q`
- `git diff --check`

## 回滚方案

Remove `skills/specrail-install/SKILL.md`, `tools/install_codex_skills.py`,
installer tests, router/docs references, lockfile entry, and `specs/GH35`.
Existing repo-distributed SpecRail skills continue to work from the repo.
