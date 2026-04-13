from pathlib import Path
import yaml


def load_settings(path: str = "config/settings.yaml") -> dict:
    settings_path = Path(path)
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")
    with settings_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}
