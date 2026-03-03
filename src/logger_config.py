import sys
from pathlib import Path
from loguru import logger
import logging


def setup_logger(log_level: str = "INFO", log_dir: str = "./logs", retention: int = 30):
    """
    配置 loguru 日志系统
    """
    # 移除默认的 handler
    logger.remove()

    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 定义日志格式
    # 时间 | 级别 | 模块:函数:行号 - 消息
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    # 添加控制台输出
    logger.add(sys.stderr, format=log_format, level=log_level, colorize=True)

    # 添加文件输出 (按天轮转)
    # 文件名格式: esjzone_downloader_YYYY-MM-DD.log
    log_file_path = log_path / "esjzone_downloader_{time:YYYY-MM-DD}.log"

    logger.add(
        log_file_path,
        format=log_format,
        level=log_level,
        rotation="00:00",  # 每天午夜轮转
        retention=f"{retention} days",  # 保留指定天数
        encoding="utf-8",
        enqueue=True,  # 线程安全
    )

    # 拦截标准库 logging (可选，如果依赖库使用了 logging)
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            # 获取对应的 Loguru 级别
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # 找到调用者的帧
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )

    logging.basicConfig(handlers=[InterceptHandler()], level=0)

    logger.info("日志系统初始化完成")


# 导出 logger 实例
__all__ = ["setup_logger", "logger"]
