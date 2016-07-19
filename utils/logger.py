# coding:utf-8
import logging


handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(name)s] - %(levelname)s: %(message)s")
handler.setFormatter(formatter)


def getlog(logger="crawler"):
    logger = logging.getLogger(logger)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
