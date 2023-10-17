"""Support for procedurally manipulating Maya attributes with stored poses.

Two main System subclasses are defined in this module:

- **Posers** drive a given attribute with stored values.
- **PoserSets** manipulate a whole set of associated attributes, each with it's
  own attribute Poser.

"""
from collections import OrderedDict

from ma import attribute, cmds, system
from py import IndexableGenerator

from . import control, reader

POSERSET_ATTR_NAME = 'poser_set'
REPRESENTANT_ATTR_NAME = 'representant'


def create_poser(attr, representant=None):
    """Create an Attribute Poser to drive an attribute.

    The type of Poser that gets created depends on the attribute's data type.

    Args:
        attr (str): name of the attribute to be driven.

    Return:
        Poser: sub-class instance.
    """
    at = attr.rsplit('.', 1)
    cls = POSERS_MAP[cmds.attributeQuery(at[1], node=at[0], at=1)]
    return cls.create(attr, representant)


def get_control_poser_node(ctl, poser_set):
    """Find a transform on top of a control driven by a specific PoserSet.

    Args:
        ctl (str): name of a control transform.
        poser_set (PoserSet): PoserSet driving the transform which to look for.

    Returns:
        tuple:
            poser transform's name(str) and list of associated attribute
            posers, if found. (None, None) otherwise.
    """
    root = poser_set.name
    for xf, attr_posers in get_control_poser_nodes(ctl):
        for attr_poser in attr_posers:
            inputs = cmds.listConnections(
                '.'.join([attr_poser.name, POSERSET_ATTR_NAME]),
                s=1, d=0)
            if inputs and inputs[0] == root:
                return xf, attr_posers
    return None, None


def get_control_poser_nodes(ctl):
    """Get the transforms of a control which are driven by posers.

    For a given control, recursively search it's transforms, from the first
    parent up towards the root of the hierarchy, for attribute Posers. Return
    those which have any and the posers themselves. These usually serve

    Args:
        ctl (control.Control or str):
            Control instance or name of a control transform node.

    Yields:
        tuple:
            node name and a list of associate attribute posers per pose-driven
            transform node of the input control.
    """
    if not isinstance(ctl, control.Control):
        ctl = control.Control(ctl)
    for x in ctl.transforms:
        posers = tuple(y for y in get_posers(x)
                       if (y.representant or '').split('.', 1)[0] == ctl)
        if posers:
            yield x, posers


def get_posers(node):
    """Get the posers driving any attribute of an input node.

    Args:
        node (str): node name.

    Yields:
        Poser: Poser sub-class instances.
    """
    for input_node in set(cmds.listConnections(node, s=1, d=0, scn=1) or []):
        cls = Poser.get_class(input_node)
        if cls is not None:
            yield cls(input_node)


