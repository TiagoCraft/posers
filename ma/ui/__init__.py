import shiboken2
from maya import OpenMayaUI

from ...py.ui import QtCore, QtGui, QtWidgets  # noqa


def get_maya_window() -> QtWidgets.QMainWindow:
    """Retrieve main Maya Window.

    Returns:
        QMainWindow holding Maya's main GUI.
    """
    ptr = OpenMayaUI.MQtUtil.mainWindow()
    return shiboken2.wrapInstance(ptr, QtWidgets.QMainWindow)
