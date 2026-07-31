"""下载进度条 UI：统一列布局，跨任务对齐 completed/total。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskProgressColumn,
    Text,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Column


@dataclass
class _MofNWidthState:
    """两行进度条共享的位数状态，保证斜杠纵向对齐"""

    completed_width: int = 1
    total_width: int = 1


class AlignedMofNCompleteColumn(ProgressColumn):
    """跨 task 对齐的 completed/total 列"""

    def __init__(
        self,
        state: Optional[_MofNWidthState] = None,
        separator: str = "/",
        table_column: Optional[Column] = None,
    ) -> None:
        self.state = state or _MofNWidthState()
        self.separator = separator
        super().__init__(table_column or Column(no_wrap=True, justify="right"))

    def render(self, task) -> Text:
        completed = int(task.completed)
        if task.total is None:
            total_str = "?"
            total_len = 1
        else:
            total_int = max(int(task.total), 0)
            total_str = str(total_int)
            total_len = len(total_str)

        completed_len = len(str(completed))
        # 位数只增不减，避免进度前进时列宽来回跳
        self.state.total_width = max(self.state.total_width, total_len)
        self.state.completed_width = max(
            self.state.completed_width,
            completed_len,
            self.state.total_width,
        )

        text = (
            f"{completed:>{self.state.completed_width}d}"
            f"{self.separator}"
            f"{total_str:<{self.state.total_width}}"
        )
        return Text(text, style="progress.download")


def create_download_progress() -> Progress:
    """
    创建统一的章节/图片下载进度条。

    列顺序: 描述 | 条 | 百分比 | completed/total | 剩余时间 | Spinner | 速率信息
    示例: 下载章节 ━… 10%  3/100  0:00:33 ⠦ 速率: 2109.9 KB/s, 线程: 5
    """
    mofn_state = _MofNWidthState()
    return Progress(
        TextColumn(
            "[progress.description]{task.description}",
            justify="left",
        ),
        BarColumn(),
        TaskProgressColumn(),
        AlignedMofNCompleteColumn(state=mofn_state),
        TimeRemainingColumn(compact=True, elapsed_when_finished=True),
        SpinnerColumn(),
        TextColumn("{task.fields[info]}"),
    )


def bind_download_progress(
    progress: Progress,
    chapter_total: int,
    *,
    lock: Optional[threading.Lock] = None,
) -> Tuple[Callable, Callable]:
    """注册章节/图片任务并返回线程安全的进度与速率回调。

    图片 total 初始为 0，可在下载过程中随 add_image_tasks 动态增大。
    """
    pbar_lock = lock or threading.Lock()
    safe_chapter_total = max(int(chapter_total), 0)

    # 预热 MofN 列宽：用章节 total 先占位，避免图片行先渲染时宽度过窄
    for column in progress.columns:
        if isinstance(column, AlignedMofNCompleteColumn):
            tw = len(str(safe_chapter_total)) if safe_chapter_total else 1
            column.state.total_width = max(column.state.total_width, tw)
            column.state.completed_width = max(column.state.completed_width, tw)
            break

    chapter_task_id = progress.add_task(
        "下载章节",
        total=safe_chapter_total,
        info="",
    )
    image_task_id = progress.add_task("下载图片", total=0, info="")

    def progress_callback(task_type: str, completed: int, total: int) -> None:
        with pbar_lock:
            if task_type == "chapter":
                progress.update(
                    chapter_task_id,
                    completed=completed,
                    total=total if total is not None else safe_chapter_total,
                )
            else:
                # 图片总数可能随章节解析动态增长；total<=0 时保持当前 total
                kwargs = {"completed": completed}
                if total is not None and total > 0:
                    kwargs["total"] = total
                progress.update(image_task_id, **kwargs)

    def rate_callback(rate: str, threads: int) -> None:
        info_str = f"速率: {rate}, 线程: {threads}"
        with pbar_lock:
            progress.update(chapter_task_id, info=info_str)
            progress.update(image_task_id, info=info_str)

    return progress_callback, rate_callback
