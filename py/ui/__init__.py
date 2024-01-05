from functools import partial
from typing import Callable, Iterable, Optional, Sequence, Tuple

from qtpy import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt
DIRECTIONS = [
    QtWidgets.QBoxLayout.Direction.TopToBottom,
    QtWidgets.QBoxLayout.Direction.LeftToRight]
ORIENTATIONS = [
    Qt.Orientation.Horizontal,
    Qt.Orientation.Vertical]


class MultiButton(QtWidgets.QWidget):
    """Button with a drop-down menu to choose between multiple actions.

    The major clickable area of the button fires the current (last used)
    action. Choosing another action from the drop-down menu both fires and
    defines it as the current action for the major button.
    """

    act_btn: QtWidgets.QPushButton
    """fires the current(last used) action."""
    act_on_switch: bool
    """toggles automatic action on switch."""
    current_action: Callable
    """the action fired when clicking the major button."""

    def __init__(
            self,
            actions: Tuple[Tuple[str, Callable]],
            parent: Optional[QtWidgets.QWidget] = None,
            act_on_switch: bool = True):
        """Default constructor.

        Args:
            actions: (str, function) pairs with the name and behavior of each
                option in the button's menu.
            parent: parent widget.
            act_on_switch: toggles automatic action on switch.
        """
        super().__init__(parent=parent)
        self.current_action = actions[0][1]
        self.act_on_switch = act_on_switch

        # layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        # main action button
        btn = self.act_btn = QtWidgets.QPushButton(actions[0][0])
        layout.addWidget(btn, 1)
        btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                          QtWidgets.QSizePolicy.Ignored)
        btn.clicked.connect(actions[0][1])

        # drop down button
        btn = self.switch_btn = QtWidgets.QPushButton()
        layout.addWidget(btn)
        btn.setIcon(self.style().standardIcon(
            QtWidgets.QStyle.SP_TitleBarUnshadeButton))
        i = self.font().pointSize()
        btn.setIconSize(QtCore.QSize(i, i))
        btn.setStyleSheet('QPushButton::menu-indicator{width:0px;}')
        btn.setFixedWidth(30)
        btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                          QtWidgets.QSizePolicy.Ignored)
        btn.clicked.connect(btn.showMenu)

        self.actions = actions

    @property
    def actions(self) -> Iterable[Tuple[str, Callable]]:
        """Get/Set the option actions of the button's menu.

        Args:
            value: (str, function) pairs with the name and behavior
            of each option in the button's menu.

        Returns:
            pairs with the name and behavior
            of each option in the button's menu.

        """
        return self._actions

    @actions.setter
    def actions(self, value: Sequence[Tuple[str, Callable]]):
        self._actions = value
        menu = QtWidgets.QMenu(self)
        for x in value:
            action = menu.addAction(x[0])
            action.triggered.connect(partial(self.switch_act, x))
        self.switch_btn.setMenu(menu)
        self.switch(value[0])

    def switch(self, action: Tuple[str, Callable]):
        """Update the current action of the button.

        Args:
            action: text to set on the main button and function to be set as
                it's click action. The function is not executed at this point.
        """
        self.act_btn.setText(action[0])
        self.act_btn.clicked.disconnect(self.current_action)
        self.current_action = action[1]
        self.act_btn.clicked.connect(action[1])

    def switch_act(self, action: Tuple[str, Callable]):
        """Update the current action of the button and fire it.

        Args:
            action: text to set on the main button and function to be set as
                it's click action. The function is also executed.
        """
        self.switch(action)
        if self.act_on_switch:
            action[1]()
