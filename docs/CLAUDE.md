# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"헤이,짜비(Hey Zzabi)" — a groupware app where a PM records a meeting, and a Django backend calls a chain of
OpenAI-backed Python functions (`ai/`) to turn that meeting into: structured plan document → requirement
definitions → generated tasks → recommended assignees → a scheduled task plan. The PM reviews/approves each
stage. There is no multi-agent framework in play — "agent" here means a single Python module with an `agent.py`
entry point that the Django service layer calls directly and sequentially.

Monorepo layout: `backend/` (Django REST API), `ai/` (LLM pipeline, imported as a plain Python package by
Django — not a separate service), `frontend/` (Next.js). `infra/` and `data/` are empty placeholders
(`.gitkeep` only) — no IaC or Docker files exist in this repo despite the AWS/Docker/Nginx badges in the root
README; deployment there is manual/undocumented in-repo.

**Don't trust the root `README.md` for tech stack** — it advertises Vite/React/Qdrant/Neo4j; the frontend is
actually Next.js (App Router) and there is no Qdrant/Neo4j code anywhere. `backend/backend_readme.md` is a
much more reliable, code-derived doc (last scanned 2026-09-18) — read it for the fuller data model/endpoint
picture, but verify anything time-sensitive against current code (some things it describes, e.g. the
`SpecValidationReport`/`RequirementValidationReport` "AI 품질감사" feature and `plan_review`/`requirement_review`
agents, and the duplicate `tasks/ai/*` endpoints, have since been deleted — see "Known dead ends" below).

## Commands

### Backend (Django) — run from `backend/`
```bash
uv venv .venv --python=3.13          # or python -m venv .venv
.venv\Scripts\activate               # Windows; source .venv/bin/activate on WSL/Linux
uv pip install -r requirements.txt   # or pip install -r requirements.txt
copy .env.example .env               # fill SECRET_KEY, OPENAI_API_KEY at minimum
python manage.py migrate
python manage.py runserver           # http://localhost:8000
```
- Tests: `python manage.py test` (Django `SimpleTestCase`/`TestCase`; `pytest`/`pytest-django` are also
  installed but there is no `pytest.ini`/`conftest.py`, so plain `pytest` from `backend/` is unverified — prefer
  `manage.py test`, optionally with an app label, e.g. `python manage.py test tasks.test_scheduler`).
- Seed common codes (department/role/skill/etc enums) from `backend/DB_front_back.xlsx`: `python manage.py seed_codes`
  (must run before `seed_demo` — it depends on these codes existing).
- Seed demo users: `python manage.py seed_demo` (`--count N`, `--password`, `--reset`; idempotent).
- Regenerate the DB spec Excel from current models: `python manage.py export_db_spec [--output path]`.
- No `MYSQL_HOST` in `.env` → falls back to local `db.sqlite3` automatically (see `config/settings.py`); set
  `MYSQL_HOST`/`MYSQL_DB`/`MYSQL_USER`/`MYSQL_PASSWORD`/`MYSQL_PORT` to use the team's MySQL/RDS instead.
- No lint/format command is configured for the backend (no flake8/black/ruff config found).

### AI pipeline (`ai/`) — run from `ai/`, same venv as backend (Django adds `ai/` to `sys.path`)
```bash
python -m pytest tests/ -v            # ~30 unit tests, no live LLM calls, no API key needed
python -m shared.retry_config         # prints the currently active model/token/retry config
python run_pipeline.py                # exercises the real pipeline against sample_meeting.txt (LLM calls, needs OPENAI_API_KEY)
python run_pipeline.py --plan-only path/to/transcript.txt
```
- Model is chosen entirely via `.env` (`OPENAI_MODEL`, optionally `OPENAI_STRONG_MODEL`/`OPENAI_FAST_MODEL`,
  `OPENAI_MAX_TOKENS`, `OPENAI_REASONING_EFFORT`) — never hardcode a model name in agent code; add a new
  `MODEL_PROFILES` entry in `ai/shared/retry_config.py` if a new model family needs different call semantics
  (temperature vs. reasoning_effort vs. token param name).
- `ai/` has its own `.env` and its own `requirements.txt` (smaller, curated: instructor/openai/pydantic/langsmith/
  pytest) — this is the accurate dependency list for the AI layer; `backend/requirements.txt` and root
  `requirements.txt` are broad `pip freeze`-style snapshots that include unused packages (see below).

