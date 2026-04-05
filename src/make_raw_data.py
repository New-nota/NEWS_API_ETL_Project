from pathlib import Path
from datetime import datetime
import json
from typing import Any
BASE_DIR = Path(__file__).resolve().parent.parent

def import_to_raw_json(data:dict[str, Any], category: str, hot_pot: str, page: int) -> str:
    NEDD_DIR = BASE_DIR / "data" / "raw"
    NEDD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    create_data = f"{timestamp}_{category}_{hot_pot}_page_{page}.json"
    file_path = NEDD_DIR / create_data
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return create_data

