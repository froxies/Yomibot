import logging
import os
import sys
from logging.handlers import RotatingFileHandler
def setup_logger(name, log_file=None, level=logging.INFO):
    if not os.path.exists('logs'):
        try:
            os.makedirs('logs')
        except:
            pass
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.hasHandlers():
        return logger
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    if log_file:
        try:
            file_handler = RotatingFileHandler(f'logs/{log_file}', maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file handler for {name}: {e}")
    return logger