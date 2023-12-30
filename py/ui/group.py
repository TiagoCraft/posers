from typing import Callable, Iterator, List, Optional

from .. import IndexableGenerator
from . import QtWidgets, Qt


class Splitter(QtWidgets.QSplitter):
    """QSplitter with custom handles that get centered when double-clicked."""

    rotate_listeners: List[Callable]
    """Sequence of functions subscribed a Splitter's rotate events. When the
    splitter's layout is rotated, the functions are triggered."""
    drag_listeners: List[Callable]
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
    def widgets(self) -> Iterator[QtWidgets.QWidget]:
        for i in range(self.count()):
            yield self.widget(i)


class SplitterHandle(QtWidgets.QSplitterHandle):
    """Custom handle that gets centered when double clicked.

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
    def index(self) -> Optional[int]:
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
