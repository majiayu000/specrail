# Product Spec

## Linked Issue

GH-35

## 用户问题

SpecRail is designed for agents, but setup remains too easy to express as a
human checklist. Users ask agents whether SpecRail is installed, how to install
or update it, whether global `AGENTS.md` should be adjusted, and how a target
repo should adopt the pack. Without a single agent-facing setup route, agents
can confuse local skill installation, global guidance, repo adoption, and remote
GitHub writes.

## 目标

- Add `specrail-install` as the agent-facing setup, install, update,
  verification, and adoption entrypoint.
- Provide a deterministic dry-run-first local Codex skill installer.
- Keep local skill installation optional and explicitly authorized.
- Document autonomous SpecRail mode for sufficiently complex work in repos that
  have not fully adopted the pack.
- Preserve human gates for global guidance edits, repo adoption, remote issue/PR
  writes, approval, and merge.

## 非目标

- Do not require local Codex skill installation for repository adoption.
- Do not silently modify `~/.codex/AGENTS.md`.
- Do not automatically copy the SpecRail pack into a target repository.
- Do not create remote issues, PRs, labels, approvals, or merges without an
  explicit user request.
- Do not replace `specrail-workflow`; setup routes into it after installation or
  adoption decisions.

## Behavior Invariants

1. Setup, installation, update, verification, and adoption requests route first
   through `skills/specrail-install/SKILL.md`.
2. `tools/install_codex_skills.py` is dry-run by default and writes only when
   `--apply` is explicitly requested.
3. The installer validates `skills-lock.json`, refuses unsafe source/target
   overlap, syncs locked skill directories, and verifies installed `SKILL.md`
   hashes.
4. Global guidance, repo adoption, and remote GitHub writes remain separate
   layers and require explicit authorization.
5. Complex unadopted work can use SpecRail mode without silently installing
   local skills or copying pack files.

## 验收标准

- [ ] `skills/specrail-install/SKILL.md` exists with routes for `doctor`,
      `install_local_skills`, `install_global_guidance`, and `adopt_repo`.
- [ ] `tools/install_codex_skills.py` previews install plans by default and
      applies writes only with `--apply`.
- [ ] Installer tests cover dry-run, apply sync/removal of stale files, and
      unsafe source/target refusal.
- [ ] `skills/specrail-workflow/SKILL.md` routes setup requests to
      `specrail-install` and documents autonomous SpecRail mode.
- [ ] `README.md`, `AGENT_USAGE.md`, and `PLAN.md` explain agent-first setup,
      optional local installation, and explicit authorization boundaries.
- [ ] `skills-lock.json` includes `specrail-install` and refreshed hashes.
- [ ] `python3 checks/check_workflow.py --repo . --all-specs` passes.
- [ ] `python3 -m pytest -q` passes.

## 边界情况

- User only asks whether SpecRail is installed: choose `doctor`, no writes.
- User asks for installation but not `--apply`: run dry-run first and report the
  planned target.
- Target directory overlaps the source skill directory: refuse.
- A repo is complex but has not adopted SpecRail: use existing specs/plan/docs
  locations for SpecRail mode; do not copy pack files unless asked.
- A running agent session does not discover newly installed skills: report that
  a new session may be needed.

## 发布说明

Adds an agent-facing SpecRail setup route and dry-run-first local Codex skill
installer, while keeping installation, global guidance, repo adoption, and
remote writes under explicit human authorization.
