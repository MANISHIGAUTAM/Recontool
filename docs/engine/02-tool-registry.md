# Tool Registry

## Overview

The `ToolRegistry` is the single source of truth for tool metadata. It spans the
**entire canonical tool catalogue** by layering three sources into validated
`ToolSpec` models:

| Layer | Source | Tools | Role |
|-------|--------|-------|------|
| 1 (base) | `data/tool_inventory.json` | 532 records → **531 unique slugs** | Canonical catalogue of every recon tool (inventory-derived stubs) |
| 2 (override) | `config/tools.yaml` | ~62 | Hand-curated **detailed contracts** (authoritative) |
| 3 (override) | `config/tools_generic.yaml` | ~13 | Declarative generic-adapter specs |

Layers 2 and 3 are the 75 **curated** tools. They **override** the inventory base
for the same canonical slug, so a richer hand-written contract is never lost. The
remaining ~456 tools are **inventory-derived** stubs that make the long tail
queryable and schedulable.

> The inventory contains 532 records but two of them (`nuclei templates` and
> `nuclei-templates`) collapse to the same slug, so after slug-dedup the canonical
> set is **531 unique tools**. Combined with the 24 curated tools that have no
> inventory entry (e.g. `nmap`, `masscan`, `ffuf`, `tlsx`), the loaded registry
> holds **~555 tools** total.

```python
reg = ToolRegistry.load()
reg.stats()
# {'total': 555, 'curated': 75, 'inventory_derived': 480,
#  'executable': 458, 'non_executable': 97, 'canonical_slugs': 531}
```

## Override precedence (curated beats inventory)

Tools are deduplicated by **canonical slug** (`slugify(name)`,
e.g. `"Abuse.ch" → "abuse-ch"`). When a curated YAML entry shares a slug with an
inventory record:

1. The curated `ToolSpec` wins — its `integration`, `binary`, `invocation`,
   `endpoint`, `parse`, `supported_input_types`/`output_types` and other contract
   fields are kept verbatim.
2. Inventory-only **quality metadata** (`confidence_score`, `reliability`,
   `scale`, `cost_tier`, `data_quality`, `classification`, `sections`, `aliases`,
   `provenance`) is merged *into* the curated spec only where the curated spec
   does not already define it.
3. The merged tool keeps `source="curated"` and is **not** flagged
   `inventory_derived`.

`config/tools_generic.yaml` never overrides a `config/tools.yaml` entry of the
same name (pre-existing behaviour, preserved).

## Section → Category → Phase mapping

Inventory `sections` are labelled `"N. Title"`. Section `N` maps **1:1** to engine
category `N` (categories 1–19). Multi-section tools keep every membership in
`categories_all`, but the **primary category is the lowest section number**
(deterministic). Each category maps to a fixed pipeline phase:

| Cat | Section / Category name | Phase |
|----:|--------------------------|-------|
| 1 | Internet-wide search & asset discovery | `p1_seed` |
| 2 | Passive DNS & subdomain enumeration | `p1_seed` |
| 3 | WHOIS / ASN / BGP / network intel | `p3_enrichment` |
| 4 | Search-engine dorking & index recon | `p3_enrichment` |
| 5 | Web technology fingerprinting | `p4_verify` |
| 6 | Historical & archive recon | `p3_enrichment` |
| 7 | Email / username / identity | `p3_enrichment` |
| 8 | Social media recon | `p3_enrichment` |
| 9 | GitHub / GitLab / source-code recon | `p3_enrichment` |
| 10 | Cloud & storage recon | `p3_enrichment` |
| 11 | Metadata & document recon | `p3_enrichment` |
| 12 | Malware / IOC / threat intel | `p6_vuln` |
| 13 | Visual recon & screenshotting | `p4_verify` |
| 14 | Frameworks & automation suites | `p1_seed` |
| 15 | Physical / geo / wireless | `p3_enrichment` |
| 16 | Dark web & onion recon | `p3_enrichment` |
| 17 | APIs & intelligence feeds | `p3_enrichment` |
| 18 | Massive living indexes | `p3_enrichment` (non-executable) |
| 19 | Common recon workflows | `p1_seed` (non-executable) |
| 20 | Content & directory discovery | `p5_deep` |
| 21 | Port scanning & service detect | `p4_verify` |
| 22 | JavaScript analysis & secrets | `p5_deep` |
| 23 | API & GraphQL recon | `p5_deep` |
| 24 | TLS/SSL & certificate analysis | `p4_verify` |
| 25 | Parameter discovery & fuzz prep | `p5_deep` |
| 26 | Mobile / APK recon | `p5_deep` |
| 27 | Active vulnerability detection | `p6_vuln` |
| 28 | Wordlists & recon resources | `p3_enrichment` |

The full table lives in `recontool/engine/inventory.py` (`SECTION_TO_CATEGORY`,
`CATEGORY_PHASE`). Input/output key types for inventory-derived tools are
inherited from the category contract in `config/categories.yaml`, so they chain
through the scheduler exactly like curated tools.

## Classification → type / activity

| `classification` | `type` | `is_active` |
|------------------|--------|-------------|
| `passive` | `passive` | `False` |
| `active` | `active` | `True` |
| `hybrid` | `hybrid` | `True` (treated as active for safety gating) |

## Inventory-derived vs fully-contracted tools

