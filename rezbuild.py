import os
import shutil
import sys

exclude_folders = ['.git', 'build']
include_folders = []


def copy(source_path, dest_path):
    """Copy source folder to input destination.

    Overwrites destination if pre-existing. This will ignore folders in the
    exclude_folders list and, if any, only include folders in the
    include_folders list

    Args:
        source_path (str): path to source folder to be copied
        dest_path (str):  destination path where to copy source content.
    """
    for subfolder in next(os.walk(source_path))[1]:
        if subfolder in exclude_folders:
            continue
        if include_folders and subfolder not in include_folders:
            continue
        src = os.path.join(source_path, subfolder)
        if os.path.exists(src):
            dest = os.path.join(dest_path, subfolder)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)


def remove_local_build(install_path):
    """Delete local test build when releasing.

    Args:
        install_path (str): path where the package is being installed to.
    """
    local_path = os.path.normpath(
        os.environ.get('REZ_LOCAL_PACKAGES_PATH', ''))
    release_path = os.path.normpath(
        os.environ.get('REZ_RELEASE_PACKAGES_PATH', ''))
    if local_path and install_path.startswith(release_path):
        dest = os.path.normpath(
            local_path + install_path[len(release_path):])
        if os.path.exists(dest):
            dirname = os.path.dirname(dest)
            if len(os.listdir(dirname)) == 1:
                dest = dirname
            print(f"Removing older local installation from {dest}")
            shutil.rmtree(dest)


if __name__ == '__main__' and 'install' in (sys.argv[1:] or []):
    root = source = os.environ['REZ_BUILD_SOURCE_PATH']
    variant = os.environ['REZ_BUILD_VARIANT_REQUIRES']
    install_root = install_path = os.environ['REZ_BUILD_INSTALL_PATH']
    if variant:
        source = os.path.join(root, 'variants', *variant.split())
        install_root = os.path.dirname(install_path)

    # copy source code
    copy(source, install_path)
    # if it's a release, remove local installation
    remove_local_build(install_path)
