# Graph Report - .  (2026-06-12)

## Corpus Check
- Corpus is ~42,511 words - fits in a single context window. You may not need a graph.

## Summary
- 1149 nodes · 2720 edges · 58 communities (52 shown, 6 thin omitted)
- Extraction: 74% EXTRACTED · 26% INFERRED · 0% AMBIGUOUS · INFERRED: 710 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Adapter Framework & Artifact Store|Adapter Framework & Artifact Store]]
- [[_COMMUNITY_AI Agentic Supervisor|AI Agentic Supervisor]]
- [[_COMMUNITY_Dependency Checks & Parallel Execution|Dependency Checks & Parallel Execution]]
- [[_COMMUNITY_Policy Engine (Scope & Auth)|Policy Engine (Scope & Auth)]]
- [[_COMMUNITY_Tool Inventory Ingestion|Tool Inventory Ingestion]]
- [[_COMMUNITY_Adapter Base Protocol|Adapter Base Protocol]]
- [[_COMMUNITY_OSINT Search Adapters|OSINT Search Adapters]]
- [[_COMMUNITY_Engine Event Types|Engine Event Types]]
- [[_COMMUNITY_AI Decision Service|AI Decision Service]]
- [[_COMMUNITY_Tiered Model Router|Tiered Model Router]]
- [[_COMMUNITY_InputOutput Fingerprinting|Input/Output Fingerprinting]]
- [[_COMMUNITY_Budget Ledger & Circuit Breaker|Budget Ledger & Circuit Breaker]]
- [[_COMMUNITY_Scan Config & Noise Filter|Scan Config & Noise Filter]]
- [[_COMMUNITY_Pure-Python Web Crawler|Pure-Python Web Crawler]]
- [[_COMMUNITY_Frontier & Dead-Letter Queue|Frontier & Dead-Letter Queue]]
- [[_COMMUNITY_CrtSh Adapter|CrtSh Adapter]]
- [[_COMMUNITY_Structured Engine Logging|Structured Engine Logging]]
- [[_COMMUNITY_Metrics Collector|Metrics Collector]]
- [[_COMMUNITY_Inventory Builder Script|Inventory Builder Script]]
- [[_COMMUNITY_CLI Entry Points|CLI Entry Points]]
- [[_COMMUNITY_Active Scan Adapters|Active Scan Adapters]]
- [[_COMMUNITY_Generic APICLI Adapters|Generic API/CLI Adapters]]
- [[_COMMUNITY_Pending-Key Dependency Tracking|Pending-Key Dependency Tracking]]
- [[_COMMUNITY_Engine Orchestration Handlers|Engine Orchestration Handlers]]
- [[_COMMUNITY_Job Execution & Concurrency|Job Execution & Concurrency]]
- [[_COMMUNITY_Adapter Context & Content Discovery|Adapter Context & Content Discovery]]
- [[_COMMUNITY_Database & Tool Registry Seeding|Database & Tool Registry Seeding]]
- [[_COMMUNITY_Work Queue Router|Work Queue Router]]
- [[_COMMUNITY_Multi-Worker Queue Execution|Multi-Worker Queue Execution]]
- [[_COMMUNITY_Generic Adapter Autoload|Generic Adapter Autoload]]
- [[_COMMUNITY_Passive OSINT Adapters|Passive OSINT Adapters]]
- [[_COMMUNITY_Tool Spec Registry Queries|Tool Spec Registry Queries]]
- [[_COMMUNITY_Tool Dependency Detection|Tool Dependency Detection]]
- [[_COMMUNITY_Execution Planning|Execution Planning]]
- [[_COMMUNITY_Event Bus & Executor|Event Bus & Executor]]
- [[_COMMUNITY_Unified Tool Registry|Unified Tool Registry]]
- [[_COMMUNITY_Registry Spec Normalization|Registry Spec Normalization]]
- [[_COMMUNITY_Queue Scan Runner|Queue Scan Runner]]
- [[_COMMUNITY_Tool Catalog Loader|Tool Catalog Loader]]
- [[_COMMUNITY_Tool Catalog Stats|Tool Catalog Stats]]
- [[_COMMUNITY_Flow Diagram Builder|Flow Diagram Builder]]
- [[_COMMUNITY_Dedupe Key Generation|Dedupe Key Generation]]
- [[_COMMUNITY_Tool Selection Profiles|Tool Selection Profiles]]
- [[_COMMUNITY_Suggested-Tools Doc Generator|Suggested-Tools Doc Generator]]
- [[_COMMUNITY_Pydantic Tool Registry Models|Pydantic Tool Registry Models]]
- [[_COMMUNITY_Registry Loader (YAML Merge)|Registry Loader (YAML Merge)]]
- [[_COMMUNITY_Executor Job Counter|Executor Job Counter]]
- [[_COMMUNITY_Engine Package Init|Engine Package Init]]
- [[_COMMUNITY_Scheduler Job Queue Accessor|Scheduler Job Queue Accessor]]
- [[_COMMUNITY_Inventory Package Init|Inventory Package Init]]
- [[_COMMUNITY_Recontool Package Root|Recontool Package Root]]
- [[_COMMUNITY_Tools Package Init|Tools Package Init]]