### Frontend (Next.js) — run from `frontend/`
```bash
npm install
npm run dev      # next dev, http://localhost:3000
npm run build     # next build
npm run start     # next start
npm run lint      # eslint (eslint-config-next)
npm run test      # vitest run
npm run test:watch
```
- Single test file: `npx vitest run src/lib/documentPipeline.test.ts`.
- On WSL: verify `which npm` resolves to a Linux-native Node (via nvm), not `/mnt/c/...` — a Windows npm binary
  under WSL causes native module/path breakage (see `작업환경설정.md`).

## Architecture

### Request flow
Browser → Next.js route handler proxy (`frontend/src/app/api/[...path]/route.ts`, forwards to `BACKEND_ORIGIN`,
same-origin so auth cookies aren't treated as third-party) → Django DRF view → app's `services.py` → sequential
calls into `ai/<module>/agent.py` functions → deterministic Python post-processing → DB write → JSON response
(or, for slow pipelines, a job row that the frontend polls).

Auth: JWT access/refresh tokens in **HttpOnly cookies** (not `Authorization` headers, not localStorage) —
`users/authentication.py` (`CookieJWTAuthentication`) reads them; `frontend/src/lib/api/client.ts`'s `apiFetch`
sends `credentials: "include"` plus an `X-CSRFToken` header on non-GET requests, and transparently refreshes
the access token once on a 401 (shared in-flight promise so concurrent 401s don't fire duplicate refreshes).
Authorization is **not** based on the `role_code` CommonCode field despite it existing on `User` — PM-only
endpoints check Django's built-in `is_staff` flag and/or membership in the `PM` group (`users/permissions.py`:
`IsPMUser`, `IsOwnerOrPM`). Treat `role_code` as a display-only field unless you first verify it's been wired
into permissions.

### Long-running AI pipelines: threads + Job model + polling, not Celery
Despite `celery`, `redis`, `langchain`, and `langgraph` all being pinned in `requirements.txt` / `backend/requirements.txt`,
**none of them are actually wired up** — there is no Celery app, no worker process, no broker config, no
LangGraph `StateGraph` in the codebase (a `ai/graph.py` LangGraph experiment existed but was dead/unreachable
code and has been deleted). Model code comments state this explicitly (`tasks/models.py`, `requirements/models.py`):
"Celery/Redis 워커 인프라가 아직 이 프로젝트에 없다." Do not assume a task queue exists.

The actual pattern for any pipeline step that takes more than a few seconds (meeting analysis, requirement
extraction, task generation/assignment):
1. `POST .../analyze/` (or `/extract/`, `/generate-tasks/`) creates a `*Job` row (`MeetingAnalysisJob`,
   `RequirementExtractionJob`, `TaskGenerationJob` — status `PENDING`/`RUNNING`/`SUCCESS`/`ERROR` + a free-text
   `stage` field) and starts a **daemon `threading.Thread`** running the actual pipeline call, then returns
   `202` with `job_id` immediately.
2. The thread function calls `close_old_connections()` on entry/exit (each thread gets its own DB connection)
   and updates the Job's `stage` via an `on_stage(label)` callback threaded through the `ai/` pipeline calls,
   so the frontend can show "지금 이 단계 처리 중" progress.
3. Frontend polls `GET .../analyze-jobs/{job_id}/` (or the extract/generate-tasks equivalent) until
   `status` is `SUCCESS`/`ERROR`.
This is explicitly a stop-gap (see `backend_readme.md` §8): if gunicorn runs multiple workers or restarts
mid-job, an in-flight thread's progress is lost — there's no persistence/retry across processes.

### The `ai/` pipeline: sequential function calls, not a graph/framework
Each subdirectory under `ai/` is one pipeline step with a consistent internal shape: `agent.py` (entry point the
Django service layer calls directly), `schemas.py` (Pydantic input/output contracts), `prompt_builder.py`
(assembles a system prompt from static YAML rules in `prompts/*.yaml` + dynamic data). There is no orchestration
graph — `backend/tasks/services.py` and `backend/meetings/services.py` just `import` and call these functions
in a fixed order from plain Python. Current chain (see `backend/tasks/services.py::generate_task_suggestions`
and `backend/meetings/services.py::run_meeting_analysis`):

```
meeting text
  → plan_draft.agent.run()            # LLM: meeting text → 7-section plan document (fact-index + full generation, parallel where the source is long)
  → (PM reviews/approves the plan → requirement_draft.agent → RequirementDefinition, human review/approve)
  → task_generation.agent.generate_tasks()      # LLM: requirements → task list (whole-doc first, then only re-asks for IDs the model dropped)
  → project_scale.agent.assess_project_complexity()   # LLM: qualitative risk read of the plan, not from summed task hours
  → team_sizing.py / work_package.py            # deterministic code: hours→headcount, grouping into WorkPackages
  → assignment_ranking.agent.decide_package_splits()  # LLM: judges whether a package should be split, and candidate fit
  → assignee_mapping.agent                       # mostly deterministic: filters candidates by employment+skill
  → assignee_recommend.agent                      # FAST_MODEL: writes only the assignment-reason/hold-reason text —
  →                                                #   the actual assignee choice is decided by rule_filter.py (code), not the LLM
  → tasks.scheduler.schedule()                    # pure deterministic code: topological sort + ASAP placement → start/end dates
  → assignment_explanation.agent.summarize_plan() # LLM: human-readable risk/checkpoint summary of the whole plan
```
The team was deliberate about this split (see module docstrings/comments): **the LLM decides what needs
judgment (task breakdown, complexity, split-or-not, candidate fit) and describes decisions in prose; anything
that must be reproducible or auditable (final assignee, dates, hour math, ID numbering) is plain Python**, so
that a schedule/assignment can be explained and regenerated deterministically without re-prompting the model.

`meeting_analysis/` (full meeting → structured JSON with evidence/citations) exists and has its own tests, but
per a 2026-09-21 decision it's **no longer called from the web request path** — `plan_draft.agent.run()`'s
default `parallel` strategy now reads the raw meeting text directly in two independent LLM calls instead. Don't
assume the "meeting → structured JSON → plan" two-step story in older docs still reflects `services.py`.

### LLM call plumbing (`ai/shared/`)
- `ai/shared/llm_client.py::create_structured()` / `get_client()` wrap the OpenAI SDK with `instructor` so a
  Pydantic model passed as `response_model` gets enforced (schema validation + automatic reask-on-failure, up to
  `MAX_RETRIES`). New agent code should use `create_structured()`; a few older modules (`meeting_analysis`,
  `plan_draft`) still call `get_client()` + `client.chat.completions.create(...)` directly.
- `ai/shared/retry_config.py::MODEL_PROFILES` is the single source of truth for per-model-family call shape
  (does it accept `temperature`? `reasoning_effort`? which token-limit kwarg — `max_tokens` vs.
  `max_completion_tokens`? tool-calling vs. JSON-mode structured output). `resolve_profile(model)` picks a
  profile by prefix match. Adding support for a new OpenAI model family means adding one entry here, not editing
  call sites.
- Provider is OpenAI-only by design — an Anthropic fallback path existed and was intentionally removed
  (2026-09-07); don't reintroduce multi-provider fallback without checking that decision first.
- LangSmith tracing (`LANGSMITH_TRACING=true` in `.env`) auto-wraps the OpenAI client and is the only
  observability/eval mechanism present — there is no separate eval harness in production code. (`ai/compare_models.py`,
  `ai/compare_plan_strategies.py`, `ai/evaluate_plan_quality.py` at the `ai/` root are manual/offline comparison
  scripts, not part of any automated pipeline.)

### Known dead ends / unimplemented — don't build on these without checking first
- 🔴 `ai/retrieval/agent.py` and `ai/qa_answer/` — a planned RAG chatbot ("Track B"). `retrieval` is entirely
  `raise NotImplementedError` (chunking/embedding/Qdrant search); `qa_answer` depends on it and can't function
  standalone. No Qdrant client/config exists anywhere despite the README's tech badges.
- ⚪ Root `requirements.txt` / `backend/requirements.txt` list `celery`, `redis`, `langchain*`, `langgraph*` —
  installed, imported nowhere relevant. Treat as unused unless you find a new, actual call site.
- ⚪ AI quality-audit ("AI 품질감사") feature — `SpecValidationReport`/`RequirementValidationReport` models and
  the `plan_review`/`requirement_review` agent modules existed but have since been fully removed (models dropped
  via migration, no `/validate/` or `/*-validation-reports/` routes remain in `meetings/urls.py` /
  `requirements/urls.py`). If you see this mentioned in `backend_readme.md` or old `docs/`, it's stale.
- ⚪ `backend/tasks/urls.py` currently only exposes `assignments/`, `assignments/{id}/`, `assignments/{id}/status/`
  — the standalone `auto-assign`/`ai/assignee-mapping`/`ai/task-generation` endpoints that `backend_readme.md`
  describes as a parallel/duplicate path have already been removed; the real flow is entirely through
  `requirements/{spec_id}/generate-tasks/` → poll job → `requirements/{spec_id}/task-draft/` →
  `requirements/{spec_id}/confirm-tasks/`.

## Coding conventions actually in use

### Backend (Django)
- One app per domain area (`common`, `users`, `projects`, `meetings`, `requirements`, `tasks`, `notifications`,
  `dashboard`); enums/lookup values mostly live in `common.CommonCode`/`CommonCodeGroup` rows (group_code + code_id),
  not Django `TextChoices` — the codebase moved away from `TextChoices` over time (see `TaskStatusCode` for a
  case that still uses a small dedicated class, with a comment documenting a past PK-collision bug from sharing
  `CommonCode`'s global PK space).
- Views stay thin: `APIView`/`generics.*APIView` subclasses parse request/permissions and call into
  `<app>/services.py` functions for actual business logic; multi-step AI pipeline orchestration lives in
  `services.py`, not in `agent.py` (that stays a single pipeline step) and not in views.
  `@extend_schema(...)` (drf-spectacular) decorators on every view method are the norm — they populate
  `/api/docs/swagger/`.
- Background-job entry points (`_run_analyze_job`, `_run_generate_tasks_job`, etc.) are private module-level
  functions next to the view that starts the thread, always call `close_old_connections()` first and in the
  `except`/error path, and never touch `request.user` (thread has no request context — pass `user_id` and
  re-query).
- Exceptions from the AI layer are caught in `services.py` and turned into `{"status": "error", "message": ...}`
  dicts rather than propagating — views/jobs check `result["status"]`, not exception types (see `ai/shared/errors.py`
  for the AI-side exception→cause-code mapping this is meant to interoperate with).
- Non-obvious decisions get a dated inline comment (`# 2026-09-17: ...`) explaining *why*, including bugs that
  were fixed — this is the dominant documentation style in this codebase; follow it rather than adding
  separate design docs for small decisions.
- Logging via stdlib `logging.getLogger(__name__)`; root logger writes to console + rotating file
  (`backend/logs/django.log`); env vars are read through `django-environ` (`env = environ.Env(...)`) in
  `config/settings.py`, but through plain `python-dotenv` inside `ai/` (different convention by design — `ai/`
  is meant to be importable/testable outside Django).

### AI modules (`ai/`)
- Every module: `agent.py` (entry point) + `schemas.py` (Pydantic) + `prompt_builder.py` (system prompt = static
  YAML rules from `prompts/*.yaml` + dynamic context) — follow this shape for a new pipeline step rather than
  inventing a different layout.
- Structured output is always via a Pydantic `response_model` through `instructor`, never manual JSON parsing of
  a raw completion.
- Deterministic logic that must be reproducible/auditable (scheduling, ID numbering, hour math, final assignee
  choice) is plain Python, kept out of prompts, usually with a comment explaining why it isn't left to the LLM.
- Model selection is by role, not hardcoded per call: `DEFAULT_MODEL` (structured judgment calls),
  `STRONG_MODEL` (the one call — meeting analysis — empirically needing a stronger reasoning model),
  `FAST_MODEL` (low-judgment prose like assignment-reason text, batched). Respect this three-tier split when
  adding new calls instead of introducing a fourth ad hoc model choice.

### Frontend (Next.js / TypeScript)
- App Router with route groups: `(auth)` (login/onboarding, no dashboard chrome) and `(dashboard)` (everything
  behind login, shares `layout.tsx`). Most interactive pages are client components (`"use client"`); the
  `frontend/src/app/api/[...path]/route.ts` catch-all is the one server-side piece, and exists purely to proxy
  to Django so auth cookies stay same-origin (see comment in `client.ts`/`route.ts` — don't reintroduce
  `next.config.ts` `rewrites()` for this, it was tried and reverted for a Turbopack redirect issue).
- All backend calls go through `apiFetch()` in `src/lib/api/client.ts` (cookie-based auth, auto CSRF header,
  single-flight 401→refresh→retry) — don't call `fetch()` directly against the backend elsewhere except the
  documented exception (audio upload bypasses the proxy directly to `NEXT_PUBLIC_BACKEND_ORIGIN` because
  Vercel's proxy layer hard-caps request bodies at 4.5MB).
- Server state via TanStack Query (`QueryProvider` in `src/lib/queryClient.tsx`, 30s `staleTime`,
  `refetchOnWindowFocus: false`) — prefer it over ad hoc `useEffect`/`useState` fetch-on-mount for anything
  backend-derived. For job polling (analyze/extract/generate-tasks jobs), match the existing pattern of polling
  the job-status endpoint rather than adding a new mechanism.
- Components are organized by feature area under `src/components/` (`dashboard/`, `documents/`, `projects/`,
  `layout/`, `ui/`), PascalCase filenames matching the exported component. No enforced Server/Client split
  beyond marking interactive components `"use client"`.
- `.test.ts`/`.test.tsx` files sit next to the module they test (e.g. `documentPipeline.ts` +
  `documentPipeline.test.ts`), run by Vitest with `jsdom`.
