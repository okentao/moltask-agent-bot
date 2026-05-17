import tempfile
import unittest
from pathlib import Path

import moltask_agent_bot as bot


class MoltaskAgentBotTests(unittest.TestCase):
    def test_scores_research_api_task_above_marketing_task(self):
        research = {
            "id": "research",
            "title": "Research: Find 5 Agent-Usable APIs",
            "description": "Find APIs without authentication and provide curl examples.",
            "category": "research",
            "requirements": ["API testing"],
            "deliverables": ["README.md"],
            "bounty_amount": "1500",
        }
        marketing = {
            "id": "marketing",
            "title": "Viral marketing campaign",
            "description": "Get upvotes and followers from social posts.",
            "category": "marketing",
            "requirements": ["50 upvotes"],
            "deliverables": ["screenshots"],
            "bounty_amount": "3000",
        }

        self.assertGreater(bot.score_task(research).score, bot.score_task(marketing).score)

    def test_dedupes_repeated_tasks_by_content_and_poster(self):
        first = {
            "id": "1",
            "title": "Same Task",
            "description": "Do the same thing",
            "poster_address": "0xabc",
        }
        second = {
            "id": "2",
            "title": "same task",
            "description": "Do the same thing",
            "poster_address": "0xABC",
        }

        self.assertEqual([task["id"] for task in bot.dedupe_tasks([first, second])], ["1"])

    def test_remember_seen_tracks_only_new_task_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            tasks = [{"id": "a"}, {"id": "b"}]

            first = bot.remember_seen(path, tasks)
            second = bot.remember_seen(path, tasks)

            self.assertEqual([task["id"] for task in first], ["a", "b"])
            self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
