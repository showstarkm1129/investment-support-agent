# Flow Scripts

Flow scripts are reusable Agent Team presets. A script fixes the target, flow,
agent order, default provider, and output expectations so the UI can run or
edit the workflow without changing Python code.

Use:

```bash
python scripts/run_flow.py --script semiconductor_sector_morning --mode simulate
```

The generated run folder contains `context.json`, `manifest.json`,
`agent_trace.json`, and one prompt file per planned Agent step.
