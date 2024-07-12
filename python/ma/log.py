"""Default configuration for loggers within Maya.

The default logger is assigned a Handler to output to Maya's log in the
ScriptEditor.
 """

import maya.utils
from py.log import TIMED_FORMATTER, get_logger, logger  # noqa

gui_log_handler = maya.utils.MayaGuiLogHandler()
gui_log_handler.setFormatter(TIMED_FORMATTER)

if not any(isinstance(x, maya.utils.MayaGuiLogHandler)
           for x in logger.handlers):
    logger.addHandler(gui_log_handler)
