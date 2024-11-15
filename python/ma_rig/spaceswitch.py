"""Space Switching is the concept of alternating transform inheritance.

SpaceSwitches allow changing or blending between different transformation
spaces for a given object.
In Maya, this is normally achieved by adding constraints to transform nodes,
with multiple targets (spaces), and modulating the influence weight of each
target.
"""
from collections import OrderedDict
from numbers import Number
from types import NoneType
from typing import Any, Iterable, Iterator, Optional

from ma import cmds, get_nc, node
from py import IndexableGenerator, T_IndexableGenerator

from . import R, S, T, control

vec3 = tuple[float, float, float]

#: Orient, Point and Aim constraint channels
O, P, A = [tuple(x + y for y in 'xyz') for x in 'opa']

# the following two dictionaries are used to code constraint types into their
# driven channels and back
CNS_MAP = OrderedDict(
    aimConstraint='a',
    orientConstraint='o',
    parentConstraint='rt',
    pointConstraint='p',
    scaleConstraint='s'
)
REV_CNS_MAP = {'a': 'r', 'o': 'r', 'p': 't', 'r': 'r', 's': 's', 't': 't'}
WUT = ['scene', 'object', 'objectrotation', 'vector', 'none']
nc = get_nc()


def compare(
        a: str, b: str
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]:
    """Compare two constraints of the same type.

    Args:
        a: Name of first constraint.
        b: Name of second constraint.

    Returns:
        Constraint differences.
    """
    cns_type = cmds.objectType(a)
    if cns_type == 'aimConstraint':
        return compare_a(a, b)
    elif cns_type == 'parentConstraint':
        return compare_rt(a, b)
    else:
        return compare_sop(a, b)


def compare_a(a: str, b: str) -> dict[str, Any]:
    """Compare two aim constraints.

    Args:
        a: Name of first aim constraint.
        b: Name of second aim constraint.

    Returns:
        Constraint difference.

    Raises:
        ValueError: If any of the inputs isn't an aimConstraint.
    """
    d, attrs = [], ['aimVector', 'offset', 'upVector', 'worldUpVector']
    for cns in (a, b):
        d = {'targets': cmds.aimConstraint(cns, q=1, tl=1) or [],
             'worldUpType': cmds.getAttr(f'{cns}.wut'),
             'worldUpMatrix': (
                 cmds.listConnections(f'{cns}.wum', s=1, d=0) or [None])[0]}
        d.update({k: [round(x, 5) for x in cmds.getAttr(f'{cns}.{k}')]
                  for k in attrs})
    result = {'targets': [[x for x in d[i]['targets']
                           if x not in d[1 - i]['targets']]
                          for i in range(2)],
              'worldUpType': d[1]['worldUpType'] - d[0]['worldUpType'],
              'worldUpMatrix': d[0]['worldUpMatrix'] != d[1]['worldUpMatrix']}
    result.update({k: [y - x for x, y in zip(d[0][k], d[1][k])]
                   for k in attrs})
    return result


