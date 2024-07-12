"""File System module used to define and access expected folder/file structures.

Provides a way to define a naming convention for folders and files, and
automatically generate paths to them based on input context. It also provides
a way to search for data on disk based on FS definitions and input context.
"""

import json
import os
import re
from collections import OrderedDict
from copy import deepcopy
from functools import partial
from typing import Any, Iterable, Iterator, Optional, Union

from py import IndexableGenerator, T_IndexableGenerator, log

from . import LOCAL_DEV_PATH, REMOTE_DEV_PATH, settings

NAMED_GROUP_PATTERN = re.compile(
    r'\(\?P<(?P<name>[a-zA-Z_]\w*?)>(?P<rule>.+?)\)'
    r'|'
    r'\(\?P=(?P<name_ref>[a-zA-Z_]\w*?)\)')
OPTIONAL_GROUP_PATTERN = re.compile(
    r'\(\?:(?P<content>(.*?({}).*?)+?)\)\?'.format(
        NAMED_GROUP_PATTERN.pattern))
TOKEN_PATTERN = re.compile(r'(\{(?P<token>.+?)})')

logger = log.get_logger(__name__)
handler = log.logging.StreamHandler()
handler.setFormatter(log.TIMED_FORMATTER)
logger.addHandler(handler)


class Branch:
    """Representation of an expected data element in the FS.

    There are several types of branch, as per their config dictionary, which
    will behave differently. The basic ones are:

        - **root**: represents mount points, which can be represented
          differently on different OS' and can be mounted or have mirrors in
          different locations. They often sit at the base of a branch
          hierarchy.
        - **folder**: common folder, treated equally on all OS'. Might hold
          child branches.
        - **file**: files can not hold child branches.
    """

    children: bool | list['Branch']
    """FS Branches nested under this one. If False, this element can't have
    nested Branches."""
    config: dict[str, Any]
    """construct defining and used to initialize this branch in the form:
    ::

        {
            'type': branch type (str),
            'id': unique name in the FS (str),
            ['description': purpose of this branch (str),]
            'mounts': {
                mount name (str): {
                    OS (str): regex/tokenized naming convention (str)}}
            OR
            ['nc': regex/tokenized naming convention (str)
                   Default: id,]
            ['re': True if using regex naming convention (bool)
                   Default: False,]
            ['priority': lower number = higher priority when matching
                         a name against the naming convention of a set
                         of branches (int). Default: 0,]
            ['children': nested branches (bool or list of Branch)
                         Default: False for files, or [] otherwise,]
        }
    
    the `children` key is removed upon initialization and replaced by the
    `children` attribute."""

    def __init__(
            self, config: dict, parent: Optional[Union['Branch', 'FS']] = None):
        """Default constructor.

        Args:
            config: construct used to initialize this branch
            parent: parent branch or FS. If not provided, this is a root Branch.
        """
        self._parent = None
        self.config = config
        self.parent = parent
        # init children
        children = config.get('children')
        if children is False or (self.type == 'file' and children is None):
            self.children = False
            return
        self.children = []
        for child in children or []:
            Branch(child, self)
        if 'children' in self.config:
            del self.config['children']

    def __getitem__(
            self, index: int | slice
    ) -> Union['Branch', list['Branch']]:
        """Delegate to `self.children`

        Args:
            index: If `slice`, return a list of Branches. Otherwise, return a
                single Branch.

        Returns:
            child branch(es)

        Raises:
            TypeError: if `self.children` is False (example: file branches)
        """
        return self.children[index]

    def __getattr__(self, key: str) -> Any:
        """Try to get attribute from self.__dict__ or delegate to self.config.

        Args:
            key: attribute name

        Returns:
            attribute value
        """
        return self.__dict__.get(key, self.config[key])

    def __iter__(self) -> Iterator['Branch']:
        """Delegates to `self.children`

        Returns:
            children iterator

        Raises:
            TypeError: if `self.children` is False (example: file branches)
        """
        return iter(self.children or [])

    def __repr__(self) -> str:
        return f'{self.__class__.__name__} <{self.id}>'

    def build_fs(
            self,
            context: Optional[dict[str, str]] = None,
            mount: Optional[str] = None):
        """Create folder structure at a give mount for this branch and context.

        Args:
            context: tokens required by the branch's naming convention.
            mount: The mount to be used on the root branch. If not provided, use
                the first (preferred) mount.
        """
        context = context or {}
        path = os.path.expanduser(self.merge(
            context, mount=mount, parents=True))
        if not os.path.exists(path):
            if not self.parent:
                raise RuntimeError(
                    f"Can't create file system for orphan branch {self!r}")
            if not isinstance(self.parent, FS):
                self.parent.build_fs(context, mount=mount)
            if self.children is not False:
                os.mkdir(path)

    def delete(self):
        """Unparent this branch and delete it"""
        self.parent = None
        [x.delete() for x in self.children or []]
        del self

    @IndexableGenerator.cast
    def find(
            self,
            context: Optional[dict[str, str]] = None,
            **kwargs
    ) -> T_IndexableGenerator[tuple[str, dict]]:
        """Get disk data matching this branch's criteria and input context.

        For name convention tokens not specified in the context, any found
        values are valid.

        Args:
            context: tokens required by the branch's naming convention.
            \\*\\*kwargs: keyword-arguments for the get_convention method, such
                as a specific mount. Some arguments will be ignored or
                overriden.

        Returns:
            Generator of tuple(data path (str), data context (dict)).
            Empty generator if root branch (often a mount point) doesn't exist.
        """
        def recursion(hierarchy, context):
            branch = hierarchy[0]
            # get the path for current branch and input context
            path = branch.merge(context, parents=True, **kwargs)
            if os.path.exists(os.path.join(path, '')):
                # iterate folder contents
                for child in os.listdir(path):
                    child_path = os.path.join(path, child)
                    is_dir = os.path.isdir(child_path)
                    # check if child path matches any of the child branches
                    for child_branch in branch.sorted_children:
                        if is_dir == (child_branch.type in ['root', 'folder']):
                            match = child_branch.match(child, **kwargs)
                            if match:
                                # child path matches a child branch
                                if child_branch.id == hierarchy[1].id:
                                    # that's the next branch in the hierarchy
                                    child_context = match.groupdict()
                                    if all(v == context.get(k, v)
                                           for k, v in child_context.items()):
                                        # child's context matches input context
                                        child_context.update(context)
                                        if len(hierarchy) > 2:
                                            for x in recursion(hierarchy[1:],
                                                               child_context):
                                                yield x
                                        else:
                                            yield child_path, child_context
                                break

        if 'parents' in kwargs:
            del kwargs['parents']
        hierarchy = self.hierarchy
        if isinstance(hierarchy[0], FS):
            hierarchy = hierarchy[1:]
        if os.path.exists(hierarchy[0].merge(context, parents=True, **kwargs)):
            return recursion(hierarchy, context or {})
        return IndexableGenerator(iter([]))

    @IndexableGenerator.cast
    def find_in_mounts(
            self,
            context: Optional[dict[str, str]] = None,
            mounts: Optional[str | Iterable[str]] = None,
            flat: bool = True, **kwargs
    ) -> T_IndexableGenerator[Iterator | tuple[str, dict[str, str]]]:
        """Get data matching this branch and input context on multiple mounts.

        For name convention tokens not specified in the context, any found
        values are valid.

        Args:
            context: tokens required by the branch's naming convention.
            mounts: One or more root mounts. If not provided (default), use all
                mounts by their preferred order.
            flat: If True, return a single generator of results. Otherwise,
                yields a generator per mount.
            \\*\\*kwargs: keyword-arguments for the get_convention method.
                Some arguments will be ignored or overriden.

        Returns:
            generator per mount or a single, flat generator of
            (data path (str), data context (dict))
        """
        hierarchy = self.hierarchy
        if isinstance(hierarchy[0], FS):
            hierarchy = hierarchy[1:]
        mounts = mounts or hierarchy[0].mounts
        if isinstance(mounts, str):
            mounts = [mounts]
        if 'mount' in kwargs:
            del kwargs['mount']
        if flat:
            return (x for mount in mounts
                    for x in self.find(context, mount=mount, **kwargs))
        return (self.find(context, mount=mount, **kwargs) for mount in mounts)

    def get(self, *args, **kwargs) -> Any:
        """Wrapper around this Branch's `config.get` method"""
        return self.config.get(*args, **kwargs)

    def get_convention(
            self,
            parents: bool = False,
            mount: Optional[str] = None,
            platform: Optional[str] = None,
            pretty: bool = False) -> str:
        """Get the naming convention for this branch.

        Args:
            parents (bool, optional): If True, return the naming convention
                for the whole hierarchy up to this Branch. Default: False,
            mount (str, optional): Root mount whose naming convention to pick.
                If not provided (default), use first (preferred) mount.
            platform (str, optional): OS whose naming convention to pick.
                If not provided (default), use current OS.
            pretty (bool, optional): If True, return a more readable
                tokenized naming convention. Default: False

        Returns:
            str: This branch's regex or tokenized naming convention.

        """
        def cleanup(match_obj):
            d = match_obj.groupdict()
            k = d['name'] or d['name_ref']
            v = d['rule']
            if k in tokens:
                if v and v != tokens[k]:
                    raise re.error(
                        'inconsistent rule for recurring token '
                        f'{{{k}}} in {self!r}: "{tokens[k]}"" != "{v}"')

                return f'(?P={k})'
            tokens[k] = v
            return f'(?P<{k}>{d["rule"] or ".+?"})'

        def pretty_optional_tokens(match_obj):
            return match_obj.groupdict()['content']

        def pretty_tokens(match_obj):
            d = match_obj.groupdict()
            return f'{{{d["name"] or d["name_ref"]}}}'

        def replace_tokens(match_obj):
            return f'(?P<{match_obj.groupdict().get("token")}>.+?)'

        result, tokens = [], {}
        hierarchy = self.hierarchy
        if isinstance(hierarchy[0], FS):
            hierarchy = hierarchy[1:]
        for p in hierarchy if parents else [self]:
            if p.type == 'root':
                mount = (next(iter(p.mounts.values()))
                         if mount is None else
                         p.mounts[mount])
                nc = (mount['linux' if os.name == 'posix' else 'windows']
                      if platform is None else
                      mount[platform])
            else:
                nc = p.get('nc', p.id)
            if not p.get('re'):
                nc = TOKEN_PATTERN.sub(
                    replace_tokens,
                    nc.replace('\\', '\\\\').replace('.', r'\.'))
            result.append(nc)
        nc = NAMED_GROUP_PATTERN.sub(cleanup, os.path.join(*result))
        if pretty:
            nc = OPTIONAL_GROUP_PATTERN.sub(pretty_optional_tokens, nc)
            nc = NAMED_GROUP_PATTERN.sub(pretty_tokens, nc).replace('\\', '')
        return nc

    def get_branch(self, name: str) -> Optional['Branch']:
        """Get Branch under this one by its unique name.

        Args:
            name (str): name of the Branch.

        Returns:
            Branch: instance if found. None otherwise.
        """
        if name == self.id:
            return self
        else:
            for child in self:
                match = child.get_branch(name)
                if match:
                    return match

    def get_parent(self) -> Optional[Union['FS', 'Branch']]:
        """Get this Branch's parent, if any.

        Returns:
            parent instance or None if this is a root
        """
        return self._parent

    def get_tokens(
            self,
            parents: bool = False,
            children: bool = False,
            optional: Optional[bool] = None,
            **kwargs
    ) -> dict[str, str]:
        """Get the tokens (and their rule) from this branch.

        Optionally, append the tokens of all branches under and/or above in the
        hierarchy, and include or filter in/out optional tokens.

        Args:
            parents: Default: False,
            children: Default: False,
            optional: Only returns optional tokens if True, non-optional if
                False or all if unspecified.
            \\*\\*kwargs: keyword-arguments for the get_convention() method.

        Returns:
            {token name (str): regex rule (str)} pairs
        """
        try:
            convention = self.get_convention(**kwargs)
            if not optional:  # None or False
                tokens = {}
                for x in NAMED_GROUP_PATTERN.finditer(convention):
                    d = x.groupdict()
                    k = d['name'] or d['name_ref']
                    tokens[k] = d['rule'] or tokens.get(k, '.+?')
            if optional is not None:  # True or False
                optional_tokens = {}
                for x in OPTIONAL_GROUP_PATTERN.finditer(convention):
                    d = x.groupdict()
                    k = d['name'] or d['name_ref']
                    optional_tokens[k] = d['rule'] or tokens.get(k, '.+?')
                if optional:
                    tokens = optional_tokens
                else:
                    tokens = {k: v for k, v in tokens.items()
                              if k not in optional_tokens}
        except re.error as e:
            logger.critical(f"Problematic convention in {self!r}: "
                            f"{self.get_convention(**kwargs)}\n{e.msg}")
            tokens = {}

        if parents and isinstance(self.parent, Branch):
            tokens.update(
                self.parent.get_tokens(parents=True, optional=optional))

        if children and self.children:
            for x in self:
                child_tokens = x.get_tokens(children=True, optional=optional)
                tokens = child_tokens | tokens

        return tokens

    def match(self, name: str, *args, **kwargs) -> Optional[re.Match]:
        """Check if a given string matches this branch's naming convention.

        Args:
            name: input string, normally a folder/file name or path.
            \\*args: arguments for the get_convention() method
            \\*\\*kwargs: keyword-arguments for the get_convention() method

        Returns:
            re.Match, or None if no match
        """
        nc = self.get_convention(*args, **kwargs)
        if nc.startswith('~'):
            nc = nc.replace('~', os.path.expanduser('~'), 1)
        return re.match(f'^({nc})$', name)

    def merge(self, context: Optional[dict[str, str]] = None, **kwargs) -> str:
        """Generate a name or path out of this branch and input context.

        Args:
            context: tokens required by the branch's naming convention.
            \\*\\*kwargs: keyword-arguments for the get_convention() method.

        Returns:
            resulting name or path

        Raises:
            ValueError: if a context with all required tokens isn't provided.
        """
        def tokens(match_obj):
            d = match_obj.groupdict()
            token = d['name'] or d['name_ref']
            if token in context.keys():
                return context[token]
            kwargs['pretty'] = True
            raise ValueError("missing value for token '{0}': {1}".format(
                token,
                ' ' * (15 - len(token)) + self.get_convention(**kwargs)))

        def optional_tokens(match_obj):
            content = match_obj.groupdict()['content']
            for x in NAMED_GROUP_PATTERN.finditer(content):
                d = x.groupdict()
                kw = d['name'] or d['name_ref']
                if kw not in context or not context[kw]:
                    return ''
            return NAMED_GROUP_PATTERN.sub(tokens, content)

        context = context or {}
        # sanitize convention
        nc = self.get_convention(**kwargs)
        if nc.startswith('~'):
            nc = nc.replace('~', os.path.expanduser('~'), 1)
        result = OPTIONAL_GROUP_PATTERN.sub(
            optional_tokens, f'^({nc})$').replace('\\', '')[2:-2]
        return NAMED_GROUP_PATTERN.sub(tokens, result)

    def parse(self, name: str, *args, **kwargs) -> Optional[dict[str, str]]:
        """Extract context from input path.

        Args:
            name: string to be tested against input naming convention.
            \\*args: arguments for the get_convention() method
            \\*\\*kwargs: keyword-arguments for the get_convention() method

        Returns:
            token-value pairs; None for invalid names
        """
        match = self.match(name, *args, **kwargs)
        if match:
            return match.groupdict()
        logger.warning(
            "{} doesn't match {!r} naming convention: {}".format(
                name, self, self.get_convention(*args, **kwargs)))

    def serialize(self, children: bool = True) -> dict[str, Any]:
        """Serialize this Branch in a JSON compatible format.

        Args:
            children: If True, includes the serialization of all the hierarchy
                of Branches under this one.

        Returns:
            serialized branch definition.
        """
        result = deepcopy(self.config)
        if children and self.children:
            result['children'] = [x.serialize(children=True)
                                  for x in self.children]
        return result

    def set_parent(self, parent: Union['FS', 'Branch', None]):
        """Update the parent of this Branch.

        Args:
            parent: Set to None to unparent this Branch, detaching it from the
                FS hierarchy.
        """
        if self._parent:
            self._parent.children.remove(self)
        self._parent = parent
        if parent and self not in parent.children:
            parent.children.append(self)

    def valid(self, context: dict[str, str]) -> bool:
        """Check if input context dict meets this Branch's naming rules.

        Args:
            context: tokens required by the branch's naming convention.

        Returns:
            True if all tokens are valid, False otherwise.
        """
        tokens = self.get_tokens(parents=True, optional=False)
        if all(x in context for x in tokens):
            tokens |= self.get_tokens(parents=True, optional=True)
            return all(re.match(f'^({tokens[x]})$', context[x])
                       for x in tokens)
        return False

    nc = property(partial(get_convention, parents=True))
    """This Branch's naming convention.

    Returns:
        str: full regex naming convention for this OS and default mount.
    """

    @property
    def hierarchy(self) -> list[Union['FS', 'Branch']]:
        """Get this Branch's every parent.

        Returns:
            FS or Branch
        """
        return (self.parent.hierarchy
                if not isinstance(self.parent, (None.__class__, FS)) else
                []) + [self]

    @property
    def leaves(self) -> list['Branch']:
        """Finds ending branches.

        Returns:
            branches with no children
        """
        if not self.children:
            return [self]
        return [y for x in self for y in x.leaves]

    optional_tokens = property(
        partial(get_tokens, parents=True, optional=True))
    """Optional tokens and their rule for this Branch's full naming convention.

    Returns:
        dict: {token name (str): regex rule (str)} pairs
    """

    parent = property(get_parent, set_parent)

    pnc = property(partial(get_convention, parents=True, pretty=True))
    """This Branch's pretty naming convention.

    Returns:
        str: full tokenized naming convention for this OS and default mount.
    """

    @property
    def sorted_children(self) -> list['Branch']:
        """Get child branches (if any), sorted by the ones you like the most.

        Returns:
            sorted children
        """
        return sorted(self.children, key=lambda a: a.get('priority', 0))

    tokens = property(partial(get_tokens, parents=True))
    """Tokens (and their rule) for this Branch's full naming convention.

    Returns:
        dict: {token name (str): regex rule (str)} pairs
    """


