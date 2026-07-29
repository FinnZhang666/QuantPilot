import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from app.config.settings import Settings


class BackupService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = Path(settings.backup_directory)

    def create(self, backup_type: str = "manual") -> Dict[str, object]:
        if backup_type not in {"manual", "daily", "weekly"}:
            raise ValueError("备份类型必须是manual、daily或weekly。")
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.root / ("quantpilot-%s-%s.zip" % (backup_type, stamp))
        database = Path(self.settings.database_url.removeprefix("sqlite:///"))
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "quantpilot.db"
            with sqlite3.connect(str(database)) as source, sqlite3.connect(str(snapshot)) as destination:
                source.backup(destination)
            manifest = {
                "product": "QuantPilot", "type": backup_type,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "database": database.name,
            }
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "database/quantpilot.db")
                for path in self._config_files():
                    archive.write(path, "config/" + path.name)
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        result = self.verify(target)
        self._apply_retention()
        return result

    def list(self) -> List[Dict[str, object]]:
        if not self.root.exists():
            return []
        return [self.verify(path) for path in sorted(self.root.glob("quantpilot-*.zip"), reverse=True)]

    def verify(self, path=None) -> Dict[str, object]:
        target = Path(path) if path else (next(iter(sorted(self.root.glob("quantpilot-*.zip"), reverse=True)), None))
        if target is None or not target.exists():
            raise FileNotFoundError("没有可验证的备份。")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        try:
            with zipfile.ZipFile(target) as archive:
                bad = archive.testzip()
                names = archive.namelist()
                valid = bad is None and "database/quantpilot.db" in names and "manifest.json" in names
        except zipfile.BadZipFile:
            names, valid = [], False
        return {
            "path": str(target), "filename": target.name, "size_bytes": target.stat().st_size,
            "sha256": digest, "valid": valid, "files": names,
        }

    def _config_files(self):
        values = [
            Path(".env.example"), Path("config/logging.yaml"),
            Path("config/review_windows_v1.yaml"), Path("config/candidate_pool_v1.yaml"),
            Path("app/ai/prompts.py"),
        ]
        return [path for path in values if path.exists()]

    def _apply_retention(self):
        for kind, keep in (
            ("daily", self.settings.backup_daily_retention),
            ("weekly", self.settings.backup_weekly_retention),
        ):
            for path in sorted(self.root.glob("quantpilot-%s-*.zip" % kind), reverse=True)[keep:]:
                path.unlink()
