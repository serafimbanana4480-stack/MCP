# Modelo de Dados

O ProjectMind deve usar SQLite como base principal no MVP. Isto facilita instalacao local, portabilidade e backups simples.

## Tabelas principais

### `files`

```sql
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  language TEXT,
  framework TEXT,
  hash TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  last_indexed_at TEXT NOT NULL,
  git_last_commit TEXT,
  is_test INTEGER NOT NULL DEFAULT 0
);
```

### `symbols`

```sql
CREATE TABLE symbols (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  qualified_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  start_line INTEGER,
  end_line INTEGER,
  signature TEXT,
  docstring TEXT,
  complexity INTEGER,
  FOREIGN KEY(file_id) REFERENCES files(id)
);
```

### `edges`

```sql
CREATE TABLE edges (
  id INTEGER PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_id INTEGER NOT NULL,
  target_type TEXT NOT NULL,
  target_id INTEGER NOT NULL,
  relation TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  evidence TEXT
);
```

### `memories`

```sql
CREATE TABLE memories (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  confidence REAL NOT NULL,
  provenance TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  branch TEXT,                       -- ex: "feature/auth-magic-link" ou NULL (global)
  last_verified_at TEXT,             -- envelhecimento: quando foi confirmada
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### `memory_feedback`

Regista o feedback do utilizador para o ranking.

```sql
CREATE TABLE memory_feedback (
  id INTEGER PRIMARY KEY,
  context_ref TEXT NOT NULL,         -- tool/payload a que se refere
  signal TEXT NOT NULL,              -- 'up' | 'down'
  note TEXT,
  created_at TEXT NOT NULL
);
```

### `branches`

Memorias podem ser por branch/versao.

```sql
CREATE TABLE branches (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  base_branch TEXT,
  created_at TEXT NOT NULL,
  merged_at TEXT
);
```

### `task_cache`

Cache de contexto por embedding da task description.

```sql
CREATE TABLE task_cache (
  id INTEGER PRIMARY KEY,
  task_hash TEXT NOT NULL UNIQUE,    -- hash do embedding da task
  task_preview TEXT NOT NULL,
  payload_json TEXT NOT NULL,        -- pacote get_relevant_context
  token_count INTEGER NOT NULL,
  hit_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
```

### `scoring_weights`

Pesos do ranking, ajustaveis pelo feedback loop.

```sql
CREATE TABLE scoring_weights (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,         -- graph_relevance, semantic_similarity, ...
  weight REAL NOT NULL,
  updated_at TEXT NOT NULL
);
```

### `telemetry`

Registo interno para auto-melhoria.

```sql
CREATE TABLE telemetry (
  id INTEGER PRIMARY KEY,
  event TEXT NOT NULL,               -- tool_used, debug_success, tokens_saved, ...
  payload_json TEXT,
  created_at TEXT NOT NULL
);
```

### `memory_links`

```sql
CREATE TABLE memory_links (
  id INTEGER PRIMARY KEY,
  memory_id INTEGER NOT NULL,
  target_type TEXT NOT NULL,
  target_ref TEXT NOT NULL,
  relation TEXT NOT NULL,
  FOREIGN KEY(memory_id) REFERENCES memories(id)
);
```

### `plans`

```sql
CREATE TABLE plans (
  id INTEGER PRIMARY KEY,
  objective TEXT NOT NULL,
  status TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  challenge_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### `debug_sessions`

```sql
CREATE TABLE debug_sessions (
  id INTEGER PRIMARY KEY,
  symptom TEXT NOT NULL,
  status TEXT NOT NULL,
  evidence_json TEXT,
  hypotheses_json TEXT,
  confirmed_cause TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### `reasoning_sessions`

Estado do ciclo de execucao autonoma (sequential_think / react_step).

```sql
CREATE TABLE reasoning_sessions (
  id INTEGER PRIMARY KEY,
  task TEXT NOT NULL,
  mode TEXT NOT NULL,                 -- sequential | react | tot
  current_step INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,               -- active | blocked | done | failed
  state_json TEXT NOT NULL,           -- passos, acoes, observacoes
  context_ref TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### `alternatives`

Ramos do Tree-of-Thoughts avaliados.

```sql
CREATE TABLE alternatives (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL,
  branch_label TEXT NOT NULL,
  approach TEXT NOT NULL,
  score REAL NOT NULL,
  challenge_json TEXT,
  selected INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(session_id) REFERENCES reasoning_sessions(id)
);
```

### `critiques`

Críticas multi-perspetiva de output/diff.

```sql
CREATE TABLE critiques (
  id INTEGER PRIMARY KEY,
  target_ref TEXT NOT NULL,           -- plan_id | edit_id | response_ref
  perspective TEXT NOT NULL,          -- architect | security | test_engineer | performance | dx
  severity TEXT NOT NULL,             -- low | medium | high
  finding TEXT NOT NULL,
  suggestion TEXT,
  created_at TEXT NOT NULL
);
```

### `learnings`

Post-mortem automatico (record_learning).

```sql
CREATE TABLE learnings (
  id INTEGER PRIMARY KEY,
  task_ref TEXT NOT NULL,
  outcome TEXT NOT NULL,              -- success | partial | failed
  what_went_well TEXT,
  what_failed TEXT,
  lessons TEXT,
  applies_to TEXT,                    -- glob de ficheiros a que se aplica
  created_at TEXT NOT NULL
);
```

### `risk_matrix`

Matriz de risco (probabilidade x impacto) por plano.

```sql
CREATE TABLE risk_matrix (
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL,
  risk TEXT NOT NULL,
  probability REAL NOT NULL,
  impact REAL NOT NULL,
  score REAL NOT NULL,
  tier TEXT NOT NULL,                 -- low | medium | high | critical
  mitigation TEXT,
  FOREIGN KEY(plan_id) REFERENCES plans(id)
);
```

## FTS5

Criar tabelas virtuais para busca textual:

```sql
CREATE VIRTUAL TABLE files_fts USING fts5(path, content);
CREATE VIRTUAL TABLE symbols_fts USING fts5(name, qualified_name, signature, docstring);
CREATE VIRTUAL TABLE memories_fts USING fts5(title, body);
```

## Provenance

Toda memoria e inferencia importante deve ter origem explicita.

Valores sugeridos:

- `code_fact`: confirmado pelo codigo.
- `test_result`: confirmado por teste.
- `user_decision`: decidido pelo utilizador.
- `llm_inference`: inferido pela IA.
- `git_history`: deduzido por historico git.
- `external_doc`: vindo de documentacao externa.

## Confianca e envelhecimento

Usar escala `0.0` a `1.0`.

Regras:

- Facto extraido diretamente do codigo: `0.95` a `1.0`.
- Resultado de teste recente: `0.9` a `1.0`.
- Decisao explicita do utilizador: `1.0`.
- Inferencia LLM sem validacao: `0.35` a `0.7`.
- Memoria antiga sem confirmacao recente: decai com o tempo.

Envelhecimento (`memory/decay.py`): `confidence_effetiva = confidence * decay(dias_desde_last_verified)`.
Estados: `active`, `stale` (nao verificada ha muito tempo), `rejected`, `superseded`.

### Feedback loop

`memory_feedback` + `scoring_weights` permitem ao utilizador ajustar o sistema:

- thumbs up/down num pacote de contexto ajusta os pesos do ranking.
- pesos sao persistidos e revistos por `evals/self_improvement.py`.

### Memoria por branch / versao

`branches` + coluna `branch` em `memories` permitem memorias locales (ex.: "decisoes desta feature branch") que se fundem ou descartam no merge.

### Export / Import

`memory/io.py` serializa memorias (e pesos) para JSON/YAML para partilha entre equipas ou migracao de projeto.

## Pydantic models essenciais

```python
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)


class Decision(BaseModel):
    title: str
    reason: str
    alternatives: list[str] = []
    affected_files: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str
    status: str = "active"


class VerifiedPlan(BaseModel):
    objective: str
    constraints: list[str] = []
    assumptions: list[str] = []
    steps: list[str]
    dependencies: list[str] = []
    risks: list[dict] = []
    success_criteria: list[str]
    verification_steps: list[str]
    status: str = "draft"


class DebugHypothesis(BaseModel):
    title: str
    explanation: str
    evidence_for: list[Evidence] = []
    evidence_against: list[Evidence] = []
    diagnostic_test: str
    confidence: float = Field(ge=0.0, le=1.0)


class ProposedEdit(BaseModel):
    file_path: str
    diff: str
    reason: str
    risks: list[str] = []
    requires_confirmation: bool = True


class ContextMode(BaseModel):
    mode: str = Field(pattern="^(exploratory|surgical|debug)$")
    token_budget: int = Field(default=6000, gt=0)


class Feedback(BaseModel):
    context_ref: str
    signal: str = Field(pattern="^(up|down)$")
    note: str | None = None


class ScoringWeights(BaseModel):
    graph_relevance: float = Field(default=0.35, ge=0.0, le=1.0)
    semantic_similarity: float = Field(default=0.25, ge=0.0, le=1.0)
    lexical_match: float = Field(default=0.20, ge=0.0, le=1.0)
    recency_git: float = Field(default=0.10, ge=0.0, le=1.0)
    architectural_importance: float = Field(default=0.10, ge=0.0, le=1.0)


class TelemetryEvent(BaseModel):
    event: str
    payload: dict = {}
    created_at: str


class AlternativeComparison(BaseModel):
    title: str
    options: list[str]
    pros: dict[str, list[str]] = {}
    cons: dict[str, list[str]] = {}
    estimated_cost: dict[str, str] = {}
    migration_effort: dict[str, str] = {}
    recommendation: str | None = None


class RefactoringSuggestion(BaseModel):
    kind: str
    target: str
    rationale: str
    expected_impact: str
    confidence: float = Field(ge=0.0, le=1.0)


class ThoughtStep(BaseModel):
    index: int
    thought: str
    success_criteria: str
    status: str = Field(pattern="^(passed|failed|blocked|pending)$")
    confidence: float = Field(ge=0.0, le=1.0)


class ReasoningSession(BaseModel):
    task: str
    mode: str = Field(pattern="^(sequential|react|tot)$")
    steps: list[ThoughtStep] = []
    status: str = "active"


class Alternative(BaseModel):
    branch_label: str
    approach: str
    score: float = Field(ge=0.0, le=1.0)
    challenge: str = ""
    selected: bool = False


class Critique(BaseModel):
    perspective: str  # architect|security|test_engineer|performance|dx
    severity: str = Field(pattern="^(low|medium|high)$")
    finding: str
    suggestion: str | None = None


class RiskEntry(BaseModel):
    risk: str
    probability: float = Field(ge=0.0, le=1.0)
    impact: float = Field(ge=0.0, le=1.0)
    tier: str = Field(pattern="^(low|medium|high|critical)$")
    mitigation: str | None = None

    @property
    def score(self) -> float:
        return round(self.probability * self.impact, 3)


class Hypothesis(BaseModel):
    title: str
    explanation: str
    probability: float = Field(ge=0.0, le=1.0)
    test_cost: float = Field(ge=0.0, le=1.0)
    diagnostic_test: str

    @property
    def priority(self) -> float:
        return round(self.probability / max(self.test_cost, 0.01), 3)


class Learning(BaseModel):
    task_ref: str
    outcome: str = Field(pattern="^(success|partial|failed)$")
    what_went_well: list[str] = []
    what_failed: list[str] = []
    lessons: list[str] = []
    applies_to: list[str] = []


class ConfidenceScore(BaseModel):
    score: int = Field(ge=0, le=100)
    justification: str
    uncertainty_sources: list[str] = []


