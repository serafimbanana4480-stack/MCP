# Motor de Reasoning Estruturado (ProjectMind)

Este módulo externaliza o pensamento da IA em artefactos verificáveis (passos, hipóteses,
críticas, evidências) que o MCP valida antes de avançar. É a camada que falta entre o
"planeamento verificado" já desenhado e o comportamento de um agente de topo
(Sequential Thinking + ReAct + Tree-of-Thoughts + Reflection).

Princípio: não basta "pensar mais" — o pensamento tem de ser visível, validável e auditável.

## Superfície MCP (tools + prompts)

### `sequential_think`

Força raciocínio em passos numerados explícitos, cada um com critério de sucesso.
O MCP valida o passo atual antes de permitir o próximo.

Entrada:

```json
{
  "task": "Implementar autenticação por magic link",
  "max_steps": 8,
  "context_ref": "optional - id de get_relevant_context"
}
```

Saída (estado do loop mantido no MCP):

```json
{
  "step_index": 2,
  "thought": "Isolar o fluxo atual de login em auth/service.py",
  "success_criteria": "Função send_magic_link existe e é coberta por teste",
  "status": "passed | failed | blocked",
  "blocked_reason": "null",
  "next_step_suggested": "...",
  "confidence": 0.82
}
```

Regras:
- Cada passo tem de ser atómico e verificável.
- Estado persistido em `reasoning_sessions` (ver modelo-dados).
- `validate_step` decide se avança; se `blocked`, sugere ferramenta de apoio.

### `react_step`

Mantém o estado do loop Reason+Act: pensamento → ação (tool call) → observação → novo pensamento.

Entrada:

```json
{
  "session_id": "string",
  "thought": "Preciso de saber quem chama create_invoice",
  "previous_actions": ["impact_analysis(src/payments/service.py:create_invoice)"]
}
```

Saída:

```json
{
  "next_action_type": "tool | think | finish",
  "suggested_tool": "impact_analysis",
  "suggested_args": { "target": "src/payments/service.py:create_invoice", "depth": 2 },
  "rationale": "Observação anterior indica risco em payments; confirmar callers.",
  "loop_count": 3
}
```

### `explore_alternatives` (Tree-of-Thoughts)

Gera 3-5 caminhos paralelos, avalia cada um com `challenge_plan` e escolhe o melhor.

Entrada:

```json
{
  "task": "Como expor a API de pagamentos?",
  "num_branches": 4,
  "evaluation_axes": ["seguranca", "performance", "esforco", "migracao"]
}
```

Saída:

```json
{
  "branches": [
    { "id": "b1", "approach": "GraphQL gateway", "score": 0.71, "challenge": "..." },
    { "id": "b2", "approach": "REST + OpenAPI", "score": 0.84, "challenge": "..." }
  ],
  "selected": "b2",
  "rationale": "Menor esforço de migração e cobertura de testes existente."
}
```

### `self_reflect`

Analisa um output da IA contra o grafo, memória e riscos conhecidos; devolve críticas estruturadas.

Entrada:

```json
{
  "output_ref": "string - id do plano / diff / resposta",
  "perspectives": ["architect", "security", "test_engineer", "performance"]
}
```

Saída:

```json
{
  "critiques": [
    { "perspective": "security", "severity": "high",
      "finding": "Magic link sem expiração", "suggestion": "Adicionar TTL de 5 min" }
  ],
  "overall_score": 0.73,
  "must_fix_before_proceed": true
}
```

### `critique_code_change`

Critica um diff proposto por múltiplas perspetivas antes de `confirm_and_apply`.

Entrada:

```json
{
  "edit_id": "string",
  "perspectives": ["architect", "security", "test_engineer", "performance", "dx"]
}
```

Saída:

```json
{
  "verdict": "approve | revise | reject",
  "findings": [...],
  "suggested_tests": ["test_magic_link_expiry"]
}
```

### `record_learning` (Post-Mortem Automático)

Regista o que correu bem, o que falhou e lições, ligado à tarefa/sessão.

Entrada:

```json
{
  "task_ref": "string",
  "outcome": "success | partial | failed",
  "what_went_well": ["..."],
  "what_failed": ["..."],
  "lessons": ["..."],
  "applies_to": ["src/auth/*"]
}
```

### `risk_assessment_matrix`

Gera matriz de risco com probabilidade × impacto para cada risco de um plano.

Entrada:

```json
{ "plan_id": "string" }
```

Saída:

```json
{
  "risks": [
    { "risk": "Quebra de sessão existente", "probability": 0.4, "impact": 0.9,
      "score": 0.36, "tier": "high", "mitigation": "Feature flag + test de regressão" }
  ]
}
```

### `play_devils_advocate`

Força contra-argumentos a uma proposta para evitar viés de confirmação.

Entrada:

```json
{ "proposal": "string", "focus": ["seguranca", "manutencao"] }
```

Saída:

```json
{ "counter_arguments": ["..."], "weakest_point": "...", "resilient_if": "..." }
```

### `cognitive_force`

Obriga a IA a responder num formato rígido (premissas → alternativas → decisão justificada).

Entrada:

```json
{
  "question": "Devemos migrar para PostgreSQL?",
  "template": "premises|alternatives|decision_with_rationale"
}
```

Saída:

```json
{
  "premises": ["..."],
  "alternatives": ["..."],
  "decision": "...",
  "rationale": "..."
}
```

### `response_confidence`

Devolve score de confiança 0-100 com justificativa para uma resposta/diff/plano.

Entrada:

```json
{ "ref": "string" }
```

Saída:

```json
{ "score": 78, "justification": "...", "uncertainty_sources": ["..."] }
```

## Prompts oficiais a adicionar

- `structured_reasoning` — cadeia `sequential_think` → `explore_alternatives` (se decisão) →
  `self_reflect` → `critique_code_change` → `record_learning` no fim.
- `evidence_debug_loop` — estende o `systematic_debug` com `react_step` e
  `hypothesis_testing_loop` (prioriza por probabilidade × custo de teste).

## Integração no fluxo existente

```text
get_relevant_context(task)
  -> memory_search + find_similar_past_solutions
  -> sequential_think  OU  create_plan + hierarchical_planning
  -> explore_alternatives        (se decisão arquitetural)
  -> challenge_plan + self_reflect (multi-perspetiva)
  -> risk_assessment_matrix
  -> implementa via propose_edit -> critique_code_change -> confirm_and_apply
  -> debug com react_step + root_cause_analysis + hypothesis_testing_loop
  -> record_learning + self_reflect final + response_confidence
```

## Modelo de dados adicional (ver modelo-dados.md)

- `reasoning_sessions` (estado de sequential_think / react_step)
- `alternatives` (ramos ToT + scores)
- `critiques` (perspetivas + severity)
- `learnings` (post-mortem)
- `risk_matrix` (prob×impact por plano)

## Benefício esperado

Estas ferramentas transformam o ProjectMind de "recuperador de contexto com plano" num
"copiloto de raciocínio" que reduz alucinação, viés de confirmação e saltos para código sem
plano validado — o salto qualitativo que separa os melhores agentes dos medianos.
