import queue
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, List, Optional, Tuple

from .config_loader import config
from .logger_config import logger


@dataclass
class Task:
    url: str
    retry_count: int = 0
    callback: Optional[Callable] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)


@dataclass
class ChapterTask(Task):
    chapter_obj: Any = None


@dataclass
class ImageTask(Task):
    chapter_obj: Any = None
    image_filename: str = ""


class DownloadManager:
    def __init__(self):
        self.chapter_queue = queue.Queue()
        self.image_queue = queue.Queue()

        self.workers = []
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

        self.lock = threading.Lock()
        self.active_threads = 0
        self.pending_retries = 0

        self.total_chapters = 0
        self.completed_chapters = 0
        self.total_images = 0
        self.completed_images = 0
        self.failed_tasks = 0

        self.bytes_downloaded = 0
        self.start_time = time.time()
        # 瞬时速率：最近 N 秒内的 (timestamp, bytes) 滑动窗口
        self.rate_window_seconds = 5.0
        self._byte_events: Deque[Tuple[float, int]] = deque()

        self.consecutive_errors = 0
        self.is_downgraded = False

        dl_config = config.get("download", {})
        self.max_threads = dl_config.get("max_threads", 5)
        self.timeout = dl_config.get("timeout_seconds", 180)
        self.max_retries = dl_config.get("retry_attempts", 2)
        self.retry_delays = dl_config.get("retry_delays", [30, 60])

        self.on_progress = None
        self.on_rate_update = None
        self._prefer_image = False
        self._disk_pause_logged = False

    def add_chapter_task(self, task: ChapterTask):
        self.chapter_queue.put(task)
        with self.lock:
            self.total_chapters += 1
            if self.on_progress:
                self.on_progress(
                    "chapter", self.completed_chapters, self.total_chapters
                )

    def add_image_task(self, task: ImageTask):
        self.add_image_tasks([task])

    def add_image_tasks(self, tasks: List[ImageTask]):
        if not tasks:
            return
        with self.lock:
            self.total_images += len(tasks)
            if self.on_progress:
                self.on_progress("image", self.completed_images, self.total_images)
        for task in tasks:
            self.image_queue.put(task)

    def start(self):
        logger.info(f"正在启动下载管理器，使用 {self.max_threads} 个线程")
        self.stop_event.clear()
        self.start_time = time.time()
        self._disk_pause_logged = False
        with self.lock:
            self.bytes_downloaded = 0
            self._byte_events.clear()

        self.workers = []

        for i in range(self.max_threads):
            t = threading.Thread(
                target=self._worker_loop, name=f"Worker-{i}", daemon=True
            )
            t.start()
            self.workers.append(t)

        monitor_t = threading.Thread(
            target=self._monitor_loop, name="Monitor", daemon=True
        )
        monitor_t.start()

    def stop(self):
        self.stop_event.set()
        # 解除磁盘暂停，避免 worker 卡在 pause_event 上
        self.pause_event.set()
        for t in self.workers:
            t.join(timeout=1.0)

    def wait_until_complete(self):
        while not self.stop_event.is_set():
            if (
                self.chapter_queue.empty()
                and self.image_queue.empty()
                and self.active_threads == 0
                and self.pending_retries == 0
            ):
                break
            time.sleep(0.5)

    def _wait_for_disk_space(self, min_free_mb: int = 200) -> bool:
        """磁盘空间不足时暂停，并周期性复检；恢复后继续。返回是否可继续工作。"""
        if self._check_disk_space(min_free_mb=min_free_mb):
            if self._disk_pause_logged:
                logger.info("磁盘空间已恢复，继续下载。")
                self._disk_pause_logged = False
            if not self.pause_event.is_set():
                self.pause_event.set()
            return True

        if not self._disk_pause_logged:
            logger.warning("磁盘空间不足！暂停下载，将定期复检。")
            self._disk_pause_logged = True
        self.pause_event.clear()

        while not self.stop_event.is_set():
            time.sleep(5)
            if self._check_disk_space(min_free_mb=min_free_mb):
                logger.info("磁盘空间已恢复，继续下载。")
                self._disk_pause_logged = False
                self.pause_event.set()
                return True

        return False

    def _worker_loop(self):
        while not self.stop_event.is_set():
            # 支持超时，便于 stop() 后及时退出
            self.pause_event.wait(timeout=1.0)
            if self.stop_event.is_set():
                break

            if not self._wait_for_disk_space():
                break

            if self.is_downgraded:
                if threading.current_thread().name != "Worker-0":
                    time.sleep(1)
                    continue

            task = None
            task_type = None
            acquired = False
            try:
                task, task_type = self._dequeue_task()
                if not task:
                    time.sleep(0.05)
                    continue

                with self.lock:
                    self.active_threads += 1
                acquired = True

                self._process_task(task, task_type)

            except Exception as e:
                logger.error(f"工作线程错误: {e}")
            finally:
                # 仅在真正领取并计入 active 的任务上结算，避免空转/异常路径双减
                if acquired:
                    with self.lock:
                        self.active_threads -= 1
                        if task_type == "chapter":
                            self.chapter_queue.task_done()
                        else:
                            self.image_queue.task_done()

    def _process_task(self, task: Task, task_type: str):
        try:
            if task.callback:
                task.callback(*task.args, **task.kwargs)

            with self.lock:
                self.consecutive_errors = 0
                if self.is_downgraded:
                    logger.info("网络已恢复，恢复并发下载。")
                    self.is_downgraded = False

                if task_type == "chapter":
                    self.completed_chapters += 1
                else:
                    self.completed_images += 1

                if self.on_progress:
                    self.on_progress(
                        task_type,
                        self.completed_chapters
                        if task_type == "chapter"
                        else self.completed_images,
                        self.total_chapters
                        if task_type == "chapter"
                        else self.total_images,
                    )

        except Exception as e:
            logger.error(f"任务失败: {task.url}, 错误: {e}")
            self._handle_failure(task, task_type, e)

    def _try_get(self, q: queue.Queue):
        try:
            return q.get_nowait()
        except queue.Empty:
            return None

    def _dequeue_task(self):
        if self.chapter_queue.empty() and self.image_queue.empty():
            return None, None

        if not self.chapter_queue.empty() and not self.image_queue.empty():
            if self._prefer_image:
                task = self._try_get(self.image_queue)
                if task:
                    self._prefer_image = False
                    return task, "image"
                task = self._try_get(self.chapter_queue)
                if task:
                    self._prefer_image = True
                    return task, "chapter"
            else:
                task = self._try_get(self.chapter_queue)
                if task:
                    self._prefer_image = True
                    return task, "chapter"
                task = self._try_get(self.image_queue)
                if task:
                    self._prefer_image = False
                    return task, "image"
            return None, None

        if not self.chapter_queue.empty():
            task = self._try_get(self.chapter_queue)
            if task:
                self._prefer_image = True
                return task, "chapter"
            return None, None

        task = self._try_get(self.image_queue)
        if task:
            self._prefer_image = False
            return task, "image"
        return None, None

    def _handle_failure(self, task: Task, task_type: str, error: Exception):
        with self.lock:
            self.consecutive_errors += 1
            if self.consecutive_errors > 5 and not self.is_downgraded:
                logger.warning("连续错误过多，降级为单线程下载。")
                self.is_downgraded = True

        if task.retry_count < self.max_retries:
            delay = self.retry_delays[min(task.retry_count, len(self.retry_delays) - 1)]
            logger.info(
                f"将在 {delay}秒后重试任务 {task.url} (尝试 {task.retry_count + 1}/{self.max_retries})"
            )

            with self.lock:
                self.pending_retries += 1

            threading.Timer(delay, self._requeue_task, args=[task, task_type]).start()
        else:
            logger.error(f"任务永久失败: {task.url}")
            with self.lock:
                self.failed_tasks += 1
                if task_type == "chapter":
                    self.completed_chapters += 1
                else:
                    self.completed_images += 1

                if self.on_progress:
                    self.on_progress(
                        task_type,
                        self.completed_chapters
                        if task_type == "chapter"
                        else self.completed_images,
                        self.total_chapters
                        if task_type == "chapter"
                        else self.total_images,
                    )

    def _requeue_task(self, task: Task, task_type: str):
        task.retry_count += 1
        if task_type == "chapter":
            self.chapter_queue.put(task)
        else:
            self.image_queue.put(task)

        with self.lock:
            self.pending_retries -= 1

    def _check_disk_space(self, min_free_mb=200):
        try:
            total, used, free = shutil.disk_usage(".")
            return (free // (1024 * 1024)) > min_free_mb
        except Exception as e:
            logger.warning(f"检查磁盘空间失败: {e}")
            return True

    def _monitor_loop(self):
        """监控下载速率和活跃线程"""
        while not self.stop_event.is_set():
            time.sleep(1)
            rate = self.get_rate()
            if self.on_rate_update:
                self.on_rate_update(rate, self.active_threads)

    def report_bytes(self, count: int):
        """累计下载字节，并写入滑动窗口用于瞬时速率。"""
        if count <= 0:
            return
        now = time.time()
        with self.lock:
            self.bytes_downloaded += count
            self._byte_events.append((now, count))
            self._trim_byte_events(now)

    def _trim_byte_events(self, now: Optional[float] = None) -> None:
        """丢弃窗口外的采样。调用方若已持有 self.lock 可直接调用。"""
        if now is None:
            now = time.time()
        cutoff = now - self.rate_window_seconds
        while self._byte_events and self._byte_events[0][0] < cutoff:
            self._byte_events.popleft()

    def get_rate(self) -> str:
        """基于最近 rate_window_seconds 的瞬时速率（KB/s）。"""
        now = time.time()
        with self.lock:
            self._trim_byte_events(now)
            if not self._byte_events:
                return "0 KB/s"

            window_bytes = sum(nbytes for _, nbytes in self._byte_events)
            oldest_ts = self._byte_events[0][0]
            # 用实际跨度，避免窗口刚开始时被固定 5s 分母压低
            elapsed = max(now - oldest_ts, 1e-3)
            # 单点采样时用极小时间会导致虚高，至少按 0.2s 估
            if len(self._byte_events) == 1:
                elapsed = max(elapsed, 0.2)
            rate = (window_bytes / 1024.0) / elapsed
            return f"{rate:.1f} KB/s"
