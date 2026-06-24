# Operations

## Daily Close Run

1. Confirm target and source config.
2. Run `scripts/run_flow.py --flow close_report --target-id TARGET-SAMPLE-6501`.
3. Confirm `manifest.json` and `context.json` were created under `runs/`.
4. Run collection and Agent Teams using the generated context.
5. Validate artifacts against `contracts/`.
6. Generate reports and app pages.
7. Review health warnings before publishing.

## Morning Run

Use `morning_report` when the goal is pre-market context. It should reuse the
latest close run when useful and explicitly mark overnight gaps.

## Chat Runs

Start with `chat_quick` or `chat_context`. Escalate to `chat_agent` or
`chat_research` only when the question needs more reasoning or new facts.

## Failure Handling

Keep partial run artifacts. A failed run is still useful when it has a manifest
and health output explaining what failed.
