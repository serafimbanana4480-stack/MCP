# Ferramentas MCP Propostas

Este ficheiro define as primitivas expostas pelo servidor MCP: **tools**, **resources** e **prompts**.

## Resources (contexto estatico, sem tool call)

- `resource://project/summary` — visao curta do projeto (linguagens, frameworks, entrypoints, riscos).
- `resource://graph/export` — grafo em JSON/Mermaid para leitura rapida.
- `resource://memory/digest` — digest de memorias ativas e decisoes recentes.

## Prompts (templates oficiais de disciplina)

- `systematic_debug` — debug_start -> collect_evidence -> generate_hypotheses -> verify_fix.
- `verified_planning` — create_plan -> validate_plan -> challenge_plan -> check_completion.

## Project intelligence

### `project_scan`

Executa ou atualiza a indexacao do projeto.

Entrada:

```json
{
  "root": "string",
  "mode": "full | incremental",
  "scope": "string | null",
  "module": "string | null",
  "include_tests": true,
  "reindex_on_pull": true
}
```

Saida:

```json
{
  "files_indexed": 1200,
  "symbols_indexed": 8400,
  "frameworks": ["react", "fastapi"],
  "duration_ms": 4200,
  "warnings": []
}
```

### `project_summary`

Produz uma visao curta do projeto.

Deve incluir:

- linguagens
- frameworks
- modulos principais
- entrypoints
- arquitetura provavel
- comandos de teste conhecidos
- riscos encontrados

### `find_symbol`

Pesquisa classes, funcoes, metodos, endpoints e componentes.

Entrada:

```json
{
  "query": "string",
  "kind": "any | class | function | method | endpoint | component",
  "limit": 20
}
```

### `get_file_overview`

Devolve resumo estrutural de um ficheiro sem enviar o ficheiro inteiro.

Inclui:

- imports
- exports
- simbolos principais
- chamadas relevantes
- testes relacionados
- decisoes ou problemas ligados ao ficheiro

## Recuperacao de contexto

### `get_relevant_context`

A ferramenta mais importante do sistema.

Entrada:

```json
{
  "task": "Implementar autentificacao por magic link",
  "token_budget": 6000,
  "mode": "exploratory | surgical | debug",
  "include_memory": true,
  "include_tests": true,
  "include_git": true
}
```

Saida:

```json
{
  "briefing": "Resumo compacto para a IA.",
  "files": [
    {
      "path": "src/auth/service.py",
      "reason": "Contem fluxo atual de autenticacao.",
      "relevance": 0.94,
      "scoring_breakdown": {
        "graph_relevance": 0.9,
        "semantic_similarity": 0.8,
        "lexical_match": 0.7,
        "recency_git": 0.5,
        "architectural_importance": 0.95
      }
    }
  ],
  "symbols": [],
  "memories": [],
  "tests": [],
  "risks": [],
  "next_steps": []
}
```

## Grafo e impacto

### `impact_analysis`

Analisa o raio de impacto de alterar um ficheiro ou simbolo.

Entrada:

```json
{
  "target": "src/payments/service.py:create_invoice",
  "depth": 3,
  "include_tests": true
}
```

Saida deve incluir:

- callers
- callees
- imports afetados
- testes provaveis
- riscos
- modulos dependentes

### `trace_request_flow`

Segue uma rota, comando ou evento pelo sistema.

Exemplo:

```json
{
  "entrypoint": "POST /api/invoices",
  "max_depth": 6
}
```

### `critical_files`

Devolve os ficheiros mais criticos por PageRank / grau de chamadas.

### `detect_smells`

Deteta ciclos de dependencia, god classes e tight coupling.

### `suggest_refactoring`

Emite sugestoes acionaveis (ex.: extrair service, mover logica para domain) com `rationale` e `expected_impact`.

### `simulate_change` (what-if)

Aplica a alteracao num grafo em memoria e devolve o novo blast radius antes de tocar no codigo.

```json
{
  "target": "src/payments/service.py:create_invoice",
  "change_type": "rename | delete | signature_change",
  "proposed_signature": "optional string"
}
```