class Poser(system.System):
    """Abstract baseclass for Attribute Posers.

    Posers drive a given attribute with stored values that can be blended in.
    The first pose value in the stack stores the default attribute value;
    others are offsets to it.

    For each attribute type a specific Poser subclass is required.
    """

    _NODETYPE = 'plusMinusAverage'
    """str: type of node to be created as root object"""

    pose_value_attr = NotImplemented
    """str: string to complete the path to the attribute
    holding a given pose's value(s). poses are stored in extra nodes
    which in turn are plugged to the Poser and which in turn is
    plugged to the driven attribute.
    """

    pose_weight_attr = NotImplemented
    """str: string to complete the path to the attribute
    holding a given pose's blending weight."""

    threshold = 0.001
    """float: Minimum absolute value for a pose. Setting a pose
    to a value below it will remove the pose for optimization purposes,
    as it's influence is considered negligible. Set threshold to 0 to
    disable this behavior."""

    @classmethod
    def create(cls, attr, representant=None):
        """Create a new attribute Poser to drive a given maya attribute.

        Args:
            attr (str): name of a maya attribute to be driven.

        Returns:
            Poser: instance
        """
        self = super().create()
        cmds.addAttr(self.name, ln=POSERSET_ATTR_NAME, at='message')
        cmds.addAttr(self.name, ln=REPRESENTANT_ATTR_NAME, at='message')
        self.representant = representant

        # connect poser to driven attribute
        cmds.connectAttr(self.output, attr)

        # set first pose to the default attribute value.
        # other poses are offsets to the default.
        attr = attr.rsplit('.', 1)
        cmds.setAttr(f'{self.input}[0]',
                     *cmds.attributeQuery(attr[1], node=attr[0], ld=1))

        return self

    @staticmethod
    def get_class(node):
        """Find the adequate Poser subclass to instantiate from a root node.

        If the node is not a proper poser root, None's returned, so this
        method can also be used to query if a node wether a Poser.

        Args:
            node (str): name of a maya node (supposedly a Poser)

        Returns:
            class or None:
                the adequate Poser sub-class to instantiate from input node
        """
        cls = system.factory.get_system_class(node)
        if cls is not None and issubclass(cls, Poser):
            return cls

    def delete(self):
        """Remove Poser and all it's pose nodes."""
        attr = self.attr

        # disconnect driven attribute and set it to the default value
        default_value = self.get_pose_value(0)
        cmds.disconnectAttr(self.output, attr)
        try:
            cmds.setAttr(attr, *default_value)
        except TypeError:
            cmds.setAttr(attr, default_value)

        # remove all pose nodes and the poser node itself
        [self.remove_pose(i) for i in cmds.getAttr(self.input, mi=1)[:0:-1]]
        cmds.delete(self.name)

    def add_pose(self):
        """Create a new pose entry in this poser.

        All the necesary nodes and connections are created to hold the pose
        values.

        Returns:
            int: index of the new pose in the poses stack.
        """
        raise NotImplementedError

    def get_pose(self, index=None):
        """Get the pose at given index in this poser.

        Args:
            index (int, optional): entry of a pose in this poser's stack of
                input poses. If none passed, pick the last pose.

        Returns:
            str:
                name of the node holding the pose data, with open formatting
                fields to complete with the name of either the attribute
                holding it's value or the attribute holding it's weight.
        """
        input_attr = self.input
        if index is None:
            index = cmds.getAttr(input_attr, mi=1)[-1]
        if index < 1:
            return None
        connections = cmds.listConnections(
            f'{input_attr}[{index}]', s=1, d=0, scn=1)
        return f'{connections[0]}{{0}}' if connections is not None else None

    def get_pose_value(self, index):
        """Get the value of a pose at given index.

        Args:
            index (int): index of the pose whose value to get.

        Returns:
            variable type:
                value of the pose, of the same data type as that of the driven
                attribute.
        """
        if index == 0:
            return cmds.getAttr(f'{self.input}[0]')
        pose = self.get_pose(index)
        return cmds.getAttr(pose.format(self.pose_value_attr))

    def remove_pose(self, index=None):
        """Remove a pose from the poses stack.

        Args:
            index (int, optional): stack index of the pose to remove. If none
                is provided (default), remove the last pose.

        Raises:
            ValueError: index must be greater than 0, which is the neutral pose
                and can't be removed.
        """
        input_attr = self.input
        if index is None:
            index = cmds.getAttr(input_attr, mi=1)[-1]
        if index < 1:
            raise ValueError("can't remove neutral pose")
        input_attr += f'[{index}]'
        pose = cmds.listConnections(input_attr, s=1, d=0, scn=1)
        if pose:
            cmds.disconnectAttr(
                cmds.listConnections(input_attr, s=1, d=0, scn=1, plugs=1)[0],
                input_attr)
            cmds.delete(pose[0])
        cmds.removeMultiInstance(input_attr, b=1)

    def set_pose_value(self, index, *value):
        """Set the value of pose at a given index.

        Args:
            index (int): stack index of the pose to set.
            \\*value (tuple): variable length attribute with the value(s) to
                set on a pose.
        """
        if self.trim_value(value) is None:
            return self.remove_pose(index)
        cmds.setAttr(self.get_pose(index).format(self.pose_value_attr), *value)

    def sum_poses(self, indices):
        """Sum the values of two or more poses.

        Args:
            indices (iterable of int): indices of each pose to be summed.

        Returns:
            Number: summed pose value
        """
        return sum([self.get_pose_value(index) for index in indices])

    def trim_value(self, value):
        """Prune small values by returning None if they're below the threshold.

        Args:
            value (numbers.Real or iterable of numbers.Real):
                value to be processed.

        Returns:
            value or None:
                input value if over the Poser's threshold, or None otherwise.
        """
        if not self.threshold:
            return value
        try:
            return None if abs(value) < self.threshold else value
        except TypeError:
            pass
        return None if all(abs(x) < self.threshold for x in value) else value

    @property
    def attr(self):
        """Get the attribute being driven by this poser.

        Returns:
            str: complete name of the attribute.
        """
        return cmds.listConnections(self.output, s=0, d=1, scn=1, plugs=1)[0]

    @property
    def input(self):
        """Attribute of the poser's root node where poses are defined/plugged.

        Returns:
            str: attribute name
        """
        raise NotImplementedError

    @property
    def node(self):
        """The node holding the attribute being driven by this poser.

        Returns:
            str: name of the node.
        """
        return cmds.listConnections(self.output, s=0, d=1, scn=1)[0]

    @property
    def output(self):
        """The attribute of this poser feeding values onto the driven attr.

        Returns:
            str: attribute name
        """
        raise NotImplementedError

    @property
    def poses(self):
        """Get all the poses defined in this poser.

        Poses are defined by a stored value of a type compatible with the
        driven attribute, and a weight that blends this value in.
        The poses are thus returned as node names with open formatting fields,
        to complete with the name of either the attribute holding the pose's
        value or the weight attribute.

        Returns:
            list of str:
                node name and formatting field for pose value/weight attributes
        """
        return [f'{x}{{0}}' for x in cmds.listConnections(
            self.input, s=1, d=0, scn=1) or []]

    @property
    def representant(self):
        """If not None, this poser drives an attribute in place of another.

        A common use case is when driving the translation, rotation or scale of
        a transform in the hierarchy of a control, while leaving the control
        free to animate. This information is used by client code such as
        PoserSets de/serialization.

        Args:
            value (str):
                fullname of attribute to represent the one driven by this poser

        Returns:
            str: fullname of connected attribute, if any.
        """
        return cmds.listConnections(
            f'{self.name}.{REPRESENTANT_ATTR_NAME}', p=1)

    @representant.setter
    def representant(self, value):
        representant_attribute = f'{self.name}.{REPRESENTANT_ATTR_NAME}'
        if not value:
            attribute.disconnect(representant_attribute)
        else:
            attribute.connect(value, representant_attribute)


