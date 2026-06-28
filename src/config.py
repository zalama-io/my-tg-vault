"""
إعدادات المشروع - تُحمَّل مرة واحدة عند بدء التشغيل
"""
import yaml
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

BASE_DIR = Path(__file__).parent.parent

@dataclass
class TelegramConfig:
    api_id: int
    api_hash: str
    session_name: str = "archiver"

@dataclass
class Settings:
    download_media: bool = True
    max_concurrent_downloads: int = 3
    batch_size: int = 100
    retry_attempts: int = 3
    delay_between_batches: float = 1.0

@dataclass
class OutputConfig:
    archive_dir: Path = BASE_DIR / "archive"
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"

@dataclass
class AppConfig:
    telegram: TelegramConfig
    channels: List[str]
    settings: Settings = field(default_factory=Settings)
    output: OutputConfig = field(default_factory=OutputConfig)

def load_config(config_path: str = None) -> AppConfig:
    """تحميل الإعدادات من ملف YAML"""
    path = Path(config_path or BASE_DIR / "config.yaml")
    
    if not path.exists():
        raise FileNotFoundError(f"ملف الإعدادات غير موجود: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    
    # إنشاء المجلدات إذا لم تكن موجودة
    output = OutputConfig(
        archive_dir=Path(raw.get("output", {}).get("archive_dir", "./archive")),
        data_dir=Path(raw.get("output", {}).get("data_dir", "./data")),
        logs_dir=Path(raw.get("output", {}).get("logs_dir", "./logs")),
    )
    for d in [output.archive_dir, output.data_dir, output.logs_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    return AppConfig(
        telegram=TelegramConfig(**raw["telegram"]),
        channels=raw.get("channels", []),
        settings=Settings(**raw.get("settings", {})),
        output=output,
    )
