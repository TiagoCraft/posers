import importlib
import os

from maya import standalone
from py import import_package


standalone.initialize()
root = os.environ['REZ_USED_REQUEST'].split('=', 1)[0].upper()
print(os.path.join(os.environ[f'REZ_{root}_ROOT'], 'python'))
for x in next(os.walk(os.path.join(
        os.environ[f'REZ_{root}_ROOT'], 'python')))[1]:
    if x == 'ma' or x.startswith('ma_'):
        import_package(
            importlib.import_module(x),
            recursive = True,
            fail = True)
standalone.uninitialize()
