"""Validated, local-first ProjectMind configuration."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from projectmind.errors import ConfigurationError


class ProjectConfig(BaseModel):
    """Human-facing project identity and language hints."""

    name: str = "project"
    languages: list[str] = Field(default_factory=list)
    monorepo: bool = False


class IndexingConfig(BaseModel):
    """Source discovery and incremental indexing settings."""

    exclude: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".projectmind",
            ".venv",
            "node_modules",
            "dist",
            "build",
            "**/*.min.js",
        ]
    )
    watch: bool = True
    reindex_on_git_pull: Literal["auto", "manual"] = "auto"
    max_file_bytes: int = Field(default=2_000_000, ge=1_024, le=100_000_000)


class ScoringWeights(BaseModel):
    """Explainable hybrid retrieval weights."""

    graph_relevance: float = Field(default=0.30, ge=0, le=1)
    semantic_similarity: float = Field(default=0.25, ge=0, le=1)
    lexical_match: float = Field(default=0.15, ge=0, le=1)
    recency_git: float = Field(default=0.10, ge=0, le=1)
    architectural_importance: float = Field(default=0.10, ge=0, le=1)
    test_coverage_bonus: float = Field(default=0.05, ge=0, le=1)
    feedback_score: float = Field(default=0.05, ge=0, le=1)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> Self:
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-8:
            raise ValueError(f"retrieval scoring weights must sum to 1.0, got {total:.8f}")
        return self


class RetrievalConfig(BaseModel):
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    cache_similarity_threshold: float = Field(default=0.92, ge=0, le=1)
    default_token_budget: int = Field(default=4_000, ge=128, le=100_000)


class MemoryConfig(BaseModel):
    default_confidence: float = Field(default=0.7, ge=0, le=1)
    half_life_days_decision: int = Field(default=180, ge=1)
    half_life_days_debug_note: int = Field(default=30, ge=1)
    consolidation_min_cluster_size: int = Field(default=3, ge=2)
    branch_scoped_by_default: bool = True


class ReasoningConfig(BaseModel):
    strict_planning_mode: bool = False
    max_react_iterations: int = Field(default=15, ge=1, le=100)
    require_post_mortem_on_task_close: bool = True
    capability_mode: Literal["deterministic", "llm_enhanced"] = "deterministic"


class SecurityConfig(BaseModel):
    sandbox_mode: Literal["subprocess", "docker"] = "subprocess"
    command_allowlist: list[str] = Field(
        default_factory=lambda: ["pytest", "npm", "yarn", "go", "cargo", "ruff", "eslint"]
    )
    network_access_in_sandbox: bool = False
    patch_ttl_seconds: int = Field(default=3_600, ge=60, le=604_800)
    max_command_output_bytes: int = Field(default=1_000_000, ge=1_024, le=50_000_000)
    docker_image: str | None = None
    docker_memory: str = "512m"
    docker_cpus: float = Field(default=1.0, ge=0.1, le=16.0)


class EmbeddingsConfig(BaseModel):
    provider: Literal["disabled", "local", "openai", "voyage"] = "disabled"
    model: str = "all-MiniLM-L6-v2"


class DashboardConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65_535)


class TelemetryConfig(BaseModel):
    enabled: bool = True
    anonymized: bool = True


class ProjectMindSettings(BaseModel):
    """Top-level settings loaded from `.projectmind/config.toml`."""

    model_config = ConfigDict(extra="forbid")

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    reasoning: ReasoningConfig = Field(default_factory=ReasoningConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

    @classmethod
    def load(cls, project_root: Path | str | None = None) -> tuple[Path, Self]:
        root = resolve_project_root(project_root)
        config_path = root / ".projectmind" / "config.toml"
        data: dict[str, object] = {}
        if config_path.exists():
            try:
                with config_path.open("rb") as handle:
                    data = tomllib.load(handle)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ConfigurationError(f"cannot read {config_path}: {exc}") from exc
        data.setdefault("project", {})
        project = data["project"]
        if isinstance(project, dict):
            project.setdefault("name", root.name or "project")
        try:
            return root, cls.model_validate(data)
        except ValueError as exc:
            raise ConfigurationError(f"invalid configuration in {config_path}: {exc}") from exc


def resolve_project_root(value: Path | str | None = None) -> Path:
    """Resolve a project root without silently depending on an MCP host's cwd."""

    candidate = value or os.environ.get("PROJECTMIND_PROJECT_ROOT") or Path.cwd()
    return Path(candidate).expanduser().resolve()


def default_config_toml(project_name: str) -> str:
    """Return the documented default configuration in TOML form."""

    return f'''[project]
name = "{project_name.replace(chr(34), "") or "project"}"
languages = []
monorepo = false

[indexing]
exclude = [".git", ".projectmind", ".venv", "node_modules", "dist", "build", "**/*.min.js"]
watch = true
reindex_on_git_pull = "auto"
max_file_bytes = 2000000

[retrieval.scoring_weights]
graph_relevance = 0.30
semantic_similarity = 0.25
lexical_match = 0.15
recency_git = 0.10
architectural_importance = 0.10
test_coverage_bonus = 0.05
feedback_score = 0.05

[memory]
default_confidence = 0.7
half_life_days_decision = 180
half_life_days_debug_note = 30
consolidation_min_cluster_size = 3
branch_scoped_by_default = true

[reasoning]
strict_planning_mode = false
max_react_iterations = 15
require_post_mortem_on_task_close = true
capability_mode = "deterministic"

[security]
sandbox_mode = "subprocess"
command_allowlist = ["pytest", "npm", "yarn", "go", "cargo", "ruff", "eslint"]
network_access_in_sandbox = false
patch_ttl_seconds = 3600
max_command_output_bytes = 1000000

[embeddings]
provider = "disabled"
model = "all-MiniLM-L6-v2"

[dashboard]
enabled = false
host = "127.0.0.1"
port = 8787

[telemetry]
enabled = true
anonymized = true
'''

