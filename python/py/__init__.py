"""Core python package with general use functionalities and variables.

These should be callable from any python environment.
"""

import functools
import importlib
import itertools
import json
import os
import pkgutil
from types import ModuleType
from typing import Any, Callable, Iterator, Optional, Union, _alias


class ContextManager:
    """Baseclass for context managers that can also be used as decorators.

    Examples:
        .. code-block:: python

            with ContextManager() as cm:
                print(cm)

            @ContextManager()
            def foo():
                print("bar")
    """

    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper

    def __enter__(self):
        # Implement this method in subclasses
        pass

    def __exit__(self, exc_type, exc_val, exc_traceback):
        # Implement this method in subclasses
        pass


def fuzzy_match(string, pattern, case_sensitive=False):
    """Search for non-consecutive character sequence in a string.

    Translated from the javascript solution proposed by Bulat Bochkariov here:
    https://www.quora.com/How-is-the-fuzzy-search-algorithm-in-Sublime-Text-\
    designed-How-would-you-design-something-similar/answer/Bulat-Bochkariov

    Args:
        string (str): string on which to search for the fuzzy 'pattern' chars.
        pattern (str): sequence of characters to be fuzzy-found on 'string'.
        case_sensitive (bool, optional): if set to false, string and pattern
            are converted to lower case before comparison, hence disregarding
            character case. Default: False

    Returns:
        list of 2-list of int: in-out indices of matched substrings.
    """
    if not case_sensitive:
        string, pattern = string.lower(), pattern.lower()
    cursor, slices = 0, []
    for i, char in enumerate(string):
        if char == pattern[cursor]:
            if slices and i == slices[-1][-1]:
                slices[-1][-1] = i + 1
            else:
                slices.append([i, i + 1])
            cursor += 1
            if cursor >= len(pattern):
                break
    return slices


def import_package(
        start_module: ModuleType,
        recursive: Optional[bool] = False,
        fail: Optional[bool] = False):
    """Recursively import all submodules of a package or of a module's package.

    Args:
        start_module: package name.
        recursive: if True, import submodules of subpackages. Default: False
        fail: if True, raise ImportError on failure. Default: False
    """
    pkg_path, module_file = os.path.split(start_module.__file__)
    pkg_name = (start_module.__name__
                if module_file.startswith('__init__.') else
                start_module.__name__.rsplit('.', 1)[0])
    for x in pkgutil.walk_packages([pkg_path], f'{pkg_name}.'):
        try:
            module = importlib.import_module(x[1])
            if fail:
                print(f'successfully imported {x[1]}')
            if recursive and x[2]:
                import_package(module, fail)
        except ImportError as e:
            if fail:
                raise e
            print(f'failed to import {x[1]}')


class IndexableGenerator:
    """Implement Sequence functionalities to a generator object.

    These include getitem, index and length. Values are cached as they are
    consumed from the generator.
    """

    cache:  list[Any]
    """Holds the values already extracted from the generator."""
    it: Iterator[Any]
    """Pointer to the input generator."""

    def __init__(self, it: Iterator[Any]):
        """Default constructor.

        Args:
            it: input generator to be treated as an indexable sequence.
        """
        self.cache: list[Any] = []
        self.it: Iterator[Any] = it

    def __getitem__(self, index: int | slice) -> tuple[Any] | Any:
        """Get value(s) at input index/indices from the stream of values.

        Args:
            index: either the index of an element in the sequence, or a slice
                of element indices.

        Returns:
            Either a tuple of values or a single value at input index/indices.
        """
        head = len(self.cache)
        if isinstance(index, slice):
            if index.start < 0 or index.stop < 0:
                self._consume()
            elif index.stop > head:
                r = list(itertools.islice(self.it, index.stop - head))
                self.cache.extend(r)
        elif index < 0:
            if not len(self):
                return
        elif index > head - 1:
            r = list(itertools.islice(self.it, index - head + 1))
            self.cache.extend(r)
            head += len(r)
        return self.cache.__getitem__(index)

    def __iter__(self):
        return itertools.chain(self.cache, self._iter())

    def __len__(self):
        self._consume()
        return len(self.cache)

    def __next__(self):
        """Transparently delegate calls to next() to the inside generator."""
        try:
            result = next(self.it)
            self.cache.append(result)
            return result
        except StopIteration:
            return None

    def _consume(self):
        result = list(self.it)
        self.cache.extend(result)

    def _iter(self):
        for x in self.it:
            self.cache.append(x)
            yield x

    @classmethod
    def cast(cls, func: Callable) -> Callable:
        """Decorator for functions returning a generator."""
        @functools.wraps(func)
        def decorated(*args, **kwargs):
            return cls(func(*args, **kwargs))
        return decorated

    def index(self, item: Any) -> int:
        """Get the index of an item in the sequence.

        Args:
            item: object to search for.

        Returns:
            index of input item.

        Raises:
            ValueError: raised when item not found.
        """
        if item in self.cache:
            return self.cache.index(item)
        for x in self._iter():
            if x == item:
                return len(self.cache) - 1
        raise ValueError(f"{item} not in IndexableGenerator")


T_IndexableGenerator = _alias(IndexableGenerator, 1)


class Settings(dict):
    """Settings dictionary that can get saved to a json file when edited.

    The dictionary can be initiated from a defaults dictionary or file.
    Once edited, values are stored to the destination settings file, which in
    turn overrides the defaults.
    Alternatively, Settings can be nested, so that editing a child instance
    triggers the parent's `save` method.
    """

    storage: Optional[Union[str, 'Settings']] = None
    """path to a file where to store values once edited, or to a parent
    Settings instance"""

    def __init__(
            self,
            storage: Optional[Union[str, 'Settings']] = None,
            default: Optional[Union[str, dict, 'Settings']] = None):
        """Default constructor.

        Args:
            storage:
                path to the file storing custom settings or parent Settings.
            default:
                default settings file or dict.
        """
        self.storage = storage
        if default:
            if isinstance(default, str):
                default = json.load(open(default, 'r'))
            self.update(default)
        self.load()

    def __setitem__(self, key, value):
        """Set a key-value pair and store the dictionary to the json file."""
        super().__setitem__(key, value)
        if self.storage:
            self.save()

    def load(self, storage: Optional[str] = None):
        """Load data from a file or current storage. Convert dicts to Settings.

        Args:
            storage:
                filepath to load. If not provided, use this instance's current
                storage if any.
        """
        storage = storage or self.storage
        if storage and isinstance(storage, str) and os.path.exists(storage):
            self.update(json.load(open(storage, 'r')))
        for k, v in self.items():
            if isinstance(v, dict):
                self[k] = Settings(self, v)

    def reload(self):
        """Clear and load again from storage, if any."""
        self.clear()
        self.load()

    def save(self):
        """Save Settings to storage file or trigger parent Settings save method

        Raises:
            IOError: if trying to save a Settings with undefined storage.
        """
        if not self.storage:
            raise IOError('no file path specified')
        if isinstance(self.storage, str):
            os.makedirs(os.path.dirname(self.storage), exist_ok=True)
            json.dump(self, open(self.storage, 'w'),
                      indent=4, sort_keys=True, separators=(',', ':'))
        elif self.storage.storage:
            self.storage.save()
