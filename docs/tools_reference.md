# ProjectMind MCP — Tool Reference

Auto-generated from `54` registered tools.

## Catalog

| Tool | Title | Read-only | Destructive |
|------|-------|-----------|-------------|
| `compare_implementations` | Compare implementations | True | False |
| `confidence_score` | Confidence score | True | False |
| `confirm_and_apply` | Confirm and apply a reviewed edit | False | True |
| `consolidate_memory` | Consolidate memory | False | False |
| `create_long_running_task` | Create long running task | False | False |
| `critique_code_change` | Critique code change | True | False |
| `critique_plan` | Critique plan | True | False |
| `detect_code_smells` | Detect code smells | True | False |
| `detect_dependency_cycles` | Detect dependency cycles | True | False |
| `detect_related_bugs` | Detect related bugs | True | False |
| `explore_alternatives` | Explore alternatives | True | False |
| `export_diagram` | Export diagram | True | False |
| `export_memory` | Export memory | True | False |
| `feedback_thumbs_down` | Memory feedback down | False | False |
| `feedback_thumbs_up` | Memory feedback up | False | False |
| `find_critical_files` | Find critical files | True | False |
| `find_similar_past_solutions` | Find similar past solutions | True | False |
| `generate_boilerplate` | Generate boilerplate | True | False |
| `get_capabilities` | Get ProjectMind capabilities | True | False |
| `get_graph_summary` | Get graph summary | True | False |
| `get_relevant_context` | Get relevant context | True | False |
| `get_usage_stats` | Get local usage statistics | True | False |
| `hierarchical_planning` | Hierarchical planning | False | False |
| `impact_analysis` | Impact analysis | True | False |
| `import_memory` | Import memory | False | False |
| `index_scope` | Index a scope | False | False |
| `memory_search` | Search memory | True | False |
| `parallel_impact_analysis` | Parallel impact analysis | True | False |
| `ping` | Ping ProjectMind | True | False |
| `play_devils_advocate` | Play devil's advocate | True | False |
| `propose_edit` | Propose a source edit | False | False |
| `react_step` | ReAct step | False | False |
| `record_decision` | Record decision | False | False |
| `record_learning` | Record learning | False | False |
| `regression_analysis` | Regression analysis | False | True |
| `reindex_on_git_pull` | Reindex after git pull | False | False |
| `reproduce_issue` | Reproduce issue | True | False |
| `resume_task` | Resume long running task | False | False |
| `risk_assessment_matrix` | Risk assessment matrix | True | False |
| `root_cause_analysis` | Root cause analysis | True | False |
| `run_command_sandboxed` | Run a restricted project command | False | True |
| `run_linters` | Run linters | False | True |
| `run_mutation_testing` | Run mutation testing | False | True |
| `scan_owasp` | Scan OWASP-oriented patterns | True | False |
| `scan_secrets` | Scan for secrets | True | False |
| `self_improvement_report` | Generate self-improvement report | True | False |
| `self_reflect` | Self reflect | True | False |
| `sequential_think` | Sequential think | False | False |
| `simulate_change` | Simulate a change | True | False |
| `status` | Get project status | True | False |
| `suggest_refactoring` | Suggest refactoring | True | False |
| `update_docs` | Update docs | True | False |
| `validate_step` | Validate plan step | False | False |
| `verify_memory` | Verify memory | False | False |

## Details

### `compare_implementations` — Compare implementations

Compare two implementation options without inventing a winner.

```python
compare_implementations(option_a: str, option_b: str, criteria: list[str], evidence_a: dict[str, str] | None = ..., evidence_b: dict[str, str] | None = ...)
```

### `confidence_score` — Confidence score

Score how well a response is grounded in the supplied context.

```python
confidence_score(response: str)
```

### `confirm_and_apply` — Confirm and apply a reviewed edit

Apply exactly one unchanged, unexpired proposal after explicit confirmation.

```python
confirm_and_apply(patch_id: str, proposal_digest: str, confirm: bool = ...)
```

### `consolidate_memory` — Consolidate memory

Cluster and consolidate overlapping local memory entries.

```python
consolidate_memory(min_cluster_size: int | None = ..., memory_type: str | None = ..., branch: str | None = ...)
```

### `create_long_running_task` — Create long running task

