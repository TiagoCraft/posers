import importlib
import os

from py import import_package

include_list = ['pipe']
root = os.environ['REZ_USED_REQUEST'].split('=', 1)[0].upper()
print(os.path.join(os.environ[f'REZ_{root}_ROOT'], 'python'))
for x in next(os.walk(os.path.join(
        os.environ[f'REZ_{root}_ROOT'], 'python')))[1]:
    if x == 'py' or x.startswith('py_') or x in include_list:
        import_package(
            importlib.import_module(x),
            recursive=True,
            fail=True)
