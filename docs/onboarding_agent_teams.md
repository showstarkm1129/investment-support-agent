# Onboarding Agent Teams

Use this checklist when handing work to Claude Code Agent Teams.

## Read First

1. `system/agents/AGENTS.md`
2. the specific `system/agents/{agent}/AGENTS.md`
3. the selected flow in `system/flows/`
4. the relevant schema in `system/contracts/`
5. the run `context.json`

## Agent Rules

- Use evidence IDs when making claims.
- Separate facts from interpretation.
- Write the artifact shape required by the contract.
- Record uncertainty and missing information.
- Do not produce trade instructions.

## Handoff Shape

Each agent handoff should include:

- flow name
- target ID
- run ID
- input artifact paths
- output artifact path
- schema path
- failure policy from `system/flows/error_policy.md`

## Completion

An Agent Team task is complete only when the expected artifact exists, validates
against the contract, and the run manifest can explain what happened.
