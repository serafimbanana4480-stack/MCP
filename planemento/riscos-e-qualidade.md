# Riscos, Qualidade e Criterios Profissionais

## Riscos tecnicos

### Indexacao lenta

Mitigacao:

- indexacao incremental por hash
- exclusoes agressivas
- cache por commit git
- processamento por lotes
- **watcher + reindex_on_pull** (so o delta)
- **monorepo_detector** + indexacao seletiva por modulo

### Grafo impreciso

Mitigacao:

- confidence por edge
- distinguir facto de inferencia
- mostrar evidencia
- `simulate_change` (what-if) valida blast radius antes de escrever
- permitir reindexacao seletiva

### Memoria com lixo

Mitigacao:

- provenance obrigatorio
- confidence decay + `last_verified`
- consolidacao periodica (auto-consolidacao LLM)
- estados: active, stale, rejected, superseded
- feedback loop corrige peso do ranking

### Contexto demasiado grande

Mitigacao:

- token budget obrigatorio
- ranking hibrido com pesos configuraveis
- **modos** (exploratory / surgical / debug)
- **RAG hierarquico**: resumo -> chunks -> simbolos
- sumarizacao estrutural
- snippets pequenos com razao de inclusao
- **task_cache** evita buscas repetidas

### Execucao insegura de comandos

Mitigacao:

- separar ferramentas read-only de ferramentas que executam comandos
- allowlist de comandos
- dry-run quando possivel
- logs de execucao
- timeout e working directory fixo
- **sandbox** (subprocess restrito ou container leve) para testes/comandos

### Escrita nao autorizada de ficheiros

Mitigacao:

- todas as ferramentas de escrita devolvem diff via `propose_edit` primeiro
- `confirm_and_apply` exige confirmacao explicita do utilizador
- `secrets_guard` bloqueia segredos/padroes inseguros (OWASP) antes de propor
- diffs sao auditados e registados em telemetria

### Execucao autonoma sem gates (a IA "saltar" passos)

A IA pode tentar implementar sem plano validado ou aplicar diff sem critica.

Mitigacao:

- o ciclo de execucao do MCP e a unica via de avanco: `validate_plan`, `critique_code_change`
  e `check_completion` sao gates que recusam se o criterio falhar.
- `confirm_and_apply` recusa diffs que nao passaram por `critique_code_change`.
- `check_completion` recusa marcar plano `done` se `unmet_criteria` nao vazios.
- audit log em `telemetria` de cada transicao de estado (quem/porque).

### Viés de confirmacao / alucinacao no raciocinio

Mitigacao:

- `play_devils_advocate` e `self_reflect` (multi-perspetiva) forcam contra-argumentos.
- `explore_alternatives` (ToT) obriga a considerar caminhos nao trivialmente favoritos.
- `response_confidence` expoe incerteza em vez de falsa certeza.
- `record_learning` + `find_similar_past_solutions` reutilizam falhas reais.

### Sessao interrompida / perda de estado

Mitigacao:

- `reasoning_sessions` e `create_long_running_task` gravam checkpoint a cada passo/edit.
- ao retomar, a IA recebe estado + aprendizagens da area (bloqueio seguro, nunca corrompido).

### Feedback loop a piorar o ranking

Mitigacao:

- `memory_feedback` ajusta pesos, mas `evals/self_improvement.py` revê e pode reverter
  se a taxa de sucesso de planos/debug cair.

## Qualidade de engenharia

Requisitos minimos:

- testes unitarios para modelos, ranking, memoria e grafo
- testes de integracao com repositorios fixture
- snapshots para saidas MCP importantes
- `ruff check`
- `ruff format`
- type checking
- documentacao de instalacao
- exemplos reais

## Evaluation harness

Criar cenarios de avaliacao:

1. Encontrar onde implementar uma feature.
2. Analisar impacto de alterar uma funcao central.
3. Recuperar uma decisao antiga.
4. Diagnosticar bug com stacktrace.
5. Criar plano de migracao.
6. Identificar testes relevantes.
7. Propor refactoring e validar via what-if.
8. Detectar segredo/OWASP num diff proposto.
9. **Execucao autonoma**: a IA corre o ciclo completo (context->plan->gate->act->verify->learn)
   num repositorio fixture e o harness verifica que nenhum gate foi saltado.
10. **Recusa de atalho**: o harness tenta forcar `confirm_and_apply` sem `critique_code_change`
    e valida que o MCP recusa.
11. **Retoma**: interromper a sessao a meio e validar que retoma do ultimo checkpoint.

Metricas:

- precision@k de ficheiros recuperados
- recall de simbolos importantes
- tokens usados e **tokens poupados** vs busca manual
- tempo de resposta
- taxa de hipoteses de debug confirmadas
- numero de passos ate fix correto
- **taxa de sucesso de planos** (validados + concluidos via `check_completion`)
- **taxa de planos bloqueados por gate** que depois passam apos correcao (sinal de aprendizagem)
- hit rate do `task_cache`
- eficacia do mutation testing (mutants killed)
- melhoria dos pesos apos feedback loop
- **taxa de falsos positivos de `self_reflect`** (criticas irrelevantes)

### Self-improvement

`evals/self_improvement.py` analisa a tabela `telemetry` e:

- sugere reponderacao do ranking com base no que ajudou
- propoe novas ferramentas ou recursos subutilizados
- deteta ferramentas com baixa taxa de sucesso
- revê ajustes de `memory_feedback` que pioraram a taxa de sucesso

## Criterio de pronto para uso diario

O ProjectMind esta pronto quando:

- instala em menos de 5 minutos num projeto novo
- indexa incrementalmente (watcher + reindex_on_pull) sem atrapalhar o trabalho
- recupera contexto melhor que busca manual em tarefas reais (modos + RAG hierarquico)
- consegue explicar porque incluiu cada ficheiro (scoring_breakdown)
- preserva decisoes importantes entre sessoes (e por branch)
- ajuda debug com evidencias e nao apenas opinioes
- escreve apenas via `propose_edit` + `critique_code_change` + `confirm_and_apply`, em sandbox
- bloqueia segredos/OWASP antes de propor diffs
- **a IA nao consegue saltar gates** (validate_plan / check_completion / critique) em testes de harness
- **sessoes interrompidas retomam do checkpoint** sem perda de estado
- **self_reflect deteta problemas de seguranca/teste antes do apply** numa fracao medida dos casos
- tem testes suficientes para evoluir sem medo
- melhora com o tempo via feedback loop e self-improvement

