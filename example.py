from ma import cmds
from ma_rig import poser

l = cmds.listRelatives(cmds.createNode('locator'), p=1)[0]
ps = poser.PoserSet.create()
ps.add_attr(f'{l}.t')
ps.add_pose('move_up')
ps.set_pose_values(0, {ps.posers[0]: [0, 10, 0]})