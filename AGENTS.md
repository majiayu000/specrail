# AGENTS.md

This repository defines reusable repository workflow contracts. Keep changes
small, explicit, and verifiable.

## Rules

- Search before adding a new workflow, schema, template, check, or policy.
- Prefer deterministic checks before LLM or agent automation.
- Do not grant agents final approval, merge, or security-disclosure authority.
- Keep templates generic; repository-specific behavior belongs in examples or
  consumer overlays.
- Preserve the dry-run default for all GitHub automation.

## Validation

Run before completion after changing workflow assets:

```sh
python3 checks/check_workflow.py --repo .
```