class EnumPoser(Poser):
    """Drive a maya Enum attribute with stored poses."""

    pose_value_attr = '.colorIfTrueR'
    """str: string to complete the path to the attribute holding a given pose's
    value(s). Poses are stored in extra nodes which in turn are plugged to the
    Poser and which in turn is plugged to the driven attribute."""

    pose_weight_attr = '.firstTerm'
    """str: string to complete the path to the attribute holding a given pose's
    blending weight."""

    def add_pose(self):
        """Create a new pose entry in this poser.

        All the necesary nodes and connections are created to hold the pose
        values.

        Returns:
            int: index of the new pose in the poses stack.
        """
        input_attr = self.input
        indices = cmds.getAttr(input_attr, mi=1)
        index = (indices or [-1])[-1] + 1
        pose = cmds.createNode('condition', ss=1)
        cmds.setAttr(f'{pose}.operation', 2)
        cmds.setAttr(f'{pose}.secondTerm', 0.5)
        cmds.setAttr(f'{pose}.colorIfFalseR', 0)
        cmds.connectAttr(f'{pose}.outColorR', f'{input_attr}[{index}]')
        return index

    @property
    def input(self):
        """Attribute of the poser's root node where poses are defined/plugged.

        Returns:
            str: attribute name
        """
        return f'{self.name}.input1D'

    @property
    def output(self):
        """The attribute of this poser feeding values onto the driven attr.

        Returns:
            str: attribute name
        """
        return f'{self.name}.output1D'