class FS:
    """Representation of a File System. Main entry point for this module.

    An FS is a collection of Branches, each representing a folder or file in the
    expected structure. The FS can be serialized and deserialized to/from JSON,
    and saved to disk.
    """

    filepath: str
    """path to the source file if constructed from a config dictionary loaded
    from disk."""
    children: list[Branch]
    """Branches describing expected folder and file structure."""

    def __init__(self):
        """Default constructor."""
        self.filepath = ''
        self.children = []

    def __getitem__(self, index: int | slice) -> Branch | list[Branch]:
        """Delegate to `self.children`

        Args:
            index (int or slice):

        Returns:
            Branch or list of Branch
        """
        return self.children[index]

    def __iter__(self) -> Iterator[Branch]:
        """Delegates to self.children

        Returns:
            children iterator
        """
        return iter(self.children)

    @classmethod
    def deserialize(cls, config: list[dict[str, Any]]) -> 'FS':
        """Construct instance from serialized data.

        Args:
            config: serialized FS configuration.

        Returns:
            new instance
        """
        self = cls()
        self.children = [Branch(x, self) for x in config]
        return self

    @classmethod
    def load(cls, filepath: Optional[str] = None) -> 'FS':
        """Deserialize from data stored on disk.

        Args:
            filepath: Path to a file with serialized configuration data.
                If not provided, use the default configuration file.

        Returns:
            new instance
        """
        filepath = filepath or get_default_config_path(
            local=settings.get('local pipeline'))
        with open(filepath, 'r') as f:
            self = cls.deserialize(json.load(f, object_pairs_hook=OrderedDict))
        self.filepath = filepath
        return self

    def get_branch(self, name: str) -> Optional[Branch]:
        """Recursively find a child Branch by its name.

        Args:
            name: branch ID

        Returns:
            Branch instance if found. None otherwise.
        """
        for x in self:
            matched = x.get_branch(name)
            if matched:
                return matched

    def save(self, filepath: Optional[str] = None):
        """Serialize and save this FS to disk.

        Args:
            filepath: File where to store serialized data.
                If not provided (default), use this instance's `filepath`
                attribute or throw an error if empty.

        Raises:
            IOError: if missing a filepath where to store.
        """
        filepath = filepath or self.filepath
        if not filepath:
            raise IOError(f"Please provide a filepath for storing {self!r}.")
        json.dump(self.serialize(), open(filepath, 'w'), indent=4)

    def serialize(self) -> list[dict[str, Any]]:
        """Serialize this FS in a JSON compatible format.

        Returns:
            serialized Branch definitions.
        """
        return [x.serialize(children=True) for x in self]

    @property
    def ids(self) -> list[str]:
        """List the ID of all branches and sub-branches.

        This can be used, for instance, to look for duplicate IDs.

        Returns:
            each branch and sub-branch ID.
        """
        def recursion(branches):
            result = []
            for branch in branches:
                result.extend([branch.id] + recursion(branch.children or []))
            return result
        return recursion(self.children)

    @property
    def leaves(self) -> list[Branch]:
        """Finds ending branches.

        Returns:
            A list of branches with no children
        """
        return [y for x in self for y in x.leaves]

    @property
    def tokens(self) -> dict[str, str]:
        """Get the tokens (and their rule) from all branches in this FS.

        Returns:
            (token name (str), regex rule (str)) pairs
        """
        return {k: v for x in self
                for k, v in x.get_tokens(children=True).items()}


