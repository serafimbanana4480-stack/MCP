# Roadmap de Desenvolvimento

> Toda a entrega e orientada a execucao autonoma por IA: cada fase termina com gates
> funcionais que a propria IA respeita (validate_plan, critique_code_change, check_completion).

## Fase 0 - Foundation

Duracao estimada: 1 a 2 semanas.

Objetivo: ter um MCP funcional que ja ajude em projetos reais.

Entregaveis:

- servidor FastMCP basico
- superficie MCP inicial: tools + resources (`resource://project/summary`) + prompts (`verified_planning`)
- configuracao por ficheiro `projectmind.toml` e `.projectmind/config.toml`
- `project_scan` (modo full + incremental por scope/module)
- `project_summary`
- busca textual com `rg` ou FTS5
- memoria SQLite simples
- integracao Git basica
- **watcher basico** (watchfiles) que marca ficheiros mudados para re-indexacao
- **propose_edit / confirm_and_apply** minimos (escrita segura)
- testes unitarios iniciais

Criterio de sucesso:

- O MCP corre localmente no Cursor, Cline ou Claude Desktop.
- Consegue resumir um repositorio real.
- Consegue recuperar memorias e ficheiros relevantes.
- Re-indexa so o delta apos mudanca detetada pelo watcher.

## Fase 1 - Indexing engine

Duracao estimada: 2 a 3 semanas.

Objetivo: passar de busca textual para entendimento estrutural.

Entregaveis:

- tree-sitter multi-linguagem
- extracao de simbolos
- deteccao de frameworks
- deteccao de endpoints
- relacao codigo-teste
- indexacao incremental por hash
- **monorepo_detector** e indexacao seletiva por dir/modulo
- **reindex_on_pull** automatico apos `git pull`
- grafo base (nos File/Symbol/Endpoint/Test)

Criterio de sucesso:

- Cobertura de mais de 85% dos ficheiros principais.
- `find_symbol` encontra funcoes/classes importantes sem depender de grep cru.
- Re-indexacao num monorepo grande toca apenas nos modulos afetados.

## Fase 2 - Grafo e recuperacao hibrida

Duracao estimada: 3 a 4 semanas.

Objetivo: devolver contexto pequeno mas muito relevante.

Entregaveis:

- grafo persistido em SQLite + NetworkX in-memory
- consultas de impacto
- `trace_request_flow`
- **scoring hibrido explicito** (pesos configuraveis em `projectmind.toml`)
- **modos de retrieval** (exploratory / surgical / debug)
- **RAG hierarquico** (resumo -> chunks -> simbolos)
- token budget
- **task_cache** por embedding da task
- embeddings locais opcionais
- selecao de contexto com justificacao (scoring_breakdown)
- **find_similar_past_solutions** (raciocinio analogico sobre a memoria)

Criterio de sucesso:

- Para uma tarefa real, `get_relevant_context` devolve menos ficheiros e mais precisos do que uma busca manual.
- Cache reduz buscas repetidas em tarefas semelhantes.

## Fase 3 - Memoria profissional

Duracao estimada: 2 semanas.

Objetivo: impedir que conhecimento importante se perca entre sessoes.

Entregaveis:

- tipos de memoria
- provenance obrigatorio
- confidence score + **last_verified** + decay
- links para ficheiros, simbolos, planos e bugs
- **auto-consolidacao** com LLM
- expiracao ou revisao de memorias antigas
- **feedback loop** (thumbs up/down ajusta pesos)
- **memoria por branch/versao**
- **export/import** de memoria

Criterio de sucesso:

- Decisoes antigas voltam a aparecer quando uma tarefa toca nos ficheiros ou conceitos afetados.
- Pesos do ranking melhoram apos feedback confirmado.

## Fase 4 - Planeamento e debug verificados (gates)

Duracao estimada: 3 a 4 semanas.

Objetivo: criar processos sistematicos e bloqueaveis para tarefas complexas.

Entregaveis:

- `create_plan` / `validate_plan` (GATE) / `challenge_plan` / `check_completion` (GATE)
- `hierarchical_planning` (epicos -> historias -> tarefas)
- `create_long_running_task` (checkpoints + retoma)
- `parallel_impact_analysis`
- `compare_implementations`
- `generate_boilerplate` (respeita convencoes da memoria)
- `debug_start` / `collect_evidence` / `root_cause_analysis` / `generate_hypotheses` /
  `hypothesis_testing_loop` / `verify_fix` (GATE)
- `detect_related_bugs` / `reproduce_issue`
- `generate_tests` / `mutation_testing`
- `static_analysis` / `analyze_regression`
- `risk_assessment_matrix` (prob x impacto, tier + mitigacao)

Criterio de sucesso:

- Planos nao passam o GATE sem riscos e testes antes da implementacao.
- Debug segue evidencia -> hipotese priorizada -> causa -> fix -> GATE verify_fix.
- Fixes sao acompanhados de defesa por mutation testing.
- Um plano so e marcado `done` apos `check_completion` confirmar criterios.

## Fase 5 - Motor de reasoning estruturado

Duracao estimada: 2 a 3 semanas.

Objetivo: tornar o raciocinio da IA visivel, validavel e auditavel (o salto para agente de topo).

Entregaveis (modulo `reasoning/`):

- `sequential_think` (passos numerados + `success_criteria` + `validate_step` GATE)
- `react_step` (loop thought -> action -> observation -> thought)
- `explore_alternatives` (Tree-of-Thoughts: ramos + avaliacao + selecao)
- `self_reflect` (critica multi-perspetiva: architect/security/test/performance)
- `critique_code_change` (GATE antes de `confirm_and_apply`)
- `play_devils_advocate` (contra-argumentos)
- `cognitive_force` (formatos rigidos de resposta)
- `response_confidence` (score 0-100 + justificativa)
- `record_learning` (post-mortem automatico)
- ciclo de execucao unificado (arquitetura.md) que liga todos os gates

Criterio de sucesso:

- A IA nao consegue saltar do plano para o codigo sem passar pelos gates.
- `self_reflect` deteta pelo menos X% dos problemas de seguranca/teste antes do apply.
- `record_learning` alimenta `find_similar_past_solutions` em tarefas retomadas.
- Uma sessao interrompida retoma do ultimo checkpoint sem perder estado.

## Fase 6 - Produto local serio

Duracao estimada: 2 a 3 semanas.

Objetivo: tornar o MCP robusto para uso diario.

Entregaveis:

- watcher incremental + reindex_on_pull
- **CLI admin** (`projectmind status/index/memory/graph/docs/telemetry`)
- relatorios de saude do projeto
- **dashboard web** opcional (FastAPI + React): grafo, memoria, historico
- **export de diagramas** (Mermaid/PlantUML/DOT)
- **composicao com outros MCPs** (GitHub, Filesystem, Terminal, Browser, Supabase)
- **scoring avancado**: centrality, smells, suggest_refactoring, simulate_change (what-if)
- **security & compliance scanner** (segredos, OWASP)
- **documentacao viva** (update_docs: README, API docs, ADR)
- **self-improvement** do proprio MCP via telemetria
- evaluation harness
- documentacao de instalacao
- exemplos para Cursor, Cline e Claude Desktop
- politica de backup para memoria local

Criterio de sucesso:

- O MCP fica confiavel o suficiente para ser usado em todos os projetos importantes.
- Telemetria mostra reducao de tokens e melhoria de taxa de sucesso de planos/debug.
- A taxa de planos bloqueados por `validate_plan` cai apos algumas iteracoes (aprendizagem).