class NumberPoser(Poser):
    """Drive a Maya int or float attribute with stored poses."""

    _NODETYPE = 'blendWeighted'
    """str: type of node to be created as root object"""

    pose_value_attr = '.input'
    """str: string to complete the path to the attribute holding a given pose's
    value(s). poses are stored in extra nodes which in turn are plugged to the
    Poser and which in turn is plugged to the driven attribute."""

    pose_weight_attr = '.weight'
    """str: string to complete the path to the attribute holding a given pose's
    blending weight."""

    @classmethod
    def create(cls, attr):
        """Create a new NumberPoser to drive input maya numeric attribute.

        Args:
            attr (str): name of a maya attribute to be driven.

        Returns:
            Poser: instance
        """
        self = super().create(attr)
        cmds.setAttr(f'{self.name}{self.pose_weight_attr}[0]', 1)
        return self

    def add_pose(self):
        """Create a new pose entry in this poser.

        All the necesary nodes and connections are created to hold the pose
        values.

        Returns:
            int: index of the new pose in the poses stack.
        """
        index = cmds.getAttr(self.name + self.pose_value_attr, mi=1)[-1] + 1
        pose = self.get_pose(index)
        cmds.setAttr(pose.format(self.pose_value_attr), 0)
        cmds.setAttr(pose.format(self.pose_weight_attr), 0)
        return index

    def delete(self):
        """Slightly faster than in superclass.

        We don't need to remove all the poses first.
        """
        default_value = self.get_pose_value(0)
        attr = self.attr
        cmds.disconnectAttr(self.output, attr)
        cmds.setAttr(attr, default_value)
        cmds.delete(self.name)

    def get_pose(self, index):
        """Get the pose at given index in this poser.

        Args:
            index (int): entry of a pose in this poser's stack of input poses.

        Returns:
            str:
                name of the node holding the pose data, with open formatting
                fields to complete with the name of either the attribute
                holding it's value or the attribute holding it's weight.
        """
        return f'{self.name}{{0}}[{index}]'

    def remove_pose(self, index):
        """Remove a pose from the poses stack.

        Args:
            index (int): stack index of the pose to remove.

        Raises:
            ValueError: index must be greater than 0, which is the neutral pose
                and can't be removed.
        """
        if index < 1:
            raise ValueError("can't remove neutral pose")
        root = self.name
        cmds.removeMultiInstance(f'{root}{self.pose_value_attr}[{index}]', b=1)
        cmds.removeMultiInstance(
            f'{root}{self.pose_weight_attr}[{index}]', b=1)

    def set_pose_value(self, index, value):
        """Set the value of pose at a given index.

        Args:
            index (int): stack index of the pose to set.
            value (int or float): value to set on a pose.
        """
        if self.threshold and abs(value) < self.threshold:
            self.remove_pose(index)
        else:
            cmds.setAttr(self.get_pose(index).format(self.pose_value_attr),
                         value)

    @property
    def input(self):
        """Attribute of the poser's root node where poses are defined/plugged.

        Returns:
            str: attribute name
        """
        return self.name + self.pose_value_attr

    @property
    def output(self):
        """The attribute of this poser feeding values onto the driven attr.

        Returns:
            str: attribute name
        """
        return f'{self.name}.output'

    @property
    def poses(self):
        """Create a new pose entry in this poser.

        All the necesary nodes and connections are created to hold the pose
        values.

        Returns:
            int: index of the new pose in the poses stack.
        """
        root = self.name
        indices = cmds.getAttr(root + self.pose_value_attr, mi=1)
        return [f'{root}{{0}}[{i}]' for i in indices[1:]]


