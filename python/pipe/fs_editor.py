"""GUI for managing FS configuration files as per the pipe.fs module."""

import json
import os
import sys
from collections import OrderedDict
from functools import partial
from typing import Any

from pipe import fs, settings
from py_ui import QtCore, QtGui, QtWidgets, group


class TreeItem(QtWidgets.QTreeWidgetItem):
    """Qt item representing a branch in an FS QTreeWidget."""

    palette = {
        'bg': {'default': {False: QtCore.Qt.transparent,
                           True: QtGui.QColor(255, 150, 150)}},
        'fg': {'default': {False: QtCore.Qt.black,
                           True: QtCore.Qt.white},
               3: {False: QtCore.Qt.gray,
                   True: QtGui.QColor(200, 200, 200)}}}

    def __init__(
            self,
            branch: fs.Branch,
            table: QtWidgets.QTableWidget,
            *args,
            **kwargs):
        """Default constructor.

        Args:
            branch: FS Branch to be represented by the item.
            table: The table widget used to display the branch's config.
            """
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.table = table
        self.setFlags(self.flags() | QtCore.Qt.ItemIsEditable)
        self.setIcon(0, icons[branch.type])
        self.setText(0, str(branch.id))
        if branch.type == 'root':
            self.setText(2, str(next(iter(branch.mounts.values()))['linux']))
        else:
            self.setText(1, str(branch.get('priority', '')))
            self.setText(2, str(branch.config.get('nc', '')))
        self.setText(3, str(branch.get('description', '')))
        self.setForeground(3, QtGui.QBrush(QtCore.Qt.gray))
        if branch.children:  # False if not a list
            for child in branch.children:
                branch = TreeItem(child, table)
                self.addChild(branch)

    def setData(self, column: int, role: Any, value: Any):
        """Set data for the item.

        Called by the table widget when the user edits a cell.

        Args:
            column:  The column of the cell that was edited.
            role: Describes the type of data specified by value, and is defined
                by the ItemDataRole enum.
            value: The new value entered by the user.
        """
        super().setData(column, role, value)
        if not isinstance(value, (str, int, bool)):
            return
        is_root = self.branch.type == 'root'
        if is_root and column == 1:
            return
        if is_root and column == 2:
            mount = next(iter(self.branch.mounts.values()))
            old_value = mount['linux']
            mount['linux'] = value
        else:
            key = ('id', 'priority', 'nc', 'description')[column]
            old_value = self.branch.get(key)
            if key == 'priority' and value:
                value = int(value)
            if value != '' or key == 'id':
                self.branch.config[key] = value
            elif key in self.branch.config:
                del self.branch.config[key]
        if value == old_value:
            return
        w = self.table.cellWidget((1, 5, 3, 2)[column], 1)
        if w:
            w.setText(str(value))
        tree = self.treeWidget()
        if tree:
            fs_editor = tree.parent().parent().parent()
            fs_editor.dirty = True
            if column == 0:
                fs_editor.check_ids()


