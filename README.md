# ProjectMind MCP

Servidor MCP local via `stdio` para indexar um repositório, recuperar contexto, preservar memória e conduzir alterações através de gates verificáveis.

## Instalação em menos de 5 minutos

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e ".[dev]"
projectmind index --scope=.
```

O servidor usa SQLite local em `.projectmind/projectmind.sqlite3`. Não envia código para serviços externos e só aplica alterações depois de `propose_edit` → `critique_code_change` aprovado → `confirm_and_apply`.

## Configuração MCP

Cursor/Cline:

```json
{
  "mcpServers": {
    "projectmind": {
      "command": "projectmind",
      "args": ["serve", "--root", "C:/caminho/do/projeto"]
    }
  }
}
```

Claude Desktop usa o mesmo bloco em `claude_desktop_config.json`. Também é possível executar `python -m projectmind.server --root .`.

## Fluxo recomendado

`project_scan` → `get_relevant_context` → `create_plan` → `validate_plan` → `challenge_plan`/`self_reflect` → `propose_edit` → `critique_code_change` → `confirm_and_apply` → `run_in_sandbox` → `check_completion` → `record_learning`.

## Segurança

Comandos fora da allowlist, caminhos fora da raiz, padrões de segredo/OWASP e aplicações sem crítica aprovada são recusados. Todas as transições ficam em `telemetry`.

