import sys
import os
import questionary
from src.client import EsjzoneDownloader
from src.config_loader import config
from src.logger_config import logger
from src.cookie_manager import cookie_manager

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

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

def function_menu(downloader):
    while True:
        clear_screen()
        choice = questionary.select(
            "功能界面：",
            choices=[
                "从网址获取小说",
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
                
                questionary.press_any_key_to_continue().ask()

        elif choice == "返回上一级菜单":
            break
        elif choice == "退出":
            sys.exit(0)

def main_menu(downloader, username=None):
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
            function_menu(downloader)
        elif choice == "编辑配置文件":
            edit_config_menu()
        elif choice == "退出":
            sys.exit(0)

def run_cli():
    # 1. 初始化日志系统 

    
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
    # 为了让用户能看到启动时的登录日志，稍微停顿一下
    import time
    time.sleep(1.5)
    
    main_menu(downloader, username)