class FSEditor(QtWidgets.QWidget):
    """Widget for managing a single FS configuration file.

    Attributes:
        fs: The FS instance currently being edited.
        file_change_listeners: List of functions to be called when the
            currently edited file changes.
        tree: The QTreeWidget displaying the FS hierarchy.
        table: The QTableWidget displaying the currently selected branch's
            config.
    """

    def __init__(self, **kwargs):
        """Default constructor."""
        super().__init__(**kwargs)
        self.fs = fs.FS()
        self.file_change_listeners = []
        self._cache = None
        self._dirty = False
        self._title = None

        layout = QtWidgets.QVBoxLayout(self)
        splitter = group.Splitter(QtCore.Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        # tree
        widget = QtWidgets.QWidget()
        splitter.addWidget(widget)
        widget_layout = QtWidgets.QVBoxLayout(widget)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QtWidgets.QTreeWidget()
        widget_layout.addWidget(self.tree)
        self.tree.currentItemChanged.connect(self.branch_changed)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(
            self.launch_context_menu)
        self.tree.setHeaderLabels(
            ['id', 'rank', 'nc', 'description'])
        header = self.tree.header()
        header.resizeSection(0, 500)
        header.resizeSection(1, 50)
        header.resizeSection(2, 250)
        header.setSectionResizeMode(1, header.Fixed)

        # preview label
        scroll_area = QtWidgets.QScrollArea()
        widget_layout.addWidget(scroll_area)
        scroll_area.setFrameShape(scroll_area.NoFrame)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(
            QtGui.QFontMetrics(self.font()).height() * 2)
        self.path_label = QtWidgets.QLabel()
        scroll_area.setWidget(self.path_label)
        self.path_label.setAlignment(QtCore.Qt.AlignTop)
        self.path_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse)

        # table
        self.table = QtWidgets.QTableWidget()
        splitter.addWidget(self.table)

        # editing buttons
        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        row.addStretch()
        new_btn = QtWidgets.QPushButton("new")
        new_btn.clicked.connect(self.new)
        row.addWidget(new_btn)
        open_btn = QtWidgets.QPushButton("open")
        open_btn.clicked.connect(self.open)
        row.addWidget(open_btn)
        save_btn = QtWidgets.QPushButton("save as")
        save_btn.clicked.connect(self.save)
        row.addWidget(save_btn)

        # shortcuts
        sc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+o"), self)
        sc.activated.connect(self.open)
        sc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+s"), self)
        sc.activated.connect(lambda *_: self.save(self._title))
        sc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Shift+s"), self)
        sc.activated.connect(self.save)
        sc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+c"), self)
        sc.activated.connect(self.copy_branch)
        sc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+x"), self)
        sc.activated.connect(self.cut_branch)
        sc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+v"), self)
        sc.activated.connect(self.paste_branch)
        sc = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+d"), self)
        sc.activated.connect(self.duplicate_branch)
        sc = QtWidgets.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key_Delete), self)
        sc.activated.connect(self.delete_branch)

        self.resize(1024, 900)
        h = self.height()
        splitter.moveSplitter(h - 575, 1)

    def branch_changed(self, item: TreeItem, previous_item: TreeItem):
        if item is None:
            return
        branch = item.branch
        table = self.table
        table.clearSpans()
        table.setRowCount(6)
        table.verticalHeader().hide()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(['label', 'value'])
        header = table.horizontalHeader()
        header.resizeSection(0, 150)
        header.setStretchLastSection(True)
        row = 0
        for key in ['type',
                    'id',
                    'description',
                    'mounts' if branch.type == 'root' else 'nc',
                    're',
                    'priority']:
            table.setCellWidget(row, 0, QtWidgets.QLabel(key))
            if key == 're':
                widget = QtWidgets.QCheckBox()
                widget.setChecked(branch.get(key, False))
                widget.stateChanged.connect(
                    partial(self.change_entry, widget, branch, key))
            else:
                widget = QtWidgets.QLineEdit()
                widget.editingFinished.connect(
                    partial(self.change_entry, widget, branch, key))
                widget.setText(str(branch.get(key, '')))
                if key == 'type':
                    widget.setEnabled(False)
                if key == 'description':
                    widget.setPlaceholderText(
                        'Please describe the purpose of this branch')
            table.setCellWidget(row, 1, widget)
            row += 1
        self.path_label.setText(branch.pnc)

    def change_entry(self, widget, branch, key, *_):
        if isinstance(widget, QtWidgets.QCheckBox):
            branch.config[key] = widget.isChecked()
            self.dirty = True
            return

        old_value = branch.config.get(key, '')
        new_value = widget.text()
        if old_value != new_value:
            item = self.tree.currentItem()
            if key == 'id':
                branch.config[key] = new_value
                # update current tree item's name
                item.setText(0, new_value)
                self.check_ids()
            else:
                if key == 'priority':
                    item.setText(1, new_value)
                    if new_value:
                        new_value = int(new_value)
                elif key == 'nc':
                    self.path_label.setText(branch.pnc)
                    item.setText(2, new_value)
                elif key == 'description':
                    item.setText(3, new_value)
                if new_value == '':
                    del branch.config[key]
                else:
                    branch.config[key] = new_value
            self.dirty = True

    def check_ids(self):
        def recursion(item):
            dup = ids.count(item.branch.id) > 1
            font = item.font(0)
            fg, bg = item.palette['fg'], item.palette['bg']
            for i in range(4):
                item.setForeground(i, fg.get(i, fg['default'])[dup])
                item.setBackground(i, bg.get(i, bg['default'])[dup])
                font.setItalic(dup)
                item.setFont(i, font)
                item.setIcon(2, icons['alert'] if dup else QtGui.QIcon())
            [recursion(item.child(i)) for i in range(item.childCount())]
        ids = self.fs.ids
        [recursion(self.tree.topLevelItem(i))
         for i in range(self.tree.topLevelItemCount())]

    def closeEvent(self, event):
        event.accept() if self.save_if_dirty() else event.ignore()

    def copy_branch(self):
        self._cache = self.tree.currentItem().branch.serialize()

    def create_branch(self, data, parent=None):
        if data['type'] == "root":
            branch = fs.Branch(data, self.fs)
            new_item = TreeItem(branch, self.table)
            self.tree.addTopLevelItem(new_item)
        else:
            parent_item = parent or self.tree.currentItem()
            if parent_item.branch.children is False:
                msg = QtWidgets.QMessageBox()
                msg.setText("this branch type can't get pregnant")
                msg.exec_()
                return
            else:
                branch = fs.Branch(data, parent_item.branch)
                new_item = TreeItem(branch, self.table)
                parent_item.addChild(new_item)
        self.tree.setCurrentItem(new_item)
        self.check_ids()
        self.dirty = True

    def cut_branch(self):
        self.copy_branch()
        self.delete_branch()

    def delete_branch(self):
        tree = self.tree
        item = tree.currentItem()
        item.branch.delete()
        par = item.parent()
        if par:
            par.takeChild(par.indexOfChild(item))
        else:
            tree.takeTopLevelItem(tree.indexOfTopLevelItem(item))
        self.check_ids()
        self.dirty = True

    def duplicate_branch(self):
        cache = self._cache
        self.copy_branch()
        self.paste_branch(self.tree.currentItem().parent())
        self._cache = cache

    def launch_context_menu(self, pos):
        menu = QtWidgets.QMenu()
        action = QtWidgets.QAction('&copy', menu)
        menu.addAction(action)
        action.triggered.connect(self.copy_branch)
        action = QtWidgets.QAction('c&ut', menu)
        menu.addAction(action)
        action.triggered.connect(self.cut_branch)
        if self._cache:
            action = QtWidgets.QAction('&paste', menu)
            menu.addAction(action)
            action.triggered.connect(self.paste_branch)
        action = QtWidgets.QAction('&duplicate', menu)
        menu.addAction(action)
        action.triggered.connect(self.duplicate_branch)
        action = QtWidgets.QAction('d&elete', menu)
        action.triggered.connect(self.delete_branch)
        menu.addAction(action)
        menu.addSection('Create:')
        for fs_type in ['root', 'folder', 'file']:
            action = QtWidgets.QAction(fs_type, menu)
            menu.addAction(action)
            action.triggered.connect(
                partial(self.create_branch, {'type': fs_type, 'id': ''}))
        menu.exec_(self.mapToGlobal(pos))

    def new(self):
        if not self.save_if_dirty():
            return
        self.tree.clear()
        self.fs = fs.FS()
        self.title = 'Untitled'

    def open(self, path=None):
        if not self.save_if_dirty():
            return
        fp = path or QtWidgets.QFileDialog.getOpenFileName(filter='*.json')[0]
        if fp:
            self.fs = fs.FS.deserialize(
                json.load(open(fp, "r"), object_pairs_hook=OrderedDict))
            self.refresh()
            self.title = fp

    def paste_branch(self, parent=None):
        self.create_branch(self._cache, parent)

    def refresh(self):
        self.tree.clear()
        for branch in self.fs.children:
            self.tree.addTopLevelItem(TreeItem(branch, self.table))
        self.check_ids()

    def save(self, path=None):
        fp = path or QtWidgets.QFileDialog.getSaveFileName(filter='*.json')[0]
        if fp:
            json.dump(self.fs.serialize(), open(fp, "w"),
                      indent=2, separators=(',', ': '))
            self.title = fp
            self.dirty = False
            return True
        return False

    def save_if_dirty(self):
        if self._dirty:
            msg = QtWidgets.QMessageBox()
            msg.setText(f"{self.title} has been modified.")
            msg.setInformativeText("Do you want to save your changes?")
            msg.setStandardButtons(msg.Save | msg.Discard | msg.Cancel)
            msg.setDefaultButton(msg.Save)
            value = msg.exec_()
            if value == msg.Cancel:
                return False
            if value == msg.Save:
                if not self.save(self._title):
                    return False
        return True

    @property
    def dirty(self):
        return self._dirty

    @dirty.setter
    def dirty(self, value):
        if self._dirty == value:
            return
        self._dirty = value
        bar = self.parent().parent().tabBar()
        i = bar.currentIndex()
        curr_name = bar.tabText(i)
        if value:
            bar.setTabText(i, f'{curr_name} *')

    @property
    def title(self):
        return self._title or 'Untitled'

    @title.setter
    def title(self, value):
        self._title = value
        [f(self, value or 'Untitled') for f in self.file_change_listeners]


