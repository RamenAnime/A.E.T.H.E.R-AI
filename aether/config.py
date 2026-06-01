"""Load settings from environment and .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT.parent / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _split_paths(value: str | None) -> List[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


@dataclass
class Settings:
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "HBr48ROZd1B2dv74C8bN"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_code_model: str = "codellama:7b"
    ollama_embed_model: str = "nomic-embed-text"
    use_airllm: bool = False
    airllm_quantization: str = "int4"
    airllm_cache_dir: str = "./models"
    chroma_persist_dir: str = "./data/vector_db"
    allowed_roots: List[str] = field(default_factory=list)
    max_file_size: int = 10_485_760
    require_permissions: bool = True
    permission_timeout: int = 30
    data_dir: str = "./data"
    traces_db: str = "./data/traces.db"
    octoprint_url: str = ""
    octoprint_api_key: str = ""
    moonraker_url: str = ""
    moonraker_api_key: str = ""
    printer_type: str = "octoprint"
    printer_profile: str = "ender3_v3"
    web_host: str = "127.0.0.1"
    web_port: int = 8787
    persona: str = "aether"
    assistant_name: str = "A.E.T.H.E.R."
    user_title: str = "sir"
    wake_word: str = "aether"
    build_dir: str = "./data/builds"
    homeassistant_url: str = ""
    homeassistant_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        allowed = _split_paths(os.getenv("ALLOWED_ROOTS", "~/Desktop,~/Documents,~/Projects"))
        expanded = [str(Path(p).expanduser()) for p in allowed]
        data_dir = os.getenv("AETHER_DATA_DIR", "./data")
        return cls(
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "HBr48ROZd1B2dv74C8bN"),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
            ollama_code_model=os.getenv("OLLAMA_CODE_MODEL", "codellama:7b"),
            ollama_embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            use_airllm=_bool(os.getenv("USE_AIRLLM"), False),
            airllm_quantization=os.getenv("AIRLLM_QUANTIZATION", "int4"),
            airllm_cache_dir=os.getenv("AIRLLM_CACHE_DIR", "./models"),
            chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "./data/vector_db"),
            allowed_roots=expanded or [str(Path.home() / "Documents")],
            max_file_size=int(os.getenv("MAX_FILE_SIZE", "10485760")),
            require_permissions=_bool(os.getenv("REQUIRE_PERMISSIONS"), True),
            permission_timeout=int(os.getenv("PERMISSION_TIMEOUT", "30")),
            data_dir=data_dir,
            traces_db=os.getenv("AETHER_TRACES_DB", f"{data_dir}/traces.db"),
            octoprint_url=os.getenv("OCTOPRINT_URL", "http://localhost:5000"),
            octoprint_api_key=os.getenv("OCTOPRINT_API_KEY", ""),
            moonraker_url=os.getenv("MOONRAKER_URL", "http://localhost:7125"),
            moonraker_api_key=os.getenv("MOONRAKER_API_KEY", ""),
            printer_type=os.getenv("PRINTER_TYPE", "octoprint"),
            printer_profile=os.getenv("PRINTER_PROFILE", "ender3_v3"),
            web_host=os.getenv("AETHER_WEB_HOST", "127.0.0.1"),
            web_port=int(os.getenv("AETHER_WEB_PORT", "8787")),
            persona=os.getenv("AETHER_PERSONA", "aether"),
            assistant_name=os.getenv("AETHER_ASSISTANT_NAME", "A.E.T.H.E.R."),
            user_title=os.getenv("AETHER_USER_TITLE", "sir"),
            wake_word=os.getenv("AETHER_WAKE_WORD", "aether"),
            build_dir=os.getenv("AETHER_BUILD_DIR", f"{data_dir}/builds"),
            homeassistant_url=os.getenv("HOMEASSISTANT_URL", ""),
            homeassistant_token=os.getenv("HOMEASSISTANT_TOKEN", ""),
        )


def ensure_dirs(settings: Settings) -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.airllm_cache_dir).mkdir(parents=True, exist_ok=True)