class Number3Poser(Poser):
    """Drive a Maya int3 or float3 attribute with stored poses."""

    pose_value_attr = '.color1'
    """str: string to complete the path to the attribute holding a given pose's
    value(s). poses are stored in extra nodes which in turn are plugged to the
    Poser and which in turn is plugged to the driven attribute."""

    pose_weight_attr = '.blender'
    """str: string to complete the path to the attribute holding a given pose's
    blending weight."""

    def add_pose(self):
        """Create a new pose entry in this poser.

        All the necesary nodes and connections are created to hold the pose
        values.

        Returns:
            int: index of the new pose in the poses stack.
        """
        input = self.input
        index = cmds.getAttr(input, mi=1)[-1] + 1
        pose = cmds.createNode('blendColors', ss=1)
        cmds.setAttr(f'{pose}.blender', 0)
        cmds.setAttr(f'{pose}.color2', 0, 0, 0)
        cmds.connectAttr(f'{pose}.output', f'{input}[{index}]')
        return index

    def get_pose_value(self, index):
        """Get the values of a pose at given index.

        Args:
            index (int): index of the pose whose value to get.

        Returns:
            tuple of Number: values of the pose.
        """
        return list(super().get_pose_value(index))[0]

    def sum_poses(self, indices):
        """Sum the values of two or more poses.

        Args:
            indices (iterable of int): indices of each pose to be summed.

        Returns:
            tuple of Number: summed pose value
        """
        values = tuple(self.get_pose_value(x) for x in indices)
        return tuple(sum(x) for x in zip(*values))

    @property
    def input(self):
        """Attribute of the poser's root node where poses are defined/plugged.

        Returns:
            str: attribute name
        """
        return f'{self.name}.input3D'

    @property
    def output(self):
        """The attribute of this poser feeding values onto the driven attr.

        Returns:
            str: attribute name
        """
        return f'{self.name}.output3D'


POSERS_MAP = {
    'enum': EnumPoser,

    'bool': NumberPoser,
    'byte': NumberPoser,
    'short': NumberPoser,
    'long': NumberPoser,
    'double': NumberPoser,
    'doubleAngle': NumberPoser,
    'doubleLinear': NumberPoser,
    'float': NumberPoser,

    'short3': Number3Poser,
    'long3': Number3Poser,
    'double3': Number3Poser,
    'float3': Number3Poser,
}


