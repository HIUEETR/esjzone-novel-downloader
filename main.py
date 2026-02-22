import sys

from src.cli import run_cli
from src.config_loader import config
from src.logger_config import logger, setup_logger


def main():
    try:
        setup_logger(
            log_level=config.log.get("level", "INFO"),
            log_dir=config.log.get("dir", "./logs"),
            retention=config.log.get("retention", 30),
        )
    except Exception as e:
        print(f"日志系统初始化失败: {e}")
        sys.exit(1)

    logger.info("--- 程序启动 ---")

    try:
        run_cli()
    except KeyboardInterrupt:
        logger.warning("用户取消操作")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
