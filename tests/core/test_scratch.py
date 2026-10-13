import os
from pathlib import Path

from suzent.core.scratch import prune_scratch


def _write(path: Path, size: int, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))


def test_prune_leaves_a_folder_under_the_cap_alone(tmp_path: Path):
    _write(tmp_path / "a.txt", 100, 1_000)

    assert prune_scratch(tmp_path, 1_000) == 0
    assert (tmp_path / "a.txt").exists()


def test_prune_removes_oldest_files_first_until_under_the_cap(tmp_path: Path):
    _write(tmp_path / "old" / "a.bin", 400, 1_000)
    _write(tmp_path / "mid.bin", 400, 2_000)
    _write(tmp_path / "new.bin", 400, 3_000)

    freed = prune_scratch(tmp_path, 900)

    assert freed == 400
    assert not (tmp_path / "old").exists()
    assert (tmp_path / "mid.bin").exists()
    assert (tmp_path / "new.bin").exists()


def test_prune_never_follows_symlinks_out_of_the_folder(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside / "keep.bin", 500, 1_000)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "link").symlink_to(outside, target_is_directory=True)
    _write(scratch / "big.bin", 500, 2_000)

    prune_scratch(scratch, 100)

    assert (outside / "keep.bin").exists()
    assert not (scratch / "big.bin").exists()
