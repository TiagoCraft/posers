from maya import cmds, mel
from maya.api import OpenMaya as om


def attribute_state(attr: str) -> int:
    """Find the state of input attribute

    Args:
        attr: name of an attribute

    Returns:
        0 = not connected
        1 = connected, not editable
        2 = animated, no key at current time
        3 = animated, key at current frame
        4 = animated, modified value of key at current time.
    """
    src = (cmds.listConnections(attr, s=1, d=0) or (None,))[0]
    f = cmds.currentTime(q=1)
    if not src:
        return 0  # not connected
    if not cmds.objectType(src, isa='animCurve'):
        return 1  # connected, not editable
    keyframes = cmds.keyframe(attr, q=1, tc=1)
    if f not in keyframes:
        return 2  # animated, no key at current time
    key = cmds.keyframe(attr, q=1, vc=1)[keyframes.index(f)]
    if cmds.getAttr(attr) == key:
        return 3  # animated, key at current frame
    return 4  # animated, modified value of key at current time
