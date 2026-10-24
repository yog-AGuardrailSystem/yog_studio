# CLAUDE.md — YOG Studio

Read this whole file before doing anything in this repo.

---

## 1. Situation (why this exists)

- This is part of a **final-year B.Tech CS project** (M S Ramaiah University of Applied Sciences).
- The project is **YOG**: a deterministic policy DSL + engine that decides **ALLOW / DENY** for actions an AI agent wants to take.
- **Team of 8, two sub-teams:**
  - **Engine team** (led by Varun and Viz): the YOG compiler/engine. Python reference prototype now, C engine in progress (lexer done).
    Repo: `github.com/yog-AGuardrailSystem/yog_engine`
  - **Studio** (this repo, owned by Vasanthan): a tool that makes YOG usable by people who don't write YOG.
- **Why Studio matters for grading:** the evaluators judge mostly on what they can **see working** in a live demo. The engine alone looks like "a compiler that says yes or no." Studio turns it into a visible end-to-end product.
- **Timeline:** started 24 Oct 2026. ~12 weeks of build + buffer. Final demo ≈ late Jan / Feb 2027.
- **Developer:** one person (Vasanthan), using Claude Code. Comfortable with Python, FastAPI, React, RAG (has built a LlamaIndex + Gemini RAG app before). Also working an internship, so time is limited — **prefer simple, working solutions over clever ones.**

---

## 2. What Studio is (one sentence)

> Upload a Python AI agent or MCP server → Studio finds its tools → you write rules in plain English → an LLM drafts YOG policy → the YOG engine verifies it → you approve → Studio tests it on generated scenarios and outputs the policy plus a patched version of your agent code.

### The 5 demoable components (only claim a component once it works)

| # | Component | What the demo shows |
|---|---|---|
| 1 | **Compiler/engine** (engine team) | Policy compiles; tokens / AST / decisions visible |
| 2 | **Custom UI** | Everything below happens inside one polished app |
| 3 | **RAG + LLM translator** | English rule → retrieved example policies shown → generated YOG |
| 4 | **Agent evaluation tool** | Table of scenarios with green ALLOW / red DENY + reasons |
| 5 | **Script modifier** | Side-by-side diff: agent code before/after `yog.check()` is added |

Plus the **demo device**: a simulated smart device (lock / valve / thermostat) controlled by the agent. YOG blocking a dangerous command on screen is the headline moment.

---

## 3. Non-negotiable principles

1. **LLM drafts, engine verifies, human approves.**
   - The LLM never writes a policy that goes live without: YOG syntax+semantic check passing → plain-English readback → scenario results → explicit user **Approve** click.
   - YOG's core is deterministic. Studio must not weaken that.
2. **Never execute uploaded user code.** Analyse it statically (Python `ast`). Evaluate *policies* against scenarios, not agents.
3. **v1 input = Python only.** One framework first (see §6). Other languages only if everything else is done.
4. **Never rewrite the user's file wholesale.** Script modifier outputs a minimal **diff**.
5. **Engine is behind an adapter.** Studio must work with the Python prototype today and switch to the C engine later by changing one class.
6. **Every LLM call is replaceable.** Provider behind one interface; prompts live in files, not inline strings.
7. **Simple > clever.** No microservices, no Kubernetes, no vector DB server, no auth system.

---

## 4. Architecture

```
            ┌─────────────────────────── FRONTEND (React) ───────────────────────────┐
            │ Upload │ Tools view │ Rules chat │ Review & Approve │ Eval report │ Diff │ Device sim │
            └───────────────────────────────┬────────────────────────────────────────┘
                                            │ REST (JSON)
            ┌───────────────────────────── BACKEND (FastAPI) ─────────────────────────┐
 upload ──► │ 1 Detector      — what is this file? (MCP server / function-calling agent / unknown)
            │ 2 Extractor     — AST → list of tools {name, params, docstring, side-effect hints}
            │ 3 Retriever     — find similar example policies (the "RAG" part)
            │ 4 Translator    — LLM: English rule + tools + examples → YOG draft
            │ 5 Validator     — YOG engine parse+check; on error → feed back to Translator (max 3 tries)
            │ 6 Explainer     — YOG → plain English readback
            │ 7 Scenario gen  — tools + policy → test cases with expected ALLOW/DENY
            │ 8 Evaluator     — run scenarios through engine → report
            │ 9 Modifier      — produce diff wrapping tool calls in yog.check()
            │10 Device sim    — fake device state + agent actions gated by YOG
            └──────────────┬──────────────────────────────┬───────────────────────────┘
                           │                              │
                 EngineAdapter (YOG)              LLMProvider (Gemini/Claude/…)
                 ├ PythonPrototypeAdapter (now)
                 └ CEngineAdapter (later, via ctypes)
```

**Detector and Extractor are deterministic** (AST + pattern rules). The LLM is only used in Translator, Explainer and (optionally) Scenario gen.

---

## 5. Tech stack (defaults — change only with a reason)

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, uvicorn, pytest.
- **Frontend:** React + Vite + TypeScript + Tailwind. Monaco editor for code/YOG views. A diff viewer component for the Modifier.
- **LLM:** provider-agnostic interface. Default: Gemini (already familiar). Keys via `.env`, never committed.
- **RAG:** ~100 example `{english, yog}` pairs in `examples/policies/*.yaml`. Embed once, store in a local file, cosine similarity with numpy. **No vector DB.**
- **Engine:** `yog.py` from `yog_engine` vendored under `engine/` (pinned commit noted in `engine/VERSION`). Wrapped by `PythonPrototypeAdapter`.
- **Packaging/run:** one `make dev` (or `scripts/dev.ps1` on Windows) starts backend + frontend.

---

## 6. Scope of input support

- **Phase 1 target (pick one, default first):**
  1. **MCP Python servers** — tools are `@mcp.tool()` / `@server.tool()` decorated functions.
  2. Plain function-calling agents — functions listed in an OpenAI-style `tools=[...]` schema.
- Detector returns `{kind, confidence, evidence[]}` — evidence = the lines/decorators that triggered it. If `unknown`, the UI lets the user pick functions manually. **Never guess silently.**

---

## 7. YOG language reference (from the Python prototype — check `engine/yog.py` if unsure)

```text
fact role(alice, admin)                 # ground data
rule is_prod(R):                        # derived predicate
    environment(R, production)
allow can_delete(User, Res):            # decision: permit
    role(User, admin)
deny can_delete(User, Res):             # decision: forbid (DENY beats ALLOW)
    is_prod(Res)
    not role(User, admin)
query can_delete(alice, db1)
```

- Keywords: `fact rule allow deny query not`. Operators: `== != < > <= >=`.
- Variables start with uppercase; constants lowercase or `"quoted"`; integers allowed.
- Body = indented lines, all must hold (AND). Multiple clauses with the same head = OR.
- Conflict rule: **DENY > ALLOW > default DENY.**
- Prototype **forbids recursion** (rule cycles are a compile error).
- Runtime: `engine.check(actor, action, resource, context_facts)` — `action` is the **decision predicate name** (e.g. `can_delete`, not `delete`).

### Known engine issues (as of 24 Oct 2026) — don't "fix" them in Studio, work around and report to engine team
- `query` ignores DENY clauses (only `check()` applies DENY > ALLOW). **Studio must always use `check()`.**
- The `__main__` demo in `yog.py` passes `delete` instead of `can_delete`.
- Grammar is not formally frozen. If generated YOG starts failing after an engine update, check the grammar first.

---

## 8. Repo layout

```
yog_studio/
├── CLAUDE.md
├── README.md
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, routes only
│   │   ├── api/                    # route modules
│   │   ├── core/                   # config, logging, errors
│   │   ├── detect/                 # detector.py
│   │   ├── extract/                # ast_extractor.py
│   │   ├── rag/                    # embed.py, retriever.py
│   │   ├── translate/              # translator.py (+ retry loop)
│   │   ├── engine/                 # adapter.py, python_prototype.py, c_engine.py (later)
│   │   ├── explain/                # explainer.py
│   │   ├── evaluate/               # scenarios.py, evaluator.py
│   │   ├── modify/                 # modifier.py (diff output)
│   │   ├── device/                 # simulator.py
│   │   └── llm/                    # provider.py, gemini.py, prompts/*.md
│   └── tests/
├── engine/                         # vendored yog.py + VERSION
├── examples/
│   ├── agents/                     # sample MCP servers + agents (inputs for demo/tests)
│   └── policies/                   # english↔yog pairs for RAG + benchmark
├── benchmark/                      # eval script + results
└── frontend/
    └── src/ (pages/, components/, api/)
```

---

## 9. Data contracts (keep these stable — UI depends on them)

```python
class Tool(BaseModel):
    name: str
    params: list[Param]            # name, type_hint, default
    docstring: str | None
    source_line: int
    side_effect_hints: list[str]   # e.g. ["deletes", "network", "filesystem"] from names/calls

class DetectResult(BaseModel):
    kind: Literal["mcp_server", "function_calling_agent", "unknown"]
    confidence: float
    evidence: list[str]

class PolicyDraft(BaseModel):
    english_rules: list[str]
    yog_source: str
    retrieved_examples: list[str]  # ids, shown in UI
    attempts: int                  # validator retries used
    valid: bool
    errors: list[str]

class Scenario(BaseModel):
    actor: str; action: str; resource: str
    context: list[str]             # extra facts
    expected: Literal["ALLOW", "DENY"]
    source: Literal["generated", "user"]

class ScenarioResult(Scenario):
    actual: Literal["ALLOW", "DENY"]
    reason: str
    trace: list[str]
    passed: bool
```

