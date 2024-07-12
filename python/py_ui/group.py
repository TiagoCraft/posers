from collections import OrderedDict
from typing import Any, Callable, Optional

from py import IndexableGenerator, T_IndexableGenerator

from . import Qt, QtGui, QtWidgets, factory


class Splitter(QtWidgets.QSplitter):
    """QSplitter with custom handles that get centered when double-clicked."""

    rotate_listeners: list[Callable]
    """Sequence of functions subscribed a Splitter's rotate events. When the
    splitter's layout is rotated, the functions are triggered."""
    drag_listeners: list[Callable]
    """Sequence of functions subscribed a Splitter's handle dragging events.
    When any of the splitter's handles is dragged, the functions are triggered.
    """

    def __init__(self, *args, **kwargs):
        """Default constructor."""
        super(Splitter, self).__init__(*args, **kwargs)
        self.rotate_listeners = []
        self.drag_listeners = []

    def createHandle(self) -> QtWidgets.QSplitterHandle:
        """Overload of superclass' function.

        Returns:
            Custom handle that moves to the center of adjacent widgets when
            double-clicked.
        """
        return SplitterHandle(self.orientation(), self)

    def center_handle(self, i: int):
        """Center a handle between adjacent widgets to even their sizes.

        Args:
            i: index of the handle to be centered.
        """
        attr = ('width', 'height')[self.orientation() == Qt.Vertical]
        w = sum(getattr(self.widget(j), attr)() for j in (i - 1, i))
        sizes = self.sizes()
        sizes[i - 1: i + 1] = [w / 2] * 2
        self.setSizes(sizes)
        [f() for f in self.drag_listeners]

    def distribute_handles(self):
        """Evenly distribute SplitterHandles."""
        attr = ('width', 'height')[self.orientation() == Qt.Vertical]
        n_widgets = self.count()
        self.setSizes([getattr(self, attr)() / float(n_widgets)] * n_widgets)
        [f() for f in self.drag_listeners]

    def rotate(self):
        """Alternate Splitter's orientation between vertical and horizontal."""
        ori = [Qt.Orientation.Vertical, Qt.Orientation.Horizontal]
        i = 1 - ori.index(self.orientation())
        self.setOrientation(ori[i])
        [f(i) for f in self.rotate_listeners]

    @property
    @IndexableGenerator.cast
    def widgets(self) -> T_IndexableGenerator[QtWidgets.QWidget]:
        for i in range(self.count()):
            yield self.widget(i)


class SplitterHandle(QtWidgets.QSplitterHandle):
    """Custom handle that gets centered when double-clicked.

    The handle moves to the center of adjacent widgets, to evenly distribute
    their width.
    """

    def __init__(self,
                 orientation: Qt.Orientation = Qt.Orientation.Horizontal,
                 parent: Optional[QtWidgets.QSplitter] = None):
        """Default constructor.

        Args:
            orientation: Default is Horizontal.
            parent: Default is None.
        """
        super(SplitterHandle, self).__init__(orientation, parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.launch_context_menu)

    @property
    def index(self) -> int:
        """Get the index of this handle in the Splitter's handles array.

        Returns:
            index of this SplitterHandle
        """
        par = self.splitter()
        n_widgets = par.count()
        for i in range(n_widgets):
            if par.handle(i) is self:
                return i

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Pressing with middle mouse button rotates the Splitter's layout.

        Args:
            event: the triggered event.
        """
        if event.buttons() == Qt.MiddleButton:
            self.splitter().rotate()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Overload of super class' function.

        Center handle between adjacent widgets.

        Args:
            event (QtGui.QMouseEvent): the triggered event.
        """
        if event.buttons() == Qt.LeftButton:
            self.splitter().center_handle(self.index)

    def launch_context_menu(self, pos):
        """Launch right click context menu.

        Args:
            pos (QtCore.QPoint): position where the context menu should appear.
        """
        par = self.splitter()
        menu = QtWidgets.QMenu()
        action = QtWidgets.QAction('rotate', menu)
        action.triggered.connect(par.rotate)
        menu.addAction(action)
        action = QtWidgets.QAction('center', menu)
        action.triggered.connect(lambda: par.center_handle(self.index))
        menu.addAction(action)
        action = QtWidgets.QAction('center all', menu)
        action.triggered.connect(par.distribute_handles)
        menu.addAction(action)
        menu.exec_(self.mapToGlobal(pos))


class TabBar(QtWidgets.QTabBar):
    """Custom QTabBar that closes tabs on middle click."""

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """middle click closes tab"""
        btn = event.button()
        if btn == Qt.LeftButton:
            # left click: activate tab
            super().mousePressEvent(event)
        elif btn == Qt.MiddleButton:
            # middle click: close tab
            self.parent().close_tab(self.tabAt(event.pos()))


class TabWidget(QtWidgets.QTabWidget):
    """QTabWidget with a button to add new tabs and a custom QTabBar."""

    def __init__(self, *args, **kwargs):
        """Default constructor."""
        super().__init__(*args, **kwargs)
        self.setTabBar(TabBar())
        self.setMovable(True)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)
        btn = QtWidgets.QPushButton('+')
        btn.clicked.connect(self.add_tab)
        self.setCornerWidget(btn)

    @classmethod
    def deserialize(cls, data: dict[str, Any], *args, **kwargs) -> 'TabWidget':
        """Create and populate a TabWidget out of serialized data.

        Args:
            data: dictionary with serialized data.
        """
        self = cls(*args, **kwargs)
        for x, y in zip(data['content'], data['titles']):
            if x['type'] in factory:
                self.addTab(factory[x['type']].deserialize(x), y)
            else:
                self._deserialize(x, y)
        count = self.count()
        if not count:
            self.add_tab()
        self.setCurrentIndex(max(data['current'], self.count() - 1))
        return self

    def _deserialize(self, data, name=None):
        """Implement in subclasses deserialization of specific content types"""
        pass

    def add_tab(
            self, widget: Optional[QtWidgets.QWidget] = None, name: str = ''):
        """Add a new tab to the TabWidget.

        Args:
            widget: widget to add to the new tab. If not provided, an empty
                QWidget is created.
            name: name of the tab. If not provided, the name of the widget's
                class (or 'empty' if none) is used.
        """
        if not widget:
            widget = QtWidgets.QWidget()
            name = name or 'empty'
        self.addTab(widget, name or widget.__class__.__name__)
        self.setCurrentWidget(widget)

    def close_tab(self, i: int):
        """Close the tab at input index.

        Args:
            i: index of the tab to close.
        """
        if self.count() > 1:
            self.widget(i).deleteLater()
            self.removeTab(i)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        """Add a new tab on double click.

        Args:
            event: the triggered event.
        """
        if event.pos().y() < self.tabBar().height():
            self.add_tab()

    def serialize(self) -> OrderedDict:
        """Serialize the TabWidget and it's contents.

        Returns:
            serialized data as an OrderedDict.
        """
        count = self.count()
        return OrderedDict(
            type=self.__class__.__name__,
            content=[w.serialize()
                     if hasattr(w, 'serialize') else
                     {'type': w.__class__.__name__}
                     for w in self.widgets],
            titles=[self.tabText(i) for i in range(count)],
            current=self.currentIndex())

    @property
    def widgets(self):
        """Generator of the TabWidget's contents.

        Yields:
            widgets in the TabWidget.
        """
        for i in range(self.count()):
            yield self.widget(i)


factory[TabWidget.__name__] = TabWidget