### `export_diagram`

Exporta o grafo em Mermaid / PlantUML / DOT.

## Memoria persistente

### `memory_search`

Pesquisa memoria por tipo, confianca e provenance.

Tipos:

- semantic
- episodic
- decision
- problem
- task
- preference

### `record_decision`

Regista uma decisao tecnica.

Entrada:

```json
{
  "title": "Usar SQLite no MVP",
  "reason": "Evita dependencia externa e simplifica instalacao local.",
  "alternatives": ["Qdrant", "Postgres"],
  "affected_files": ["src/projectmind/memory/store.py"],
  "confidence": 0.9,
  "provenance": "user_decision"
}
```

### `record_attempt`

Regista uma tentativa, resultado e evidencia.

Util para debug e tarefas longas.

### `consolidate_memory`

Resume memorias antigas (auto-consolidacao com LLM), remove duplicados e promove factos confirmados. Pode rodar periodicamente ou sob demanda.

### `memory_feedback`

Regista thumbs up/down do utilizador a um pacote de contexto; ajusta os pesos do ranking.

```json
{ "context_ref": "string", "signal": "up | down", "note": "optional" }
```

### `set_branch_memory`

Associa memorias a uma branch/versao (ex.: "decisoes desta feature branch").

### `export_memory` / `import_memory`

Serializa/restaura memorias (e pesos) em JSON/YAML para equipas ou migracao.

## Escrita segura (proposta + confirmacao)

### `propose_edit`

Devolve um diff/patch proposo **sem** aplicar. Todas as ferramentas de escrita passam por aqui primeiro.

Entrada:

```json
{
  "file_path": "src/auth/service.py",
  "new_content": "optional",
  "diff": "optional unified diff"
}
```

Saida:

```json
{
  "edit_id": "string",
  "diff": "unified diff",
  "reason": "string",
  "risks": ["string"],
  "requires_confirmation": true
}
```

### `confirm_and_apply`

Aplica o `edit_id` apos confirmacao explicita do utilizador. Corre em sandbox quando aplicavel e regista o resultado na telemetria.

### `run_in_sandbox`

Executa testes/comandos num subprocess restrito (container leve opcional), com timeout e working directory fixo.

## Planeamento

### `create_plan`

Cria um plano estruturado para uma tarefa (modelo `VerifiedPlan`).

### `hierarchical_planning`

Divide uma tarefa grande em hierarquia ePICOS -> historias -> tarefas tecnicas,
com dependencias e criterio de conclusao por nivel. Entrada `{ "objective": "string", "depth": 3 }`.
Saida: `{ "epics": [ { "title": "string", "stories": [ { "title": "string", "tasks": [ { "title": "string", "done_when": "string" } ] } ] } ] }`

### `validate_plan`

Gate obrigatorio. Verifica se o plano tem:

- objetivo claro
- assuncoes explicitas
- dependencias
- riscos (com mitigation)
- estrategia de testes
- criterio de conclusao

Devolve `{ "valid": true|false, "missing": [], "warnings": [] }`. Se `valid=false`, o
ciclo de execucao fica `blocked` ate corrigir.

### `challenge_plan`

Ataca o plano por perspetivas diferentes (usa internamente `self_reflect`):

- compatibilidade retroativa
- seguranca
- migracoes
- performance
- testes
- UX ou DX
- modos de falha

Devolve `{ "challenges": [], "must_fix": true|false }`.

### `check_completion`

Gate final. Confirma se os criterios de conclusao foram alcancados (com base em testes,
grafo e memorias). Entrada `{ "plan_id": "string" }`.
Saida: `{ "complete": true|false, "unmet_criteria": [], "evidence": [] }`.

### `create_long_running_task`

Cria tarefa com checkpoints e permite retomar depois de dias; guarda progresso em memoria.
Checkpoint automatico a cada `propose_edit` e a cada passo de `sequential_think`.

### `parallel_impact_analysis`

Analisa varias mudancas em simultaneo (uti para refatoracoes largas).

### `compare_implementations`

