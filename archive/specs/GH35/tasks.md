# Task Plan

## Linked Issue

GH-35

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## 实现任务

- [ ] `SP35-T001` Owner: setup | Done when: `skills/specrail-install/SKILL.md` defines `doctor`, `install_local_skills`, `install_global_guidance`, and `adopt_repo` routes with explicit authorization boundaries | Verify: inspection and skill lock validation pass
- [ ] `SP35-T002` Owner: tooling | Done when: `tools/install_codex_skills.py` previews locked skill copy operations by default and writes only with `--apply` | Verify: `python3 tools/install_codex_skills.py --repo .`
- [ ] `SP35-T003` Owner: tooling | Done when: installer validates `skills-lock.json`, refuses unsafe targets, and verifies installed hashes after apply | Verify: `python3 -m pytest -q tests/test_install_codex_skills.py`
- [ ] `SP35-T004` Owner: workflow | Done when: `skills/specrail-workflow/SKILL.md` routes setup requests to `specrail-install` and documents autonomous SpecRail mode | Verify: inspection and workflow validation pass
- [ ] `SP35-T005` Owner: docs | Done when: README, AGENT_USAGE, PLAN, and CHANGELOG document agent-first setup, optional local installation, repo adoption, and explicit boundaries | Verify: inspection and workflow validation pass
- [ ] `SP35-T006` Owner: coordinator | Done when: PR #33 links GH-35 and validation evidence is current | Verify: PR body, CI, and local checks

## 并行拆分

- Tooling lane: `tools/install_codex_skills.py`,
  `tests/test_install_codex_skills.py`.
- Skill lane: `skills/specrail-install/SKILL.md`,
  `skills/specrail-workflow/SKILL.md`, `skills-lock.json`.
- Docs lane: `README.md`, `AGENT_USAGE.md`, `PLAN.md`, `CHANGELOG.md`.

One coordinator owns final validation and PR body updates.

## 验证

- `python3 tools/install_codex_skills.py --repo .`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `python3 -m pytest -q`
- `git diff --check`
- `python3 checks/pr_gate.py --repo . --evidence <evidence.json> --json`

## Handoff Notes

Use `Fixes #35` only after the setup skill, installer, tests, docs, lockfile,
GH-35 spec packet, and validation evidence are in PR #33.