| | Curated (full contract) | Inventory-derived (stub) |
|--|--|--|
| `source` | `"curated"` | `"inventory"` |
| `validation_status` | unset / curated value | `"inventory_derived"` |
| `is_inventory_derived` | `False` | `True` |
| Invocation/endpoint | concrete | none (synthesised for CLI; missing for API) |
| Execution | runs immediately | CLI: runs once binary present; API: blocked until promoted |

Query them explicitly:

```python
reg.curated_tools()        # 75 hand-written contracts
reg.inventory_tools()      # inventory-derived stubs
reg.executable_tools()     # has an api/cli execution path
reg.non_executable_tools() # web/gui/dataset-only, indexes, presets
reg.by_slug("abuse-ch")    # canonical-slug lookup
```

## Non-executable tools

Tools with no `api`/`cli` integration mode (web/gui/dataset/mobile-only), plus the
reference-index (cat 18) and workflow-preset (cat 19) categories, are registered
but flagged `non_executable=True` with a human-readable `non_executable_reason`
and `enabled=False`. The scheduler skips them gracefully; nothing fails.

## Promoting an inventory stub to a full contract

An inventory-derived stub becomes a first-class executable tool by adding a
curated entry that shares its slug:

1. **CLI tool** — add a `config/tools.yaml` (or `tools_generic.yaml`) entry with
   `binary` + `invocation` + a `parse` block. (Until then, the engine synthesises
   a best-effort `"{binary} {value}"` invocation so the tool can still run when the
   binary is installed.)
2. **API tool** — add a `tools_generic.yaml` entry with `endpoint`, optional
   `headers`/`requires_key`, and a `parse` block. (A bare inventory API stub is
   reported *blocked with reason* `inventory_stub: no API endpoint contract…`
   until promoted, because no real endpoint can be fabricated.)

The curated entry automatically overrides the stub on next load — no inventory
edits required.

## ToolSpec Schema

```python
class ToolSpec(BaseModel):
    name: str                          # Unique identifier
    slug: str = ""                     # Canonical dedup key (slugify(name))
    source: str = "curated"            # "curated" | "inventory"
    category: int = 0                  # Primary category number (1-28)
    categories_all: list[int]          # Every category membership (multi-section)
    purpose: str = ""                  # Human-readable description
    phase: str = ""                    # Pipeline phase (p1_seed, p2_expansion, ...)
    type: str = "passive"              # passive | active | hybrid
    is_active: bool = False            # Touches the target?
    integration: str = ""              # api | cli | (web/gui/dataset for stubs)
    binary: str = ""                   # Executable name on PATH
    invocation: str = ""               # Command template
    endpoint: str = ""                 # API URL template
    supported_input_types: list[str]   # What this tool accepts
    output_types: list[str]            # What this tool produces
    consumes: list[str]                # Event-driven: input key types
    produces: list[str]                # Event-driven: output key types
    timeout: int = 300                 # Max execution seconds
    parallel_safe: bool = True         # Can run concurrently
    enabled: bool = True               # Selectable by the scheduler
    # Inventory-derived quality metadata + flags
    classification: str = ""           # passive | active | hybrid (raw)
    confidence_score: float = 0.0
    reliability: str = ""
    scale: str = ""
    cost_tier: str = ""                # free | freemium | paid | mixed | unknown
    data_quality: str = ""
    web_only: bool = False
    sections: list[str]                # Raw inventory section labels
    aliases: list[str]                 # possible_aliases from inventory
    provenance: str = ""
    validation_status: str = ""        # "inventory_derived" for stubs
    non_executable: bool = False       # No programmatic interface?
    non_executable_reason: str = ""    # Why it cannot be auto-run
    metadata: dict                     # Raw inventory extras (worth/difficulty/…)
```

## Loading the Registry

```python
from recontool.engine.registry import ToolRegistry

# Load from default config directory
registry = ToolRegistry.load()

# Or build programmatically for testing
registry = ToolRegistry(tools={"mytool": ToolSpec(name="mytool", ...)})
```

## Querying Tools

```python
# By name
spec = registry.get("subfinder")

# By category
cat2_tools = registry.by_category(2)

# By input type
domain_tools = registry.by_input_type("domain")

# By output type
subdomain_producers = registry.by_output_type("subdomain")

# All tools
all_tools = registry.all_tools()

# Inventory-aware queries
registry.curated_tools()        # hand-curated contracts only
registry.inventory_tools()      # inventory-derived stubs only
registry.executable_tools()     # have an api/cli execution path
registry.non_executable_tools() # web/gui/dataset-only, indexes, presets
registry.by_slug("abuse-ch")    # canonical-slug lookup
registry.tools_for_inputs({"domain", "ip"})  # index-backed eligibility
registry.stats()                # headline counts for observability
```

## Adding a New Tool

### Option 1: YAML (declarative, no code)

Add to `config/tools_generic.yaml`:

```yaml
- name: certspotter
  phase: p1_seed
  category: 2
  integration: api
  consumes: [domain]
  produces: [subdomain]
  endpoint: "https://api.certspotter.com/v1/issuances?domain={domain}"
  enabled: true
```

### Option 2: tools.yaml (detailed)

Add to `config/tools.yaml` under the `tools:` key:

```yaml
tools:
  subfinder:
    category: 2
    phase: p2_expand
    type: passive
    binary: subfinder
    invocation: "subfinder -d {domain} -all -silent -oJ"
    input: domain
    output: subdomain
```

### Option 3: Programmatic (testing)

```python
spec = ToolSpec(
    name="custom_scanner",
    consumes=["live_host"],
    produces=["finding"],
    enabled=True,
)
registry = ToolRegistry(tools={"custom_scanner": spec})
```