---

## 10. Milestones (week = Mon–Sun, W1 starts 26 Oct 2026)

Each milestone ends with a **working demo path**, tests passing, and a merged PR.

| Week | Deliver | Done when |
|---|---|---|
| **W1** | Repo scaffold, FastAPI + React running, EngineAdapter over vendored `yog.py` | `POST /check` returns ALLOW/DENY from a sample policy; UI shows it |
| **W2** | Detector + AST Extractor for MCP Python | 5 sample agents in `examples/agents/` correctly detected; tools listed in UI with evidence |
| **W3** | 60+ English↔YOG example pairs + retriever | Query an English rule → top-3 similar examples returned and shown |
| **W4** | Translator + Validator retry loop | English rule → valid YOG in ≤3 attempts for most sample rules; errors shown if not |
| **W5** | Explainer + Review & Approve screen | Draft shows YOG, plain-English readback, Approve/Edit/Reject |
| **W6** | Scenario generator + Evaluator | Red/green report table with reasons + traces |
| **W7** | Script Modifier | Diff view: tool functions wrapped with `yog.check()`; patched file downloads |
| **W8** | Device simulator + demo agent | Agent commands a fake device; dangerous commands visibly blocked |
| **W9** | Benchmark (target 100 rules) | Script prints syntax-valid %, semantically-correct %, with/without retry loop |
| **W10** | Swap to C engine if ready (CEngineAdapter) | Same tests pass on both adapters; else stay on Python, note it |
| **W11** | UI polish, error states, loading states | Full demo runs without touching a terminal |
| **W12** | Buffer + demo rehearsal + report screenshots | Recorded backup video of the full demo |

**If behind schedule, cut in this order:** C-engine swap → second input framework → benchmark size (keep ≥30) → UI polish. **Never cut** the Review & Approve step.

---

## 11. Benchmark (the evidence slide)

- `examples/policies/` holds `{id, english, tools_context, gold_yog, scenarios}`.
- **Semantic correctness** = generated policy gives the same ALLOW/DENY as the gold policy on every scenario (not string equality).
- Report: syntax-valid %, semantically-correct %, avg retries, failure categories.
- Rules must be written by humans (team members) — **not** generated by the same LLM being tested.

---

## 12. Demo script (what the final run looks like)

1. Open Studio → upload `examples/agents/smart_home_mcp.py`.
2. Detector: "MCP server, 0.95" with evidence lines highlighted.
3. Tools appear: `unlock_door`, `set_thermostat`, `open_valve`, …
4. Type: *"The agent may never unlock the door between 11pm and 6am"* and *"Thermostat must stay between 16 and 28 degrees."*
5. Show retrieved examples → generated YOG → plain-English readback → **Approve**.
6. Evaluation table: 12 scenarios, all green.
7. Diff view: patched agent code.
8. Device simulator: agent tries to unlock at 3am → **DENY** on screen, door stays locked, reason shown.

---

## 13. How Claude Code should work in this repo

- **Plan first.** For any non-trivial task, write the plan (files to touch, approach) and wait for approval before editing.
- **Tell before acting.** No surprise file creation, deletion, installs, or git operations. Ask before each.
- **Small steps.** One milestone sub-task per branch. Branch names: `feature/<thing>`, `fix/<thing>`, `chore/<thing>`. Never commit to `main`.
- **Tests with every module.** Backend: pytest. Every bug fixed gets a regression test.
- **Don't touch `engine/`** except to update the vendored copy on request. Engine bugs → write them down in `docs/engine_issues.md` for the engine team.
- **Secrets:** never print or commit API keys. Use `.env`; keep `.env.example` updated.
- **When stuck:** say so plainly, explain why (missing info, ambiguous spec, model limits), and propose what would unblock it. Don't fake confidence.
- **Communication style:** blunt, short, bullets. If something in this plan is a bad idea, say so before building it.

---

## 14. Open decisions (resolve early)

- [ ] Repo name/location: `yog-AGuardrailSystem/yog_studio` (recommended, same org, same branch rules).
- [ ] First input framework: MCP Python (default) vs function-calling.
- [ ] LLM provider + budget (free tier limits matter for the benchmark).
- [ ] Engine pin: which `yog_engine` commit to vendor; who notifies Studio on grammar changes.
- [ ] Demo device: smart home (default) vs factory valve vs drone.
