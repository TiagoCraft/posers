from maya import cmds, mel  # noqa: F401
from maya.api import OpenMaya as om  # noqa: F401
from py import ContextManager

from .log import logger  # noqa: F401


def get_selection_mode() -> str:
    """Get the current selection mode.

    Returns:
        selection mode. Default: 'object'
    """
    for x in ['object', 'component', 'root', 'leaf', 'template',
              'hierarchical', 'preset']:
        if cmds.selectMode(**{'q': True, x: True}):
            return x
    return 'object'


class KeepSel(ContextManager):
    """Context manager to preserve selection after code execution."""

    sel: list[str]
    """name of each selected node"""
    mode: str
    """current selection mode"""

    def __enter__(self):
        self.sel = cmds.ls(sl=1)
        self.mode = get_selection_mode()

    def __exit__(self, exc_type, exc_val, exc_traceback):
        cmds.selectMode(**{self.mode: True})
        cmds.select([x for x in self.sel if cmds.objExists(x)], ne=1)


def name_to_node(name):
    return om.MGlobal.getSelectionListByName(name).getDependNode(0)
