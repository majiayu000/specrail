# Task Plan

## Linked Issue

GH-28

## Spec Packet

- Product: `product.md`
- Tech: `tech.md`

## Tasks

- [ ] `SP28-T001` Owner: workflow | Done when: `skills/specrail-implement-queue/SKILL.md` exists and describes the approved-spec queue route | Verify: skill lock validation passes
- [ ] `SP28-T002` Owner: workflow | Done when: `specrail-workflow` routes queues to the new skill without changing single issue behavior | Verify: inspection and pack validation pass
- [ ] `SP28-T003` Owner: integration | Done when: `integrations/threads.md` documents queue handoff fields while preserving the optional integration boundary | Verify: inspection and pack validation pass
- [ ] `SP28-T004` Owner: coordinator | Done when: `skills-lock.json` includes the new skill with a correct hash | Verify: `python3 checks/check_workflow.py --repo . --all-specs`
- [ ] `SP28-T005` Owner: coordinator | Done when: validation and tests pass and the PR links GH-28 | Verify: test output and PR body

## Dependencies

This change depends on the existing focused route skills and optional threads
integration. It does not require a local threads installation.

## Verification

- `python3 checks/check_workflow.py --repo . --all-specs`
- `uvx pytest -q` or the repository's Python test command
- `git diff --check`

## Handoff Notes

Use `Fixes #28` only if the PR includes the skill, router update, integration
handoff, lockfile update, and passing validation.
