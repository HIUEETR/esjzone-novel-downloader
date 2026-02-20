from __future__ import annotations

import re
import json
import uuid
import time
import pickle
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Dict, Tuple
from http.cookiejar import CookieJar

import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, SpinnerColumn

from .epub import build_epub
from .model import Book, Chapter
from .parser import parse_book, parse_chapter, parse_favorites, parse_novel_status
from .logger_config import logger
from .config_loader import config
from .cookie_manager import cookie_manager
from .download_manager import DownloadManager, ChapterTask, ImageTask

class EsjzoneDownloader:
    def __init__(
        self,
        base_delay: float = 0.5,
        session: Optional[requests.Session] = None,
        cookies: Optional[Union[Dict, CookieJar, str, Path]] = None,
    ) -> None:
        self.session = session or requests.Session()
        self.base_delay = base_delay
        
        # 初始化调试目录
        self.debug_dir = Path("debug")
        self._lock = threading.Lock()
        self._pbar_lock = threading.Lock()

        # 设置默认请求头
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Connection": "keep-alive",
        })

        # 优先使用传入的 cookies，否则尝试加载默认
        if cookies:
            self._load_cookies(cookies)
        else:
            self._load_default_cookies()

    def _load_default_cookies(self):
        """从 cookie_manager 加载默认 Cookie"""
        loaded_cookies = cookie_manager.load_cookies()
        if loaded_cookies:
            for c in loaded_cookies:
                kwargs = {"path": c.get("path", "/")}
                if c.get("domain"):
                    kwargs["domain"] = c.get("domain")
                
                self.session.cookies.set(
                    c["name"],
                    c["value"],
                    **kwargs
                )
            logger.info(f"从默认路径加载了 {len(loaded_cookies)} 个 Cookie")

    def _load_cookies(self, cookies: Union[Dict, CookieJar, str, Path]) -> None:
        """加载指定 Cookie 到会话中"""
        try:
            if isinstance(cookies, (str, Path)):
                path = Path(cookies)
                if path.exists():
                     if path.suffix == '.pkl':
                         with open(path, 'rb') as f:
                             self.session.cookies.update(pickle.load(f))
                     elif path.suffix == '.json':
                         with open(path, 'r') as f:
                             data = json.load(f)
                             if isinstance(data, dict):
                                 self.session.cookies.update(data)
            elif isinstance(cookies, (dict, CookieJar)):
                self.session.cookies.update(cookies)
            
            logger.info(f"成功加载 Cookie，当前会话共有 {len(self.session.cookies)} 个 Cookie")
        except Exception as e:
            logger.error(f"加载 Cookie 失败: {e}")

    def download_image(self, url: str) -> bytes | None:
        """
        下载图片并返回二进制数据。
        如果下载失败，返回 None。
        """
        try:
            with self.safe_request(url, stream=True) as response:
                return response.content
        except Exception as e:
            logger.warning(f"下载图片失败: {url}, 错误: {e}")
            raise e

    def _dump_debug(self, response: Optional[requests.Response] = None, request: Optional[requests.PreparedRequest] = None, exception: Optional[Exception] = None):
        """
        以线程安全的方式将调试信息转储到文件。
        """
        try:
            # 仅在需要写入时创建目录
            if not self.debug_dir.exists():
                self.debug_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())
            filename = f"debug_{timestamp}_{unique_id}.log"
            file_path = self.debug_dir / filename

            debug_info = []
            debug_info.append(f"时间戳: {datetime.now().isoformat()}")
            debug_info.append(f"异常信息: {repr(exception) if exception else 'None'}")
            
            # 提取请求信息
            req_url = "N/A"
            req_headers = {}
            
            if response:
                req_url = response.request.url
                req_headers = dict(response.request.headers)
            elif request:
                req_url = request.url
                req_headers = dict(request.headers)
            
            debug_info.append(f"请求 URL: {req_url}")
            debug_info.append("请求头:")
            debug_info.append(json.dumps(req_headers, indent=2, default=str))

            # 提取响应信息
            if response:
                debug_info.append(f"响应状态码: {response.status_code}")
                debug_info.append("响应头:")
                debug_info.append(json.dumps(dict(response.headers), indent=2, default=str))
                debug_info.append("-" * 80)
                debug_info.append("响应正文:")
                debug_info.append(response.text)
            else:
                debug_info.append("响应状态码: N/A")
                debug_info.append("响应头: N/A")
                debug_info.append("-" * 80)
                debug_info.append("响应正文: N/A")

            content = "\n".join(debug_info)

            with file_path.open("w", encoding="utf-8") as f:
                f.write(content)
            
            logger.debug(f"调试信息已保存到: {file_path}")

        except Exception as e:
            logger.error(f"写入调试转储失败: {e}")

    @contextmanager
    def safe_request(self, url: str, method: str = 'GET', **kwargs):
        """
        统一的请求封装，确保 Cookie 自动管理并统一处理异常。
        使用上下文管理器以捕获解析阶段的异常。
        """
        response = None
        try:
            # 执行请求
            logger.debug(f"正在请求: {url}")
            response = self.session.request(method, url, **kwargs)
            
            # 检查 HTTP 错误
            if not response.ok:
                # 状态码异常立即转储
                self._dump_debug(response, exception=f"非预期状态码: {response.status_code}")
                response.raise_for_status()
            
            yield response

        except Exception as e:
            # 捕获请求异常或解析异常
            req = None
            if response is None and isinstance(e, RequestException):
                req = e.request
            
            # 转储调试信息
            self._dump_debug(response=response, request=req, exception=e)
            
            # 重新抛出异常
            raise e

    def login(self, email: str = None, password: str = None) -> bool:
        """
        登录 ESJ Zone
        """
        if not email:
            email = config.account.get('username')
        if not password:
            password = config.account.get('password')
            
        if not email or not password:
            logger.error("未提供账号或密码，且配置文件中也未设置")
            return False

        login_url = "https://www.esjzone.one/inc/mem_login.php"
        payload = {
            "email": email,
            "pwd": password,
            "remember_me": "on",
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.esjzone.one",
            "Referer": "https://www.esjzone.one/login",
        }
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"正在重试登录 ({attempt}/{max_retries})...")
                    
                logger.info("开始尝试账号密码登录...")
                # 调试：打印部分账号信息以确认配置加载正确
                masked_email = email[:3] + "***" if email else "None"
                logger.debug(f"使用的账号: {masked_email}")

                with self.safe_request(login_url, method='POST', data=payload, headers=headers) as resp:
                    if resp.status_code == 200:
                        logger.info("登录请求成功，正在验证是否实际登录有效...")
                        # 调试：打印登录响应内容的前200个字符
                        logger.debug(f"登录响应内容: {resp.text[:200]}")
                        resp_json = None
                        try:
                            resp_json = resp.json()
                        except Exception:
                            logger.warning("登录响应不是合法 JSON，将继续使用 Cookie 校验")
                        
                        if isinstance(resp_json, dict):
                            status = resp_json.get("status")
                            if status is not None and status != 200:
                                msg = resp_json.get("msg", "")
                                logger.warning(f"登录响应状态异常: {status}，msg: {msg}")
                                continue
                        
                        # 再次校验
                        if self.validate_cookie():
                            logger.info("登录并验证成功")
                            self.save_current_cookies()
                            return True
                        else:
                            logger.warning("登录请求返回200，但Cookie验证失败")
                            # 验证失败，可能是需要重试
                    else:
                        logger.error(f"登录失败，状态码: {resp.status_code}")
                        
            except Exception as e:
                logger.error(f"登录过程中发生异常: {e}")
                if attempt < max_retries:
                    time.sleep(2)
                
        logger.error("登录最终失败")
        return False

    def save_current_cookies(self):
        """保存当前会话的 Cookie"""
        cookies_list = []
        for cookie in self.session.cookies:
            cookie_dict = {
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain,
                'path': cookie.path,
            }
            cookies_list.append(cookie_dict)
        cookie_manager.save_cookies(cookies_list)

    def validate_cookie(self) -> Optional[str]:
        """
        校验当前 Cookie 是否有效
        返回用户名或 None
        """
        profile_url = "https://www.esjzone.one/my/profile.html"
        logger.debug(f"正在校验 Cookie 有效性: {profile_url}")
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"正在重试 Cookie 校验 ({attempt}/{max_retries})...")
                    
                with self.safe_request(profile_url) as resp:
                    html = resp.text
                    if "window.location.href='/my/login';" in html:
                        logger.warning("Cookie 已失效，已清理内存 Cookie")
                        self.session.cookies.clear()
                        # Cookie 失效不需要重试，直接返回 None
                        return None
                    
                    result = cookie_manager.validate_and_return_username(html)
                    if result:
                        return result
                    
            except Exception as e:
                logger.error(f"校验 Cookie 时发生异常: {e}")
                if attempt < max_retries:
                    time.sleep(2)
                    
        return None

    def get_favorites(self, page: int = 1, sort_by: str = 'new') -> Tuple[List[Dict[str, str]], int]:
        """
        获取收藏列表
        sort_by: 'new' (最近更新) or 'favor' (最近收藏)
        """
        # 将语义化的 sort_by 映射为服务器预期的值/URL
        if sort_by == 'new':
            # "new" 在本应用中表示 "最近更新" -> 服务器使用 'udate'
            cookie_val = 'udate'
            url = f"https://www.esjzone.one/my/favorite/udate/{page}"
        else:
            # "favor" 在本应用中表示 "最近收藏" -> 服务器使用默认值 ('new'?)
            cookie_val = 'new'
            url = f"https://www.esjzone.one/my/favorite/{page}"
            
        self.session.cookies.set('favorite_sort', cookie_val, domain='www.esjzone.one', path='/')
        
        logger.info(f"正在获取收藏列表 (第 {page} 页, 排序: {sort_by})...")
        
        with self.safe_request(url) as resp:
            html = resp.text
            return parse_favorites(html)

    def get_novel_status(self, url: str) -> Dict[str, str]:
        """
        获取小说的基本状态信息（用于检查更新）
        只解析标题、更新时间和最新章节，不下载封面或解析完整章节列表。
        """
        logger.info(f"正在检查更新: {url}")
        
        with self.safe_request(url) as resp:
            html = resp.text
            return parse_novel_status(html, url)

    def fetch_book(self, url: str, download_images: bool = True) -> Book:
        logger.info(f"开始解析书籍信息: {url}")
        
        max_retries = 2
        last_error = None
        book = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"正在重试解析书籍信息 ({attempt}/{max_retries})...")
                    
                with self.safe_request(url) as resp:
                    html = resp.text
                    book = parse_book(html, url)
                # 成功则退出循环
                break
            except Exception as e:
                last_error = e
                logger.error(f"解析书籍信息失败: {e}")
                if attempt < max_retries:
                    time.sleep(2)
        
        if book is None:
            logger.error(f"获取书籍信息最终失败，已重试 {max_retries} 次")
            if last_error:
                raise last_error
            else:
                raise Exception("获取书籍信息失败")
        
        logger.info(f"书籍解析成功: {book.title} (共 {len(book.chapters)} 章)")

        # 下载封面 (仍然同步下载，因为它在正文前)
        cover_ext = ".png"
        if download_images and book.cover_url:
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"正在下载封面 ⌈ 第 {attempt + 1} 次尝试 ⌋: {book.cover_url}")
                    img_data = None
                    try:
                        # 添加超时设置
                        with self.safe_request(book.cover_url, stream=True, timeout=60) as response:
                             img_data = response.content
                    except Exception as e:
                        logger.warning(f"下载封面请求异常: {e}")
                        pass

                    if not img_data:
                        raise Exception("下载失败，返回空数据")
                    
                    # 尝试识别
                    image_obj = Image.open(BytesIO(img_data))
                    if image_obj.format == "JPEG":
                        book.cover_image = img_data
                        cover_ext = ".jpg"
                    elif image_obj.format == "GIF":
                        book.cover_image = img_data
                        cover_ext = ".gif"
                    else:
                        # 转换为 PNG
                        output_buffer = BytesIO()
                        image_obj.save(output_buffer, format="PNG")
                        book.cover_image = output_buffer.getvalue()
                        cover_ext = ".png"
                    break # 成功
                    
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"封面下载失败: {e}, 正在重试...")
                        time.sleep(1)
                    else:
                        logger.error(f"封面下载失败: {e}, 已跳过")
                        book.cover_image = None

        intro_content = []
        if book.cover_image:
            intro_content.append(f'<div style="text-align: center;"><img src="images/cover{cover_ext}" alt="封面"/></div>')
        
        intro_content.append(f"<h1>{book.title}</h1>")
        intro_content.append(f"<p><strong>作者:</strong> {book.author}</p>")
        if book.tags:
             intro_content.append(f"<p><strong>Tags:</strong> {', '.join(book.tags)}</p>")
        
        intro_content.append(f"<p><strong>源网址:</strong> <a href=\"{book.url}\">{book.url}</a></p>")
        intro_content.append(f"<p>由 <a href=\"https://github.com/HIUEETR/esjzone-novel-downloader\">esjzone-novel-downloader</a> 生成</p>")
        
        intro_content.append(f"<h3>简介</h3>")
        intro_lines = book.introduction.split('\n')
        for line in intro_lines:
            if line.strip():
                intro_content.append(f"<p>{line.strip()}</p>")
        
        intro_content.append(f"<h3>目录</h3>")
        intro_content.append("<ul>")
        for ch in book.chapters:
            intro_content.append(f'<li><a href="chapter_{ch.index}.xhtml">{ch.title}</a></li>')
        intro_content.append("</ul>")

        intro_html = "\n".join(intro_content)
        
        intro_chapter = Chapter(
            url=book.url,
            title="书籍信息",
            index=0,
            content_html=intro_html,
            content_text=f"{book.title}\n作者: {book.author}\nTags: {', '.join(book.tags)}\n\n简介:\n{book.introduction}",
        )
        
        book.chapters.insert(0, intro_chapter)

        # 启动异步下载管理器
        manager = DownloadManager()
        
        # 初始化进度条 (Rich)
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            SpinnerColumn(),
            TextColumn("{task.fields[info]}"),
        )
        
        chapter_task_id = progress.add_task("下载章节", total=len(book.chapters) - 1, info="")
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
                # 提交章节任务 (跳过第0章介绍)
                for ch in book.chapters[1:]:
                    task = ChapterTask(
                        url=ch.url,
                        chapter_obj=ch,
                        callback=self._process_chapter_task,
                        args=(ch, download_images, manager)
                    )
                    manager.add_chapter_task(task)
                    
                manager.start()
                manager.wait_until_complete()
        except KeyboardInterrupt:
            logger.warning("用户中断下载，正在停止...")
            manager.stop()
            raise
        finally:
            manager.stop()
        
        logger.info(f"下载完成。成功: {manager.completed_chapters} 章, {manager.completed_images} 图。失败: {manager.failed_tasks}")
        
        return book

    def _process_chapter_task(self, chapter: Chapter, download_images: bool, manager: DownloadManager):
        """章节下载任务处理函数"""
        logger.debug(f"正在处理章节: {chapter.url}")
        
        with self.safe_request(chapter.url) as ch_resp:
            manager.report_bytes(len(ch_resp.content))
            ch_html = ch_resp.text
            title, content_html = parse_chapter(ch_html, chapter.url, chapter.title)
            
            if download_images:
                content_html = self._extract_and_queue_images(content_html, chapter, manager)
            
            chapter.title = title
            chapter.content_html = content_html
            chapter.content_text = _plain_text_from_html(content_html)

    def _extract_and_queue_images(self, html_content: str, chapter: Chapter, manager: DownloadManager) -> str:
        """解析图片并添加到下载队列"""
        soup = BeautifulSoup(html_content, "html.parser")
        img_tags = soup.find_all("img")
        
        if not img_tags:
            return str(soup)

        tasks = []
        for img in img_tags:
            src = img.get("src")
            if not src:
                continue
            
            if src.startswith("images/"):
                continue

            if not src.startswith("http"):
                if src.startswith("/"):
                    src = f"https://www.esjzone.one{src}"
                else:
                    logger.warning(f"跳过无法解析的图片链接: {src}")
                    # 添加调试日志
                    logger.debug(f"无效链接所在的章节: {chapter.title} ({chapter.url})")
                    logger.debug(f"完整的 img 标签: {img}")
                    continue

            ext = ".png"
            if src.lower().endswith(".gif"):
                ext = ".gif"
                
            filename = f"{uuid.uuid4().hex}{ext}"
            
            task = ImageTask(
                url=src,
                chapter_obj=chapter,
                image_filename=filename,
                callback=self._process_image_task,
                args=(src, filename, chapter, manager)
            )
            tasks.append(task)
            
            img["src"] = f"images/{filename}"
        manager.add_image_tasks(tasks)
        return str(soup)

    def _process_image_task(self, url: str, filename: str, chapter: Chapter, manager: DownloadManager):
        """图片下载任务处理函数"""
        logger.debug(f"正在下载图片: {url}")
        
        with self.safe_request(url, stream=True) as response:
            img_data = response.content
            manager.report_bytes(len(img_data))
            
        if not img_data:
            raise Exception("下载图片返回空数据")

        try:
            if filename.lower().endswith(".gif"):
                 final_data = img_data
            else:
                image_obj = Image.open(BytesIO(img_data))
                final_data = None
                
                output_buffer = BytesIO()
                image_obj.save(output_buffer, format="PNG")
                final_data = output_buffer.getvalue()
            

            chapter.images[filename] = final_data
            
        except Exception as e:
            raise Exception(f"图片处理失败: {e}")


    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        return re.sub(r'[\\/*?:"<>|]', "", filename).strip()

    def _get_filename(self, book: Book, url: str, ext: str) -> str:
        """根据配置生成文件名"""
        download_config = config.get('download', {})
        naming_mode = download_config.get('naming_mode', 'book_name')
        
        if naming_mode == 'number':
            # 提取数字ID
            book_id = url.split('/')[-1].replace('.html', '')
            return f"{book_id}.{ext}"
        else:
            # 默认使用书名
            safe_title = self._sanitize_filename(book.title)
            return f"{safe_title}.{ext}"

    def _resolve_output_path(self, url: str, filename: Union[str, Path], override_dir: Optional[str] = None) -> Path:
        """根据配置决定最终保存路径"""
        filename = Path(filename)
        book_id = url.split('/')[-1].replace('.html', '')
        
        # 从配置中获取下载设置
        download_config = config.get('download', {})
        use_book_dir = download_config.get('use_book_dir', True)
        default_dir = download_config.get('dir', 'downloads')

        if override_dir:
            base_dir = Path(override_dir)
            final_path = base_dir / filename.name
        elif use_book_dir:
            base_dir = Path(default_dir) / book_id
            final_path = base_dir / filename.name
        else:
            base_dir = Path(default_dir)
            final_path = base_dir / filename.name

        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"创建目录失败 {base_dir}: {e}")
            raise

        # 检查是否需要更新 .gitignore
        self._check_gitignore(base_dir)

        logger.info(f"文件将保存至: {final_path.absolute()}")
        return final_path

    def _check_gitignore(self, directory: Path):
        """检查并更新 .gitignore"""
        try:
            gitignore_path = Path(".gitignore")
            if not gitignore_path.exists():
                return

            # 获取相对路径的第一级目录作为忽略项
            try:
                # 尝试获取相对于当前工作目录的路径
                rel_path = directory.absolute().relative_to(Path.cwd())
                root_dir = rel_path.parts[0]
                ignore_pattern = f"{root_dir}/"
            except ValueError:
                # 如果不在当前目录下，忽略
                return

            # 读取现有的 ignore 规则
            with open(gitignore_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if ignore_pattern not in content:
                logger.info(f"将 {ignore_pattern} 添加到 .gitignore")
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    f.write(f"\n{ignore_pattern}\n")
        except Exception as e:
            logger.warning(f"更新 .gitignore 失败: {e}")

    def download(self, url: str, output_path: Optional[Union[str, Path]] = None, download_dir_override: Optional[str] = None) -> Path:
        """
        统一的下载入口，根据配置分发任务
        """
        download_config = config.get('download', {})
        fmt = download_config.get('download_format', 'epub').lower()
        
        if fmt == 'epub':
            return self.download_epub(url, output_path, download_dir_override)
        elif fmt == 'txt':
            return self.download_text(url, output_path, download_dir_override)
        else:
            # 尝试回退到 epub，并抛出异常提示
            msg = f"不支持的下载格式: {fmt}，仅支持 'epub' 或 'txt'"
            logger.error(msg)
            raise ValueError(msg)

    def download_text(self, url: str, output_path: Optional[Union[str, Path]] = None, download_dir_override: Optional[str] = None) -> Path:
        book = self.fetch_book(url, download_images=False)
        
        # 如果未指定 output_path，或者指定的是临时名称，则根据配置生成
        if not output_path or str(output_path) in ["output.txt", "output.epub"]:
            filename = self._get_filename(book, url, "txt")
        else:
            filename = str(output_path)

        final_path = self._resolve_output_path(url, filename, download_dir_override)
        
        lines = []
        lines.append(f"{book.title}\n")
        lines.append(f"作者: {book.author}\n")
        
        if book.tags:
             lines.append(f"Tags: {', '.join(book.tags)}\n")
        
        lines.append(f"源网址: {book.url}\n")
        lines.append("由 esjzone-novel-downloader 生成 (https://github.com/HIUEETR/esjzone-novel-downloader)\n\n")
        
        lines.append("简介:\n")
        lines.append(f"{book.introduction}\n\n")
        
        lines.append("目录:\n")
        for ch in book.chapters:
             lines.append(f"{ch.title}\n")
        lines.append("\n" + "="*20 + "\n\n")

        for ch in book.chapters:
            lines.append(f"{ch.title}\n")
            lines.append("-" * len(ch.title) + "\n\n")
            if ch.content_text:
                lines.append(ch.content_text + "\n\n")
        
        try:
            with open(final_path, 'w', encoding="utf-8") as f:
                f.writelines(lines)
            logger.info(f"TXT 下载完成: {final_path}")
        except Exception as e:
            logger.error(f"TXT 写入失败: {e}")
            raise
            
        return final_path

    def download_epub(self, url: str, output_path: Optional[Union[str, Path]] = None, download_dir_override: Optional[str] = None) -> Path:
        book = self.fetch_book(url, download_images=True)
        
        # 如果未指定 output_path，或者指定的是临时名称，则根据配置生成
        if not output_path or str(output_path) in ["output.txt", "output.epub"]:
            filename = self._get_filename(book, url, "epub")
        else:
            filename = str(output_path)

        final_path = self._resolve_output_path(url, filename, download_dir_override)
        
        build_epub(book, book.chapters, final_path)
        logger.info(f"EPUB 下载完成: {final_path}")
        return final_path


def _plain_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)