class PoserSet(system.System):
    """A Poser coordinately driving several attributes with Attribute Posers.

    Each pose can drive one or more of the attributes driven by the PoserSet.
    """

    @classmethod
    def create(cls, name=None, parent=None, attrs=None):
        """Poser Set constructor.

        Args:
            name (str, optional): name of the new Poser. If not provided,
                use the node type, as Maya would do, letting the software
                resolve name clash with an index at the end.
            parent (str, optional): name or uuid of parent object.
            attr (iterable of str, optional): optional list with names of
                attributes to be driven. An adequate attribute Poser sub-class
                will be created for each.

        Returns:
            PoserSet: class instance.
        """
        self = super().create(name=name, parent=parent)
        root = self.name
        [cmds.setAttr('.'.join([root, x]), keyable=0)
         for x in cmds.listAttr(root, k=1)]
        [self.add_attr(x) for x in attrs or []]
        return self

    @classmethod
    def deserialize(cls, data, name=None, parent=None):
        """Create a PoserSet out of serialized data.

        Args:
            data (dict): serialized data.
            name (str, optional): name of the new PoserSet. If not provided,
                use the node type, as Maya would do, letting the software
                resolve name clash with an index at the end.
            parent (str, optional): name or uuid of parent object.

        Returns:
            PoserSet: class instance
        """
        self = super(PoserSet, cls).deserialize(name=name, parent=parent)
        self.inject(data)
        return self

    def add_attr(self, attr, representant=None):
        """Include input attribute in this PoserSet.

        An attribute Poser of the adequate Poser sub-class is created for this
        attribute, and associated with the PoserSet.

        Args:
            attr (str): name of the attribute
            representant (str, optional): fullname of another attribute.
                which is connected to the poser as a representant attribute for
                the one being driven.

        Returns:
            Poser: sub-class instance
        """
        poser = create_poser(attr)
        cmds.connectAttr(f'{self.name}.message',
                         f'{poser.name}.{POSERSET_ATTR_NAME}')
        return poser

    def add_group(self, name):
        """Add a group separator attribute.

        That's just an empty enum attribute, to visually separate poses in
        Maya's Attribute Editor and other tools.

        Args:
            name (str): name for the separator attribute
        """
        cmds.addAttr(self.name, ln=name, at='enum', en='------:')
        cmds.setAttr(f'{self.name}.{name}', cb=1)

    def add_pose(self, name, keyable=True):
        """Create a new pose entry on this PoseSet.

        An attribute is created on the PoserSet's root node, to drive the
        weight value of poses on the associated attribute Posers. No pose
        entries at attribute Poser level are created yet, however. Those are
        managed when the pose values are set, being created, edited or removed
        from depending on the input values.

        Args:
            name (str): name of the new pose attribute.
            keyable (bool, optional): Whether to display the pose in the
                channelbox and make it keyable. Default: True.
        """
        cmds.addAttr(self.name, ln=name, at='float', dv=0, min=0, max=1,
                     k=keyable)

    def connect_pose(self, index, driver=None):
        """Drives a pose with a Reader

        Args:
            index (int): index of the pose to be driven.
            driver (str, int or reader.Reader, optional):
                Driving attribute or Reader. If an index is passed,
                pick child Reader with that index. If a str is provided,
                connect to this attribute if existing. If None (default),
                creates a new Reader with standard name.
                Default: None

        Returns:
            reader.ConeReader: input or new ConeReader
        """
        result = driver

        if isinstance(driver, str):
            obj = driver.split('.', 1)[0]
            if not (cmds.objExists(obj) and cmds.addAttr(driver, q=1, ex=1)):
                return None
        else:
            if isinstance(driver, int):
                result = self.readers[driver]
            elif driver is None:
                result = self.add_reader()
            driver = result.output

        pose_attr = f'{self.name}.{self.poses[index]}'
        cmds.connectAttr(driver, pose_attr)
        return result

    def delete(self):
        """Delete PoserSet and all the associated Attribute Posers."""
        [x.delete() for x in self.posers]
        super().delete()

    def get_pose(self, index):
        """For a given pose in this PoseSet, get associated attribute poses.

        Args:
            index (int): index of the pose attribute in the custom attributes
            list of this PoseSet's root node.

        Yields:
            tuple:
                each attribute Poser and the index of it's corresponding
                attribute pose associated to the PoserSet pose.
        """
        outputs = set(cmds.listConnections(
            '.'.join([self.name, self.poses[index]]), s=0, d=1, plugs=1) or [])
        for poser in self.posers:
            i = None
            for j in cmds.getAttr(poser.input, mi=1)[1:]:
                pose = poser.get_pose(j)
                if pose is None:
                    continue
                if pose.format(poser.pose_weight_attr) in outputs:
                    i = j
                    break
            yield (poser, i)

    def get_pose_values(self, index):
        """Get the value of each attribute pose in a given PoserSet pose.

        Args:
            index (int): index of the pose attribute in the custom attributes
                list of this PoseSet's root node.

        Yields:
            tuple:
                each attribute Poser and the value of it's corresponding
                attribute pose associated to the PoserSet pose.
        """
        outputs = set(cmds.listConnections(
            '.'.join([self.name, self.poses[index]]), s=0, d=1, plugs=1) or [])
        for poser in self.posers:
            value = None
            for pose in poser.poses:
                if pose.format(poser.pose_weight_attr) in outputs:
                    value = cmds.getAttr(pose.format(poser.pose_value_attr))
                    if isinstance(value, list):
                        value = list(value[0])
                    break
            yield (poser, value)

    def remove_attr(self, index):
        """Exclude attribute at given index from this PoserSet.

        Action also deletes the attribute's Poser.

        Args:
            index (int): index of the attribute Poser to be removed.
        """
        self.posers[index].delete()

    def remove_group(self, index):
        """Remove a group separator attribute.

        Args:
            index (int): index of the group attribute
        """
        cmds.deleteAttr(f'{self.name}.{self.groups.keys()[index]}')

    def remove_pose(self, index):
        """Remove a pose from this PoserSet.

        The pose attribute is deleted from the root node. Corresponding
        attribute poses are also removed from the associated attribute Posers.

        Args:
            index (int): index of the pose attribute in the custom attributes
            list of this PoseSet's root node.
        """
        pose_attr = self.poses[index]
        [p.remove_pose(i) for p, i in self.get_pose(index) if i is not None]
        cmds.deleteAttr(f'{self.name}.{pose_attr}')

    def set_pose_values(self, index, values):
        """Set the values of a pose.

        Attribute Posers not specified are excluded from the pose. Others not
        yet present are included, and those already existing are updated.

        Args:
            index (int): index of the pose attribute in the custom attributes
                list of this PoseSet's root node.
            values (dict): {poser: value(s)} pairs.
        """

        pose = '.'.join([self.name, self.poses[index]])
        for poser, i in self.get_pose(index):
            value = values.get(poser, None)
            if value is None or poser.trim_value(value) is None:
                if i is not None:
                    poser.remove_pose(i)
            else:
                if i is None:
                    i = poser.add_pose()
                    cmds.connectAttr(
                        pose, poser.get_pose(i).format(poser.pose_weight_attr))
                try:
                    poser.set_pose_value(i, *value)
                except TypeError:
                    poser.set_pose_value(i, value)

    def sum_poses(self, indices):
        """Sum the values of two or more poses.

        Args:
            indices (iterable of int): indices of each pose to be summed.

        Yields:
            tuple: (poser, summed pose value(s)) pairs.
        """
        d = {poser: [0, i] if i is not None else [0]
             for poser, i in self.get_pose(indices[0])}
        for index in indices[1:]:
            [d[poser].append(i) for poser, i in self.get_pose(index)
             if i is not None]
        for poser in self.posers:
            yield poser, poser.sum_poses(d[poser])

    def serialize(self):
        pass

    @property
    @IndexableGenerator.cast
    def attrs(self):
        """Get the list of attributes driven by this PoserSet.

        Yields:
            str: name of each driven attribute.
        """
        for x in self.posers:
            yield x.attr

    @property
    def groups(self):
        """Get pose groups and their nested poses.

        Returns:
            dict: {group (str): poses (list of str)}
        """
        root = self.name
        poses = cmds.listAttr(root, ud=1, s=1) or []
        result = []
        grp = ['', []]
        for x in poses:
            if cmds.getAttr(f'{root}.{x}', type=1) != 'float':
                if any(grp):
                    result.append(grp)
                grp = [x, []]
            else:
                grp[1].append(x)
        if any(grp):
            result.append(grp)
        return OrderedDict(result)

    @property
    @IndexableGenerator.cast
    def posers(self):
        """Get all the attribute posers associated to this PoserSet.

        Yields:
            Poser: each driven attribute's Poser.
        """
        for obj in cmds.listConnections(f'{self.name}.message',
                                        s=0, d=1) or []:
            try:
                yield Poser.get_class(obj)(obj)
            except TypeError:
                pass

    @property
    def poses(self):
        """Get all the poses defined in this PoserSet.

        Poses are represented by a custom, float attribute in the PoserSet's
        root node, which in turn drives the weight attribute of each
        corresponding pose in its associated attribute Posers.

        Returns:
            list of str: pose attribute name.
        """
        root = self.name
        return [x for x in cmds.listAttr(root, ud=1, s=1) or []
                if cmds.getAttr(f'{root}.{x}', type=1) == 'float']

    @property
    @IndexableGenerator.cast
    def readers(self):
        """Get child ConeReaders.

        Returns:
            list of reader.ConeReader: each child ConeReader instance
        """
        return system.get_systems_tree(self, 0, reader.Reader).keys()


system.factory.register(Poser)
system.factory.register(PoserSet)
