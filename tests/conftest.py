import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_TAKEOUT = REPO_ROOT / "sources" / "Takeout"

HAS_EXIFTOOL = shutil.which("exiftool") is not None
HAS_REAL_SAMPLES = SOURCES_TAKEOUT.exists()

requires_exiftool = pytest.mark.skipif(not HAS_EXIFTOOL, reason="exiftool not installed")
requires_real_samples = pytest.mark.skipif(not HAS_REAL_SAMPLES, reason="sources/Takeout sample data not present")


def copy_sample(rel_path: str, dest_dir: Path) -> Path:
    """Copy one file from the read-only sources/Takeout tree into a tmp dir.

    Never opens the source for writing. Callers must only ever write to the
    returned copy.
    """
    src = SOURCES_TAKEOUT / rel_path
    dest = dest_dir / Path(rel_path).name
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest
