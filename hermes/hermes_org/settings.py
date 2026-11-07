"""환경변수 기반 설정. .env(hermes/.env)가 있으면 먼저 읽는다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

HERMES_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = HERMES_DIR.parent
BACKLOG_DIR = HERMES_DIR / "backlog"
WORKSPACE_DIR = HERMES_DIR / "workspace"
ORG_CONFIG = HERMES_DIR / "config" / "org.yaml"


def load_dotenv(path: Path = HERMES_DIR / ".env") -> None:
    """의존성 없이 KEY=VALUE 형식의 .env를 os.environ에 주입(기존 값 우선)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Settings:
    provider: str = "ollama"
    model: str = "hermes3:8b"
    base_url: str = "http://localhost:11434"
    api_key: str = "NA"
    temperature: float = 0.2
    max_iterations: int = 2
    shell_timeout: int = 600
    repo_root: Path = field(default_factory=lambda: REPO_ROOT)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
        provider = os.environ.get("HERMES_LLM_PROVIDER", "ollama").lower()
        base_url = os.environ.get("HERMES_BASE_URL", "")
        if not base_url and provider == "ollama":
            # ollama CLI와 같은 서버를 쓰도록 OLLAMA_HOST(host:port)를 존중한다
            ollama_host = os.environ.get("OLLAMA_HOST", "localhost:11434")
            base_url = ollama_host if "://" in ollama_host else f"http://{ollama_host}"
        return cls(
            provider=provider,
            model=os.environ.get("HERMES_MODEL", "hermes3:8b"),
            base_url=(base_url or "http://localhost:11434").rstrip("/"),
            api_key=os.environ.get("HERMES_API_KEY", "NA"),
            temperature=float(os.environ.get("HERMES_TEMPERATURE", "0.2")),
            max_iterations=int(os.environ.get("HERMES_MAX_ITERATIONS", "2")),
            shell_timeout=int(os.environ.get("HERMES_SHELL_TIMEOUT", "600")),
        )

    @property
    def litellm_model(self) -> str:
        """CrewAI(LiteLLM) 모델 식별자."""
        if self.provider == "ollama":
            return f"ollama/{self.model}"
        return f"openai/{self.model}"

    @property
    def openai_compatible_base(self) -> str:
        """OpenAI 호환 /v1 엔드포인트 주소."""
        if self.provider == "ollama":
            return f"{self.base_url}/v1"
        return self.base_url
