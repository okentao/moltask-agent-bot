#!/usr/bin/env python3
"""Small Moltask watcher for AI agents.

The bot lists open Moltask tasks, scores them against local agent skills, and
can submit a dry-run or real response. It defaults to read-only behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


API_BASE = "https://moltask.com/api"
DEFAULT_STATE_FILE = ".moltask-agent-bot-state.json"
DEFAULT_SKILLS = {
    "research": 35,
    "writing": 25,
    "data": 20,
    "coding": 20,
    "automation": 15,
    "documentation": 15,
    "api": 15,
    "testing": 10,
}
AVOID_TERMS = {
    "viral": -40,
    "upvotes": -35,
    "followers": -35,
    "tweet": -25,
    "private key": -60,
    "seed phrase": -80,
    "deposit": -40,
    "gpu": -20,
    "test ask": -25,
}


@dataclass
class Candidate:
    task: dict[str, Any]
    score: int
    reasons: list[str]


def request_json(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {"Accept": "application/json", "User-Agent": "moltask-agent-bot/0.1"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {payload}") from exc


def fetch_open_tasks() -> list[dict[str, Any]]:
    payload = request_json("/tasks?status=open")
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise RuntimeError("Unexpected /tasks response: missing tasks array")
    return tasks


def task_fingerprint(task: dict[str, Any]) -> str:
    return "|".join(
        str(task.get(key, "")).strip().lower()
        for key in ("title", "poster_address", "bounty_amount")
    )


def dedupe_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for task in tasks:
        key = task_fingerprint(task)
        if key in seen:
            continue
        seen.add(key)
        unique.append(task)
    return unique


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen_task_ids": [], "submissions": []}
    with path.open("r", encoding="utf-8") as fh:
        state = json.load(fh)
    state.setdefault("seen_task_ids", [])
    state.setdefault("submissions", [])
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def remember_seen(path: Path, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    state = load_state(path)
    seen = set(state.get("seen_task_ids", []))
    new_tasks = [task for task in tasks if task.get("id") not in seen]
    if new_tasks:
        seen.update(str(task.get("id")) for task in new_tasks if task.get("id"))
        state["seen_task_ids"] = sorted(seen)
        save_state(path, state)
    return new_tasks


def remember_submission(path: Path, task_id: str, wallet: str, result: Any) -> None:
    state = load_state(path)
    state.setdefault("submissions", []).append(
        {
            "task_id": task_id,
            "wallet": wallet.lower(),
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "result": result,
        }
    )
    save_state(path, state)


def score_task(task: dict[str, Any]) -> Candidate:
    text = " ".join(
        str(task.get(key, ""))
        for key in ("title", "description", "category")
    ).lower()
    score = 0
    reasons: list[str] = []

    for term, points in DEFAULT_SKILLS.items():
        if term in text:
            score += points
            reasons.append(f"+{points} {term}")

    for term, points in AVOID_TERMS.items():
        if term in text:
            score += points
            reasons.append(f"{points} avoid:{term}")

    requirements = task.get("requirements") or []
    deliverables = task.get("deliverables") or []
    if requirements:
        score += min(len(requirements) * 3, 12)
        reasons.append(f"+requirements:{len(requirements)}")
    if deliverables:
        score += min(len(deliverables) * 3, 12)
        reasons.append(f"+deliverables:{len(deliverables)}")

    if not task.get("deadline"):
        score += 4
        reasons.append("+no_deadline")
    if str(task.get("bounty_amount", "0")).isdigit():
        score += min(int(task["bounty_amount"]) // 500, 20)
        reasons.append("+bounty")

    return Candidate(task=task, score=score, reasons=reasons)


def safe_text(value: Any) -> str:
    return str(value).encode("ascii", errors="replace").decode("ascii")


def summarize(candidate: Candidate) -> str:
    task = candidate.task
    desc = safe_text(task.get("description", "")).replace("\n", " ")
    if len(desc) > 180:
        desc = desc[:177] + "..."
    return (
        f"{candidate.score:>3} | {task.get('bounty_amount', '?')} MOLT | "
        f"{safe_text(task.get('category', 'other'))} | {safe_text(task.get('title'))}\n"
        f"      id={task.get('id')} reasons={', '.join(candidate.reasons)}\n"
        f"      {desc}"
    )


def submit_work(task_id: str, wallet: str, message: str) -> Any:
    if not wallet.startswith("0x") or len(wallet) != 42:
        raise ValueError("wallet must be an EVM address")
    return request_json(
        f"/tasks/{urllib.parse.quote(task_id)}/submit",
        method="POST",
        body={"worker_address": wallet, "message": message},
    )


def fetch_profile(wallet: str) -> Any:
    if not wallet.startswith("0x") or len(wallet) != 42:
        raise ValueError("wallet must be an EVM address")
    return request_json(f"/profile?address={urllib.parse.quote(wallet)}")


def build_candidates(tasks: list[dict[str, Any]], dedupe: bool = True) -> list[Candidate]:
    source = dedupe_tasks(tasks) if dedupe else tasks
    return sorted((score_task(task) for task in source), key=lambda c: c.score, reverse=True)


def print_candidates(candidates: list[Candidate], limit: int, min_score: int) -> int:
    visible = [c for c in candidates if c.score >= min_score][:limit]
    print(f"Matching candidates: {len(visible)}")
    for candidate in visible:
        print(summarize(candidate))
    return len(visible)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor and score Moltask bounties")
    parser.add_argument("--limit", type=int, default=10, help="number of candidates to print")
    parser.add_argument("--min-score", type=int, default=35, help="minimum score to show")
    parser.add_argument("--submit-task-id", help="submit work to this task id")
    parser.add_argument("--wallet", default=os.getenv("MOLTASK_WALLET", ""))
    parser.add_argument("--message-file", help="markdown file to submit")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="local JSON state file")
    parser.add_argument("--watch", action="store_true", help="poll for new tasks")
    parser.add_argument("--interval", type=int, default=60, help="seconds between watch polls")
    parser.add_argument("--cycles", type=int, default=1, help="watch cycles; 0 means forever")
    parser.add_argument("--no-dedupe", action="store_true", help="show duplicate task posts too")
    parser.add_argument("--profile", action="store_true", help="fetch the wallet profile and exit")
    parser.add_argument("--dry-run", action="store_true", help="never submit, only print")
    args = parser.parse_args()
    state_path = Path(args.state_file)

    if args.profile:
        if not args.wallet:
            parser.error("--wallet is required for --profile")
        print(json.dumps(fetch_profile(args.wallet), indent=2))
        return 0

    if args.submit_task_id:
        if args.dry_run:
            print(f"DRY RUN: would submit {args.message_file!r} to {args.submit_task_id}")
            return 0
        if not args.wallet or not args.message_file:
            parser.error("--wallet and --message-file are required when submitting")
        with open(args.message_file, "r", encoding="utf-8") as fh:
            message = fh.read()
        result = submit_work(args.submit_task_id, args.wallet, message)
        remember_submission(state_path, args.submit_task_id, args.wallet, result)
        print(json.dumps(result, indent=2))
        return 0

    cycle = 0
    while True:
        tasks = fetch_open_tasks()
        candidates = build_candidates(tasks, dedupe=not args.no_dedupe)
        new_tasks = remember_seen(state_path, tasks) if args.watch else tasks
        print(f"Open tasks: {len(tasks)}")
        if args.watch:
            print(f"New tasks this cycle: {len(new_tasks)}")
        visible_count = print_candidates(candidates, args.limit, args.min_score)
        if visible_count == 0:
            print(textwrap.dedent(
                """\
                No suitable tasks met the threshold. Lower --min-score or wait for
                a new heartbeat cycle rather than claiming poor-fit work.
                """
            ).strip())

        if not args.watch:
            break
        cycle += 1
        if args.cycles and cycle >= args.cycles:
            break
        time.sleep(max(args.interval, 5))
    return 0


if __name__ == "__main__":
    sys.exit(main())
