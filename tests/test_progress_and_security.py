from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock

from src.client import _redact_headers, _truncate_text
from src.download_manager import DownloadManager
from src.progress_ui import (
    AlignedMofNCompleteColumn,
    bind_download_progress,
    create_download_progress,
)


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
        self.assertIn("AlignedMofNCompleteColumn", column_types)
        # 百分比在 m/n 之前
        self.assertLess(
            column_types.index("TaskProgressColumn"),
            column_types.index("AlignedMofNCompleteColumn"),
        )

    def test_mofn_slash_aligns_across_tasks(self):
        progress = create_download_progress()
        mofn = next(
            c for c in progress.columns if isinstance(c, AlignedMofNCompleteColumn)
        )
        # 模拟两行：章节 22/153、图片 10/12
        chapter = type("T", (), {"completed": 22, "total": 153})()
        image = type("T", (), {"completed": 10, "total": 12})()
        # 先渲染位数更大的，再渲染小的，宽度应保持
        s1 = str(mofn.render(chapter))
        s2 = str(mofn.render(image))
        self.assertEqual(s1.index("/"), s2.index("/"), f"{s1!r} vs {s2!r}")
        # 反向顺序预热也应对齐
        progress2 = create_download_progress()
        mofn2 = next(
            c for c in progress2.columns if isinstance(c, AlignedMofNCompleteColumn)
        )
        # bind 会用章节 total 预热；这里手动预热
        mofn2.state.total_width = 3
        mofn2.state.completed_width = 3
        a = str(mofn2.render(image))
        b = str(mofn2.render(chapter))
        self.assertEqual(a.index("/"), b.index("/"), f"{a!r} vs {b!r}")

class SlidingRateTest(unittest.TestCase):
    def test_rate_uses_recent_window_not_lifetime_average(self):
        mgr = DownloadManager()
        mgr.rate_window_seconds = 5.0
        # 模拟：很久以前下了很多，最近几乎没下 -> 瞬时应接近 0，而不是被历史均值抬高
        old = time.time() - 30
        with mgr.lock:
            mgr.bytes_downloaded = 10 * 1024 * 1024  # 10MB 历史总量
            mgr._byte_events.append((old, 10 * 1024 * 1024))
            mgr.start_time = old
        # 修剪后窗口应为空
        self.assertEqual(mgr.get_rate(), "0 KB/s")

    def test_rate_reflects_recent_burst(self):
        mgr = DownloadManager()
        mgr.rate_window_seconds = 5.0
        now = time.time()
        # 在窗口内写入约 100KB，跨度约 1s
        with mgr.lock:
            mgr._byte_events.append((now - 1.0, 50 * 1024))
            mgr._byte_events.append((now - 0.1, 50 * 1024))
            mgr.bytes_downloaded = 100 * 1024
        rate_str = mgr.get_rate()
        self.assertTrue(rate_str.endswith("KB/s"))
        value = float(rate_str.split()[0])
        # 100KB / ~1s ≈ 100 KB/s，允许一定误差
        self.assertGreater(value, 50.0)
        self.assertLess(value, 200.0)

    def test_report_bytes_appends_and_trims(self):
        mgr = DownloadManager()
        mgr.rate_window_seconds = 1.0
        mgr.report_bytes(1024)
        self.assertEqual(len(mgr._byte_events), 1)
        # 手工塞入过期事件再 report 触发 trim
        with mgr.lock:
            mgr._byte_events.appendleft((time.time() - 10, 999))
        mgr.report_bytes(2048)
        # 过期事件应被裁掉，仅保留窗口内
        self.assertTrue(all(time.time() - ts <= 1.5 for ts, _ in mgr._byte_events))


if __name__ == "__main__":
    unittest.main()
