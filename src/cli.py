import sys
import os
import argparse
import questionary
import time
from src.client import EsjzoneDownloader
from src.config_loader import config
from src.logger_config import logger
from src.cookie_manager import cookie_manager
from src.favorites_manager import FavoritesManager
from src.monitor import MonitorManager
from src.utils import clear_screen, truncate_and_pad

def _try_login():
    """尝试使用当前配置的账号密码登录"""
    username = config.account.get('username')
    password = config.account.get('password')
    
    if username and password:
        logger.info("检测到账号密码，正在尝试登录...")
        # 登录前先清理旧 Cookie，避免干扰
        cookie_manager.delete_cookies()
        
        # 实例化下载器并尝试登录
        try:
            downloader = EsjzoneDownloader()
            if downloader.login():
                logger.info("登录成功！")
            else:
                logger.warning("登录失败，请检查账号密码。")
        except Exception as e:
            logger.error(f"登录过程发生错误: {e}")
        
        # 暂停以便用户查看结果
        input("\n按回车键继续...")

def edit_account_menu():
    while True:
        clear_screen()
        current_username = config.account.get('username', '')
        current_password = config.account.get('password') or ''
        
        choices = [
            "修改账号",
            "修改密码",
            "返回上一级菜单"
        ]
        
        choice = questionary.select(
            f"账号设置 ⌈ 当前账号: {current_username} ⌋",
            choices=choices,
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if choice == "修改账号":
            new_username = questionary.text("请输入账号：", default=current_username).ask()
            if new_username is not None:
                config.set('account.username', new_username)
                config.save()
                _try_login()
        elif choice == "修改密码":
            new_password = questionary.password("请输入密码：", default=current_password).ask()
            if new_password is not None:
                config.set('account.password', new_password)
                config.save()
                _try_login()
        elif choice == "返回上一级菜单":
            break

def edit_download_menu():
    while True:
        clear_screen()
        dl_config = config.get('download', {})
        choices = [
            f"修改下载目录 ⌈ 当前: {dl_config.get('dir', 'downloads')} ⌋",
            f"修改下载格式 ⌈ 当前: {dl_config.get('download_format', 'epub')} ⌋",
            f"修改命名模式 ⌈ 当前: {dl_config.get('naming_mode', 'book_name')} ⌋",
            f"修改是否创建子目录 ⌈ 当前: {dl_config.get('use_book_dir', False)} ⌋",
            f"修改最大线程数 ⌈ 当前: {dl_config.get('max_threads', 5)} ⌋",
            f"修改超时时间 ⌈ 当前: {dl_config.get('timeout_seconds', 180)} 秒 ⌋",
            f"修改最大重试次数 ⌈ 当前: {dl_config.get('retry_attempts', 3)} ⌋",
            "返回上一级菜单"
        ]
        
        choice = questionary.select(
            "下载设置",
            choices=choices,
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if choice.startswith("修改下载目录"):
            val = questionary.text("请输入下载目录：", default=dl_config.get('dir', 'downloads')).ask()
            if val:
                config.set('download.dir', val)
                config.save()
        elif choice.startswith("修改下载格式"):
            val = questionary.select(
                "请选择下载格式：",
                choices=["epub", "txt"],
                default=dl_config.get('download_format', 'epub'),
                instruction="⌈ 使用↑↓选择 ⌋"
            ).ask()
            if val:
                config.set('download.download_format', val)
                config.save()
        elif choice.startswith("修改命名模式"):
            val = questionary.select(
                "请选择命名模式：",
                choices=["book_name", "number"],
                default=dl_config.get('naming_mode', 'book_name'),
                instruction="⌈ 使用↑↓选择 ⌋"
            ).ask()
            if val:
                config.set('download.naming_mode', val)
                config.save()
        elif choice.startswith("修改是否创建子目录"):
            val = questionary.confirm(
                "是否为每本图书创建一个子目录？",
                default=dl_config.get('use_book_dir', False)
            ).ask()
            config.set('download.use_book_dir', val)
            config.save()
        elif choice.startswith("修改最大线程数"):
            val = questionary.text("请输入最大线程数：", default=str(dl_config.get('max_threads', 5))).ask()
            if val and val.isdigit():
                config.set('download.max_threads', int(val))
                config.save()
        elif choice.startswith("修改超时时间"):
            val = questionary.text("请输入超时时间（秒）：", default=str(dl_config.get('timeout_seconds', 180))).ask()
            if val and val.isdigit():
                config.set('download.timeout_seconds', int(val))
                config.save()
        elif choice.startswith("修改最大重试次数"):
            val = questionary.text("请输入最大重试次数：", default=str(dl_config.get('retry_attempts', 3))).ask()
            if val and val.isdigit():
                config.set('download.retry_attempts', int(val))
                config.save()
        elif choice == "返回上一级菜单":
            break

def edit_log_menu():
    while True:
        clear_screen()
        log_config = config.get('log', {})
        choices = [
            f"修改日志级别 ⌈ 当前: {log_config.get('level')} ⌋",
            f"修改日志目录 ⌈ 当前: {log_config.get('dir')} ⌋",
            f"修改保留天数 ⌈ 当前: {log_config.get('retention')} ⌋",
            "返回上一级菜单"
        ]
        
        choice = questionary.select(
            "日志设置",
            choices=choices,
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if choice.startswith("修改日志级别"):
            val = questionary.select(
                "请选择日志级别：",
                choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                default=log_config.get('level', 'INFO'),
                instruction="⌈ 使用↑↓选择 ⌋"
            ).ask()
            if val:
                config.set('log.level', val)
                config.save()
        elif choice.startswith("修改日志目录"):
            val = questionary.text("请输入日志目录：", default=log_config.get('dir', './logs')).ask()
            if val:
                config.set('log.dir', val)
                config.save()
        elif choice.startswith("修改保留天数"):
            val = questionary.text("请输入保留天数：", default=str(log_config.get('retention', 30))).ask()
            if val and val.isdigit():
                config.set('log.retention', int(val))
                config.save()
        elif choice == "返回上一级菜单":
            break

def edit_cookie_menu():
    while True:
        clear_screen()
        cookie_config = config.get('cookie', {})
        choices = [
            f"修改 Cookie 路径 ⌈ 当前: {cookie_config.get('path')} ⌋",
            "返回上一级菜单"
        ]
        
        choice = questionary.select(
            "Cookie 设置",
            choices=choices,
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if choice.startswith("修改 Cookie 路径"):
            val = questionary.text("请输入 Cookie 文件路径：", default=cookie_config.get('path', 'data/cookies.json')).ask()
            if val:
                config.set('cookie.path', val)
                config.save()
        elif choice == "返回上一级菜单":
            break

def edit_config_menu():
    while True:
        clear_screen()
        choice = questionary.select(
            "编辑配置文件：",
            choices=[
                "编辑账号密码",
                "编辑下载设置",
                "编辑日志设置",
                "编辑 Cookie 设置",
                "返回上一级菜单"
            ],
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if choice == "编辑账号密码":
            edit_account_menu()
        elif choice == "编辑下载设置":
            edit_download_menu()
        elif choice == "编辑日志设置":
            edit_log_menu()
        elif choice == "编辑 Cookie 设置":
            edit_cookie_menu()
        elif choice == "返回上一级菜单":
            break

def favorite_menu(downloader, favorites_manager):
    # 询问排序方式
    sort_choices = [
        questionary.Choice("按最近更新", value="new"),
        questionary.Choice("按最近收藏", value="favor"),
        "返回上一级菜单"
    ]
    
    sort_by = questionary.select(
        "请选择收藏夹排序方式：",
        choices=sort_choices,
        instruction="⌈ 使用↑↓选择 ⌋"
    ).ask()
    
    if sort_by == "返回上一级菜单":
        return

    # 确保数据已更新（仅首次进入时更新）
    favorites_manager.ensure_updated(sort_by)

    page = 1
    items_per_page = 10
    
    while True:
        clear_screen()
        
        # 获取所有数据（包含缓存和后台更新的数据）
        novels = favorites_manager.get_novels(sort_by)
        total_novels = len(novels)
        
        # 计算总页数
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
        
        # 添加导航提示信息
        choices.append(questionary.Separator(f"--- 第 {page} / {total_pages} 页 ⌈ 共 {total_novels} 本 ⌋ ---"))
        
        # 使用 wcwidth 计算显示宽度并对齐
        # 标题宽度设为 24 (约12个汉字)，最新章节设为 24，更新时间保持原样
        title_width = 24
        latest_width = 24
        
        # 构造表头
        header_title = truncate_and_pad("标题", title_width)
        header_latest = truncate_and_pad("最新章节", latest_width)
        
        # 注意：Separator 没有选择指针，所以可能会比下面的选项向左偏。
        # 为了视觉对齐，可以在前面加两个空格模拟指针占位（视具体终端和 questionary 版本而定）
        header = f"{'序号':>4}   {header_title}      {header_latest}      {'更新时间'}"
        choices.append(questionary.Separator(header))

        for idx, novel in enumerate(current_novels):
            abs_idx = start_idx + idx + 1
            title = novel['title']
            latest = novel['latest_chapter']
            update = novel['update_time']
            
            display_title = truncate_and_pad(title, title_width)
            display_latest = truncate_and_pad(latest, latest_width)

            # 格式: 序号. 标题 | 最新: ... | 更新: ...
            label = f"{abs_idx:>4}. {display_title}   |   {display_latest}   |   {update}"
            choices.append(questionary.Choice(label, value=novel))
            
        choices.append(questionary.Separator("--- 操作 ---"))
        
        # 添加分页选项
        if page > 1:
            choices.append(questionary.Choice(f"← 上一页 ⌈ 第 {page-1} 页 ⌋", value="prev"))
        if page < total_pages:
            choices.append(questionary.Choice(f"→ 下一页 ⌈ 第 {page+1} 页 ⌋", value="next"))
        
        if total_pages > 1:
             choices.append(questionary.Choice("跳转页码", value="jump"))

        choices.append(questionary.Choice("返回上一级菜单", value="back"))
        
        selection = questionary.select(
            "我的收藏夹",
            choices=choices,
            instruction="⌈ 使用↑↓翻页/选择，回车确认 ⌋"
        ).ask()
        
        if selection == "back":
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
                else:
                    print(f"页码无效，请输入 1 到 {total_pages} 之间的数字")
                    time.sleep(1)
        elif isinstance(selection, dict):
            # 选中了一本小说
            novel_url = selection['url']
            novel_title = selection['title']
            print(f"\n准备下载: {novel_title}")
            try:
                downloader.download(novel_url)
            except Exception as e:
                logger.error(f"下载失败: {e}")
            
            questionary.press_any_key_to_continue(message="按任意键继续...").ask()

def monitor_menu(downloader, favorites_manager):
    monitor_manager = MonitorManager()
    
    while True:
        clear_screen()
        choice = questionary.select(
            "获取最新小说：",
            choices=[
                "开始检查",
                "配置",
                "返回上一级菜单"
            ],
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if choice == "开始检查":
            monitor_manager.start_check(downloader)
        elif choice == "配置":
            monitor_manager.configure_monitor(favorites_manager)
        elif choice == "返回上一级菜单":
            break

def function_menu(downloader, favorites_manager):
    while True:
        clear_screen()
        choice = questionary.select(
            "功能界面：",
            choices=[
                "从网址获取小说",
                "我的收藏夹",
                "获取最新小说",
                "返回上一级菜单",
                "退出"
            ],
            instruction="⌈ 使用↑↓选择 ⌋"  
        ).ask()
        
        if choice == "从网址获取小说":
            
            url = questionary.text("格式为 https://www.esjzone.one/detail/123456789.html\n请输入小说网址：").ask()
            if url:
                # 显示当前下载配置
                download_config = config.get('download')
                print(f"当前下载配置: {download_config}")
                try:
                    downloader.download(url)
                except Exception as e:
                    logger.error(f"下载失败: {e}")
                
                questionary.press_any_key_to_continue(message="按任意键继续...").ask()

        elif choice == "我的收藏夹":
            favorite_menu(downloader, favorites_manager)
        elif choice == "获取最新小说":
            monitor_menu(downloader, favorites_manager)
        elif choice == "返回上一级菜单":
            break
        elif choice == "退出":
            sys.exit(0)

def main_menu(downloader, username=None):
    # 初始化收藏夹管理器
    favorites_manager = FavoritesManager(downloader)

    while True:
        clear_screen()
        print(f"用户：{username or '未登录'}")
        choice = questionary.select(
            "请选择功能：",
            choices=[
                "进入功能界面",
                "编辑配置文件",
                "退出"
            ],
            instruction="⌈ 使用↑↓选择 ⌋"
        ).ask()
        
        if choice == "进入功能界面":
            function_menu(downloader, favorites_manager)
        elif choice == "编辑配置文件":
            edit_config_menu()
        elif choice == "退出":
            sys.exit(0)

def parse_cli_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="ESJZone 小说下载器")
    parser.add_argument("--max-threads", type=int, help="最大下载线程数")
    parser.add_argument("--timeout", type=int, help="超时时间（秒）")
    parser.add_argument("--retry-attempts", type=int, help="最大重试次数")
    
    # 使用 parse_known_args 避免与可能存在的其他参数冲突
    # 但在这里我们通常只关心这些参数
    args, unknown = parser.parse_known_args()
    
    if args.max_threads:
        config.set('download.max_threads', args.max_threads)
        logger.info(f"命令行覆盖：最大线程数设置为 {args.max_threads}")
    if args.timeout:
        config.set('download.timeout_seconds', args.timeout)
        logger.info(f"命令行覆盖：超时时间设置为 {args.timeout}")
    if args.retry_attempts:
        config.set('download.retry_attempts', args.retry_attempts)
        logger.info(f"命令行覆盖：最大重试次数设置为 {args.retry_attempts}")

def run_cli():
    # 1. 解析命令行参数
    parse_cli_args()
    
    # 2. 初始化下载器
    downloader = EsjzoneDownloader()
    
    # 3. 检查登录状态
    logger.info("正在检查登录状态...")
    username = downloader.validate_cookie()
    
    if username:
        logger.info(f"欢迎回来, {username} ⌈ Cookie 有效 ⌋")
    else:
        # 检查是否有保存的凭证
        stored_user = config.account.get('username')
        stored_pass = config.account.get('password')
        
        if stored_user and stored_pass:
            logger.info("Cookie 失效或不存在，尝试使用账号密码登录...")
            if downloader.login():
                logger.info("登录成功")
                # 再次获取用户名以显示
                username = downloader.validate_cookie()
                if not username:
                    username = stored_user
            else:
                logger.warning("登录失败，跳过")
        else:
            logger.info("未配置账号密码或配置不全，跳过登录")
            
    # 4. 进入主菜单
    # 为了能看到启动时的登录日志，稍微停顿一下
    time.sleep(1.5)
    
    main_menu(downloader, username)
