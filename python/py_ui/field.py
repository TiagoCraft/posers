from math import ceil
from numbers import Number
from typing import Callable, Optional

from . import QtCore, QtGui, QtWidgets, view


class ComboBox(QtWidgets.QComboBox):
    """Expand QComboBox with a searchable popup List.
    """

    proxy_model: view.ProxyModel
    """Proxy_view's model, based on the ComboBox's source model."""
    proxy_view: QtWidgets.QListView
    """Replaces the original view."""
    search_bar: 'SearchBar'
    """Used to filter the proxy_view."""

    def __init__(self, *args, **kwargs):
        """Default constructor."""
        super().__init__(*args, **kwargs)

        self.proxy_model = view.ProxyModel(self.model())

        self.proxy_view = QtWidgets.QListView()
        self.proxy_view.setModel(self.proxy_model)
        self.proxy_view.setEditTriggers(self.proxy_view.NoEditTriggers)
        self.proxy_view.clicked.connect(self.select)
        self.proxy_view.keyPressEvent = self.key_press

        self.search_bar = SearchBar()
        self.search_bar.search_listeners.append(self.search)
        self.search_bar.line.editingFinished.connect(self.proxy_view.setFocus)

    def search(
            self,
            pattern: Optional[str] = None,
            search_method: int = 1,
            case_sensitive: bool = False):
        """Filter the proxy model's content based on a string pattern.

        Args:
            pattern: only items with a text validating to the
                search pattern will be displayed. If no string is passed,
                remove the filtering and show all model items.
            search_method: informs which search method to use:
                either regex (0) or fuzzy match (1).
            case_sensitive: If set to True, only match
                characters to the pattern if they have the same case.
        """
        self.proxy_model.search(pattern, search_method, case_sensitive)

    def select(self, index: QtCore.QModelIndex):
        """Set current proxy_list selection as the ComboBox's selection.

        Args:
            index: proxy_model's (current) item index.
        """
        index = self.proxy_model.mapToSource(index).row()
        if index > -1:
            self.setCurrentIndex(index)
            self.hidePopup()

    def key_press(self, event: QtGui.QKeyEvent):
        """If pressing enter on the proxy_view, apply current selection.

        Args:
            event: The triggered event.
        """
        view = self.proxy_view
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.select(view.currentIndex())
        else:
            super(QtWidgets.QListView, view).keyPressEvent(event)
        event.accept()

    def showPopup(self):
        """Overloads base function to customize the popup."""
        super().showPopup()
        frame = self.findChild(QtWidgets.QFrame)
        layout = frame.layout()
        layout.addWidget(self.search_bar)
        layout.addWidget(self.proxy_view)
        self.search_bar.line.setFocus()


class LineEditWithDel(QtWidgets.QLineEdit):
    """QLineEdit with a popup clear button."""

    btn: QtWidgets.QPushButton
    """integrated clear button."""
    listeners: list[Callable]
    """holds functions to be called in order upon an editingFinished signal.
    These functions are called with the new text value of this widget as an
    argument."""

    def __init__(self, *args, **kwargs):
        """Default constructor."""
        super().__init__(*args, **kwargs)
        self.listeners = []
        btn = self.btn = QtWidgets.QPushButton(parent=self)
        btn.setStyleSheet("background-color: rgba(255, 255, 255, 0);"
                          "border: none")
        btn.hide()
        btn.setIcon(self.style().standardIcon(
            QtWidgets.QStyle.SP_DialogCloseButton))
        btn.clicked.connect(self.clear)
        layout = QtWidgets.QHBoxLayout()
        layout.addStretch()
        layout.addWidget(btn)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.editingFinished.connect(self.edit_finished)
        self.textChanged.connect(self.edit)

    def edit(self):
        """Hide or show the clear button as text changes."""
        self.btn.show() if self.text() else self.btn.hide()

    def edit_finished(self):
        """Execute any listening functions upon finishing editing text."""
        txt = self.text()
        [x(txt) for x in self.listeners]

    def clear(self):
        """Clear the text in this line edit and inform listening functions."""
        super().clear()
        self.edit_finished()


