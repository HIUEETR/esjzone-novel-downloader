import json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional
import concurrent.futures
import questionary
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

import time
from src.logger_config import logger
from src.config_loader import config
from src.client import EsjzoneDownloader
from src.model import Book
from src.utils import clear_screen, truncate_and_pad

DATA_DIR = Path("data")
MONITOR_FILE = DATA_DIR / "monitor.json"
LATEST_FILE = DATA_DIR / "latest.json"

from src.download_manager import DownloadManager, ChapterTask, ImageTask
from src.epub import build_epub

console = Console()

class MonitorManager:
    def __init__(self):
        self.ensure_data_dir()

    def ensure_data_dir(self):
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)

    def load_json(self, file_path: Path) -> List[Dict]:
        if not file_path.exists():
            return []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 {file_path} 失败: {e}")
            return []

    def save_json(self, file_path: Path, data: List[Dict]):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存 {file_path} 失败: {e}")

    def configure_monitor(self, favorites_manager):
        """配置监控列表"""
        # 1. 选择来源列表
        choices = [
            questionary.Choice("从 '最近更新' 列表选择", value="new"),
            questionary.Choice("从 '最近收藏' 列表选择", value="favor"),
            "返回上一级菜单"
        ]
        
        source = questionary.select(
            "请选择小说来源：",
            choices=choices,
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if source == "返回上一级菜单":
            return

        # 2. 获取小说列表
        # 确保数据已更新
        logger.info("正在加载收藏列表...")
        favorites_manager.ensure_updated(source)
        novels = favorites_manager.get_novels(source)
        
        if not novels:
            logger.warning("列表为空！")
            return

        # 3. 加载当前监控列表
        current_monitor_list = self.load_json(MONITOR_FILE)
        # 使用字典存储，方便查找和更新
        monitored_novels = {item['url']: item for item in current_monitor_list}
        
        # 4. 分页显示与交互
        page = 1
        items_per_page = 10
        
        while True:
            clear_screen()
            
            total_novels = len(novels)
            if total_novels == 0:
                total_pages = 1
            else:
                total_pages = (total_novels + items_per_page - 1) // items_per_page
                
            # 确保页码在有效范围内
            if page > total_pages:
                page = total_pages
            if page < 1:
                page = 1
                
            # 获取当前页的小说
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            current_novels = novels[start_idx:end_idx]
            
            choices = []
            choices.append(questionary.Separator(f"--- 第 {page} / {total_pages} 页 ⌈ 共 {total_novels} 本 ⌋ ---"))
            choices.append(questionary.Separator(f"--- 已监控: {len(monitored_novels)} 本 ---"))
            
            # 表头
            title_width = 30
            header_title = truncate_and_pad("标题", title_width)
            header = f"{'状态':<4}   {header_title}      {'最新章节'}"
            choices.append(questionary.Separator(header))
            
            for novel in current_novels:
                url = novel['url']
                title = novel.get('title', '未知标题')
                latest = novel.get('latest_chapter', '')
                
                is_monitored = url in monitored_novels
                status_mark = "[√]" if is_monitored else "[ ]"
                
                display_title = truncate_and_pad(title, title_width)
                display_latest = truncate_and_pad(latest, 20)
                
                label = f"{status_mark:<4}   {display_title}      {display_latest}"
                choices.append(questionary.Choice(label, value=novel))
                
            choices.append(questionary.Separator("--- 操作 ---"))
            
            if page > 1:
                choices.append(questionary.Choice(f"← 上一页 ⌈ 第 {page-1} 页 ⌋", value="prev"))
            if page < total_pages:
                choices.append(questionary.Choice(f"→ 下一页 ⌈ 第 {page+1} 页 ⌋", value="next"))
            if total_pages > 1:
                choices.append(questionary.Choice("跳转页码", value="jump"))
                
            choices.append(questionary.Choice("保存并退出", value="save"))
            choices.append(questionary.Choice("不保存退出", value="cancel"))
            
            selection = questionary.select(
                "请选择要切换监控状态的小说：",
                choices=choices,
                instruction="⌈ 使用↑↓翻页/选择，回车切换状态 ⌋"
            ).ask()
            
            if selection == "save":
                # 保存到 monitor.json
                final_list = list(monitored_novels.values())
                self.save_json(MONITOR_FILE, final_list)
                logger.info(f"监控列表已更新，当前共监控 {len(final_list)} 本小说。")
                time.sleep(1.5)
                break
            elif selection == "cancel":
                break
            elif selection == "prev":
                page -= 1
            elif selection == "next":
                page += 1
            elif selection == "jump":
                val = questionary.text(f"请输入页码 ⌈ 1-{total_pages} ⌋：").ask()
                if val and val.isdigit():
                    target_page = int(val)
                    if 1 <= target_page <= total_pages:
                        page = target_page
            elif isinstance(selection, dict):
                # 切换状态
                url = selection['url']
                if url in monitored_novels:
                    del monitored_novels[url]
                else:
                    # 添加到监控列表
                    monitored_novels[url] = {
                        "title": selection.get('title'),
                        "url": url
                    }
                # 不退出循环，刷新页面显示新状态

    def fetch_novel_status(self, downloader: EsjzoneDownloader, novel_entry: Dict) -> Optional[Dict]:
        """获取单本小说的最新状态"""
        url = novel_entry.get('url')
        title = novel_entry.get('title')
        if not url:
            return None
            
        try:
            # 仅获取信息，不下载图片
            status = downloader.get_novel_status(url)
            
            return {
                "title": status.get('title') or title,
                "url": url,
                "update_chapter": status.get('latest_chapter', ''),
                "update_time": status.get('update_time', '未知时间')
            }
        except Exception as e:
            logger.error(f"检查更新失败 {title}: {e}")
            return None

    def start_check(self, downloader: EsjzoneDownloader):
        """开始检查更新"""
        monitor_list = self.load_json(MONITOR_FILE)
        if not monitor_list:
            logger.warning("监控列表为空，请先进行配置！")
            input("\n按回车键继续...")
            return

        logger.info(f"开始检查 {len(monitor_list)} 本小说的更新情况...")
        
        latest_data = self.load_json(LATEST_FILE)
        # 建立 URL 到 entry 的映射方便查找
        latest_map = {item['url']: item for item in latest_data}
        
        updated_novels = []
        
        # 多线程检查
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task("正在检查更新...", total=len(monitor_list))
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_novel = {
                    executor.submit(self.fetch_novel_status, downloader, novel): novel 
                    for novel in monitor_list
                }
                
                for future in concurrent.futures.as_completed(future_to_novel):
                    novel = future_to_novel[future]
                    try:
                        result = future.result()
                        if result:
                            url = result['url']
                            entry = latest_map.get(url)
                            
                            if not entry:
                                # 新增记录
                                entry = {
                                    "title": result['title'],
                                    "url": url,
                                    "latest_chapter": "", # 初始为空
                                    "update_time": result['update_time'],
                                    "update_chapter": result['update_chapter']
                                }
                                # 逻辑：如果 latest_chapter 为空，则将 update_chapter 写入 latest_chapter
                                # 这意味着初次添加时不提示更新，认为已读
                                entry['latest_chapter'] = result['update_chapter']
                                latest_map[url] = entry
                            else:
                                # 更新现有记录的 update_chapter 和 update_time
                                entry['update_chapter'] = result['update_chapter']
                                entry['update_time'] = result['update_time']
                                # 注意：这里不更新 latest_chapter，只有下载后才更新
                            
                            # 检查是否有更新
                            if entry['latest_chapter'] != entry['update_chapter']:
                                updated_novels.append(entry)
                                
                    except Exception as e:
                        logger.error(f"处理 {novel.get('title')} 时出错: {e}")
                    
                    progress.advance(task)

        # 保存最新的状态 (主要是 update_chapter 的变化)
        self.save_json(LATEST_FILE, list(latest_map.values()))

        if not updated_novels:
            logger.info("没有发现新的更新。")
            input("\n按回车键继续...")
            return

        logger.info(f"发现 {len(updated_novels)} 本小说有更新：")
        for idx, novel in enumerate(updated_novels, start=1):
            logger.info(f"{idx}. {novel['title']} | 最新: {novel['update_chapter']} | 上次: {novel['latest_chapter']}")
        
        action = questionary.select(
            "更新检查完成，是否进入下载流程：",
            choices=[
                "进入下载",
                "仅查看并返回"
            ],
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if action != "进入下载":
            input("\n按回车键继续...")
            return
        
        choices = []
        for novel in updated_novels:
            label = f"{novel['title']} | 最新: {novel['update_chapter']} | 上次: {novel['latest_chapter']}"
            choices.append(questionary.Choice(label, value=novel))
            
        selected_to_download = questionary.checkbox(
            "请选择要下载的小说：",
            choices=choices,
            instruction="⌈ 使用空格选择，回车确认 ⌋"
        ).ask()
        
        if not selected_to_download:
            return

        # 下载流程
        for novel in selected_to_download:
            self.process_download(downloader, novel, latest_map)
            
        # 最后再次保存，更新 latest_chapter
        self.save_json(LATEST_FILE, list(latest_map.values()))
        input("\n按回车键继续...")

    def process_download(self, downloader: EsjzoneDownloader, novel_entry: Dict, latest_map: Dict):
        """处理单本小说的下载逻辑"""
        title = novel_entry['title']
        url = novel_entry['url']
        latest_chap = novel_entry['latest_chapter']
        update_chap = novel_entry['update_chapter']
        
        print(f"\n正在处理: {title}")
        
        action = questionary.select(
            "请选择下载模式：",
            choices=[
                "下载整本小说",
                f"下载更新章节 ({latest_chap} -> {update_chap})",
                "跳过"
            ],
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if action == "跳过":
            return
            
        try:
            if action == "下载整本小说":
                downloader.download(url)
                # 更新记录
                latest_map[url]['latest_chapter'] = update_chap
                
            elif action.startswith("下载更新章节"):
                self.download_range(downloader, url, latest_chap, update_chap)
                # 更新记录
                latest_map[url]['latest_chapter'] = update_chap
                
        except Exception as e:
            logger.error(f"下载失败: {e}")

    def download_range(self, downloader: EsjzoneDownloader, url: str, start_chapter_title: str, end_chapter_title: str):
        """下载指定范围的章节"""
        # 1. 获取书籍信息
        book = downloader.fetch_book(url, download_images=True) # 需要图片
        
        # 2. 找到起始和结束章节的索引
        start_idx = -1
        end_idx = -1
        
        # 简单的标题匹配
        for i, chap in enumerate(book.chapters):
            if chap.title == start_chapter_title:
                start_idx = i
            if chap.title == end_chapter_title:
                end_idx = i
        
        # 如果找不到起始章节（可能改名了），默认从头下？或者提示？
        # 用户需求是从 latest_chapter 到 latest_chapter (update_chapter)
        # 这里的 start_chapter_title 是我们记录的 'latest_chapter' (已读)
        # 所以我们需要下载的是 start_idx + 1 到 end_idx
        
        target_chapters = []
        
        if start_idx == -1:
            logger.warning(f"未找到起始章节 '{start_chapter_title}'，将下载整本...")
            target_chapters = book.chapters
        else:
            # 下载 start_idx 之后的章节，直到 end_idx (包含)
            # 注意：如果 end_idx == -1 (未找到最新章节?), 则下载到最后
            if end_idx == -1:
                 target_chapters = book.chapters[start_idx+1:]
            else:
                 target_chapters = book.chapters[start_idx+1 : end_idx+1]
        
        if not target_chapters:
            logger.info("没有需要下载的章节。")
            return

        logger.info(f"即将下载 {len(target_chapters)} 章...")
        
        # 3. 使用 build_epub 或 download_text，但需要传入特定的章节列表
        
        # 确定输出路径
        # 假设默认 epub
        try:
            filename = downloader._get_filename(book, url, "epub")
        except AttributeError:
             # _get_filename might be private or not exposed. Check client.py.
             # It is _get_filename. It is private. But Python allows access.
             # Alternatively, reimplement logic.
             filename = f"{book.title}.epub"
             
        output_path = downloader._resolve_output_path(url, filename)
        
        # 确保输出目录存在
        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)

        manager = DownloadManager()
        
        # 初始化进度条 (复制自 client.py)
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            SpinnerColumn(),
            TextColumn("{task.fields[info]}"),
        )
        
        chapter_task_id = progress.add_task("下载章节", total=len(target_chapters), info="")
        image_task_id = progress.add_task("下载图片", total=0, info="")
        
        def progress_callback(type, completed, total):
            if type == 'chapter':
                progress.update(chapter_task_id, completed=completed, total=total)
            else:
                progress.update(image_task_id, completed=completed, total=total if total > 0 else None)
        
        def rate_callback(rate, threads):
            info_str = f"速率: {rate}, 线程: {threads}"
            progress.update(chapter_task_id, info=info_str)
            progress.update(image_task_id, info=info_str)
            
        manager.on_progress = progress_callback
        manager.on_rate_update = rate_callback
        
        try:
            with progress:
                for ch in target_chapters:
                    task = ChapterTask(
                        url=ch.url,
                        chapter_obj=ch,
                        callback=downloader._process_chapter_task,
                        args=(ch, True, manager) # 默认下载图片
                    )
                    manager.add_chapter_task(task)
                    
                manager.start()
                manager.wait_until_complete()
        finally:
            manager.stop()
            
        # 生成 EPUB
        range_filename = f"{book.title}_更新_{len(target_chapters)}章.epub"
        # 使用 sanitize
        safe_range_filename = re.sub(r'[\\/*?:"<>|]', "", range_filename).strip()
        final_path = output_path.parent / safe_range_filename
        
        build_epub(book, target_chapters, final_path)
        logger.info(f"更新下载完成: {final_path}")

