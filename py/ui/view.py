from . import QtCore
from .. import fuzzy_match


class ProxyModel(QtCore.QSortFilterProxyModel):
    """ProxyModel with recursive nested search.

    Searches can be performed using one of two methods:

      - **regex**: built-in Qt method; looks for consecutive sequences of
        characters and uses wildcards to represent characters between them.

      - **fuzzy**: looks for a non-consecutive sequence of characters. E.g:
        'hello world' will match the pattern 'hwd', but not 'hdw.

    Searches can also be case sensitive or insensitive.

    Attributes:
    """

    filter_pattern = ''
    """str: sequence of characters used to filter items with fuzzy find."""
    search_method = 1
    """int: 0 = Regex; 1 = fuzzy. Default: 1"""
    case_sensitive = False
    """bool: If true, take character case into account. Default: False"""

    def __init__(self, model):
        """Default constructor.

        Args:
            model (QtCore.QAbstractItemModel): source model for this proxy.
        """
        super().__init__()
        self.setSourceModel(model)
        self.setDynamicSortFilter(True)
        self.setFilterKeyColumn(-1)

    def fuzzy_filter(self, source_row, source_index):
        """Fuzzy matching method for filtering items in the proxy model.

        Recursively checks if any children of a given row passes the filter,
        in which case this row does too.

        Args:
            source_row (int): a row under the source_index QModelIndex
            source_index (QtCore.QModelIndex): holder of the input source_row.

        Returns:
            bool: True if a row is valid, False otherwise.
        """
        def recursion(row, parent_index):
            index = model.index(row, 0, parent_index)
            if not index.isValid():
                return False
            child_count = model.rowCount(index)
            if not child_count:
                return False
            for i in range(child_count):
                item = model.itemFromIndex(model.index(i, 0, index))
                result = fuzzy_match(item.text(), pattern, self.case_sensitive)
                if sum(x[1] - x[0] for x in result) == pattern_len:
                    return True
                if recursion(i, index):
                    return True
            return False

        pattern = self.filter_pattern
        if not pattern:
            return True
        pattern_len = len(pattern)
        model = self.sourceModel()
        item = model.itemFromIndex(model.index(source_row, 0, source_index))
        result = fuzzy_match(item.text(), pattern, self.case_sensitive)
        if sum(x[1] - x[0] for x in result) == pattern_len:
            return True
        return recursion(source_row, source_index)

    def regex_filter(self, source_row, source_index):
        """Traditional regex method to filter items in this proxy model.

        Recursively checks if any children of a given row passes the filter,
        in which case this row does too.

        Args:
            source_row (int): a row under the source_index QModelIndex
            source_index (QtCore.QModelIndex): holder of the input source_row.

        Returns:
            bool: True if a row is valid, False otherwise.
        """
        def recursion(row, parent_index):
            index = model.index(row, 0, parent_index)
            if not index.isValid():
                return False
            child_count = model.rowCount(index)
            if not child_count:
                return False
            for i in range(child_count):
                if super().filterAcceptsRow(i, index):
                    return True
                if recursion(i, index):
                    return True
            return False

        if super().filterAcceptsRow(source_row, source_index):
            return True
        model = self.sourceModel()
        return recursion(source_row, source_index)

    def filterAcceptsRow(self, source_row, source_index):
        """Redefinition of super method.

        Recursively checks if any children of a given row passes the filter,
        in which case this row does too.

        Args:
            source_row (int): a row under the source_index QModelIndex
            source_index (QtCore.QModelIndex): holder of the input source_row.

        Returns:
            bool: True if a row is valid, False otherwise.
        """
        f = self.fuzzy_filter if self.search_method == 1 else self.regex_filter
        return f(source_row, source_index)

    def search(self, text, search_method=1, case_sensitive=False):
        """Sets the expression for filtering what source data to show.

        If an empty string is passed, all the source content is included.

        Args:
            text (str): search string. Accepts wildcards syntax.
            search_method (int, optional): informs which search method to use:
                either regex (0) or fuzzy match (1). Default: 1
            case_sensitive (bool, optional): If set to True, only match
                characters to the pattern if they have the same case.
                Default: False
        """
        self.filter_pattern = text
        self.search_method = search_method
        self.case_sensitive = case_sensitive
        self.setFilterRegExp(QtCore.QRegExp(
            text,
            cs=(QtCore.Qt.CaseSensitive
                if case_sensitive else
                QtCore.Qt.CaseInsensitive),
            syntax=QtCore.QRegExp.Wildcard))
