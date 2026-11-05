"""Read-only historical replay inputs on hosts without symlink privileges."""

import hashlib
import shutil
from pathlib import Path


def inventory(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("Historical replay copy requires physical regular inputs")
        if path.is_file():
            raw = path.read_bytes()
            result[path.relative_to(root).as_posix()] = (len(raw), hashlib.sha256(raw).hexdigest())
    return result


def materialize_directory(source, target):
    """Preserve the same verifier and bytes; never synthesize extended attributes.

    The ordinary symlink path is unchanged. Only Windows' explicit missing
    symlink privilege permits an isolated copy, checked before and after copying.
    Native source verifiers still fail if required provenance is unavailable.
    """
    source, target = Path(source), Path(target)
    try:
        target.symlink_to(source, target_is_directory=True)
        return "linked"
    except OSError as error:
        if getattr(error, "winerror", None) != 1314:
            raise
    before = inventory(source)
    shutil.copytree(source, target)
    if inventory(target) != before or inventory(source) != before:
        raise ValueError("Historical replay input changed while copying")
    return "copied_bytes_verified"
