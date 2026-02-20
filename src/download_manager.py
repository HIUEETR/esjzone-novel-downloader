import threading
import time
import queue
import logging
import shutil
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, List, Dict
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor

from .logger_config import logger
from .config_loader import config

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
        self.pause_event.set() # 初始状态为运行中
        
        self.lock = threading.Lock()
        self.active_threads = 0
        
        # 统计数据
        self.total_chapters = 0
        self.completed_chapters = 0
        self.total_images = 0
        self.completed_images = 0
        self.failed_tasks = 0
        
        # 速率监控
        self.bytes_downloaded = 0
        self.start_time = time.time()
        
        # 错误处理
        self.consecutive_errors = 0
        self.is_downgraded = False
        
        # 加载配置
        dl_config = config.get('download', {})
        self.max_threads = dl_config.get('max_threads', 5)
        self.timeout = dl_config.get('timeout_seconds', 180)
        # 默认重试次数改为2次，符合用户需求
        self.max_retries = dl_config.get('retry_attempts', 2)
        self.retry_delays = dl_config.get('retry_delays', [30, 60])
        
        # 回调函数
        self.on_progress = None # Function(type, completed, total)
        self.on_rate_update = None # Function(rate_str)

    def add_chapter_task(self, task: ChapterTask):
        self.chapter_queue.put(task)
        with self.lock:
            self.total_chapters += 1
            if self.on_progress:
                self.on_progress('chapter', self.completed_chapters, self.total_chapters)

    def add_image_task(self, task: ImageTask):
        self.add_image_tasks([task])

    def add_image_tasks(self, tasks: List[ImageTask]):
        if not tasks:
            return
        with self.lock:
            self.total_images += len(tasks)
            if self.on_progress:
                self.on_progress('image', self.completed_images, self.total_images)
        for task in tasks:
            self.image_queue.put(task)
    
    def start(self):
        logger.info(f"正在启动下载管理器，使用 {self.max_threads} 个线程")
        self.stop_event.clear()
        self.start_time = time.time()
        
        # 清除现有工作线程（如果存在）
        self.workers = []
        
        for i in range(self.max_threads):
            t = threading.Thread(target=self._worker_loop, name=f"Worker-{i}", daemon=True)
            t.start()
            self.workers.append(t)
            
        # 启动监控线程
        monitor_t = threading.Thread(target=self._monitor_loop, name="Monitor", daemon=True)
        monitor_t.start()
            
    def stop(self):
        self.stop_event.set()
        for t in self.workers:
            t.join(timeout=1.0)
            
    def wait_until_complete(self):
        while not self.stop_event.is_set():
            if self.chapter_queue.empty() and self.image_queue.empty() and self.active_threads == 0:
                break
            time.sleep(0.5)

    def _worker_loop(self):
        while not self.stop_event.is_set():
            # 检查暂停状态
            self.pause_event.wait()
            
            # 检查磁盘空间
            if not self._check_disk_space():
                logger.warning("磁盘空间不足！暂停下载。")
                self.pause_event.clear()
                continue

            # 降级逻辑
            if self.is_downgraded:
                if threading.current_thread().name != "Worker-0":
                    time.sleep(1)
                    continue

            try:
                # 优先级: 章节 > 图片
                task = None
                task_type = None
                
                try:
                    task = self.chapter_queue.get_nowait()
                    task_type = 'chapter'
                except queue.Empty:
                    try:
                        task = self.image_queue.get_nowait()
                        task_type = 'image'
                    except queue.Empty:
                        time.sleep(0.1)
                        continue
                
                with self.lock:
                    self.active_threads += 1
                
                self._process_task(task, task_type)
                
            except Exception as e:
                logger.error(f"工作线程错误: {e}")
            finally:
                if task:
                    with self.lock:
                        self.active_threads -= 1
                        if task_type == 'chapter':
                            self.chapter_queue.task_done()
                        else:
                            self.image_queue.task_done()

    def _process_task(self, task: Task, task_type: str):
        try:
            # 执行任务
            if task.callback:
                task.callback(*task.args, **task.kwargs)
            
            # 成功
            with self.lock:
                self.consecutive_errors = 0
                if self.is_downgraded:
                    logger.info("网络已恢复，恢复并发下载。")
                    self.is_downgraded = False
                
                if task_type == 'chapter':
                    self.completed_chapters += 1
                else:
                    self.completed_images += 1
                
                if self.on_progress:
                    self.on_progress(task_type, 
                                   self.completed_chapters if task_type == 'chapter' else self.completed_images,
                                   self.total_chapters if task_type == 'chapter' else self.total_images)
                                   
        except Exception as e:
            logger.error(f"任务失败: {task.url}, 错误: {e}")
            self._handle_failure(task, task_type, e)

    def _handle_failure(self, task: Task, task_type: str, error: Exception):
        with self.lock:
            self.consecutive_errors += 1
            if self.consecutive_errors > 5 and not self.is_downgraded:
                logger.warning("连续错误过多，降级为单线程下载。")
                self.is_downgraded = True
        
        if task.retry_count < self.max_retries:
            delay = self.retry_delays[min(task.retry_count, len(self.retry_delays)-1)]
            logger.info(f"将在 {delay}秒后重试任务 {task.url} (尝试 {task.retry_count+1}/{self.max_retries})")
            
            # 启动定时器线程重新入队
            threading.Timer(delay, self._requeue_task, args=[task, task_type]).start()
        else:
            logger.error(f"任务永久失败: {task.url}")
            with self.lock:
                self.failed_tasks += 1
                # 即使失败也视为已处理，以避免阻塞进度条
                if task_type == 'chapter':
                    self.completed_chapters += 1
                else:
                    self.completed_images += 1
                
                if self.on_progress:
                    self.on_progress(task_type, 
                                   self.completed_chapters if task_type == 'chapter' else self.completed_images,
                                   self.total_chapters if task_type == 'chapter' else self.total_images)

    def _requeue_task(self, task: Task, task_type: str):
        task.retry_count += 1
        if task_type == 'chapter':
            self.chapter_queue.put(task)
        else:
            self.image_queue.put(task)

    def _check_disk_space(self, min_free_mb=200):
        try:
            total, used, free = shutil.disk_usage(".")
            return (free // (1024 * 1024)) > min_free_mb
        except:
            return True

    def _monitor_loop(self):
        """监控下载速率和活跃线程"""
        while not self.stop_event.is_set():
            time.sleep(1)
            rate = self.get_rate()
            if self.on_rate_update:
                self.on_rate_update(rate, self.active_threads)

            
    def report_bytes(self, count: int):
        with self.lock:
            self.bytes_downloaded += count

    def get_rate(self) -> str:
        elapsed = time.time() - self.start_time
        if elapsed <= 0: return "0 KB/s"
        rate = (self.bytes_downloaded / 1024) / elapsed
        return f"{rate:.1f} KB/s"
