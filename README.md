# ESJ Zone Novel Downloader

一个用于从 ESJ Zone 下载小说的命令行工具。

## ✨ 功能特点

- **多格式支持**: 支持下载为 EPUB 和 TXT 格式。
  - EPUB 包含自动生成的封面、目录和简介页面。
- **交互式界面**: 简单易用的命令行交互菜单，支持键盘操作。
- **高级下载管理**:
  - **多线程下载**: 极速下载体验，支持自定义线程数。
  - **智能进度显示**: 实时显示下载进度条。
  - **非阻塞图片获取**: 文字内容与插图并行下载，互不阻塞。
- **书库管理**:
  - **收藏夹同步**: 支持获取账号收藏夹内容（按更新时间或收藏时间排序）。
  - **更新监控**: 可配置监控列表，自动检查并提示小说更新。
- **自定义配置**:
  - 自定义下载目录和文件命名方式（书名或编号）。
  - 支持自动创建书籍子目录。
  - 可调节超时时间与重试次数。
- **账号管理**: 支持设置账号密码（用于访问受限内容），自动处理 Cookie。
- **日志记录**: 详细的日志记录，方便排查问题。
- **现代化依赖管理**: 使用 `uv` 进行极速依赖安装和环境管理。

## 🚀 快速开始

### 前置要求

- Python 3.13 或更高版本
- Windows 操作系统 (推荐)

### 安装与运行

本项目提供了一个全自动启动脚本 `start.bat`，它可以自动处理依赖安装和程序启动。

1. **下载项目代码**

   ```bash
   git clone git@github.com:HIUEETR/esjzone-novel-downloader.git
   cd esjzone-novel-downloader
   ```

2. **运行启动脚本**
   双击运行 `start.bat` 或在命令行中执行：

   ```cmd
   start.bat
   ```

   脚本会自动检测环境自动使用 `uv` 来管理依赖并运行。如果未安装 `uv`，脚本会尝试自动安装。

### 手动运行 (如果不使用 start.bat)

如果你更喜欢手动管理：

**使用 uv (推荐):**

```bash
# 安装 uv (如果尚未安装)
pip install uv

# 运行程序 (自动处理虚拟环境和依赖)
uv run main.py
```

**使用 pip:**
由于项目默认使用 `pyproject.toml` 管理依赖，如果必须使用 pip，你需要手动安装所有依赖：

```bash
pip install -r requirements.txt
python main.py
```

## ⚙️ 配置说明

程序首次运行时会自动生成 `config.yaml` 配置文件。你可以通过 CLI 菜单修改配置，也可以直接编辑该文件。

主要配置项：

- **account**: 账号信息 (username, password)
- **download**:
  - `dir`: 下载目录 (默认为 `downloads`)
  - `format`: 下载格式 (`epub` 或 `txt`)
  - `naming_mode`: 命名模式 (`book_name` 或 `number`)
  - `use_book_dir`: 是否为每本书创建独立文件夹
  - `max_threads`: 最大下载线程数
  - `timeout_seconds`: 请求超时时间
  - `retry_attempts`: 失败重试次数
- **log**: 日志级别和保存路径

## 🛠️ 开发与贡献

本项目使用 `uv` 进行依赖管理。

## ✅TODO List

* [X] 分章节下载
* [X] 监控更新
* [X] 获取收藏列表
* [X] 鸣谢
* [X] 多线程
* [X] 图片章节互不阻塞
* [X] 进度条
* [X] CLI
* [X] 日志
* [X] 为epub添加封面和目录
* [X] 为epub添加简介
* [X] 登录
* [X] 获取图片
* [X] 获取小说

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=HIUEETR/esjzone-novel-downloader&type=Date)](https://star-history.com/#HIUEETR/esjzone-novel-downloader&Date)

## 🙏 致谢

<p align="center">
  <a href="https://github.com/404-novel-project/novel-downloader">
    <img src="https://github.com/404-novel-project.png" width="70px;" />
  </a>
  <a href="https://github.com/readest/readest">
    <img src="https://github.com/readest.png" width="70px;" />
  </a>
</p>

<p align="center">
  本项目的设计与实现受到  
  <b>novel-downloader</b> 的启发，  
  并推荐使用 <b>readest</b> 进行阅读。
</p>

## 📄 许可证

MIT License
