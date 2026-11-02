"""The pristine demo house: plugins-extra/demo/house/ is copied over the house directory at every start of
the demo backend, so a reset (the backend exits, Docker starts it again) wipes whatever a guest changed:
settings, rules, history and stats databases, the status cache."""
import hashlib
import os
import shutil
from pathlib import Path

SEED = Path(__file__).resolve().parent / "house"


def reset_house(house, seed=SEED):
    """Empty `house` (the directory itself stays: it is a mount) and copy `seed` into it, byte for byte."""
    house, seed = Path(house), Path(seed)
    if house.resolve() == seed.resolve() or seed.resolve() in house.resolve().parents:
        raise ValueError("the house directory cannot be the seed")
    for p in house.iterdir():
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink()
    shutil.copytree(seed, house, dirs_exist_ok=True, symlinks=False)
    for root, dirs, files in os.walk(house):         # the backend writes here as its own user
        for n in dirs + files:
            os.chmod(os.path.join(root, n), 0o755 if n in dirs else 0o644)


def digest(root) -> str:
    """One hash of a tree: every file's path and bytes, in order (the reset check compares the house with the seed)."""
    h, root = hashlib.sha256(), Path(root)
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()