Compara alternativas (ex.: Redis vs PostgreSQL sessions) com pros, contras, custo estimado e esforco de migracao.

```json
{
  "title": "Session store",
  "options": ["redis", "postgres"],
  "context": "optional string"
}
```

### `generate_boilerplate`

Gera scaffolding respeitando decisoes e convencoes guardadas na memoria (ex.: "cria endpoint seguindo o padrao do projeto"). Devolve proposta via `propose_edit`.

## Debug

### `debug_start`

Abre uma sessao de debug.

Entrada:

```json
{
  "symptom": "Teste falha com timeout ao criar invoice",
  "stacktrace": "optional string",
  "recent_changes": true
}
```

### `collect_evidence`

Recolhe stacktrace, logs, testes relacionados, alteracoes recentes e grafo de impacto.

### `root_cause_analysis`

Combina stacktrace + grafo + memoria de bugs semelhantes e devolve causa mais provavel
com cadeia de evidencias. Entrada `{ "debug_session_id": "string" }`.
Saida: `{ "likely_cause": "string", "evidence_chain": [], "confidence": 0.8 }`.

### `generate_hypotheses`

Cria hipoteses com `evidence_for`, `evidence_against`, `diagnostic_test` e `confidence`.

### `hypothesis_testing_loop`

Gera hipoteses, prioriza por `probabilidade * (1/custo_de_teste)`, e executa
sequencialmente ate encontrar a causa. Entrada `{ "debug_session_id": "string" }`.
Saida: `{ "ordered_hypotheses": [ { "title": "string", "priority": 0.7, "test": "string" } ], "confirmed": "string|null" }`.

### `verify_fix`

Gate final de debug. Confirma que a correcao resolve o problema e nao quebra regressao conhecida.
Devolve `{ "fixed": true|false, "regression_risk": "low|medium|high", "evidence": [] }`.

### `detect_related_bugs`

Procura padroes semelhantes na memoria e no codigo (reutiliza aprendizagens passadas).

### `reproduce_issue`

Tenta montar um teste minimo de reproducao com base no sintoma e stacktrace.

### `generate_tests` / `mutation_testing`

Gera testes a partir do grafo de cobertura e aplica mutation testing para medir eficacia.

### `static_analysis`

Corre ESLint / Ruff / SonarQube via subprocess e devolve achados ligados ao grafo.

### `analyze_regression`

Executa analise de regressao automatica apos um fix.

## Qualidade e vivacidade

### `scan_secrets`

Procura segredos e padroes inseguros (OWASP top 10 comuns) no diff ou no repo.

### `update_docs`

Mantem README, API docs e ADR (Architecture Decision Records) atualizados com base no grafo e memorias.

### `self_improve`

Analisa logs de uso e sugere melhorias no ranking ou novas ferramentas (telemetria interna).

## CLI administrativa

Comandos fora do MCP para o humano operar:

```text
projectmind status
projectmind index [--scope=src/auth] [--module=payments]
projectmind memory search "auth"
projectmind memory consolidate
projectmind graph impact LoginService
projectmind graph export --format=mermaid
projectmind docs update
projectmind telemetry report
```

## Motor de reasoning estruturado

Ferramentas do modulo `reasoning/` (contratos completos em `reasoning-engine.md`).
O MCP usa estas ferramentas como **gates** no ciclo de execucao.

### `sequential_think`

Forca raciocinio em passos numerados; cada passo tem `success_criteria` e `status`.
O MCP valida o passo antes de avancar (`gate: validate_step`).

Entrada:

```json
{ "task": "string", "max_steps": 8, "context_ref": "optional" }
```

Saida:

```json
{
  "session_id": "string",
  "step_index": 2,
  "thought": "string",
  "success_criteria": "string",
  "status": "passed | failed | blocked",
  "blocked_rereason": "null",
  "next_step_suggested": "string",
  "confidence": 0.82
}
```

### `react_step`

Mantem o loop Reason+Act. Devolve a proxima acao sugerida com base nas observacoes.

Entrada:

