from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock

from src.client import _redact_headers, _truncate_text
from src.progress_ui import bind_download_progress, create_download_progress


class SecurityHelpersTest(unittest.TestCase):
    def test_redact_headers(self):
        headers = {
            "User-Agent": "test-agent",
            "Cookie": "session=secret",
            "Set-Cookie": "token=abc",
            "Authorization": "Bearer xyz",
        }
        redacted = _redact_headers(headers)
        self.assertEqual(redacted["User-Agent"], "test-agent")
        self.assertEqual(redacted["Cookie"], "[REDACTED]")
        self.assertEqual(redacted["Set-Cookie"], "[REDACTED]")
        self.assertEqual(redacted["Authorization"], "[REDACTED]")

    def test_truncate_text(self):
        text = "a" * 100
        out = _truncate_text(text, limit=20)
        self.assertTrue(out.startswith("a" * 20))
        self.assertIn("truncated", out)


class ProgressBindTest(unittest.TestCase):
    def test_image_total_grows_dynamically(self):
        progress = MagicMock()
        # add_task called twice -> chapter id 0, image id 1
        progress.add_task.side_effect = [0, 1]
        lock = threading.Lock()
        progress_cb, rate_cb = bind_download_progress(progress, 10, lock=lock)

        progress_cb("chapter", 3, 10)
        progress_cb("image", 1, 3)
        progress_cb("image", 2, 5)
        rate_cb("12.3 KB/s", 2)

        # chapter update
        self.assertEqual(
            progress.update.call_args_list[0].args[0],
            0,
        )
        self.assertEqual(progress.update.call_args_list[0].kwargs["completed"], 3)
        self.assertEqual(progress.update.call_args_list[0].kwargs["total"], 10)

        # image first total 3, then 5
        self.assertEqual(progress.update.call_args_list[1].kwargs["completed"], 1)
        self.assertEqual(progress.update.call_args_list[1].kwargs["total"], 3)
        self.assertEqual(progress.update.call_args_list[2].kwargs["completed"], 2)
        self.assertEqual(progress.update.call_args_list[2].kwargs["total"], 5)

        # rate updates both tasks
        self.assertIn("速率: 12.3 KB/s", progress.update.call_args_list[3].kwargs["info"])

    def test_create_progress_has_mofn_column(self):
        progress = create_download_progress()
        column_types = [type(c).__name__ for c in progress.columns]
        self.assertIn("TaskProgressColumn", column_types)
        self.assertIn("MofNCompleteColumn", column_types)
        # 百分比在 m/n 之前
        self.assertLess(
            column_types.index("TaskProgressColumn"),
            column_types.index("MofNCompleteColumn"),
        )


if __name__ == "__main__":
    unittest.main()