Create a durable long-running task with an attached plan.

```python
create_long_running_task(spec: str, max_steps: int = ...)
```

### `critique_code_change` — Critique code change

Critique a unified diff against explicit, deterministic criteria.

```python
critique_code_change(diff: str)
```

### `critique_plan` — Critique plan

Critique a persisted sequential plan.

```python
critique_plan(plan_id: str)
```

### `detect_code_smells` — Detect code smells

Heuristically flag god classes, shotgun surgery, and similar smells.

```python
detect_code_smells(scope: str = ..., god_class_loc: int = ..., god_class_methods: int = ..., god_class_fan_out: int = ..., shotgun_min_changes: int = ...)
```

### `detect_dependency_cycles` — Detect dependency cycles

List canonical dependency cycles in the local graph.

```python
detect_dependency_cycles(scope: str = ...)
```

### `detect_related_bugs` — Detect related bugs

Retrieve related historical bugs from local memory.

```python
detect_related_bugs(description: str, limit: int = ...)
```

### `explore_alternatives` — Explore alternatives

Return 3-5 challenged implementation alternatives ranked by score.

```python
explore_alternatives(task: str, num_branches: int = ...)
```

### `export_diagram` — Export diagram

Render the local graph as Mermaid, PlantUML, or Graphviz DOT.

```python
export_diagram(scope: str = ..., format: str = ...)
```

### `export_memory` — Export memory

Export validated local memory to a JSON file below the project root.

```python
export_memory(path: str)
```

### `feedback_thumbs_down` — Memory feedback down

Record negative feedback for a memory entry.

```python
feedback_thumbs_down(memory_id: str)
```

### `feedback_thumbs_up` — Memory feedback up

Record positive feedback for a memory entry.

```python
feedback_thumbs_up(memory_id: str)
```

### `find_critical_files` — Find critical files

Rank files by dependency centrality within the local graph.

```python
find_critical_files(top_n: int = ..., scope: str = ...)
```

### `find_similar_past_solutions` — Find similar past solutions

Retrieve analogical past solutions from local memory.

```python
find_similar_past_solutions(task_description: str, branch: str | None = ..., limit: int = ...)
```

### `generate_boilerplate` — Generate boilerplate

Return review-only boilerplate descriptions for a pattern.

```python
generate_boilerplate(pattern: str, convention_limit: int = ...)
```

### `get_capabilities` — Get ProjectMind capabilities

Describe deterministic and optional capabilities without side effects.

```python
get_capabilities()
```

### `get_graph_summary` — Get graph summary

Return file/node/edge counts and language breakdown for a scope.

```python
get_graph_summary(scope: str = ...)
```

### `get_relevant_context` — Get relevant context

Assemble explainable, token-budgeted context for a task.

```python
get_relevant_context(task: str, mode: str = ..., token_budget: int = ..., include_memory: bool = ..., depth: int = ..., branch: str | None = ...)
```

### `get_usage_stats` — Get local usage statistics

Aggregate local, anonymised tool telemetry.

```python
get_usage_stats()
```

### `hierarchical_planning` — Hierarchical planning

Decompose a goal into a hierarchical plan with checkpoints.

```python
hierarchical_planning(goal: str)
```

### `impact_analysis` — Impact analysis

Estimate the blast radius of changing a node or a unified diff.

```python
impact_analysis(node_id_or_diff: str)
```

### `import_memory` — Import memory

Import a previously exported memory JSON file.

```python
import_memory(path: str, conflict: str = ...)
```

### `index_scope` — Index a scope

Discover and persist source symbols for a path into the local graph.

```python
index_scope(path: str = ...)
```

### `memory_search` — Search memory

Lexically search local memory with branch, age, and feedback ranking.

```python
memory_search(query: str, memory_type: str | None = ..., min_confidence: float = ..., branch: str | None = ..., include_global: bool = ..., tags: list[str] | None = ..., limit: int = ...)
```

### `parallel_impact_analysis` — Parallel impact analysis

Run impact analysis for several changes in one call.

```python
parallel_impact_analysis(changes: list[str])
```

### `ping` — Ping ProjectMind

Validate the MCP handshake, database, and selected project root.

```python
ping()
```

### `play_devils_advocate` — Play devil's advocate

Surface counter-arguments and risks for a proposal.

