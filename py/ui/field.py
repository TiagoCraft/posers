from . import QtGui, QtWidgets


class LineEditWithDel(QtWidgets.QLineEdit):
    """QLineEdit with a popup clear button.

    Attributes:
        btn (QtWidgets.QPushButton):
        listeners (list of function): holds functions to be called in order
            upon an editingFinished signal. These functions are called with the
            new text value of this widget as an argument.
    """

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


class SearchBar(QtWidgets.QWidget):
    """Support widget for searching views with a ProxyModel.

    It allows filtering ProxyModel items using a pattern string and choosing
    from  available search methods and their variations.

    Attributes:
        search_listeners (list of function): list of functions to call when the
            text in the search line is edited - typically, the search() method
            from the associated View's ProxyModel.
    """

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

    def search(self, text):
        """Trigger all the listening functions with the search arguments.

        These arguments are the input pattern, search method and case
        sensitivity.
        Called when the text line in this widget is edited.

        Args:
            text (str): search pattern as per the LineEditWithDel sub-widget.
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
    def case_sensitive(self):
        """Get/Set the case_sensitive attribute and trigger the search signal

        If True, take character case into account. Default: False.

        Args:
            value (bool): new value for the case sensitivity attribute.

        Returns:
            bool: current case_sensitive value.
        """
        return self._case_sensitive

    @case_sensitive.setter
    def case_sensitive(self, value):
        self._case_sensitive = value
        self.cs_action.setChecked(value)
        self.search(self.line.text())

    @property
    def search_method(self):
        """Get/Set the search_method attribute and trigger the search signal

        Can be regex (0) or fuzzy (1) matching. Default: 1

        Args:
            value (int): new value for the search_method attribute.

        Returns:
            int: current search_method value.
        """
        return self._search_method

    @search_method.setter
    def search_method(self, value):
        self._search_method = value
        self.sm_action.setChecked(value)
        self.search(self.line.text())
