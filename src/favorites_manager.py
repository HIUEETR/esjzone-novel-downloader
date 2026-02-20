import json
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, MofNCompleteColumn

from .client import EsjzoneDownloader
from .logger_config import logger

class FavoritesManager:
    def __init__(self, downloader: EsjzoneDownloader, data_dir: str = "data"):
        self.downloader = downloader
        self.data_dir = Path(data_dir)
        self.data_file = self.data_dir / "favorites.json"
        
        # 从文件加载缓存
        self.cache: Dict[str, List[Dict]] = {
            "new": [],   # 最近更新
            "favor": []  # 最近收藏
        }
        
        # 记录本次启动后是否已更新过
        self._updated_flags = {
            "new": False,
            "favor": False
        }
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 确保数据目录存在
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
        self.load_data()

    def load_data(self):
        """加载本地缓存数据"""
        with self._lock:
            if self.data_file.exists():
                try:
                    with open(self.data_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            # 合并现有键
                            for key in ["new", "favor"]:
                                if key in data:
                                    self.cache[key] = data[key]
                    logger.info(f"已加载本地收藏数据: new={len(self.cache['new'])}, favor={len(self.cache['favor'])}")
                except Exception as e:
                    logger.error(f"加载收藏数据失败: {e}")

    def save_data(self):
        """保存数据到本地"""
        with self._lock:
            try:
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
                logger.debug("收藏数据已保存")
            except Exception as e:
                logger.error(f"保存收藏数据失败: {e}")

    def get_novels(self, sort_by: str) -> List[Dict]:
        """获取指定排序的所有小说列表"""
        with self._lock:
            return self.cache.get(sort_by, [])

    def ensure_updated(self, sort_by: str):
        """确保数据已更新（本次会话仅更新一次）"""
        if self._updated_flags.get(sort_by):
            return

        logger.info(f"正在更新收藏列表 ({sort_by})...")
        self._update_favorites(sort_by)
        self._updated_flags[sort_by] = True

    def _fetch_page(self, page: int, sort_by: str):
        """获取单页数据的辅助函数"""
        return self.downloader.get_favorites(page, sort_by)

    def _update_favorites(self, sort_by: str):
        """执行更新逻辑（多线程 + 进度条）"""
        # 暂时禁用客户端日志以避免干扰进度条
        logger.disable("src.client")
        try:
            # 1. 获取第一页以确定总页数
            novels_p1, total_pages = self.downloader.get_favorites(1, sort_by)
            results = {1: novels_p1}
            
            if total_pages > 1:
                pages_to_fetch = list(range(2, total_pages + 1))
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    MofNCompleteColumn(),
                    TaskProgressColumn(),
                    transient=True 
                ) as progress:
                    task_id = progress.add_task(f"更新收藏列表 (共 {total_pages} 页)...", total=len(pages_to_fetch))
                    
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_page = {
                            executor.submit(self._fetch_page, p, sort_by): p 
                            for p in pages_to_fetch
                        }
                        
                        for future in as_completed(future_to_page):
                            page = future_to_page[future]
                            try:
                                novels, _ = future.result()
                                results[page] = novels
                            except Exception as e:
                                logger.error(f"获取第 {page} 页失败: {e}")
                                results[page] = [] # 保持空列表占位
                            finally:
                                progress.advance(task_id)
            
            # 按页码顺序合并
            final_list = []
            for p in sorted(results.keys()):
                final_list.extend(results[p])
                
            with self._lock:
                self.cache[sort_by] = final_list
                self.save_data()
                
            # 恢复日志并在最后显示一条总结
            logger.enable("src.client")
            logger.info(f"收藏列表更新完成，共 {len(final_list)} 本")
            
        except Exception as e:
            logger.enable("src.client")
            logger.error(f"更新过程发生错误: {e}")
        finally:
            # 确保日志被重新启用
            logger.enable("src.client")
