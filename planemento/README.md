# ProjectMind MCP - Plano de Criacao

Este dossier descreve a criacao de um MCP local profissional para aumentar muito o rendimento da IA em projetos reais de software.

O objetivo e criar um servidor MCP local, executado por `stdio`, que funcione como o cerebro tecnico do projeto: le o repositorio, cria memoria persistente, entende arquitetura, recupera contexto relevante, ajuda a planear tarefas complexas e conduz debug baseado em evidencias.

## Visao

O ProjectMind MCP deve transformar a IA de um assistente que "olha ficheiros" para um colaborador que entende o projeto como sistema vivo.

Ele deve responder a perguntas como:

- Onde vive a logica principal desta feature?
- Que ficheiros podem partir se eu alterar este simbolo?
- Que decisoes tecnicas foram tomadas anteriormente?
- Que testes cobrem esta zona?
- Qual e o plano mais seguro para implementar esta mudanca?
- Que hipoteses explicam este bug e que evidencias existem?

## Ganhos esperados

- Menos tokens desperdicados em leitura repetida de ficheiros.
- Melhor recuperacao de contexto entre sessoes.
- Menos alucinacoes sobre arquitetura e decisoes antigas.
- Debug mais metodico e menos tentativa-erro.
- Planeamento mais robusto antes de grandes alteracoes.
- Melhor consistencia quando varios modelos ou agentes trabalham no mesmo projeto.

## Componentes principais

1. Indexador incremental e live (watcher + reindex_on_pull + monorepo/selectivo).
2. Grafo arquitetural com ficheiros, simbolos, chamadas, imports, rotas e testes.
3. Recuperacao hibrida de contexto com ranking por texto, simbolos, grafo, embeddings, git e importancia (scoring ponderado + modos + RAG hierarquico + cache por task).
4. Memoria persistente estruturada com provenance, confidence/last_verified, consolidacao ativa, feedback loop e memorias por branch.
5. Planeador verificado com riscos, assuncoes, criterios de sucesso e challenge automatico.
6. Motor de debug baseado em evidencias, hipoteses e testes de diagnostico.
7. Inteligencia Git para perceber alteracoes recentes, ownership e blast radius.
8. Escrita segura (propose_edit + confirm_and_apply em sandbox) e scanner de segredos/OWASP.
9. Superficie MCP completa: tools + resources (resource://) + prompts oficiais.
10. Telemetria e self-improvement do proprio MCP.
11. **Motor de reasoning estruturado** (Sequential Thinking, ReAct, Tree-of-Thoughts, Reflection, Devil's Advocate, Cognitive Forcing, score de confianca) — ver `reasoning-engine.md`.

## Stack recomendada

- Python 3.12+
- FastMCP
- Pydantic v2
- SQLite com FTS5
- tree-sitter
- NetworkX
- fastembed ou sentence-transformers
- GitPython ou dulwich
- watchfiles
- pytest
- ruff
- mypy ou pyright
- FastAPI + React (dashboard opcional)

## Design para execucao autonoma por IA

O ProjectMind nao e so um servidor de ferramentas: e um **ambiente de execucao
verificavel** onde uma IA pode planear, raciocinar, agir e rever sem saltar passos.
Para isso, todos os artefactos (planos, passos, hipoteses, criticas, diffs, aprendizagens)
sao **estado persistido** que a propria IA consulta e o MCP valida. A IA nunca "decorre"
contexto — ela lê do MCP, escreve no MCP, e o MCP bloqueia avancos invalidos.

Implicacoes de desenho:

- **Idempotencia**: toda tool pode ser chamada de novo sem efeitos laterais duplicados.
- **Checkpoints**: tarefas longas gravam progresso a cada passo (retoma após dias).
- **Gatekeeping**: `validate_plan`, `validate_step`, `critique_code_change` e
  `self_reflect` sao portoes obrigatorios; o MCP recusa avancar se o criterio falhar.
- **Auditabilidade**: cada acao gera evento de telemetria com ref e justificativa.
- **Recuperacao de contexto propria**: o MCP mantem a "verdade" (grafo + memoria); a IA
  pergunta, nao assume.
- **Falha segura**: se uma tool falha, o estado fica `blocked` com razao, nunca corrompido.

## Estrutura deste dossier

- `arquitetura.md`: arquitetura geral, modulos internos e fluxo de dados.
- `ferramentas-mcp.md`: ferramentas, resources e prompts MCP propostos e contratos de entrada/saida.
- `modelo-dados.md`: modelo de dados para SQLite, grafo, memoria e pesos de scoring.
- `reasoning-engine.md`: motor de reasoning estruturado (Sequential/ReAct/ToT/Reflection).
- `roadmap.md`: fases de desenvolvimento e criterios de sucesso.
- `workflows-ia.md`: como a IA deve usar o MCP no dia a dia.
- `riscos-e-qualidade.md`: riscos tecnicos, seguranca, testes e criterios profissionais.