```python
play_devils_advocate(proposal: str)
```

### `propose_edit` — Propose a source edit

Store a reviewable source edit without changing the target file.

```python
propose_edit(target: str, patch: str, patch_format: str = ...)
```

### `react_step` — ReAct step

Advance a persisted ReAct loop with one observable thought/action.

```python
react_step(task_id: str, current_thought: str, previous_actions: list[dict[str, object]] | None = ...)
```

### `record_decision` — Record decision

Persist a durable engineering decision to local memory.

```python
record_decision(content: str, tags: list[str] | None = ..., related_node_ids: list[str] | None = ..., branch: str | None = ..., confidence: float | None = ...)
```

### `record_learning` — Record learning

Persist a post-incident learning to local memory.

```python
record_learning(outcome: str, what_went_well: str = ..., what_failed: str = ..., lessons: str = ..., tags: list[str] | None = ..., related_node_ids: list[str] | None = ..., branch: str | None = ..., confidence: float | None = ...)
```

### `regression_analysis` — Regression analysis

Plan and run regression tests affected by a fix diff.

```python
regression_analysis(fix_diff: str, confirm: bool = ...)
```

### `reindex_on_git_pull` — Reindex after git pull

Reindex only the files changed by the most recent git pull.

```python
reindex_on_git_pull(old_head: str | None = ..., new_head: str = ...)
```

### `reproduce_issue` — Reproduce issue

Generate a review-only regression reproduction proposal.

```python
reproduce_issue(description: str, error: str)
```

### `resume_task` — Resume long running task

Restore durable state and mark a paused long-running task active.

```python
resume_task(task_id: str)
```

### `risk_assessment_matrix` — Risk assessment matrix

Produce hypothesis-labeled delivery risks for a plan.

```python
risk_assessment_matrix(plan_id: str)
```

### `root_cause_analysis` — Root cause analysis

Rank evidence-based root-cause candidates for an error trace.

```python
root_cause_analysis(error: str)
```

### `run_command_sandboxed` — Run a restricted project command

Run allowlisted argv without a shell; subprocess mode is restricted, not a full sandbox.

```python
run_command_sandboxed(command: list[str], confirm: bool = ..., cwd: str = ..., timeout_seconds: float = ...)
```

### `run_linters` — Run linters

Run an allowlisted linter and normalise its diagnostics.

```python
run_linters(scope: str = ..., tool: str | None = ..., confirm: bool = ...)
```

### `run_mutation_testing` — Run mutation testing

Run the project's mutation-testing adapter over a scope.

```python
run_mutation_testing(scope: str, confirm: bool = ...)
```

### `scan_owasp` — Scan OWASP-oriented patterns

Run deterministic local insecure-pattern rules over supported source files.

```python
scan_owasp(scope: str = ...)
```

### `scan_secrets` — Scan for secrets

Scan local text for redacted credential indicators without network access.

```python
scan_secrets(scope: str = ...)
```

### `self_improvement_report` — Generate self-improvement report

Suggest evidence-based improvements; never apply them automatically.

```python
self_improvement_report()
```

### `self_reflect` — Self reflect

Critique an output against explicit, deterministic criteria.

```python
self_reflect(output: str)
```

### `sequential_think` — Sequential think

Persist a bounded, visible execution checklist for a task.

```python
sequential_think(task: str, max_steps: int = ...)
```

### `simulate_change` — Simulate a change

Disk-free blast-radius simulation over an in-memory graph copy.

```python
simulate_change(proposed_change: str, scope: str = ...)
```

### `status` — Get project status

Return local index, memory, plan, patch, and telemetry counts.

```python
status()
```

### `suggest_refactoring` — Suggest refactoring

Return ranked refactoring actions for a graph node.

```python
suggest_refactoring(node_id: str)
```

### `update_docs` — Update docs

Propose documentation patches from the live graph (never writes).

```python
update_docs(scope: str = ..., dry_run: bool = ...)
```

### `validate_step` — Validate plan step

Record externally supplied evidence for a sequential plan step.

```python
validate_step(step_id: str, evidence: str, succeeded: bool = ...)
```

### `verify_memory` — Verify memory

Mark a memory entry as verified, restoring its initial confidence.

```python
verify_memory(memory_id: str)
```
