import yaml
import json
import pickle
from pathlib import Path
from typing import List, Dict, Union, Optional
from bs4 import BeautifulSoup
from loguru import logger
from .config_loader import config

class CookieManager:
    def __init__(self):
        self.cookie_path = Path(config.cookie.get('path', './cookies.yaml'))

    def load_cookies(self) -> List[Dict]:
        """
        加载 Cookie，支持 yaml, json, pkl
        """
        try:
            if self.cookie_path.suffix == '.yaml':
                with open(self.cookie_path, 'r', encoding='utf-8') as f:
                    cookies = yaml.safe_load(f)
            elif self.cookie_path.suffix == '.json':
                with open(self.cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
            elif self.cookie_path.suffix == '.pkl':
                with open(self.cookie_path, 'rb') as f:
                    cookies = pickle.load(f)
            else:
                logger.error(f"不支持的 Cookie 文件格式: {self.cookie_path.suffix}")
                return []
            
            if not isinstance(cookies, list):
                # 如果是 pkl 加载出来的 dict，或者是 dict 格式，尝试转换为 list
                if isinstance(cookies, dict):
                     # 简单的 dict -> list 转换
                     cookies = [{'name': k, 'value': v} for k, v in cookies.items()]
                else:
                    logger.warning(f"Cookie 数据格式异常: {type(cookies)}")
                    return []

            logger.info(f"成功加载 {len(cookies)} 个 Cookie")
            return cookies
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.error(f"加载 Cookie 失败: {e}")
            return []

    def validate_and_return_username(self, html: str) -> Union[str, None]:
        """
        校验 Cookie 有效性并返回用户名
        """
        # 1. 检查是否包含特定的重定向脚本 (Cookie 失效特征)
        invalid_signature = (
            '<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />\n'
            '<script language="javascript">\n'
            "window.location.href='/my/login';\n"
            '</script>'
        )
        
        # 注意：HTML 可能包含空白字符差异，最好用包含判断或去除空白后比较
        # 这里为了稳健，检查关键特征字符串
        if "window.location.href='/my/login';" in html:
            logger.warning("Cookie 已失效，已清理并准备重新登录")
            self.delete_cookies()
            return None

        # 2. 尝试提取用户名 (Cookie 有效特征)
        soup = BeautifulSoup(html, 'html.parser')
        user_name_tag = soup.find('h6', class_='user-name')
        
        if user_name_tag:
            username = user_name_tag.get_text(strip=True)
            logger.info(f"Cookie 校验通过，用户名：{username}")
            return username
        
        # 既不是明确失效，也不是明确成功 (可能是其他页面或结构变更)
        logger.warning("未检测到登录状态，可能 Cookie 已失效或页面结构变更")
        return None

    def save_cookies(self, cookies: List[Dict]):
        """
        保存 Cookie 到文件
        """
        try:
            # 确保目录存在
            self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self.cookie_path.suffix == '.yaml':
                with open(self.cookie_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(cookies, f, allow_unicode=True)
            elif self.cookie_path.suffix == '.json':
                with open(self.cookie_path, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
            elif self.cookie_path.suffix == '.pkl':
                with open(self.cookie_path, 'wb') as f:
                    pickle.dump(cookies, f)
            
            logger.info(f"Cookie 已保存至: {self.cookie_path}")
        except Exception as e:
            logger.error(f"保存 Cookie 失败: {e}")

    def delete_cookies(self):
        """删除失效的 Cookie 文件"""
        try:
            if self.cookie_path.exists():
                self.cookie_path.unlink()
                logger.info(f"已删除失效 Cookie 文件: {self.cookie_path}")
        except Exception as e:
            logger.error(f"删除 Cookie 文件失败: {e}")

# 全局实例
cookie_manager = CookieManager()