class Slider(QtWidgets.QLineEdit):
    """Alternative to QtWidgets.QSpinBox.

    It includes a slider bar in the background of the text field, which can be
    dragged horizontally to edit the value.
    Dragging the mouse vertically will alter the order of magnitude of the
    horizontal step - or how much it affects the slider's value.
    The step value is displayed in a pop-up label while clicking.
    Sliders initiate for float or int values, depending on the initial values.
    """

    DARK: QtGui.QColor = QtGui.QColor(0, 0, 0, 10)
    """Slider bar background color."""
    LIGHT: QtGui.QColor = QtGui.QColor(255, 255, 255, 12)
    """Slider bar color."""
    PRECISION: int = 3
    """The number of decimals if the Slider is initiated for float values."""
    _default_step = _step = 0.1
    _threshold = False
    """Set to True each time the mouse is pressed.
    While True, click+drag has no effect on the value, and the mouse must be
    moved 25 pixels before it is overcome, so as to clearly distinguish
    click+drag gestures from simple clicks with residual unintentional drag."""
    label: QtWidgets.QLabel
    """Displays the step value while clicking."""
    bounds: tuple[Optional[Number], Optional[Number]]
    """Minimum and maximum values for the slider. If any boundary is None, the
    slider won't have a lower and/or upper bound."""
    lock_mouse: bool = True
    """bool: If true, the mouse stays static during click+drag. This option is
    incompatible with remote desktop control. Default: True"""
    use_wheel: bool = False
    """bool: if True, scrolling over unfocused sliders will change it's value
    by the amount defined in the "step" attribute. Default: False"""

    def __init__(
            self,
            default_value: Optional[Number] = None,
            bounds: tuple[Optional[Number], Optional[Number]] = (None, None),
            step: Optional[Number] = None,
            parent: Optional[QtWidgets.QWidget] = None):
        """Default constructor.

        Args:
            default_value: initial value for the slider. If None (default), try
                to use the minimum value, and if not provided either, use 0.
            bounds: minimum and maximum values for the slider. If any boundary
                is None, the slider won't have a lower and/or upper bound.
            step: define the default_step used to increment the value while
                click+dragging.
            parent: parent widget or layout.
        """
        super().__init__(parent)
        self.bounds = bounds
        bounded = all(x is not None for x in bounds)

        # step label
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 2, 2)
        layout.addStretch()
        self.label = QtWidgets.QLabel(parent=parent)
        self.label.setStyleSheet('QLabel {background-color: hsl(0,0,50)}')
        layout.addWidget(self.label)
        self.label.hide()

        # set validator
        if any(isinstance(x, float) for x in bounds + (default_value,)):
            self.setValidator(
                QtGui.QDoubleValidator(
                    float(bounds[0]), float(bounds[1]), self.PRECISION)
                if bounded else
                QtGui.QDoubleValidator())
        else:
            self.setValidator(QtGui.QIntValidator(*bounds)
                              if bounded else
                              QtGui.QIntValidator())

        # set step
        if bounded and step is None:
            step = (bounds[1] - bounds[0]) * 0.1
        if step is not None:
            if isinstance(self.validator(), QtGui.QIntValidator):
                step = ceil(step)
            self.default_step = step

        # set default value
        for x in (default_value, bounds[0], 0):
            if x is not None:
                self.set_value(x)
                self._value = x
                break

        self.editingFinished.connect(self.update)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                           QtWidgets.QSizePolicy.Minimum)
        self.setMinimumSize(self.font().pixelSize() * 3,
                            self.font().pixelSize() * 2)

    def get_value(self) -> Number:
        """Get the slider's current value.

        Returns:
            the QLineEdit's current text as a number.
        """
        txt = self.text()
        if not txt:
            return self._value
        if txt.startswith('.'):
            txt = f'0{txt}'
        cls = (int if isinstance(self.validator(), QtGui.QIntValidator)
               else float)
        return cls(txt)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Arrow up and down keys will increment and decrement the value.

        Args:
            event: The triggered event.
        """
        key = event.key()
        if key in [16777235, 16777237]:
            step = self.default_step
            if isinstance(self.validator(), QtGui.QIntValidator):
                step = ceil(step)
            if key == 16777235:
                self.set_value(self.get_value() + step)
            elif key == 16777237:
                self.set_value(self.get_value() - step)
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Left mouse click+drag to change value.

        Horizontal motion changes the value, vertical motion changes the
        horizontal motion influence on the value.
        A 25 pixels drag threshold must be overcome first before dragging
        affects the slider's value.

        Args:
            event: The triggered event.
        """
        if event.buttons() == QtCore.Qt.LeftButton:
            pos = event.pos()
            offset = pos - self._click
            if self.lock_mouse:
                self._offset += offset
                QtGui.QCursor.setPos(self.mapToGlobal(self._click))
            else:
                self._offset = offset

            # vertical motion edits step
            offset_y = self._offset.y()
            vertical_step = self.font().pixelSize() * 5.0
            if abs(offset_y) > vertical_step:
                self.step = self.step * 10**(round(-offset_y / vertical_step))
                if self.step >= 1:
                    self.step = int(round(self.step))
                self._offset.setY(0)
                if not self.lock_mouse:
                    self._click.setY(pos.y())
                if isinstance(self.validator(), QtGui.QIntValidator):
                    self.step = max(self.step, 0.1)

            # if this is an integer slider and the offset is less than 1,
            # stop here and keep accumulating
            offset_x = self._offset.x()
            if isinstance(self.validator(), QtGui.QIntValidator):
                if abs(offset_x) * self.step * 0.5 < 1:
                    return

            # horizontal motion threshold must be overcome before value changes
            if self._threshold:
                if abs(offset_x) > 25:
                    self._threshold = False
                    offset_x = offset.x()
                    self._offset.setX(offset_x)
                else:
                    return

            offset_x = round(offset_x * 0.5) * self.step
            self.set_value(self.get_value() + offset_x)
            self._offset.setX(0)
            if not self.lock_mouse:
                self._click.setX(pos.x())

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Prepare a click or click+drag gesture.

        Stores the cursor position and value, resets the offset and threshold,
        sets step back to its default value and shows the step label.

        Args:
            event: The triggered event.
        """
        self._value = self.get_value()
        self._click = event.pos()
        self._threshold = True
        self._offset = QtCore.QPoint(0, 0)
        self.step = self.default_step
        if event.buttons() == QtCore.Qt.LeftButton:
            self.label.show()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        """Hide the step label. If no drag happened, set focus.

        Args:
            event: The triggered event.
        """
        self.label.hide()
        if self._threshold:
            self.selectAll()
            self.setFocus()
        else:
            self.deselect()
            self.clearFocus()

    def paintEvent(self, event):
        """Normal QLineEdit paint plus a background slider bar."""
        super().paintEvent(event)
        bounds = self.bounds
        if bounds[0] != bounds[1] and all(isinstance(x, Number)
                                          for x in bounds):
            w, h = self.width(), self.height()
            value = self.get_value()
            div = (value - bounds[0]) * w / (bounds[1] - bounds[0])
            painter = QtGui.QPainter(self)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(self.LIGHT)
            painter.drawRect(0, 0, div, h)
            painter.setBrush(self.DARK)
            painter.drawRect(div, 0, w - div, h)

    def set_value(self, value: Number):
        """Set the slider's value.

        Args:
            value: new value.
        """
        for f, v in zip((max, min), self.bounds):
            if v is not None:
                value = f(v, value)
        validator = self.validator()
        cls = int if isinstance(validator, QtGui.QIntValidator) else float
        if cls == float:
            value = round(value, self.PRECISION)
        self.setText(str(cls(value)))

    def update(self):
        """Synchronize the slider's cached value with the current value.

        The cached value is used to render the slider bar as it is dragged,
        until the mouse is released and the current value is finally accepted.
        """
        self._value = self.get_value()

    def wheelEvent(self, event):
        """Mouse scrolling will offset the Slider's value by the step amount"""
        focused = self.hasFocus()
        if self.use_wheel or focused:
            step = self.step
            if isinstance(self.validator(), QtGui.QIntValidator):
                step = ceil(step)
            self.set_value(
                self.get_value() + (step if event.delta() > 0 else -step))
            if not focused:
                self.editingFinished.emit()

    @property
    def default_step(self) -> Number:
        """Get or set the default step for changing the slider's value.

        Used by the scroll wheel and as initial step for the horizontal drag,
        which can be temporarily modulated by the vertical drag motion.

        Args:
            value: Usually a power of 10.

        Returns:
            Default step value.
        """
        return self._default_step

    @default_step.setter
    def default_step(self, value: Number):
        self._default_step = self.step = value

    @property
    def step(self) -> Number:
        """Get or set the step for changing the slider's value.

        Value offset for horizontal drag events and, optionally, for
        scroll wheel events too. Vertical drag alters this value.
        Editing this value updates the label's text.

        Args:
            value: Usually a power of 10.

        Returns:
            Default step value
        """
        return self._step

    @step.setter
    def step(self, value):
        self._step = value
        self.label.setText(str(value))

    value = property(get_value, set_value)