## God Nodes (most connected - your core abstractions)
1. `Event` - 86 edges
2. `AdapterContext` - 78 edges
3. `Adapter` - 73 edges
4. `EventBus` - 50 edges
5. `Normalizer` - 42 edges
6. `EventDrivenScheduler` - 40 edges
7. `EntityDiscovered` - 38 edges
8. `ArtifactStore` - 37 edges
9. `ToolFailed` - 37 edges
10. `Scope` - 34 edges

## Surprising Connections (you probably didn't know these)
- `Any` --uses--> `Event`  [INFERRED]
  recontool/engine/output.py → recontool/adapters/base.py
- `Session` --uses--> `Base`  [INFERRED]
  recontool/core/db.py → recontool/core/models.py
- `AdapterContext` --uses--> `Adapter`  [INFERRED]
  recontool/adapters/active.py → recontool/adapters/base.py
- `AdapterContext` --uses--> `AdapterContext`  [INFERRED]
  recontool/adapters/active.py → recontool/adapters/base.py
- `AdapterContext` --uses--> `Event`  [INFERRED]
  recontool/adapters/active.py → recontool/adapters/base.py

## Import Cycles
- None detected.

## Communities (58 total, 6 thin omitted)

### Community 0 - "Adapter Framework & Artifact Store"
Cohesion: 0.05
Nodes (48): Adapter framework.  Adapters are PURE (docs/D4-adr.md ADR-011): they run one too, load_builtin(), Import adapter modules so their @register decorators fire, then register     the, ArtifactStore, Filesystem artifact store.  Large blobs (JS files harvested from Wayback, respon, Persist raw tool output as JSON; return the relative key., Persist a JS file harvested from the web; return the relative key., Append discovered entities to a typed, append-only output file:         out/<too (+40 more)

### Community 1 - "AI Agentic Supervisor"
Cohesion: 0.07
Nodes (41): AI agentic supervisor — runtime decisioning over the pipeline.  Consulted by the, Return the subset of adapters to keep, or None to keep all.         Heuristic ke, Supervisor, Asset, combine(), confidence_from_tools(), Confidence scoring via noisy-OR combination of independent sources.  confidence, Noisy-OR over a set of independent source weights -> [0,1]. (+33 more)

### Community 2 - "Dependency Checks & Parallel Execution"
Cohesion: 0.10
Nodes (38): DependencyChecker, DependencyChecker, Return list of missing environment variables., Return list of paths that are not readable., Check whether a tool's runtime dependencies are satisfied., The scan has finished (all tools done, no more pending keys)., ScanCompleted, ParallelExecutor (+30 more)

### Community 3 - "Policy Engine (Scope & Auth)"
Cohesion: 0.06
Nodes (27): Decision, PolicyEngine, Policy Engine — scope + authorization + demo/test-mode gate (diagram box C).  En, Single authorization decision point for the whole run., May we begin a run against this seed at all?, May an ACTIVE (target-touching) check run against this entity?, _apex(), apex_domain() (+19 more)

### Community 4 - "Tool Inventory Ingestion"
Cohesion: 0.08
Nodes (44): all_categories(), build_inventory_spec(), category_io(), classification_to_type(), derive_integration(), load_inventory_records(), load_inventory_specs(), non_executable_reason() (+36 more)

### Community 5 - "Adapter Base Protocol"
Cohesion: 0.07
Nodes (21): Adapter, Event, Check if the tool is installed and available. Default: True., Pre-execution setup (create temp dirs, validate config). Default: no-op., Validate inputs before execution. Returns list of error strings (empty = valid)., Parse raw stdout into a structured dict. Default: wraps in 'raw' key., Parse output files into a structured dict. Default: empty., Convert parsed output into normalized Event objects. Default: empty. (+13 more)

### Community 6 - "OSINT Search Adapters"
Cohesion: 0.12
Nodes (15): Censys, CriminalIP, FullHunt, GreyNoise, _host_of(), InternetDB, _is_ip(), LeakIX (+7 more)

### Community 7 - "Engine Event Types"
Cohesion: 0.14
Nodes (34): EngineEvent, _now(), PendingKeyCreated, PendingKeyResolved, Typed event classes and in-process async pub/sub EventBus.  All engine events ar, A tool produced an output artifact (file, data blob)., A new pending key was created (output from a tool)., A pending key has been resolved (dependency satisfied). (+26 more)

### Community 8 - "AI Decision Service"
Cohesion: 0.08
Nodes (24): AIDecisionService, DecisionResult, AI decisioning layer for the event-driven engine.  Classifies tool output entiti, Determine if an entity is noise (should be discarded).          Checks against k, Determine if an entity should trigger downstream tool execution., Check which pending keys from the list are considered fulfilled.          Return, Determine if a tool should be rescanned.          Default heuristic: rescan if c, Determine if an entity needs manual review.          Default heuristic: findings (+16 more)

### Community 9 - "Tiered Model Router"
Cohesion: 0.09
Nodes (18): ModelRouter, Tiered model router — use the cheapest model that can do the job.    - LIGHT mod, Ask the model for a STRICT JSON decision. Returns None if unavailable         or, _cfg(), _csv_env(), load_tool_registry(), Any, Central configuration, rate-limit profiles, and tool-registry loading.  Configur (+10 more)

### Community 10 - "Input/Output Fingerprinting"
Cohesion: 0.09
Nodes (25): _canonical(), fingerprint_config(), fingerprint_inputs(), fingerprint_output(), has_changed(), Input/output fingerprinting for incremental scans.  Uses SHA-256 hashing of sort, Produce a canonical string representation for hashing., Compute a SHA-256 fingerprint of a tool's inputs. (+17 more)

### Community 11 - "Budget Ledger & Circuit Breaker"
Cohesion: 0.10
Nodes (11): Enum, BudgetLedger, CircuitBreaker, CircuitRegistry, Provider-aware reliability primitives — circuit breaker + budget ledger.  Author, One breaker per provider key (shared across that provider's adapters)., Per-run, per-provider quota ledger.      Each provider gets a budget of quota un, Per-provider breaker.      Trips OPEN after `failure_threshold` consecutive fail (+3 more)

### Community 12 - "Scan Config & Noise Filter"
Cohesion: 0.19
Nodes (27): EntityDiscovered, A new entity has been discovered by a tool., ExecutionResult, Result of a single tool execution., NoiseConfig, NoiseFilter, Which noise filters are active. Everything off unless `enabled`., Decide whether a discovered entity should be re-fed as a new lead. (+19 more)

### Community 13 - "Pure-Python Web Crawler"
Cohesion: 0.11
Nodes (20): _mask(), extract_links(), host_of(), _LinkExtractor, PyCrawler, Pure-Python web crawler (no external binary required).  A self-contained, scope-, Collect URL-bearing attributes from HTML using only the stdlib., Return absolute http(s) URLs referenced by an HTML document. (+12 more)

### Community 14 - "Frontier & Dead-Letter Queue"
Cohesion: 0.10
Nodes (9): DeadLetter, DeadLetterEntry, FrontierItem, FrontierManager, Frontier Manager + Checkpoint + Dead-letter (the diagram's boxes I and U).  The, Jobs that exhausted retries or were blocked by an open circuit. Inspectable, Return the jobs to retry and clear the queue., Priority work-queue with dedup-driven convergence and depth/budget caps. (+1 more)

### Community 15 - "CrtSh Adapter"
Cohesion: 0.09
Nodes (15): CrtSh, Map parsed outputs to entity discovery events.          Delegates to emit_normal, Return subdomain pending key values this output resolves., crt.sh is safe to run concurrently., No dependencies - crt.sh runs from seed domains only., 30 second timeout for API requests., Retry on transient HTTP errors., Certificate Transparency adapter using crt.sh API.      This adapter serves as t (+7 more)

### Community 16 - "Structured Engine Logging"
Cohesion: 0.11
Nodes (15): EngineLogger, _now_iso(), Structured logging and observability for the event-driven engine.  Provides an E, Log a tool execution failure., Log the discovery of a new entity., Log a pending key creation or resolution., Log a concurrency/scheduling decision., Log an AI decisioning outcome. (+7 more)

### Community 17 - "Metrics Collector"
Cohesion: 0.08
Nodes (14): MetricsCollector, Metrics collection for the event-driven engine.  Provides in-memory counters and, Export metrics snapshot as a JSON string., In-memory metrics collector for engine observability.      Tracks counters, gaug, Record a tool execution.          Args:             tool: Name of the tool., Record discovery of an entity., Record a pending key action (created or resolved).          Args:             ac, Record that a duplicate entity was suppressed. (+6 more)

### Community 18 - "Inventory Builder Script"
Cohesion: 0.14
Nodes (23): best_worth(), build(), build_caveats(), classify(), cost_tier(), _count(), find_possible_aliases(), integration_modes() (+15 more)

### Community 19 - "CLI Entry Points"
Cohesion: 0.16
Nodes (22): create_all(), Create all tables. Idempotent., build_scan_infra(), Shared setup for both execution paths: (profile, scope, http, api_keys)., Run a single-process event-driven scan with real tool execution.      Discovery, run_engine_scan(), engine(), export() (+14 more)

### Community 20 - "Active Scan Adapters"
Cohesion: 0.19
Nodes (12): Adapter, _abs(), DnsResolve, _first_cve(), HttpProbe, JsAnalyze, Nuclei, PortScan (+4 more)

### Community 21 - "Generic API/CLI Adapters"
Cohesion: 0.20
Nodes (16): emit_events(), _emit_one(), GenericApiAdapter, GenericCliAdapter, _get(), _input_values(), parse_records(), Generic, registry-driven adapters.  Instead of hand-coding one Python class per (+8 more)

### Community 22 - "Pending-Key Dependency Tracking"
Cohesion: 0.13
Nodes (13): _now(), PendingKey, PendingKeyStore, Pending-key model and store for inter-tool dependency tracking.  A "pending key", Check if all required key types have at least one resolved key.          Returns, In-memory representation of a pending key., DB-backed CRUD for pending keys.      Requires a SQLAlchemy session (from recont, Create and persist a new pending key. (+5 more)

### Community 23 - "Engine Orchestration Handlers"
Cohesion: 0.12
Nodes (10): Handle entity discovery by updating available keys and scheduling., Handle tool completion by updating state and checking convergence., Handle tool failure by updating state., Handle pending key resolution., Re-check blocked tools to see if they can now be scheduled., Find tools eligible to run based on available keys.          A tool is eligible, Queue a tool for execution., Build inputs dict for a tool from available entity values.          Maps the too (+2 more)

### Community 24 - "Job Execution & Concurrency"
Cohesion: 0.15
Nodes (12): A tool has started executing., ToolRunning, Get or create a per-host semaphore.          Evicts the oldest entries when the, Execute a batch of jobs with concurrency controls.          Jobs run in parallel, Execute a single job with concurrency controls.          Acquires global + per-t, Actually execute a job and emit events., Try to extract a host/target from job inputs for per-host limiting., Get or create a per-tool semaphore. (+4 more)

### Community 25 - "Adapter Context & Content Discovery"
Cohesion: 0.15
Nodes (12): AdapterContext, Build the shell command string for CLI tools. Returns None for API adapters., Everything an adapter needs to run one unit of work., Can this adapter run given current config/keys/tooling? Override for         CLI, ContentDiscovery, is_hit(), load_wordlist(), _rand_path() (+4 more)

### Community 26 - "Database & Tool Registry Seeding"
Cohesion: 0.16
Nodes (15): _connect_args(), init_engine(), Database engine + session management. SQLite by default, PostgreSQL-ready., Transactional session context., session_scope(), Persisted tool capability registry — the static half of the matrix.      One row, ToolRow, Seed the persisted tool registry (ToolRow) from the full catalog.  Idempotent: r (+7 more)

### Community 27 - "Work Queue Router"
Cohesion: 0.16
Nodes (16): A single (key, tool) job — the dynamic half of the matrix (WorkQueue).      `ded, WorkItem, _eligible_types(), enqueue(), Deterministic Router + dedupe-aware WorkQueue enqueue.  The Router answers "whic, Stable per-(entity, tool) key. Equivalent entity spellings collapse via     the, All registered tools that consume `key_type`.      Deterministic join. `default_, Create pending WorkItems for every tool that consumes `key_type`.      Returns t (+8 more)

### Community 28 - "Multi-Worker Queue Execution"
Cohesion: 0.18
Nodes (13): discovered_assets(), Unique (entity_type, value) asset pairs from a tool's events., claim_one(), ClaimedItem, _has_active(), _now(), Multi-worker, queue-driven execution over the persisted `work_item` table.  This, Runs N concurrent async workers against the work_item queue for a scan. (+5 more)

### Community 29 - "Generic Adapter Autoload"
Cohesion: 0.18
Nodes (14): load_generic_specs(), Auto-register generic adapters from config/tools_generic.yaml.  Every tool in th, Build + register adapter classes for every generic spec not already     covered, register_generic(), build_adapter_class(), Create a registrable Adapter subclass from a declarative spec., params_from_url(), Parameter & form extraction (Category 25 — fuzz prep).  Two pure, testable helpe (+6 more)

### Community 30 - "Passive OSINT Adapters"
Cohesion: 0.22
Nodes (8): AlienVaultOTX, HackerTarget, _looks_ip(), Passive adapters — no direct target contact.  These query third-party indexes/ar, Subfinder, Wayback, AdapterContext, Event

### Community 31 - "Tool Spec Registry Queries"
Cohesion: 0.12
Nodes (9): Primary input type (from 'input' field or first consumes entry)., Primary output type (from 'output' field or first produces/output_types)., True if the engine has a programmatic execution path for this tool.          Non, True if this spec came from data/tool_inventory.json (no full contract)., Full specification for a tool in the registry., Return all tools in a given category., Return all tools in a given phase., Return tools that produce a given output type. (+1 more)

### Community 32 - "Tool Dependency Detection"
Cohesion: 0.14
Nodes (9): Installation and dependency detection for tools.  DependencyChecker inspects the, Check if a binary is available on PATH., Check if a binary version meets the requirement.          Attempts to run `binar, Check if an API key environment variable is set and non-empty., Result of a dependency check for a tool., Run all checks for a tool and return a composite ReadinessResult.          Handl, True if the tool has enough to route through a generic adapter.          CLI too, ReadinessResult (+1 more)

### Community 33 - "Execution Planning"
Cohesion: 0.22
Nodes (13): build_adapter_for(), _default_parse(), ExecutionPlan, plan_execution(), Route registry tools to the generic adapter mechanism.  The engine never hand-wr, Decide how a tool runs and surface a clear reason when it cannot., Return a ready-to-run generic Adapter subclass for a tool, or None.      Thin wr, How (and whether) a tool can be executed by the engine. (+5 more)

### Community 34 - "Event Bus & Executor"
Cohesion: 0.17
Nodes (6): EventBus, Register a handler for a specific event type., Remove a handler for a specific event type., Dispatch an event to all registered handlers for its type.          Uses return_, Parallel execution engine with concurrency controls.  Implements per-tool, per-h, Handler

### Community 35 - "Unified Tool Registry"
Cohesion: 0.17
Nodes (6): Unified registry loading tools from config/tools.yaml and config/tools_generic.y, (Re)build the slug and input-type indexes from ``self._tools``., Return all registered tool specs., All canonical inventory slugs the registry covers (532 when complete)., Slugs of every registered tool (curated + inventory)., ToolRegistry

### Community 36 - "Registry Spec Normalization"
Cohesion: 0.17
Nodes (7): Enrich a curated spec with inventory-only quality metadata.          Curated inv, Map tools.yaml fields to ToolSpec fields., Get a tool spec by name., Return tools that accept a given input type (index-backed, O(matches))., Return tools whose consumed types intersect ``available`` (deduped).          Us, Look up a tool by canonical slug., Any

### Community 37 - "Queue Scan Runner"
Cohesion: 0.19
Nodes (10): build_noise(), Construct the optional NoiseFilter (or None when disabled)., enqueue_key(), QueueScanResult, Create pending work items for every ENABLED tool that consumes `key_type`     (w, Seed the work queue and drain it with `workers` concurrent workers., Precomputed `input_type -> [enabled tool specs]` map, built once per scan., RouteIndex (+2 more)

### Community 38 - "Tool Catalog Loader"
Cohesion: 0.28
Nodes (12): contracted_slugs(), _from_flow(), _from_suggested(), load_all_tools(), _norm(), normalize(), Single canonical loader for the FULL tool catalog (nothing eliminated).  This is, Turn a raw consumes/produces string into canonical types. (+4 more)

### Community 39 - "Tool Catalog Stats"
Cohesion: 0.20
Nodes (5): Tools backed by a hand-curated YAML contract., Tools materialised from the canonical inventory (no full contract)., Tools the orchestrator can attempt to run (api/cli execution path)., Tools registered for visibility but skipped by the orchestrator., Headline counts for observability / docs.

### Community 40 - "Flow Diagram Builder"
Cohesion: 0.42
Nodes (9): alnum(), build(), contract_for(), _esc(), invocation(), load_yaml_contracts(), _render_category(), _render_master() (+1 more)

### Community 41 - "Dedupe Key Generation"
Cohesion: 0.39
Nodes (8): _canonical_url(), canonical_value(), dedupe_key(), endpoint_key(), finding_key(), Deterministic dedupe keys + idempotent upserts.  The heart of normalization: re-, Normalize a value so equivalent representations collapse together., _sha()

### Community 42 - "Tool Selection Profiles"
Cohesion: 0.40
Nodes (5): apply_selection(), is_excessive(), Tool-selection profiles — which tools a scan is allowed to run (flag-gated)., Enable the tools allowed by `mode`; disable the rest. Returns the count     enab, ToolRegistry

### Community 43 - "Suggested-Tools Doc Generator"
Cohesion: 0.60
Nodes (5): build(), _modes_block(), _output_files(), Generate capability docs for SUGGESTED tool additions (gap-closing tools).  Thes, Suggested

### Community 44 - "Pydantic Tool Registry Models"
Cohesion: 0.40
Nodes (4): BaseModel, Enhanced tool registry with Pydantic-validated ToolSpec models.  Loads tools fro, Retry configuration for a tool., RetryPolicy

### Community 45 - "Registry Loader (YAML Merge)"
Cohesion: 0.40
Nodes (3): Load the unified registry.          Layering (highest precedence last so curated, Map tools_generic.yaml fields to ToolSpec fields., Path

## Knowledge Gaps
- **11 isolated node(s):** `Any`, `ToolSpec`, `Any`, `ToolSpec`, `Any` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AdapterContext` connect `Adapter Context & Content Discovery` to `Adapter Framework & Artifact Store`, `Policy Engine (Scope & Auth)`, `Adapter Base Protocol`, `OSINT Search Adapters`, `Scan Config & Noise Filter`, `Pure-Python Web Crawler`, `CrtSh Adapter`, `CLI Entry Points`, `Active Scan Adapters`, `Generic API/CLI Adapters`, `Generic Adapter Autoload`, `Passive OSINT Adapters`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Why does `Event` connect `Adapter Base Protocol` to `Adapter Framework & Artifact Store`, `AI Agentic Supervisor`, `Dependency Checks & Parallel Execution`, `Policy Engine (Scope & Auth)`, `OSINT Search Adapters`, `AI Decision Service`, `Pure-Python Web Crawler`, `CrtSh Adapter`, `Active Scan Adapters`, `Generic API/CLI Adapters`, `Adapter Context & Content Discovery`, `Generic Adapter Autoload`, `Passive OSINT Adapters`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Why does `ToolSpec` connect `Tool Spec Registry Queries` to `Tool Dependency Detection`, `Execution Planning`, `Unified Tool Registry`, `Registry Spec Normalization`, `Tool Catalog Stats`, `Engine Event Types`, `Input/Output Fingerprinting`, `Pydantic Tool Registry Models`, `Registry Loader (YAML Merge)`?**
  _High betweenness centrality (0.101) - this node is a cross-community bridge._
- **Are the 65 inferred relationships involving `Event` (e.g. with `DnsResolve` and `HttpProbe`) actually correct?**
  _`Event` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 60 inferred relationships involving `AdapterContext` (e.g. with `DnsResolve` and `HttpProbe`) actually correct?**
  _`AdapterContext` has 60 INFERRED edges - model-reasoned connections that need verification._
- **Are the 48 inferred relationships involving `Adapter` (e.g. with `DnsResolve` and `HttpProbe`) actually correct?**
  _`Adapter` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `EventBus` (e.g. with `DependencyChecker` and `ExecutionResult`) actually correct?**
  _`EventBus` has 38 INFERRED edges - model-reasoned connections that need verification._