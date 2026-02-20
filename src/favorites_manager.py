import json
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

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
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 后台更新状态
        self._updating = False
        self._stop_event = threading.Event()
        
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

    def start_background_update(self, sort_by: str):
        """启动后台更新线程"""
        if self._updating:
            logger.warning("后台更新已在运行中")
            return

        self._stop_event.clear()
        self._updating = True
        
        # 在守护线程中启动
        thread = threading.Thread(
            target=self._update_loop,
            args=(sort_by,),
            daemon=True
        )
        thread.start()
        logger.info(f"后台更新线程已启动 (排序: {sort_by})")

    def stop_update(self):
        """停止后台更新"""
        if self._updating:
            self._stop_event.set()
            # 这里不等待 join 以保持 UI 响应，仅发出停止信号
            logger.info("正在停止后台更新...")

    def _update_loop(self, sort_by: str):
        """后台更新循环"""
        try:
            page = 1
            all_novels = []
            total_pages = 1 # 初始猜测
            
            while not self._stop_event.is_set():
                try:
                    # 获取页面
                    logger.debug(f"正在获取第 {page} 页...")
                    # sort_by 匹配缓存键: 'new' 或 'favor'
                    novels, current_total_pages = self.downloader.get_favorites(page, sort_by)
                    
                    if not novels:
                        logger.warning(f"第 {page} 页未获取到数据，停止更新")
                        break
                        
                    # 如果总页数改变（通常在第一页），更新它
                    if page == 1:
                        total_pages = current_total_pages
                        
                    all_novels.extend(novels)
                    
                    # 增量更新还是最后更新？
                    # 用户要求"update to data"
                    # 最后统一更新以确保一致性
                    
                    logger.info(f"已获取第 {page}/{total_pages} 页，本页 {len(novels)} 本")
                    
                    if page >= total_pages:
                        break
                        
                    page += 1
                    time.sleep(1) # 礼貌请求
                    
                except Exception as e:
                    logger.error(f"更新过程出错 (页码 {page}): {e}")
                    break
            
            if all_novels and not self._stop_event.is_set():
                with self._lock:
                    self.cache[sort_by] = all_novels
                    self.save_data()
                logger.info(f"后台更新完成，共更新 {len(all_novels)} 本小说")
                
        except Exception as e:
             logger.error(f"后台更新线程异常: {e}")
        finally:
            self._updating = False