def compare_rt(a: str, b: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare two parent constraints.

    Args:
        a: Name of first parent constraint.
        b: Name of second parent constraint.

    Returns:
        Targets difference.

    Raises:
        ValueError: If any of the inputs isn't a parentConstraint
    """
    if any(not cmds.objectType(x, isa='parentConstraint') for x in [a, b]):
        raise ValueError("please provide two parentConstraints")
    dicts = [
        {k: [[round(x, 5)
              for x in cmds.getAttr(f'{cns}.target[{i}].{at}')[0]]
             for at in ['targetOffsetTranslate', 'targetOffsetRotate']]
         for i, k in enumerate(cmds.parentConstraint(cns, q=1, tl=1) or [])}
        for cns in [a, b]]
    return tuple(
        {k: v for k, v in d.items()
         if k not in dicts[1 - i] or v != dicts[1 - i][k]}
        for i, d in enumerate(dicts))


def compare_sop(a: str, b: str) -> dict[str, Any]:
    """Compare two scale, orient or point constraints.

    Args:
        a: Name of first scale, orient or point constraint.
        b: Name of second scale, orient or point constraint.

    Returns:
        Targets and offset difference.

    Raises:
        ValueError:
            If not both constraints are scale, orient or point constraints.
    """
    cns_type = cmds.objectType(a)
    if (
        cmds.objectType(b) != cns_type
        or cns_type not in ['scaleConstraint',
                            'orientConstraint',
                            'pointConstraint']
    ):
        raise ValueError(
            "please provide two valid constraints of the same type.")
    dicts = [{'targets': getattr(cmds, cns_type)(cns, q=1, tl=1) or [],
              'offset': [round(x, 5) for x in cmds.getAttr(f'{cns}.offset')]}
             for cns in [a, b]]
    return {'targets': [[x for x in d['targets']
                         if x not in dicts[1 - i]['targets']]
                        for i, d in enumerate(dicts)],
            'offset': [y - x for x, y in zip(dicts[0]['offset'],
                                             dicts[1]['offset'])]}


def equal(a: str, b: str) -> bool:
    """Check if two constraints are identical.

    Args:
        a: Name of first constraint.
        b: Name of second constraint.

    Returns:
        True if the two constraints are equal, False otherwise.
    """
    cns_type = cmds.objectType(a)
    comp = compare(a, b)
    if cns_type == 'parentConstraint':
        return not any(x for x in comp)
    elif cns_type == 'aimConstraint':
        return not (comp['targets']
                    or comp['worldUpType']
                    or comp['worldUpMatrix']
                    or any(y for x in ['aimVector', 'offset', 'upVector',
                                       'worldUpVector']
                           for y in comp[x]))
    else:
        return not (comp['targets'] or any(x for x in comp['offset']))


@IndexableGenerator.cast
def get_control_spaceswitch(
        ctl: control.Control | str
) -> T_IndexableGenerator['SpaceSwitch']:
    """Get the SpaceSwitch transforms from the transforms stack of a control.

    Args:
        ctl: Control or name of a control transform node.

    Yields:
        each space switching transform from the stack, starting
        from the immediate parent of the control itself and going up the
        hierarchy.
    """
    if not isinstance(ctl, control.Control):
        ctl = control.Control(ctl)
    for xf in ctl.transforms:
        ss = SpaceSwitch(xf)
        if any(ss.get_cns()):
            yield ss


def merge(a: str, b: str):
    """Replace first input constraint by the second one.

    Replaces output connections and deletes the first constraint.

    Args:
        a: Name of first constraint.
        b: Name of second constraint.
    """
    attrs = {
        'aimConstraint': ['cr'],
        'orientConstraint': ['cr'],
        'pointConstraint': ['ct'],
        'parentConstraint': ['cr', 'ct'],
        'scaleConstraint': ['cs']
    }

    cns_type = cmds.objectType(a)
    if cmds.objectType(b) != cns_type:
        raise TypeError("please provide two constraints of the same type.")

    for at in attrs[cns_type]:
        for ch in 'xyz':
            src = f'{b}.{at}{ch}'
            dests = cmds.listConnections(f'{a}.{at}{ch}', s=0, d=1, p=1) or []
            for dest in dests:
                cmds.connectAttr(src, dest, f=1)
    cmds.delete(a)


def split(cns: str, *targets: int) -> str:
    """Duplicate a constraint and connect the new one to specified targets.

    Args:
        cns: Name of a constraint.
        targets: Index of target attributes to be connected to the new
            constraint.

    Returns:
        Name of the new constraint.
    """
    cns2 = cmds.duplicate(cns)[0]
    inputs = cmds.listConnections(cns, s=1, d=0, p=1, c=1)
    for src, dest in zip(inputs[1::2], inputs[::2]):
        dest_node, dest_attr = dest.split('.', 1)
        if dest_node == cns:  # handle connections to itself
            src = src.replace(cns, cns2)
        cmds.connectAttr(src, f'{cns2}.{dest_attr}')
    connections = cmds.listConnections(cns, s=0, d=1, p=1, c=1)
    outputs = [(src, dest)
               for src, dest in zip(connections[::2], connections[1::2])
               if dest.split('.', 1)[0] != cns]
    for i in targets:
        cmds.connectAttr(f'{cns2}.{outputs[i][0].split(".", 1)[1]}',
                         outputs[i][1], f=1)
    return cns2


class SpaceSwitchGuide(node.Node):
    """A guide for creating SpaceSwitches.

    Creates a hierarchy of attributes on any node to define future constraints:
    - ss_channels: SRT channel proxies, to which the driving constraint
        definition is plugged.
    - ss_constraints: multi-compound attribute representing each constraint
        definition - type, targets, weights, offset and aim constraint specific
        settings.

    Some of the declared targets might not exist yet, so data such as offsets
    would be hard to define or impossible to infer. These will be calculated
    when the constraints are created.
    """

    @classmethod
    def create(
            cls, name: Optional[str] = None, parent: Optional[str] = None
    ) -> 'SpaceSwitchGuide':
        """Create a SpaceSwitchGuide.

        Args:
            name: Name of the new Node. If not provided, use the node type, as
                Maya would do, letting the software resolve name clashes with
                an index at the end.
            parent: name or uuid of parent object. If none
                provided, use the scene's root.

        Returns:
            SpaceSwitchGuide class instance.
        """
        self: SpaceSwitchGuide = super().create(name=name, parent=parent)
        self.create_attributes()
        return self

    @classmethod
    def deserialize(
            cls,
            data: dict[str, Any],
            name: Optional[str] = None,
            parent: Optional[str] = None
    ) -> 'SpaceSwitchGuide':
        """Create SpaceSwitch guide out of serialized data.

        Args:
            data: serialized data.
            name: maya node where to create the SpaceSwitch guide attributes.
            parent: name or uuid of parent object.

        Returns:
            SpaceSwitchGuide class instance.
        """
        self: cls = super().deserialize(name=name, parent=parent)
        [self.add(**cns) for cns in data['constraints']]
        return self

    def add(self, **kwargs: dict[str, Any]) -> list[int]:
        """Add new constraint definitions.

        Depending on the (optional) mix of channels passed via kwargs, one or
        multiple entries might get created

        Args:
            **kwargs: Details for the constraint definition. While no values are
                mandatory, the most relevant possible keys are 'channels',
                'targets' and 'weights'. See SpaceSwitch.set() for more details.

        Returns:
            List of indices of the newly created constraints.
        """

        # group input channels (if any) by constraint type
        channel_groups = {}
        [channel_groups.setdefault(x[0], []).append(x)
         for x in kwargs.get('channels', [None]) if x]
        rt = channel_groups.pop('r', []) + channel_groups.pop('t', [])
        if rt:
            channel_groups['rt'] = rt

        # create an entry for each group of channels (constraint type)
        index = max(self.indices or [-1])
        result = []
        for channels in channel_groups.values() or [None]:
            index += 1  # next available index
            result.append(index)
            kwargs['channels'] = channels
            cmds.getAttr(f'{self.cns_attr}[{index}].type')  # create
            self.set(**kwargs)  # set up
        return result

    def create_attributes(self):
        """Create the hierarchy of constraints attributes on the node.

        Can be run multiple times, as only the missing attributes are created.
        """
        name = self.name
        # driven channels
        if not cmds.attributeQuery('ss_channels', n=name, ex=1):
            cmds.addAttr(name, ln='ss_channels', at='compound', nc=9)
            for ch in S[1:] + R[1:] + T[1:]:
                cmds.addAttr(name, ln=f'{ch}_', at='message', p='ss_channels')
        # constraints array
        if not cmds.attributeQuery('ss_constraints', n=name, ex=1):
            cmds.addAttr(
                name, ln='ss_constraints', at='compound', nc=7, multi=1)
            cmds.addAttr(
                name, ln='type', at='enum', p='ss_constraints',
                en=':'.join(CNS_MAP.keys()))
            cmds.addAttr(name, ln='message_', at='message', p='ss_constraints')
            cmds.addAttr(
                name, ln='offset', at='bool', dv=True, p='ss_constraints')
            # constraint targets array
            cmds.addAttr(
                name, ln='targets', at='compound', nc=3, multi=1,
                p='ss_constraints')
            cmds.addAttr(name, ln='target_msg', at='message', p='targets')
            cmds.addAttr(name, ln='target_ref', dt='string', p='targets')
            cmds.addAttr(name, ln='weight', at='float', p='targets')
            # AimConstraint-specific settings
            cmds.addAttr(
                name, ln='up_target_msg', at='message', p='ss_constraints')
            cmds.addAttr(
                name, ln='up_target_ref', dt='string', p='ss_constraints')
            cmds.addAttr(
                name, ln='up_type', at='enum', p='ss_constraints',
                en=':'.join(WUT), dv=2)

    def get_driven_channels(self, index: int) -> list[str]:
        """Get channels driven by the constraint entry at input index.

        Args:
            index: Index of the constraint entry.

        Returns:
            List of channels driven by the constraint.
        """
        cns_attr = f'{self.cns_attr}[{index}]'
        channels = [x.rsplit('.', 1)[-1][:-1]
                    for x in cmds.listConnections(
                cns_attr + '.message_', s=0, d=1, p=1) or []]
        cns_type = CNS_MAP[cmds.getAttr(cns_attr + '.type', asString=1)]
        if cns_type not in ('s', 'rt'):
            channels = [f'{cns_type}{x[1:]}' for x in channels]
        return channels

    @IndexableGenerator.cast
    def get_target_weights(
            self, index: int
    ) -> T_IndexableGenerator[tuple[str, float]]:
        """Get the targets and their weights for the constraint at input index.

        Args:
            index: Index of the constraint entry.

        Yields:
            Tuple of target name and its weight.
        """
        cns_attr = f'{self.cns_attr}[{index}]'
        for j in cmds.getAttr(cns_attr + '.targets', mi=1) or []:
            target_attr = f'{cns_attr}.targets[{j}]'
            target = (cmds.listConnections(
                target_attr + '.target_msg', s=1, d=0) or [None])[0]
            if not target:
                target = cmds.getAttr(target_attr + '.target_ref')
            if not target:
                continue
            yield target, cmds.getAttr(target_attr + '.weight')

    def remove(self, index: int = -1):
        """Remove a constraint entry."""
        cmds.removeMultiInstance(f'{self.cns_attr}[{self.indices[index]}]', b=1)

    def serialize(self) -> OrderedDict:
        """Serialize this SpaceSwitchGuide.

        Returns:
            json compatible serialized data.
        """
        data = super().serialize()
        data['constraints'] = list(filter(
            bool, [self.serialize_constraint(x) for x in self.indices]))
        return data

    def serialize_constraint(self, index: int) -> Optional[dict[str, Any]]:
        """Serialize a specific constraint entry.

        Args:
            index: Index of the constraint entry.

        Returns:
            Serialized constraint data as a dictionary in the form:
            code-block::
                {
                    'channels': List of driven channels. Constraint type
                        inferred from the first character of any channel,
                    'targets': List of driver transforms,
                    'weights': List of target weights,
                    'offset': whether to maintain offsets,
                    [aimConstraint specific settings]
                }
        """
        cns_attr = f'{self.cns_attr}[{index}]'
        # channels
        result = {'channels': self.get_driven_channels(index)}
        if not result['channels']:
            return
        # targets and weights
        result['targets'], result['weights'] = zip(
            *self.get_target_weights(index))
        if not result['targets']:
            return
        # offsets
        result['offset'] = cmds.getAttr(cns_attr + '.offset')
        # aim constraint specific settings
        if cmds.getAttr(f'{cns_attr}.type', asString=1) == 'aimConstraint':
            result['wut'] = cmds.getAttr(cns_attr + '.up_type')
            result['wuo'] = (cmds.listConnections(
                f'{cns_attr}.up_target_msg', s=1, d=0) or [None])[0]
            if not result['wuo']:
                result['wuo'] = cmds.getAttr(f'{cns_attr}.up_target_ref')
        return result

    def set(
            self,
            index: int = -1,
            channels: Optional[Iterable[str]] = None,
            **kwargs: dict[str, Any]):
        """Set the constraint entry at input index.

        Args:
            index: Index of the constraint entry.
            channels: Series of 2-char strings representing what channels the
                targets should drive and the sort of constraint to use.
                The first character can be:
                    - **s**: a scale constraint
                    - **r** or **t**: rotation or translation parent constraint
                    - **o**: orient constraint
                    - **p**: point constraint
                    - **a**: aim constraint
                The second character can be **x**, **y** or **z**, representing
                the axis to be driven by input targets.
            **kwargs: Additional constraint settings.
                - targets: List of driver transforms.
                - weights: List of target weights.
                - offset: Whether to maintain offsets.
                - wut: Aim constraint specific settings.
                - wuo: Aim constraint specific settings.
        """
        cns_attr = f'{self.cns_attr}[{self.indices[index]}]'

        # type and channels
        if channels:
            # set type
            cmds.setAttr(
                f'{cns_attr}.type',
                list(CNS_MAP.values()).index(
                    'rt' if channels[0][0] in 'rt' else channels[0][0]))
            # connect channels
            ch_attr = f'{self.channels_attr}.{{}}_'
            source = f'{cns_attr}.message_'
            for channel in channels:
                channel = f'{REV_CNS_MAP[channel[0]]}{channel[1]}'
                cmds.connectAttr(source, ch_attr.format(channel), f=1)

        # targets and weights
        targets = kwargs.get('targets', [])
        weights = kwargs.get('weights', [1.0] + [0.0] * (len(targets) - 1))
        for i, target in enumerate(targets):
            target_attr = f'{cns_attr}.targets[{i}]'
            # message connect if it exists or set as string otherwise
            (cmds.connectAttr(f'{target}.msg', f'{target_attr}.target_msg')
             if cmds.objExists(target) else
             cmds.setAttr(f'{target_attr}.target_ref', target, type='string'))
            # set its weight
            cmds.setAttr(f'{target_attr}.weight', weights[i])

        # offset
        offset = kwargs.get('offset', True)
        if isinstance(offset, Number):
            offset = bool(offset)
        elif isinstance(offset, (list, tuple)):
            if isinstance(offset[0], Number):
                offset = any(offset)
            else:
                offset = any(any(y) for x in offset for y in x)
        cmds.setAttr(f'{cns_attr}.offset', offset)

        # aim constraint specific settings
        if 'wut' in kwargs:
            cmds.setAttr(f'{cns_attr}.up_type', kwargs['wut'])
        wuo = kwargs.get('wuo')
        if wuo:
            (cmds.connectAttr(wuo, f'{cns_attr}.up_target_msg')
             if cmds.objExists(wuo) else
             cmds.setAttr(f'{cns_attr}.up_target_ref', wuo, type='string'))

    @property
    def cns_attr(self) -> str:
        """Name of the multi-compound attribute representing each constraint.

        Returns:
            attribute name.
        """
        return f'{self.name}.ss_constraints'

    @property
    def channels_attr(self) -> str:
        """Name of the compound attribute representing driven channels.

        Returns:
            attribute name.
        """
        return f'{self.name}.ss_channels'

    @property
    def indices(self) -> list[int]:
        """Get the indices of each constraint definition entry.

        Returns:
            List of indices.
        """
        return cmds.getAttr(self.cns_attr, mi=1) or []


class SpaceSwitch(node.Node):
    """Manages dynamic parenting of a transform via constraints.

    To do:
        Ability to expose constraint weights either as a float per constraint
        target or as an enum per constraint in a node of our choice.
    """

    DEFAULT_NAME = nc.Type.transform.value

    @classmethod
    def deserialize(
            cls,
            data: dict[str, Any],
            name: Optional[str] = None,
            parent: Optional[str] = None
    ) -> 'SpaceSwitch':
        """Create a SpaceSwitch out of serialized data.

        Args:
            data: serialized data.
            name: Name of the new Node. If not provided, use the node type, as
                Maya would do, letting the software resolve name clashes with
                an index at the end.
            parent: Name or uuid of parent object.

        Returns:
            SpaceSwitch class instance.
        """
        self: SpaceSwitch = super().deserialize(name=name, parent=parent)
        [self.add(**x) for x in data['constraints']]
        return self

    def _create(self, type: str, constraints: dict[str, Any]):
        """Create constraints where needed.

        Args:
            type: Type of constraint.
            constraints: Dictionary containing the constraints.
        """
        unconstrained_channels = constraints.get(None, [])
        if not unconstrained_channels:
            return
        root = self.name
        cns = cmds.createNode(f'{type}Constraint', p=root, ss=1)
        # rest pose
        cmds.setAttr(f'{cns}.erp', True)
        s, r, t = [cmds.getAttr(f'{root}.{x}')[0] for x in 'srt']
        for k, v in {'rs': s, 'rsrr': r, 'rst': t}.items():
            if cmds.attributeQuery(k, n=cns, ex=1):
                cmds.setAttr(f'{cns}.{k}', *v)
        # interpolation mode
        if type in ['orient', 'parent']:
            cmds.setAttr(f'{cns}.int', 2)
        # connections
        d = {'aim': {'pim': 'cpim', 'ro': 'cro', 'rp': 'crp', 'rpt': 'crt',
                     't': 'ct'},
             'orient': {'pim': 'cpim', 'ro': 'cro'},
             'parent': {'pim': 'cpim', 'ro': 'cro', 'rp': 'crp', 'rpt': 'crt'},
             'point': {'pim': 'cpim', 'rp': 'crp', 'rpt': 'crt'},
             'scale': {'pim': 'cpim'}}
        [cmds.connectAttr(f'{root}.{k}', f'{cns}.{v}')
         for k, v in d[type].items()]
        for ch in unconstrained_channels:
            cmds.connectAttr(f'{cns}.c{ch}', f'{root}.{ch}')
        # update constraints dictionary
        del constraints[None]
        constraints[cns] = unconstrained_channels

    def _split(self, constraints: dict[str, Iterable[str]]):
        """Fork constraints which affect unspecified channels.

        Args:
            constraints: (constraint name, list of channels) pairs.
        """
        root = self.name
        for cns in list(constraints.keys()):
            if not cns:
                continue
            plugs = cmds.listConnections(cns, s=0, d=1, p=1, c=1)
            channels = [y for x, y in zip(plugs[::2], plugs[1::2])
                        if x.split('.', 1)[1][:-1] in ['constraintTranslate',
                                                       'constraintRotate',
                                                       'constraintScale']
                        and y.split('.', 1)[0] != cns]
            affected = [f'{root}.{cmds.attributeQuery(x, n=root, ln=1)}'
                        for x in constraints[cns]]
            if not all(x in affected for x in channels):
                new_cns = split(cns, *[channels.index(x) for x in affected])
                constraints[new_cns] = constraints[cns]
                del constraints[cns]

    def _verify(self, type: str, constraints: dict[str, Iterable[str]]):
        """Check that no channel is driven by other than expected constraint.

        Doesn't verify if any constraint is associated with an unconventional
        channel. That is still acceptable in Maya, so let's keep that door open.

        Args:
            type: Type of constraint.
            constraints: (constraint name, list of channels) pairs.
        """
        for x in constraints:
            if (
                x is False
                or x and not cmds.objectType(x, isa=f'{type}Constraint')
            ):
                ch = ', '.join([f'{self.name}.{y}' for y in constraints[x]])
                raise TypeError(f"{ch} driven by non-{type}Constraint '{x}'")

    def add(
            self,
            targets: str | Iterable[str],
            channels: Optional[Iterable[str]] = None,
            offset: bool = True,
            weights: Optional[float | Iterable[float]] = None,
            update: bool = True,
            **kwargs):
        """Add input objects as SpaceSwitch targets.

        Args:
            targets: Name of each new target transform.
            channels: Series of 2-char strings representing what channels the
                targets should drive and the sort of constraint to use.

                The first character can be:

                - **s**: a scale constraint
                - **r** or **t**: rotation or translation parent constraint
                - **o**: orient constraint
                - **p**: point constraint
                - **a**: aim constraint

                The second character can be **x**, **y** or **z**, representing
                the axis to be driven by input targets.
                Default: ['sx', 'sy', 'sz', 'rx', 'ry', 'rz', 'tx', 'ty', 'tz']
            offset: If True, respect the offset between each target and the
                space-switching transform at time of bind.
            weights: Weight of each target. If a single or no value is provided,
                all targets will be weighted equally.
            update: If a constraint already includes input target and 'offset'
                is True, update its offset.

        Raises:
            TypeError: Can't add targets to channels which are already driven
                by constraints of a different type.
        """
        channels = channels or S[1:] + R[1:] + T[1:]

        # scale constraints
        chns = [x for x in channels if x.startswith('s')]
        if chns:
            self.add_s(targets, chns, offset, weights, update, **kwargs)

        # parent constraints
        chns = [x for x in channels if x[0] in 'rt']
        if chns:
            self.add_rt(targets, chns, offset, weights, update, **kwargs)

        # aim constraints
        chns = [f'r{x[1]}' for x in channels if x.startswith('a')]
        if chns:
            self.add_a(targets, chns, offset, weights, **kwargs)

        # orient constraints
        chns = [f'r{x[1]}' for x in channels if x.startswith('p')]
        if chns:
            self.add_o(targets, chns, offset, weights, **kwargs)

        # point constraints
        chns = [f't{x[1]}' for x in channels if x.startswith('p')]
        if chns:
            self.add_p(targets, chns, offset, weights, **kwargs)

    def add_a(
            self,
            targets: str | Iterable[str],
            channels: Optional[str | Iterable[str]] = None,
            offset: bool | vec3 = True,
            weights: Optional[float | Iterable[float]] = None,
            **kwargs: dict[str, Any]):
        """Add input objects as aimConstraint targets.

        Args:
            targets:
            channels: Default: ['rx', 'ry', 'rz']
            offset: Whether to maintain an offset to input targets.
            weights: Weight of each target. If a single or no value is provided,
                all targets will be weighted equally.

        Raises:
            TypeError: Can't add targets to channels which are already driven
                by a constraint other than a aimConstraint.
        """
        # process channels
        channels = channels or R[1:]
        if isinstance(channels, str):
            channels = [channels]
        # process constraints
        constraints = self.get_cns_dict(*channels)
        self._verify('aim', constraints)
        self._split(constraints)
        self._create('aim', constraints)
        # process targets
        targets = [targets] if isinstance(targets, str) else targets
        # process offset
        k = 'mo' if offset is None or isinstance(offset, bool) else 'offset'
        kwargs[k] = offset
        # process weights
        if isinstance(weights, (Number, NoneType)):
            weights = [weights or 0] * len(targets)

        for cns in constraints:
            tl = cmds.aimConstraint(cns, q=1, tl=1) or []
            if not offset:
                # reset existing offset
                cmds.setAttr(f'{cns}.o', 0, 0, 0)
            # add new targets, set target weights
            for target, weight in zip(targets, weights):
                if target not in tl:
                    cmds.aimConstraint(target, cns, w=weight or 1, **kwargs)
                    if not weight:
                        cmds.aimConstraint(target, cns, w=0)
            if not tl:
                for wal in cmds.aimConstraint(cns, q=1, wal=1)[1:]:
                    cmds.setAttr(f'{cns}.{wal}', 0)

    def add_o(
            self,
            targets: str | Iterable[str],
            channels: Optional[str | Iterable[str]] = None,
            offset: bool | vec3 = True,
            weights: Optional[float | Iterable[float]] = None,
            **kwargs: dict[str, Any]):
        """Add input objects as orientConstraint targets.

        Args:
            targets:
            channels: Default: ['rx', 'ry', 'rz']
            offset: Whether to maintain an offset to input targets.
            weights: Weight of each target. If a single or no value is provided,
                all targets will be weighted equally.

        Raises:
            TypeError: Can't add targets to channels which are already driven
                        by a constraint other than a orientConstraint.
        """
        # process channels
        channels = channels or R[1:]
        if isinstance(channels, str):
            channels = [channels]
        # process constraints
        constraints = self.get_cns_dict(*channels)
        self._verify('orient', constraints)
        self._split(constraints)
        self._create('orient', constraints)
        # process targets
        targets = [targets] if isinstance(targets, str) else targets
        # process offset
        k = 'mo' if offset is None or isinstance(offset, bool) else 'offset'
        kwargs[k] = offset
        # process weights
        if isinstance(weights, (Number, NoneType)):
            weights = [weights or 0] * len(targets)

        for cns in constraints:
            tl = cmds.orientConstraint(cns, q=1, tl=1) or []
            if not offset:
                # reset existing offset
                cmds.setAttr(f'{cns}.o', 0, 0, 0)
            # add new targets, set target weights
            for target, weight in zip(targets, weights):
                if target not in tl:
                    cmds.orientConstraint(target, cns, w=weight or 1, **kwargs)
                    if not weight:
                        cmds.orientConstraint(target, cns, w=0)
            # at least 1 constraint target must have non-zero weight
            if not (tl or sum(weights)):
                weight_alias_0 = cmds.orientConstraint(cns, q=1, wal=1)[0]
                cmds.setAttr(f'{cns}.{weight_alias_0}', 1)

    def add_p(
            self,
            targets: str | Iterable[str],
            channels: Optional[str | Iterable[str]] = None,
            offset: bool | vec3 = True,
            weights: Optional[float | Iterable[float]] = None,
            **kwargs: dict[str, Any]):
        """Add input objects as pointConstraint targets.

        Args:
            targets:
            channels: Default: ['tx', 'ty', 'tz']
            offset: Whether to maintain an offset to input targets.
            weights: Weight of each target. If a single or no value is provided,
                all targets will be weighted equally.

        Raises:
            TypeError: Thrown if any input channel is driven by a constraint
                other than a pointConstraint
        """
        # process channels
        channels = channels or T[1:]
        if isinstance(channels, str):
            channels = [channels]
        # process existing constraints
        constraints = self.get_cns_dict(*channels)
        self._verify('point', constraints)
        self._split(constraints)
        self._create('point', constraints)
        # process targets
        targets = [targets] if isinstance(targets, str) else targets
        # process offset
        k = 'mo' if offset is None or isinstance(offset, bool) else 'offset'
        kwargs[k] = offset
        # process weights
        if isinstance(weights, (Number, NoneType)):
            weights = [weights or 0] * len(targets)

        for cns in constraints:
            tl = cmds.pointConstraint(cns, q=1, tl=1) or []
            if not offset:
                # reset existing offset
                cmds.setAttr(f'{cns}.o', 0, 0, 0)
            # add new targets, set target weights
            for target, weight in zip(targets, weights):
                if target not in tl:
                    cmds.pointConstraint(target, cns, w=weight or 1, **kwargs)
                if not weight:
                    cmds.pointConstraint(target, cns, w=0)
            # at least 1 constraint target must have non-zero weight
            if not (tl or sum(weights)):
                weight_alias_0 = cmds.pointConstraint(cns, q=1, wal=1)[0]
                cmds.setAttr(f'{cns}.{weight_alias_0}', 1)

    def add_rt(
            self,
            targets: str | Iterable[str],
            channels: Optional[Iterable[str]] = None,
            offset: bool | Iterable[tuple[vec3, vec3]] = True,
            weights: Optional[float | Iterable[float]] = None,
            update: bool = True,
            **kwargs: dict[str, Any]):
        """Add input objects as parentConstraint targets

        Args:
            targets:
            channels: Default: ['rx', 'ry', 'rz', 'tx', 'ty', 'tz']
            offset: Whether to maintain an offset to input targets.
                It may be True, False or specific offset value(s) as:
                ((target_0 rotation offset, target_0 translation offset), ...)
            weights: Weight of each target. If a single or no value is provided,
                all targets will be weighted equally.
            update: If a constraint already includes input target, and 'offset'
                is True, update it's offset. Default: True

        Raises:
            TypeError: Thrown if any input channel is driven by a constraint
                other than a parentConstraint
        """

        # process channels
        channels = channels or R[1:] + T[1:]
        if isinstance(channels, str):
            channels = [channels]
        # process existing constraints
        constraints = self.get_cns_dict(*channels)
        self._verify('parent', constraints)
        self._split(constraints)
        self._create('parent', constraints)
        # process targets
        targets = [targets] if isinstance(targets, str) else targets
        # process offsets
        if isinstance(offset, (bool, NoneType)):
            kwargs['mo'] = offset
        elif isinstance(offset[0][0], Number):
            offset = [offset] * len(targets)
        # process weights
        if isinstance(weights, (Number, NoneType)):
            weights = [weights or 0] * len(targets)

        for cns in constraints:
            tl = cmds.parentConstraint(cns, q=1, tl=1) or []
            if update and not offset:
                # zero the offset for existing targets
                [cmds.setAttr(f'{cns}.target[{i}].{at}', 0, 0, 0)
                 for i in [tl.index(x) for x in targets if x in tl]
                 for at in ['tor', 'tot']]
            for target, weight in zip(targets, weights):
                # add new targets, set target weights
                if update or target not in tl:
                    cmds.parentConstraint(target, cns, w=weight, **kwargs)
            # update offsets if specific values provided
            if offset and not isinstance(offset, bool):
                tl_1 = cmds.parentConstraint(cns, q=1, tl=1) or []
                [cmds.setAttr(f'{cns}.target[{index}].to{at}',
                              *offset[i][j])
                 for i, index in enumerate([tl_1.index(x) for x in targets])
                 for j, at in enumerate('rt')]
            # at least 1 constraint target must have non-zero weight
            if not (tl or sum(weights)):
                weight_alias_0 = cmds.parentConstraint(cns, q=1, wal=1)[0]
                cmds.setAttr(f'{cns}.{weight_alias_0}', 1)

    def add_s(
            self,
            targets: str | Iterable[str],
            channels: Optional[Iterable[str]] = None,
            offset: bool | vec3 = True,
            weights: Optional[float | Iterable[float]] = None,
            update: bool = True,
            **kwargs: dict[str, Any]):
        """Add input objects as scaleConstraint targets.

        Args:
            targets:
            channels: Default: ['sx', 'sy', 'sz']
            offset: Whether to maintain an offset to input targets.
            weights: Weight of each target. If a single or no value is provided,
                all targets will be weighted equally.
            update: If a constraint already includes input target, and 'offset'
                is True, update it's offset.

        Raises:
            TypeError: Thrown if any input channel is driven by a constraint
                other than a scaleConstraint
        """
        # process channels
        channels = channels or S[1:]
        if isinstance(channels, str):
            channels = [channels]
        # process existing constraints
        constraints = self.get_cns_dict(*channels)
        self._verify('scale', constraints)
        self._split(constraints)
        self._create('scale', constraints)
        # process targets
        targets = [targets] if isinstance(targets, str) else targets
        # process offset
        k = 'mo' if offset is None or isinstance(offset, bool) else 'offset'
        kwargs[k] = offset
        # process weights
        if isinstance(weights, (Number, NoneType)):
            weights = [weights or 0] * len(targets)

        for cns in constraints:
            tl = cmds.scaleConstraint(cns, q=1, tl=1) or []
            # add new targets, set target weights
            for target, weight in zip(targets, weights):
                if update or target not in tl:
                    cmds.scaleConstraint(target, cns, w=weight or 1, **kwargs)
                    if not weight:
                        cmds.scaleConstraint(target, cns, w=0)
            # at least 1 constraint target must have non-zero weight
            if not (tl or sum(weights)):
                weight_alias_0 = cmds.scaleConstraint(cns, q=1, wal=1)[0]
                cmds.setAttr(f'{cns}.{weight_alias_0}', 1)

    def get_cns(self, *channels: str) -> Iterator[str | None | bool]:
        """Get the constraints driving each input channel (or all of them).

        Args:
            channels: each channel's name

        Yields:
            name of each channel's constraint if any, None for disconnected
            channels and False for channels driven by other sources.
        """
        for channel in channels or S[1:] + R[1:] + T[1:]:
            source = cmds.listConnections(f'{self.name}.{channel}', s=1, d=0)
            if source:
                if cmds.objectType(source[0], isa='constraint'):
                    yield source[0]
                else:
                    yield False
            else:
                yield None

    def get_cns_dict(
            self, *channels: str
    ) -> dict[str | None | bool, list[str]]:
        """Get constraints driving each input channel (or all of them) as a dict

        Args:
            channels: Each channel name

        Returns:
            {constraint (str, None or False): channels (list of str), ...} pairs
        """
        constraints = {}
        channels = channels or S[1:] + R[1:] + T[1:]
        for ch, cns in zip(channels, self.get_cns(*channels)):
            constraints.setdefault(cns, []).append(ch)
        return constraints

    def get_weights(
            self, *channels: str
    ) -> dict[str, list[list[str], list[Number]]]:
        """Get the target weights for input channels

        Args:
            *channels: Each channel name

        Returns:
            {channel: ([target, ...], [weight, ...]), ...} pairs
        """
        result = {x: [y] for x, y in self.get_cns_dict(*channels).items()}
        for cns in result:
            w = []
            if cns:
                f = getattr(cmds, cmds.objectType(cns))
                w = f(f(cns, q=1, tl=1), cns, q=1, w=1)
            result[cns].append([w] if isinstance(w, Number) else w)
        return result

    def optimize(self, *channels: str):
        """Merges identical constraints.

        Args:
            *channels: Each channel name

        To do: If two constraints are equal but not all their channels where
            provided, only merge the provided channels.
            Ex.: we might want separate parentConstraints for translation and
            rotation, even if they share the same targets.
        """
        channels = channels or S[1:] + R[1:] + T[1:]
        constraints = list(set(x for x in self.get_cns(*channels) if x))
        for i, cns in enumerate(constraints):
            cns_type = cmds.objectType(cns)
            for other in constraints[i + 1:]:
                if cmds.objectType(other) == cns_type and equal(cns, other):
                    merge(cns, other)
                    break

    def remove(
            self,
            targets: Optional[str | Iterable[str]] = None,
            *channels: str):
        """Remove targets from constraints driving channels.

        If neither targets nor channels are specified, remove all constraints on
        this node.

        Args:
            targets: If specified, only remove input targets. Otherwise, remove
                every target (the entire constraint) driving the channels.
            channels: If specified, remove targets from constraints affecting
                these particular channels. otherwise, remove targets from all
                constraints on this node.
        """
        constraints = self.get_cns_dict(*channels)
        if channels and not all(constraints):
            invalid = constraints.get(None, []) + constraints.get(False, [])
            invalid = ', '.join([f'{self.name}.{x}' for x in invalid])
            raise ValueError(f"Channels not driven by constraints: {invalid}")
        for cns in constraints:
            if cns is None:
                continue
            func = getattr(cmds, cmds.objectType(cns))
            targets = targets or func(cns, q=1, tl=1)
            func(targets, cns, rm=1)

    def serialize(self) -> OrderedDict:
        """Serialize this SpaceSwitch.

        Returns:
            json-compatible data required to recreate this SpaceSwitch.

        """
        data = super().serialize()
        cnss = self.get_cns_dict()
        data['constraints'] = []
        for cns, channels in cnss.items():
            if not cns:
                continue
            cns_type = cmds.objectType(cns)
            func = getattr(cmds, cns_type)
            weights = next(iter(self.get_weights(*channels).values()))[1]
            if cns_type not in ('parentConstraint', 'scaleConstraint'):
                channels = [f'{CNS_MAP[cns_type]}{x[-1]}' for x in channels]
            result = {'channels': channels,
                      'targets': func(cns, q=1, tl=1),
                      'weights': weights}
            if cns_type == 'parentConstraint':
                result['offset'] = [
                    [cmds.getAttr(cns + f'.tg[{i}].to{y}')[0]
                     for y in 'rt']
                    for i in range(len(result['targets']))]
            else:
                result['offset'] = func(cns, q=1, o=1)
                if cns_type == 'aimConstraint':
                    # grab aim, u, wu, wut, wuo
                    result['aim'] = func(cns, q=1, aim=1)
                    result['u'] = func(cns, q=1, u=1)
                    result['wu'] = func(cns, q=1, wu=1)
                    result['wut'] = WUT.index(func(cns, q=1, wut=1))
                    result['wuo'] = func(cns, q=1, wuo=1)[0]
            data['constraints'].append(result)
        return data

    def set_weights(self, weights: Number | Iterable[Number], *channels: str):
        """Set constraint weights of specified channels.

        Args:
            weights: Weights to be set.
            *channels: Each channel name.
        """
        for cns in set(self.get_cns(*channels)):
            if cns is None:
                continue
            f = getattr(cmds, cmds.objectType(cns))
            targets = f(cns, q=1, tl=1)
            if isinstance(weights, Number):
                weights = [weights] * len(targets)
            d = {}
            [d.setdefault(x, []).append(y) for x, y in zip(weights, targets)]
            for weight, targets in d.items():
                f(targets, cns, w=weight)
