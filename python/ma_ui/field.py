from math import ceil
from numbers import Number
from typing import Optional, Tuple

from ma import attribute, cmds
from py_ui import field

from . import QtCore, QtGui, QtWidgets


class MaSlider(field.Slider):
    """Builds upon py.core.ui.Slider to link it with a Maya attribute.

    Alternative to QtWidgets.QSpinBox. It includes a slider bar in the
    background of the text field, which can be dragged to edit the value.
    It initiates for float or int values depending on the Maya attribute type.
    """

    KEY = QtGui.QColor(205, 40, 40)
    ANIM = QtGui.QColor(220, 120, 120)
    EDIT = QtGui.QColor(255, 200, 200)
    LOCK = QtGui.QColor(160, 200, 240)  # 240, 240, 165
    auto_update: bool = False
    """If set to True, the attribute updates while dragging. Otherwise, wait
    for mouse release."""
    attr: str
    """name of the Maya attribute associated to this slider."""

    def __init__(
            self,
            attr: str,
            step: Optional[Number] = None,
            parent: Optional[QtWidgets.QWidget] = None):
        """Default constructor.

        Args:
            attr: name of a Maya float or int attribute to be represented by
                this slider.
            step: define the default_step used to increment the value while
                click+dragging.
            parent: parent widget or layout.
        """
        super(field.Slider, self).__init__(parent)
        self.attr = attr
        bounds = self.bounds
        bounded = all(x is not None for x in bounds)

        # step label
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 2, 2)
        layout.addStretch()
        self.label = QtWidgets.QLabel(str(self.step), parent=self.parent())
        self.label.setStyleSheet(
            'QLabel {background-color: hsl(0,0,50)}')
        layout.addWidget(self.label)
        self.label.hide()

        # set validator
        if cmds.getAttr(attr, type=1) == 'long':
            self.setValidator(QtGui.QIntValidator(*bounds)
                              if bounded else
                              QtGui.QIntValidator())
        else:
            self.setValidator(
                QtGui.QDoubleValidator(
                    bounds[0], bounds[1], self.PRECISION)
                if bounded else
                QtGui.QDoubleValidator())

        # set step:
        if bounded and step is None:
            step = (bounds[1] - bounds[0]) * 0.1
        if step is not None:
            if isinstance(self.validator(), QtGui.QIntValidator):
                step = ceil(step)
            self.default_step = step

        # set default value
        self.set_value(self._value)
        self.editingFinished.connect(self.update)

    @property
    def _value(self) -> Number:
        """Get Maya's attribute value.

        Returns:
            attribute value.
        """
        return cmds.getAttr(self.attr)

    @property
    def bounds(self) -> Tuple[Optional[Number], Optional[Number]]:
        """Minimum and maximum values of the corresponding Maya attribute.

        Returns:
            minimum (or None) and maximum (or None) boundaries.
        """

        node, attr = self.attr.split('.', 1)
        min, max = None, None
        if cmds.attributeQuery(attr, n=node, mne=1):
            min = cmds.attributeQuery(attr, n=node, min=1)[0]
        if cmds.attributeQuery(attr, n=node, mxe=1):
            max = cmds.attributeQuery(attr, n=node, max=1)[0]
        return min, max

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Left mouse click+drag to change value.

        Horizontal motion changes the value, vertical motion changes the
        horizontal motion influence on the value.
        A 25 pixels drag threshold must be overcome first before dragging
        affects the slider's value.

        If auto_update is True, the maya attribute updates while dragging.

        Args:
            event: the triggered event.
        """
        super().mouseMoveEvent(event)
        if self.auto_update and event.buttons() == QtCore.Qt.LeftButton:
            self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Prepare a click or click+drag gesture.

        Stores the cursor position and value, resets the offset and threshold,
        sets step back to its default value and shows the step label.

        While dragging, we'll update the value based on the displacement.
        Start's a maya Undo chunk, so that any changes to the maya attribute
        (be that live while dragging or only upon mouse release) only create a
        single entry in the undo stack.

        Attrs:
            event: the triggered event.
        """
        self._click = event.pos()
        self._threshold = True
        self._offset = QtCore.QPoint(0, 0)
        self.step = self.default_step
        if event.buttons() == QtCore.Qt.LeftButton:
            self.label.show()
        if self.auto_update:
            cmds.undoInfo(openChunk=True)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        """Hide the step label. If no drag happened, set focus.

        Args:
            event: the triggered event.
        """
        self.label.hide()
        if event.button() == QtCore.Qt.MiddleButton:
            attr = self.attr
            if attribute.state(attr) < 3:
                cmds.setKeyframe(attr)
            else:
                cmds.cutKey(attr, time=(cmds.currentTime(q=1),))
                self.value = self._value
            return
        if self._threshold:
            self.selectAll()
            self.setFocus()
        else:
            self.update()
            self.deselect()
            self.clearFocus()
        if self.auto_update:
            cmds.undoInfo(closeChunk=True)

    def update(self):
        """Set the Maya attribute's value with that of the slider."""
        cmds.setAttr(self.attr, self.value)

    def wheelEvent(self, event: QtGui.QWheelEvent):
        """Mouse scrolling offsets the slider's value by the step amount.

        Args:
            event: the triggered event.
        """
        super().wheelEvent(event)
        self.update()