def get_data_path(
        branch_name: str,
        context: dict[str, str],
        mounts: Optional[str | Iterable[str]] = None,
        local: Optional[bool] = None
) -> Iterator | tuple[str, dict[str, str]]:
    """Utility to get the path to some data on disk.

    Args:
        branch_name: name of the Branch representing requested data.
        context: tokens required by the branch's naming convention.
        mounts: if provided sequentially look for the FS definition on these
            mounts by input order, ignoring unspecified mounts. Otherwise, look
            for it in every mount.
        local: use the local default FS config to start from if True, or the
            remote if False. If not provided grab the local if it exists or fall
            back to remote otherwise.

    Returns:
        generator per mount or a single, flat generator of
        tuple(data path (str), data context (dict))
    """
    default_config_path = get_default_config_path(local=local)
    err = ValueError(f'Branch not found: {branch_name}')
    branch = None
    if 'project' in context:
        fs = get_project_fs(context, mounts, local)
        branch = fs.get_branch(branch_name)
        if not branch and fs.filepath == default_config_path:
            raise err
    branch = branch or FS.load(default_config_path).get_branch(branch_name)
    if not branch:
        raise err
    return branch.find_in_mounts(context, mounts=mounts)


def get_default_config_path(local: Optional[bool] = None) -> str:
    """Path to the file with the default FS configuration.

    Args:
        local: return the local path if True or remote path if
            False. If not provided (default) grab the local if it exists or
            fall back to remote otherwise.

    Returns:
        filepath
    """
    result = os.path.join(
        REMOTE_DEV_PATH if local is False else LOCAL_DEV_PATH,
        'scripts', 'fs.json')
    if local is None and not os.path.exists(result):
        result = os.path.join(REMOTE_DEV_PATH, 'scripts', 'fs.json')
    return result


def get_project_fs(
        context: str | dict[str, str],
        mounts: Optional[str | Iterable[str]] = None,
        local: Optional[bool] = None) -> FS:
    """Get the FS for input project.

    Args:
        context: name of a project or dictionary defining it.
        mounts: if provided sequentially look for the FS definition on these
            mounts by input order, ignoring unspecified mounts. Otherwise, look
            for it in every mount.
        local: use the local default FS config to start from if True, or the
            remote if False. If not provided grab the local if it exists or fall
            back to remote otherwise.

    Returns:
        FS instance
    """
    if isinstance(context, str):
        context = {'project': context}
    fs = FS.load(get_default_config_path(local=local))
    branch = fs.get_branch('project fs')
    path = next(branch.find_in_mounts(context, mounts=mounts))
    if path:
        return FS.load(os.path.expanduser(path[0]))
    return fs