class SearchBar(QtWidgets.QWidget):
    """Support widget for searching views with a ProxyModel.

    It allows filtering  items using a pattern string and choosing
    from  available search methods and their variations.
    """

    search_listeners: list[Callable]
    """list of functions to call when the text in the search line is edited -
    typically, the search() method from the associated View's ."""
    _search_method = 1
    _case_sensitive = False

    def __init__(self, *args, **kwargs):
        """Default constructor."""
        self.search_listeners = []

        super().__init__(*args, **kwargs)
        metrics = QtGui.QFontMetricsF(self.font())
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        btn = QtWidgets.QPushButton(u'\u2315')
        layout.addWidget(btn)
        btn.setStyleSheet(
            "QPushButton::menu-indicator{width:0px;}"
            "QPushButton{background-color: rgba(255, 255, 255, 0);"
            "border: none}"
        )
        btn.setMinimumSize(metrics.width(u'\u2315') + 15,
                           metrics.height() * 1.5)
        line = self.line = LineEditWithDel()
        layout.addWidget(line, 1)
        line.setPlaceholderText(' search...')
        line.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                           QtWidgets.QSizePolicy.Ignored)
        line.listeners.append(self.search)
        # settings menu
        menu = QtWidgets.QMenu(self)
        self.sm_action = action = QtWidgets.QAction('fuzzy search', menu)
        action.setCheckable(True)
        action.setChecked(self._search_method == 1)
        action.triggered.connect(self.toggle_fuzzy)
        menu.addAction(action)
        self.cs_action = action = QtWidgets.QAction('case sensitive', menu)
        action.setCheckable(True)
        action.setChecked(self.case_sensitive)
        action.triggered.connect(self.toggle_case_sensitive)
        menu.addAction(action)
        btn.setMenu(menu)
        btn.clicked.connect(btn.showMenu)

    def search(self, text: str):
        """Trigger all the listening functions with the search arguments.

        These arguments are the input pattern, search method and case
        sensitivity.
        Called when the text line in this widget is edited.

        Args:
            text: search pattern as per the LineEditWithDel sub-widget.
        """
        search_method = self.search_method
        case_sensitive = self.case_sensitive
        [x(text, search_method, case_sensitive)
         for x in self.search_listeners]

    def toggle_case_sensitive(self):
        """Toggle the case_sensitive attribute value."""
        self.case_sensitive = not self.case_sensitive

    def toggle_fuzzy(self):
        """Toggle the search_method attribute value."""
        self.search_method = 1 - self.search_method

    @property
    def case_sensitive(self) -> bool:
        """Get/Set the case_sensitive attribute and trigger the search signal

        If True, take character case into account. Default: False.

        Args:
            value: new value for the case sensitivity attribute.

        Returns:
            current case_sensitive value.
        """
        return self._case_sensitive

    @case_sensitive.setter
    def case_sensitive(self, value: bool):
        self._case_sensitive = value
        self.cs_action.setChecked(value)
        self.search(self.line.text())

    @property
    def search_method(self) -> int:
        """Get/Set the search_method attribute and trigger the search signal

        Can be regex (0) or fuzzy (1) matching. Default: 1

        Args:
            value: new value for the search_method attribute.

        Returns:
            current search_method value.
        """
        return self._search_method

    @search_method.setter
    def search_method(self, value: int):
        self._search_method = value
        self.sm_action.setChecked(value)
        self.search(self.line.text())