class TabWidget(group.TabWidget):
    """Tab Widget for holding multiple FSEditors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resize(1024, 900)
        self.add_tab()

    def add_tab(self):
        """Add a new FSEditor tab."""
        w = FSEditor()
        self.addTab(w, w.title)
        w.file_change_listeners.append(self.rename_tab)
        self.setCurrentWidget(w)

    def closeEvent(self, event):
        """Override closeEvent to prompt user to save dirty tabs."""
        for i in range(self.count()):
            if not self.widget(i).save_if_dirty():
                event.ignore()
                return
        event.accept()

    def rename_tab(self, widget, name):
        """Rename a tab.

        Args:
            widget: The widget whose tab to rename.
            name: The new name for the tab.
            """
        self.tabBar().setTabText(self.indexOf(widget), name)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    root = os.path.realpath(
        f'{os.path.split(__file__)[0]}/../../resources')
    icons = {k: QtGui.QIcon(os.path.join(root, f'{k}_transparent.png'))
             for k in ['alert', 'file', 'folder', 'root']}
    win = TabWidget()
    win.setWindowTitle(f'FS {os.getenv("REZ_BISNAGA_VERSION")}')
    win.setWindowIcon(QtGui.QIcon(os.path.join(root, 'parcel.png')))
    win.widget(0).open(fs.get_default_config_path(settings['local pipeline']))
    win.show()
    app.exec_()
