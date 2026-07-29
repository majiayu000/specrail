---
name: implx
description: Use only when the user explicitly says implx. Inventory and drain the actionable issue and PR queue using current GitHub state, original branches, repository-native verification, and the caller's external-action authorization.
---

# Implx

Delegate the full queue workflow to
`skills/specrail-implement-queue/SKILL.md`.

Plain `implx` processes the full actionable queue unless the caller limits the
scope. `implx auto` permits unattended continuation only for the named run and
does not broaden repository, security, or external-action authority.

Start from current GitHub Issues, PRs, reviews, CI, and remote branches. Finish
existing PRs before creating replacement work. Report every blocked item and
the exact next action.
