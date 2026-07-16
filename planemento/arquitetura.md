# Arquitetura do ProjectMind MCP

## Principio central

O servidor nao deve ser apenas uma camada de busca. Deve ser uma camada de entendimento persistente do projeto.

O modelo mental e:

```text
Repositorio local
  -> watcher (watchfiles + git hooks)
  -> scanner incremental (mudanca + dependentes via grafo)
  -> parser estrutural (tree-sitter + framework detector)
  -> grafo arquitetural (SQLite + NetworkX in-memory)
  -> memoria estruturada (provenance + confidence + consolidacao ativa)
  -> recuperador hibrido (scoring ponderado + token budget + cache por task)
  -> ferramentas / resources / prompts MCP para a IA
  -> telemetria interna (o que ajudou, taxa de sucesso, reducao de tokens)
```

## Superficie MCP (para alem de tools)

O servidor expoe tres tipos de primitivas MCP para maximizar rendimento:

- **Tools**: acoes que a IA invoca (recuperacao, planeamento, debug, escrita proposta).
- **Resources** (`resource://`): contexto estatico que a IA pode ler sob demanda sem tool call.
  - `resource://project/summary` — visao curta do projeto.
  - `resource://graph/export` — grafo arquitetural em formato leve (JSON/Mermaid).
  - `resource://memory/digest` — digest das memorias ativas e decisoes recentes.
- **Prompts**: templates oficiais que forçam disciplina.
  - `systematic_debug` — cadeia debug_start -> collect_evidence -> generate_hypotheses -> verify_fix.
  - `verified_planning` — cadeia create_plan -> validate_plan -> challenge_plan -> check_completion.

## Modulos internos

```text
projectmind-mcp/
  src/projectmind/
    server.py
    core/
      config.py             # projectmind.toml por projeto + .projectmind/config.toml
      models.py
      security.py
      exceptions.py
      secrets_guard.py      # deteta segredos/OWASP antes de escrever ou enviar
    indexing/
      scanner.py
      monorepo_detector.py  # deteta multiplos package.json/pyproject.toml
      tree_sitter_indexer.py
      symbol_extractor.py
      framework_detector.py
      incremental.py        # indexacao seletiva por dir/modulo
      watcher.py            # watchfiles + git hooks -> eventos de mudanca
      git_diff_indexer.py   # re-indexa so o que mudou + dependentes
      reindex_on_pull.py    # re-indexa automaticamente apos git pull
    graph/
      builder.py
      store.py
      queries.py
      impact.py
      centrality.py         # PageRank/grau -> ficheiros mais criticos
      smells.py             # ciclos de dependencia, god classes, coupling
      refactoring_advisor.py# sugestoes (extrair service, mover p/ domain)
      whatif.py             # simulacao de mudancas antes de implementar
    retrieval/
      hybrid_retriever.py
      context_selector.py
      ranking.py            # scoring ponderado e configuravel (feedback loop)
      token_budget.py
      task_cache.py         # cache por embedding da task description
      summarizer.py         # resumo hierarquico de ficheiros grandes
      rag_hierarchical.py   # resumos de ficheiro -> chunks -> simbolos
      modes.py              # exploratory | surgical | debug
    memory/
      store.py
      types.py
      consolidator.py       # consolida memorias episodicas (auto-consolidacao LLM)
      provenance.py
      decay.py              # envelhecimento de confidence
      feedback.py           # thumbs up/down ajusta pesos do ranking
      branch_memory.py      # memorias por branch/versao (ex: feature branch)
      io.py                 # export/import de memoria (equipas/migracao)
    planning/
      planner.py
      validator.py
      challenger.py
      completion.py
      long_running.py       # checkpoints + retoma de tarefas longas
      compare.py            # compare_implementations (pros/contras/custo/migracao)
      scaffolder.py         # generate_boilerplate respeitando convencoes
    debugging/
      engine.py
      stacktrace_parser.py
      evidence.py
      hypothesis_tester.py
      related_bugs.py       # procura padroes semelhantes em memoria+codigo
      test_gen.py           # geracao/mutation testing via grafo de cobertura
      reproduce.py          # monta teste minimo de reproducao
      regression.py         # analise de regressao automatica apos fix
      static_analysis.py    # ESLint/Ruff/SonarQube via subprocess
    git/
      intelligence.py       # blame por simbolo, mudancas desde ultima tag
      diff_parser.py
      ownership.py
      github_bridge.py      # PRs/issues se ligado ao GitHub MCP
    integrations/
      mcp_composer.py       # compoe com GitHub/Filesystem/Terminal/Browser/Supabase
      dashboard.py          # FastAPI + React simples (grafo, memoria, historico)
      diagram_exporter.py   # Mermaid / PlantUML / DOT a partir do grafo
    docs/
      living_docs.py        # update_docs: README, API docs, ADR atualizados
    reasoning/
      sequential.py         # sequential_think: passos numerados + criterio de sucesso
      react.py              # react_step: estado thought->action->observation->thought
      tree_of_thoughts.py   # explore_alternatives: ramos + avaliacao + selecao
      reflection.py         # self_reflect + critique_code_change (multi-perspetiva)
      devils_advocate.py    # play_devils_advocate: contra-argumentos
      cognitive_force.py    # cognitive_force: formatos rigidos de resposta
      confidence.py         # response_confidence: score 0-100 + justificativa
      risk_matrix.py        # risk_assessment_matrix: prob x impacto
      learning.py           # record_learning: post-mortem automatico
      gates.py              # portoes obrigatorios (validate_step, must_fix, approve)
    evals/
      scenarios.py
      metrics.py
      reports.py
      self_improvement.py   # analisa logs e sugere melhorias de ranking/tools
    telemetry/
      recorder.py           # tokens poupados, sucesso de planos, uso de tools
      llm_router.py         # sugere "Claude p/ arquitetura, Grok p/ debug"
```

