from collections import OrderedDict

from maya import cmds
from maya.api import OpenMaya as om

SYSTEM_TYPE_ATTR_NAME = 'system_type'


def add_system_attr(obj, value):
    """Add the SystemType attribute to a node.

    Used to identify and cast instances of System subclasses.

    Args:
        obj (str): name of maya node where to add the attribute.
        value (str): system type value.
    """
    if not cmds.attributeQuery(SYSTEM_TYPE_ATTR_NAME, n=obj, ex=1):
        cmds.addAttr(obj, ln=SYSTEM_TYPE_ATTR_NAME, dt='string')
    cmds.setAttr('.'.join([obj, SYSTEM_TYPE_ATTR_NAME]), value, type='string')


def name_to_node(name):
    return om.MGlobal.getSelectionListByName(name).getDependNode(0)


class Node(str):
    """Baseclass for complex structures represented by a Maya node.

    The class derives from str and is initialized with a node's UUID.

    Attributes:
        fn (om.MFnDependencyNode): cached api function set to work with this
            system's root DependNode.
    """

    DEFAULT_NAME = 'grp'
    """str: default node name when using namespaces."""
    _NODETYPE = 'transform'
    """str: type of node to be created as root object"""
    dependnode = None
    """om.MObject: cached api object of this system's root node."""

    def __new__(cls, value):
        """Initialize a Node from it's root node uuid.

        Args:
            value (str or om.MObject): uuid or name of a maya node. If a name
                is passed, replace by object's uuid.

        Returns:
            Node or None: instance, or None if object doesn't exist.
        """
        if isinstance(value, str):
            value = name_to_node(value)
        if value:
            fn = om.MFnDagNode()
            if fn.hasObj(value):
                fn.setObject(value)
            else:
                fn = om.MFnDependencyNode(value)
            self = super().__new__(cls, fn.uuid())
            self.dependnode = value
            self._fn = fn
            return self

    def __eq__(self, other):
        """Nodes are equal if their class and str conversion (uuid) are equal.

        Args:
            other: value to check for equalty (usually a Node subclass).

        Returns:
            bool: True if input value is equal to this Node instance.
        """
        return self.__class__ == other.__class__ and super().__eq__(other)

    def __hash__(self):
        return hash(str(self))

    def __repr__(self):
        """String representation of a Node.

        Returns:
            str: "<node type>('root name')". Example: Asset('duck')
        """
        return f"{type(self).__name__}('{self.name}')"

    @classmethod
    def create(cls, name=None, parent=None):
        """Create a new Node in current maya scene.

        The node is created based on the nodetype variable defined for
        each Node (sub)class, and a 'system type' attribute is added to it
        with the class name as it's value.

        Args:
            name (str, optional): name of the new node. If not provided,
                use the node type, as Maya would do, letting the software
                resolve nameclash with an index at the end.
            parent (str, optional): name or uuid of parent object. If none
                provided, use the scene's root.

        Returns:
            Node: class instance.
        """
        if parent is not None:
            parent = cmds.ls(parent)[0]
        name = name or cls._NODETYPE
        print(f"Creating {cls.__name__}({name})")
        if name.endswith(':'):
            name += cls.DEFAULT_NAME
        root = cmds.createNode(cls._NODETYPE, name=name, parent=parent, ss=1)
        return cls(root)

    @classmethod
    def deserialize(cls, name=None, parent=None, *args, **kwargs):
        """Create a Node out of serialized data.

        Args:
            name (str, optional): name of the new Node. If not provided,
                use the node type, as Maya would do, letting the software
                resolve nameclash with an index at the end.
            parent (str, optional): name or uuid of parent object.
            args: passed on to default constructor (create method).
            kwargs: passed on to default constructor (create method).

        Returns:
            Node: class instance
        """
        return cls.create(name=name, parent=parent, *args, **kwargs)

    def delete(self):
        """Delete this Node"""
        ns = self.namespace
        node_repr = repr(self)
        cmds.delete(self.name)
        if ns and not cmds.namespaceInfo(ns, ls=1):
            cmds.namespace(rm=ns)
        print(f"{node_repr} deleted")

    def export(self, filename, **kwargs):
        """Export this Node to a maya ascii file.

        Args:
            filename (str): full path to the saved file.
        """
        cmds.select(self.name)
        settings = {'pr': 1, 'typ': 'mayaAscii'}
        settings.update(**kwargs)
        cmds.file(filename, es=True, **settings)
        print(f'{self!r} exported to {filename}')

    def get_name(self):
        """Get the name of the maya node.

        Returns:
            str: name of this node
        """
        if isinstance(self.fn, om.MFnDagNode):
            return self.fn.partialPathName()
        return self.fn.name()

    def rename(self, value):
        """Set the name of the maya node.

        Args:
            value (str): new name
        """
        sep = ':'
        if sep in self.name:
            if sep in value:
                self.namespace = value.rsplit(sep, 1)[0]
            else:
                self.namespace = ''
        if value[-1] == sep:
            value += self.DEFAULT_NAME
        cmds.rename(self.name, value)

    def serialize(self):
        """Serialize this Node instance.

        Returns:
            OrderedDict: required data to rebuild this Node (sub)class.
        """
        print(5, f'Serializing {self!r}')
        return OrderedDict(type=self.__class__.__name__)

    name = property(get_name, rename)

    @property
    def fn(self):
        if om.MObjectHandle(self.dependnode).isValid():
            return self._fn
        raise RuntimeError(
            f'Invalid depend node. {type(self).__name__}({self}) not found')

    @property
    def namespace(self):
        """The namespace part (if any) of this maya node's name.

        Args:
            value (str): new namespace for the maya node.

        Returns:
            str: namespace of the maya node.
        """
        return self.fn.namespace

    @namespace.setter
    def namespace(self, value):
        ns = self.namespace
        if ns:
            if value:
                sep = ':'
                if cmds.namespace(ex=value):
                    cmds.namespace(mv=(ns, value))
                elif sep in value:
                    par, value = value.rsplit(sep, 1)
                    if not cmds.namespace(ex=par):
                        cmds.namespace(add=par)
                    cmds.namespace(ren=(self.namespace, value), p=par)
                else:
                    cmds.namespace(ren=(self.namespace, value))
            else:
                cmds.namespace(rm=ns, mnr=1)

    @property
    def nodename(self):
        """Maya node name (path excluded).

        Returns:
            str: nodename.
        """
        return self.fn.name()


