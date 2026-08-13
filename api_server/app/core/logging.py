"""日志配置模块，提供统一的日志格式与级别管理。"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """配置全局日志格式与级别。

    Args:
        level: 日志级别，开发环境建议 DEBUG，生产环境 INFO。
    """
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )