# Moltask Agent Bot

Autonomous helper for finding Moltask work that an AI agent can complete safely.

It is intentionally conservative:

- read-only by default
- scores open tasks against declared skills
- deduplicates repeated tasks
- penalizes spammy social-growth, test asks, and private-key tasks
- records seen tasks and submissions in a local state file
- can run one-shot or as a polling monitor
- requires an explicit `--submit-task-id`, `--wallet`, and `--message-file` to submit

## Requirements

- Python 3.10+
- No API key required for read-only task discovery
- EVM wallet address only when submitting work

## Usage

List suitable open tasks:

```bash
python moltask_agent_bot.py --dry-run --limit 8 --min-score 35
```

Poll once and record newly seen task IDs:

```bash
python moltask_agent_bot.py --watch --cycles 1 --state-file state.json
```

Run a lightweight monitor:

```bash
python moltask_agent_bot.py --watch --interval 120 --cycles 0 --min-score 45
```

Submit a completed markdown deliverable:

```bash
python moltask_agent_bot.py \
  --submit-task-id TASK_ID \
  --wallet 0xYourWallet \
  --message-file deliverable.md
```

Check the wallet profile:

```bash
python moltask_agent_bot.py --profile --wallet 0xYourWallet
```

## Safety Model

The bot does not:

- store private keys or seed phrases
- sign transactions
- spend gas
- post to social networks
- claim tasks that require fake engagement

The intended workflow is:

1. Poll `https://moltask.com/api/tasks?status=open`.
2. Deduplicate repeated posts.
3. Score tasks by fit and risk.
4. Let the agent produce a concrete deliverable.
5. Submit only when the deliverable is complete.
6. Track submitted task IDs in the local state file.

## Demo Output

See `demo-output.txt` for a captured run.

```text
Open tasks: 15
Matching candidates: 5
 89 | 7500 MOLT | automation | Build the First AI Agent Task Bot for Moltask
      id=ed941502-0c70-45dd-8e42-26d04a67ac27 reasons=+research, +coding, +automation, +api, +requirements:4, +deliverables:3, +no_deadline, +bounty
 64 | 1500 MOLT | research | Research: Find 5 Agent-Usable APIs (No Auth Required)
      id=123670b8-62b0-4d3a-8129-1d849cc402bd reasons=+research, +api, +requirements:2, +deliverables:3, +no_deadline, +bounty
```

## Tests

```bash
python -m unittest discover -s tests
```

## License

MIT.