class System(Node):
    """Systems in maya are structures identified by a root node.

    The root has a 'system type' attribute, informing on the system subclass
    used to instantiate the system. This allows easy and systematic recognition
    of scene contents that may require so.
    """

    @classmethod
    def create(cls, name=None, parent=None):
        """Create a new System in current maya scene.

        The root node is created, based on the nodetype variable defined for
        each System (sub)class, and a 'system type' attribute is added to it
        with the class name as it's value.

        Args:
            name (str, optional): name of the new system. If not provided,
                use the node type, as Maya would do, letting the software
                resolve nameclash with an index at the end.
            parent (str, optional): name or uuid of parent object. If none
                provided, use the scene's root.

        Returns:
            System: class instance.
        """
        self = super().create(name, parent)
        self.create_attributes()
        return self

    def create_attributes(self):
        """Add any missing attributes expected in this system."""
        add_system_attr(self.name, self.__class__.__name__)

    @property
    def type(self):
        """Get/set the system type attribute's value.

        Args:
            value (str): new value for the attribute. Modifying this value will
                change the class that gets initiated the next type a system is
                instantiated with this node through the Systems Factory.

        Returns:
            str: current value of the system type attribute
        """
        return cmds.getAttr(f'{self.name}.{SYSTEM_TYPE_ATTR_NAME}')

    @type.setter
    def type(self, value):
        cmds.setAttr(
            '.'.join([self.name, SYSTEM_TYPE_ATTR_NAME]),
            value, type='string')