## Fluxo de indexacao

### Batch (inicial / sob demanda)

1. Descobrir ficheiros do projeto.
2. `monorepo_detector.py` identifica sub-projetos (multiplos `package.json`, `pyproject.toml`, etc.) para indexacao por modulo.
3. Aplicar regras de exclusao: `.git`, `node_modules`, caches, builds, ambientes virtuais.
4. Detetar linguagem e framework.
5. Extrair simbolos, imports, exports, endpoints, testes e dependencias.
6. Guardar metadados em SQLite.
7. Atualizar grafo.
8. Gerar embeddings locais apenas para blocos relevantes.
9. Marcar timestamp, hash de conteudo e commit git.

### Live / incremental (watcher)

1. `watcher.py` deteta eventos de mudanca via `watchfiles` (e/ou git hooks).
2. `git_diff_indexer.py` calcula o diff inteligente (git diff) e isola os ficheiros mudados.
3. Re-indexa apenas ficheiros mudados + ficheiros dependentes (via grafo, relacoes IMPORTS / CALLS / CHANGED_WITH).
4. Atualiza embeddings e grafo em delta, sem re-ler o repositorio inteiro.
5. Marca na memoria os "hot files" (alterados recentemente) para sinais de recency.
6. `reindex_on_pull.py` re-indexa o delta automaticamente apos `git pull` (configuravel).

Suporta indexacao seletiva: `project_scan(scope="src/auth")` ou `project_scan(module="payments")`.

Isto mantem o indice sempre fresco mesmo em desenvolvimento ativo e evita re-indexacao lenta de projetos grandes.

## Fluxo de recuperacao

Quando a IA pede contexto, o MCP deve combinar sinais:

- match textual via FTS5
- match por simbolo
- proximidade no grafo
- ficheiros alterados recentemente (hot files)
- ficheiros com bugs conhecidos
- decisoes anteriores relacionadas
- testes ligados ao codigo
- importancia arquitetural (entrypoints, hubs de chamadas, cobertura de testes, complexidade ciclomatica)
- limite de tokens pedido

### Scoring hibrido (ponderado e configuravel)

A selecao de contexto depende do ranking. A formula deve ser explicita e configuravel em `projectmind.toml`:

```text
score_final = 0.35 * graph_relevance
           + 0.25 * semantic_similarity
           + 0.20 * lexical_match
           + 0.10 * recency_git
           + 0.10 * architectural_importance
```

Sinais adicionais que alimentam estes termos:

- `graph_relevance`: centralidade no grafo, callers/callees, proximidade ao alvo.
- `semantic_similarity`: embeddings locais da task vs. bloco de codigo.
- `lexical_match`: FTS5 / BM25 sobre simbolos e conteudo.
- `recency_git`: ficheiros alterados recentemente, mudancas desde ultima tag/release.
- `architectural_importance`: entrypoints, nós de alto grau, cobertura de testes, complexidade ciclomatica, decisoes ligadas.

**Feedback loop**: o utilizador pode dar thumbs up/down ao pacote devolvido. `memory/feedback.py` regista o sinal e ajusta os pesos do ranking (ex.: subir `semantic_similarity` se o utilizador validar respostas semanticas). Os pesos sao persistidos e revistos periodicamente.

### Modos de recuperacao

`get_relevant_context` aceita `mode`:

- `exploratory`: alargado — bao para descoberta inicial e brainstorming.
- `surgical`: muito focado no alvo — para alteracoes pequenas e precisas.
- `debug`: enviesado para evidencias, testes, logs e bugs passados.

### RAG hierarquico

