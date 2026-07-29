# Task Plan

## Linked Issue

GH-30

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Tasks

- [ ] `SP30-T001` Owner: workflow | Done when: `skills/implx/SKILL.md` exists and describes the shortcut route | Verify: skill validation passes
- [ ] `SP30-T002` Owner: workflow | Done when: `implx` routes to `specrail-implement-queue`, threads integration, implementation flow, PR gates, and closure audit | Verify: inspection and workflow validation pass
- [ ] `SP30-T003` Owner: workflow | Done when: `skills/specrail-workflow/SKILL.md` mentions the explicit shortcut without changing existing queue routing | Verify: inspection and pack validation pass
- [ ] `SP30-T004` Owner: coordinator | Done when: `skills-lock.json` includes `implx` and refreshed hashes for changed skills | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP30-T005` Owner: coordinator | Done when: validation and tests pass and the PR links GH-30 | Verify: test output and PR body

## Dependencies

This change depends on the existing SpecRail focused route skills and optional
threads integration. It does not require a local threads installation.

## Verification

- `python3 /Users/apple/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/implx`
- `python3 checks/check_workflow.py --repo . --all-specs`
- `uvx pytest -q`
- `git diff --check`

## Handoff Notes

Use `Fixes #30` only if the PR includes the shortcut skill, router note,
lockfile update, GH-30 spec packet, and passing validation.
