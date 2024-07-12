import os

from py import Settings


LOCAL_USER_DATA_PATH = os.path.expanduser('~/Documents/userdata')
LOCAL_DEV_PATH = os.path.expanduser('~/dev')
REMOTE_DEV_PATH = '/nas1/dev' if os.name == 'posix' else 'P:'

settings = Settings(
    os.path.join(LOCAL_USER_DATA_PATH, 'pipe.json'),
    {
        'local pipeline': None,  # None = look for local or default to remote
        'rez packages path': None,
        'shell': False
    }
)

