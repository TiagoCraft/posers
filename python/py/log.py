"""Define a root logger and formatters for all the codebase.

Helper functions ensure we nest all loggers under the root logger.
"""
import logging
import logging.handlers


#
# General purpose logger and formatters:
#
LOGGER_NAME: str = 'craft'

MINIMAL_FORMATTER = logging.Formatter(fmt='%(levelname)s : %(message)s')
# DEBUG : Hello world!

BASIC_FORMATTER = logging.Formatter(
    fmt='%(levelname)s (%(name)s): %(message)s')
# DEBUG (py) : Hello world!

TIMED_FORMATTER = logging.Formatter(
    fmt='%(levelno)02d | %(asctime)s | %(name)s : %(message)s',
    datefmt='%Y-%m-%d %H.%M.%S')
# 10 | 2000-01-01 00.00.01 | py : Hello world!
# .split(' : ', 1)[0].split(' | ') to grab different parts of the message

logger = logging.getLogger(LOGGER_NAME)
logger.setLevel(logging.INFO)
logger.propagate = 0


def get_logger(name: str, root: str = LOGGER_NAME) -> logging.Logger:
    """Get or create a logger nested under provided root logger.

    Args:
        name: name of the logger. Usually, the name of a module.
        root: name of the root logger. Default: LOGGER_NAME

    Returns:
        new Logger.
    """
    return logging.getLogger(f'{root}.{name}')


def set_level(level: int | str):
    """Set log and log handlers to input level.

    Args:
        level: if its a str use one of predefined levels in the logging module.
    """
    if isinstance(level, str):
        level = getattr(logging, level)
    logger.setLevel(level)
    for hndl in logger.handlers:
        hndl.setLevel(level)
