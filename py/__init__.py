import functools
import itertools


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


class IndexableGenerator:
    """Implement Sequence functionalities to a generator object.

    These include getitem, index and length. Values are cached as they are
    consumed from the generator.

    Attributes:
        cache (list): holds the values already extracted from the generator.
        it (generator): pointer to the input generator.
    """

    def __init__(self, it):
        """Default constructor.

        Args:
            it (generator): input generator to be treated as an indexable
            sequence.
        """
        self.cache = []
        self.it = it

    def __getitem__(self, index):
        """Get value(s) at input index/indices from the stream of values.

        Args:
            index (int or slice): either the index of an element in the
                sequence, or a slice of element indices.

        Returns:
            variable type: Either a tuple of values or a single value at
                input index/indices.
        """
        head = len(self.cache)
        if isinstance(index, slice):
            if index.start < 0 or index.stop < 0:
                self._consume()
            elif index.stop > head:
                r = list(itertools.islice(self.it, index.stop - head))
                self.cache.extend(r)
        elif index < 0:
            self._consume()
        elif index > head - 1:
            r = list(itertools.islice(self.it, index - head + 1))
            self.cache.extend(r)
            self.head += len(r)
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
    def cast(cls, func):
        """Decorator for functions returning a generator."""
        @functools.wraps(func)
        def decorated(*args, **kwargs):
            return cls(func(*args, **kwargs))
        return decorated

    def index(self, item):
        """Get the index of an item in the sequence.

        Args:
            item: object to search for.

        Returns:
            int: index of input item.

        Raises:
            ValueError: raised when item not found.
        """
        if item in self.cache:
            return self.cache.index(item)
        for x in self._iter():
            if x == item:
                return len(self.cache) - 1
        raise ValueError("{} not in IndexableGenerator".format(item))


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
