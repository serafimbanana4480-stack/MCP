# Workflows para a IA

O MCP so aumenta rendimento se a IA o usar de forma disciplinada. Este ficheiro define regras praticas para clientes como Cursor, Cline, Claude Desktop ou Codex.

## Regra geral

Para qualquer tarefa nao trivial, a IA deve consultar o ProjectMind antes de alterar codigo.

Tarefas nao triviais incluem:

- features medias ou grandes
- refatoracoes
- bugs reais
- alteracoes em autenticacao, pagamentos, permissoes ou dados
- migracoes
- alteracoes com impacto em varios modulos
- tarefas retomadas depois de varios dias

## Contrato de execucao autonoma (obrigatorio)

A IA NAO executa em "modo livre". Ela segue o ciclo de execucao do MCP e respeita os gates.
Regras duras:

1. **Nunca escrevas ficheiros diretamente.** Toda escrita passa por `propose_edit`.
2. **Nunca apliques um diff sem `critique_code_change`->approve e `confirm_and_apply`.**
3. **Nunca marques plano como concluido sem `check_completion`->complete.**
4. **Nunca saltes `validate_plan`, `challenge_plan` ou `self_reflect` numa tarefa nao trivial.**
5. **Se um gate devolver `blocked`, para e segue a `suggested_tool`.** Nao contornes.
6. **Consulta `find_similar_past_solutions` e `record_learning` em tarefas retomadas.**
7. **Corre testes em `run_in_sandbox`, nunca no ambiente do utilizador.**
8. **Cada passo de `sequential_think` tem de ter `success_criteria` verificavel.**

Estas regras devem ir para as system instructions do cliente (Cursor/Cline/Claude Desktop).

## Workflow de feature

1. `get_relevant_context` (modo `exploratory` para discovery, `surgical` para implementacao).
2. `memory_search` + `find_similar_past_solutions` para decisoes/problemas relacionados.
3. `create_plan` ou `sequential_think` (passos com `success_criteria`). Para tarefas grandes,
   `hierarchical_planning` (epicos -> historias -> tarefas).
4. **GATE** `validate_plan` -> se `valid=false`, corrige os `missing` e repete.
5. **GATE** `challenge_plan` + `self_reflect(perspectives=[architect,security,test_engineer])`;
   se `must_fix`, resolve antes de avancar.
6. **GATE** `risk_assessment_matrix`; riscos `tier>=high` sem `mitigation` bloqueiam.
7. `explore_alternatives` se houver decisao arquitetural; regista com `record_decision`.
8. Para tarefas longas: `create_long_running_task` com checkpoints.
9. Implementar em passos pequenos: `propose_edit` -> **GATE** `critique_code_change` (approve)
   -> `confirm_and_apply` (nunca escrever direto).
10. `impact_analysis` nos ficheiros alterados; para multiplas mudancas `parallel_impact_analysis`.
11. `run_in_sandbox` com testes relevantes; se falhar, `react_step` orienta o proximo passo.
12. **GATE** `check_completion` -> se `complete=false`, itera sobre `unmet_criteria`.
13. `record_decision` para decisoes importantes; `set_branch_memory` se afeta feature branch.
14. `record_learning` + `self_reflect` final + `response_confidence`; `memory_feedback` ao contexto.

## Workflow de debug

1. `debug_start` com sintoma e stacktrace.
2. `collect_evidence` (stacktrace, logs, testes, alteracoes recentes, grafo).
3. `root_cause_analysis` devolve causa provavel + cadeia de evidencias.
4. `generate_hypotheses` + `hypothesis_testing_loop` (ordena por prioridade =
   probabilidade / custo_de_teste) ate confirmar causa.
5. Escolher a hipotese mais testavel; `reproduce_issue` ou teste de diagnostico.
6. `detect_related_bugs` para reutilizar aprendizagens passadas.
7. Confirmar causa.
8. Fix minimo via `propose_edit` -> **GATE** `critique_code_change` -> `confirm_and_apply`.
9. `static_analysis` (Ruff/ESLint) + `analyze_regression`.
10. **GATE** `verify_fix` -> se `fixed=false` ou `regression_risk=high`, volta ao passo 4.
11. `mutation_testing` para validar a defesa; `record_learning` com causa e tentativas.

## Workflow de refatoracao

1. `find_symbol` ou `get_relevant_context`.
2. `impact_analysis` com profundidade 2 ou 3.
3. `detect_smells` e `critical_files` para priorizar.
4. `suggest_refactoring` para opcoes acionaveis.
5. `simulate_change` (what-if) para prever blast radius.
6. `play_devils_advocate` sobre a abordagem de refatoracao (evita viés de confirmacao).
7. `hierarchical_planning` de passos reversiveis; **GATE** `validate_plan`.
8. Validar compatibilidade publica com `challenge_plan`.
9. Alterar um limite arquitetural de cada vez via `propose_edit` + `critique_code_change`.
10. `run_in_sandbox` testes por modulo; **GATE** `check_completion`.
11. `record_decision` se a arquitetura mudar; `record_learning` no fim.

## Workflow de comparacao de alternativas

1. `explore_alternatives` (ToT) com `evaluation_axes` ou `compare_implementations`.
2. `find_similar_past_solutions` + `memory_search` por decisoes semelhantes.
3. `play_devils_advocate` sobre a opcao favorita.
4. `record_decision` com escolha e alternativas rejeitadas (provenance, confidence).
5. `risk_assessment_matrix` sobre a implementacao escolhida.

## Regras para prompt do cliente

Adicionar algo deste genero nas regras do cliente:

```text
Para tarefas nao triviais, usa sempre o ProjectMind MCP antes de escrever codigo.
Comeca por get_relevant_context (modo exploratory) ou project_summary.
Antes de grandes alteracoes, corre o ciclo: create_plan/hierarchical_planning
  -> validate_plan (GATE) -> challenge_plan + self_reflect (GATE) -> risk_assessment_matrix (GATE).
Em cada passo de implementacao: propose_edit -> critique_code_change (GATE) -> confirm_and_apply.
Nunca saltes gates: se receberes "blocked", segue a suggested_tool.
Em debug: debug_start -> collect_evidence -> root_cause_analysis -> hypothesis_testing_loop -> verify_fix (GATE).
Usa sequential_think para passos com sucesso verificavel; react_step para loops acao-observacao.
Regista decisoes com record_decision e aprendizagens com record_learning.
Nunca escrevas ficheiros diretamente; corre testes em sandbox.
Nao assumas arquitetura se o MCP conseguir verificar no codigo.
Usa memory_feedback e response_confidence para calibrar a tua confianca.
```

## Como medir melhoria

Indicadores:

- menos ficheiros lidos manualmente pela IA
- menos ciclos de tentativa-erro
- menos bugs de regressao
- decisoes anteriores recuperadas automaticamente
- planos com riscos explicitos
- tempo menor ate primeira implementacao correta
- menor uso de tokens em tarefas grandes

