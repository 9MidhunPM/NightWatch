from pathlib import Path

from nightwatch.storage.database import ensure_database_directory


def test_database_initializes_new_path(tmp_path: Path) -> None:
    database_file = tmp_path / "data" / "nightwatch.db"
    ensure_database_directory(f"sqlite+aiosqlite:///{database_file}")
    assert database_file.parent.is_dir()