```json
{ "session_id": "string", "thought": "string", "previous_actions": ["string"] }
```

Saida:

```json
{
  "next_action_type": "tool | think | finish",
  "suggested_tool": "impact_analysis",
  "suggested_args": { "target": "src/payments/service.py:create_invoice", "depth": 2 },
  "rationale": "string",
  "loop_count": 3
}
```

### `explore_alternatives`

Tree-of-Thoughts: gera 3-5 caminhos, avalia com `challenge_plan`, escolhe o melhor.

Entrada:

```json
{ "task": "string", "num_branches": 4, "evaluation_axes": ["seguranca", "performance", "esforco", "migracao"] }
```

Saida:

```json
{
  "branches": [
    { "id": "b1", "approach": "GraphQL gateway", "score": 0.71, "challenge": "string" },
    { "id": "b2", "approach": "REST + OpenAPI", "score": 0.84, "challenge": "string" }
  ],
  "selected": "b2",
  "rationale": "string"
}
```

### `self_reflect`

Critica um output (plano/diff/resposta) contra grafo, memoria e riscos.

Entrada:

```json
{ "output_ref": "string", "perspectives": ["architect", "security", "test_engineer", "performance"] }
```

Saida:

```json
{
  "critiques": [
    { "perspective": "security", "severity": "high", "finding": "string", "suggestion": "string" }
  ],
  "overall_score": 0.73,
  "must_fix_before_proceed": true
}
```

### `critique_code_change`

Critica um diff proposto por multiplas perspetivas antes de `confirm_and_apply`.

Entrada:

```json
{ "edit_id": "string", "perspectives": ["architect", "security", "test_engineer", "performance", "dx"] }
```

Saida:

```json
{ "verdict": "approve | revise | reject", "findings": [], "suggested_tests": ["test_x"] }
```

### `risk_assessment_matrix`

Matriz risco = probabilidade x impacto, com tier e mitigacao por risco.

Entrada: `{ "plan_id": "string" }`
Saida: `{ "risks": [ { "risk": "string", "probability": 0.4, "impact": 0.9, "score": 0.36, "tier": "high", "mitigation": "string" } ] }`

### `play_devils_advocate`

Contra-argumentos a uma proposta. Entrada `{ "proposal": "string", "focus": [] }`.
Saida: `{ "counter_arguments": [], "weakest_point": "string", "resilient_if": "string" }`

### `cognitive_force`

Forca formato rigido de resposta. Entrada `{ "question": "string", "template": "premises|alternatives|decision_with_rationale" }`.
Saida: `{ "premises": [], "alternatives": [], "decision": "string", "rationale": "string" }`

### `response_confidence`

Score 0-100 com justificativa. Entrada `{ "ref": "string" }`.
Saida: `{ "score": 78, "justification": "string", "uncertainty_sources": [] }`

### `record_learning`

Post-mortem automatico. Entrada:

```json
{
  "task_ref": "string",
  "outcome": "success | partial | failed",
  "what_went_well": [], "what_failed": [], "lessons": [], "applies_to": []
}
```

### `find_similar_past_solutions`

Raciocinio analogico: procura na memoria casos semelhantes (task embedding) e devolve
o que funcionou / falhou antes. Entrada `{ "task": "string", "kind": "any | bug | plan" }`.
Saida: `{ "matches": [ { "memory_ref": "string", "similarity": 0.8, "outcome": "string", "takeaway": "string" } ] }`

### `validate_step`

Gate interno: recebe o resultado de um passo e decide `passed|failed|blocked`.
Usado por `sequential_think` e `react_step`. Nao e exposto como tool primaria, mas sim
como funcao de controlo invocada pelo ciclo de execucao.

## Composicao com outros MCPs

O ProjectMind pode compor-se com:
- **GitHub MCP**: PRs, issues, reviews ligados a `github_bridge`.
- **Filesystem / Terminal**: leitura e execucao em sandbox.
- **Browser**: documentacao externa (`external_doc` provenance).
- **Supabase / DB MCP**: relacoes `READS_TABLE` / `WRITES_TABLE` reais.


