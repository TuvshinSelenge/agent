import json
from pathlib import Path


def write_fixtures(fixture_dir: Path, entries: list[dict]) -> Path:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "test.json").write_text(json.dumps(entries), encoding="utf-8")
    return fixture_dir