`rag_hierarchical.py` devolve contexto em piramide: resumo do ficheiro -> chunks relevantes -> simbolos exatos, permitindo drill-down sem estourar o token budget.

### Caching e orçamento de tokens

- `task_cache.py` guarda resultados de `get_relevant_context` por embedding da task description; tarefas semelhantes reutilizam o pacote.
- `summarizer.py` faz resumo hierarquico de ficheiros grandes: primeiro `summary`, depois chunks relevantes sob demanda.
- `token_budget.py` garante que o pacote nunca ultrapassa o `token_budget` pedido, cortando por score.

O resultado nao deve ser um dump enorme. Deve ser um pacote compacto:

```json
{
  "summary": "Resumo curto do contexto recuperado.",
  "files": [],
  "symbols": [],
  "memories": [],
  "risks": [],
  "scoring_breakdown": [],
  "suggested_next_tools": []
}
```

## Grafo arquitetural

Tipos de nos:

- Project
- Directory
- File
- Symbol
- Function
- Class
- Method
- Endpoint
- DatabaseTable
- Test
- ExternalDependency
- Decision
- Problem

Tipos de relacoes:

- CONTAINS
- IMPORTS
- EXPORTS
- CALLS
- INHERITS
- IMPLEMENTS
- API_ROUTE
- READS_TABLE
- WRITES_TABLE
- TEST_COVERS
- CHANGED_WITH
- DECISION_AFFECTS
- PROBLEM_AFFECTS

### Analise avancada

Alem da navegacao, o grafo alimenta analise qualitativa:

- `centrality.py`: PageRank / grau de entrada para identificar os **ficheiros mais criticos** (hubs de chamadas). Usado por `architectural_importance` no scoring e por `impact_analysis`.
- `smells.py`: deteta **ciclos de dependencia**, god classes, tight coupling e outros code smells arquiteturais.
- `refactoring_advisor.py`: emite sugestoes acionaveis (ex.: extrair service, mover logica para domain, quebrar ciclo).
- `whatif.py`: **simulacao de mudancas** ("what-if") — aplica a alteracao num grafo em memoria e mostra o novo blast radius antes de tocar no codigo.

## Ciclo de execucao autonoma (a "spine" do agente)

O MCP nao e passivo: expoe um **ciclo de controlo** que a IA segue e que o MCP fiscaliza.
Cada transicao de estado passa por um `gate` que pode bloquear o avanco.

```text
[CONTEXT]  get_relevant_context + memory_search + find_similar_past_solutions
    |
[PLAN]     create_plan / sequential_think / explore_alternatives
    |-- GATE validate_plan  (objetivo, assuncao, risco, teste, conclusao) -> else blocked
    |-- GATE challenge_plan + self_reflect(multi-perspetiva) -> must_fix? -> blocked
    |-- GATE risk_assessment_matrix (tier alto sem mitigacao -> blocked)
    |
[ACT]      propose_edit (diff) -> critique_code_change -> GATE approve/reject
    |                                    |
    |                              GATE confirm_and_apply (humano ou politica)
    |-- run_in_sandbox (testes)
    |
[VERIFY]   verify_fix / check_completion -> GATE conclusao alcancada? -> else loop
    |
[LEARN]    record_learning + self_reflect final + response_confidence
```

Propriedades:
- **Estado unico**: `reasoning_sessions` guarda o passo atual, acoes e observacoes.
- **Bloqueio explicito**: um `gate` que falha devolve `blocked` + `blocked_reason` +
  `suggested_tool` (ex.: "corre impact_analysis primeiro").
- **Sem atalhos**: o MCP recusa `confirm_and_apply` se o diff nao passou por
  `critique_code_change`, e recusa marcar plano como `done` se `check_completion` falhar.
- **Retry com memoria**: ao retomar, a IA recebe o estado e as aprendizagens da area.

## Politica de seguranca local

O MCP deve ser local-first e seguro por defeito:

- Nunca enviar codigo para servicos externos sem configuracao explicita.
- Permitir embeddings locais por defeito.
- Bloquear comandos destrutivos por defeito.
- Registar comandos executados e resultados de diagnostico.
- Separar leitura de projeto, escrita de memoria e execucao de comandos.
- `secrets_guard.py`: deteta segredos e padroes inseguros (OWASP top 10 comuns) antes de escrever ficheiros ou propor diffs.
- Execucao de testes/comandos em **sandbox** (subprocess restrito ou container leve) com timeout e working directory fixo.
- Ferramentas de escrita devolvem diff proposto (`propose_edit`); a aplicacao real exige `confirm_and_apply` com confirmacao explicita do utilizador.
- **Silent mode**: tools que nao aparecem no chat mas alimentam o contexto automaticamente (ex.: enriquecer `get_relevant_context` em background).

