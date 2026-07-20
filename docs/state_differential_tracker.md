# Technical Reference Manual: Async Live Bounty State-Differential Tracker & Event Telemetry Hooks

## 1. Overview & Architectural Goals

The **Async Live Bounty State-Differential Ingestion Tracker** (`core/tracker.py`) operates as a non-blocking background daemon within the Bug Bounty Automation Engine. It continuously tracks bug bounty program metadata across target source platforms (Cantina, HackenProof, Immunefi, Sherlock) and detects real-time state mutations.

Key operational objectives:
1. **Max Reward Drift Detection**: Identify payout cap increases or decreases.
2. **Legal & Access Model Drift Detection**: Detect changes in `primacy_model`, `kyc_required`, or `invite_only` rules.
3. **Order-Agnostic Structural Scope Drift Detection**: Track asset contract additions or removals without false positives caused by list order changes.
4. **Automated LLM Queue Eviction**: Reset `preflight_queue` items for mutated projects back to `PENDING` status to force re-parsing by the 27B LLM cluster.
5. **Real-Time Telemetry Streaming**: Push high-priority mutation alert strings via FastAPI Server-Sent Events (SSE) `/api/ingestion/stream` to frontend dashboards.

---

## 2. Order-Agnostic Asset State Comparison Workflow

When fresh snapshot payloads arrive from source platform sync logic (`cbb`, `hbb`, `ibb`, `sbb`), assets are processed using an order-agnostic lookup table:

```
+--------------------------+          +--------------------------+
|  Incoming Asset Payload  |          |   Database Asset State   |
+--------------------------+          +--------------------------+
             |                                     |
             v                                     v
    Key: (identifier, type)               Key: (identifier, type)
             \                                     /
              \                                   /
               v                                 v
          +-------------------------------------------+
          | Order-Agnostic Set Comparison Matrix      |
          | Added Assets   = Incoming - Database      |
          | Removed Assets = Database - Incoming      |
          +-------------------------------------------+
```

### Key Normalization Algorithm
Asset keys are generated as normalized tuples:
$$\text{AssetKey} = \left(\text{lowercase}(\text{asset\_identifier} \lor \text{url}),\, \text{lowercase}(\text{type} \lor \text{'contract'})\right)$$

If $\text{AddedAssets} \neq \emptyset$ or $\text{RemovedAssets} \neq \emptyset$, a `STRUCTURAL_SCOPE_DRIFT` mutation event is generated.

---

## 3. Database Schema & Mutation Logging

Differential mutations are recorded in the `bounty_state_mutations` relation within `unified_bug_bounties.db`:

```sql
CREATE TABLE IF NOT EXISTS bounty_state_mutations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_slug TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    mutation_type TEXT NOT NULL CHECK (mutation_type IN ('MAX_REWARD_DRIFT', 'STRUCTURAL_SCOPE_DRIFT', 'LEGAL_ACCESS_DRIFT')),
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    log_message TEXT NOT NULL,
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mutations_slug ON bounty_state_mutations (project_slug, detected_at);
```

### Mutation Categories & Log Formatting

| Mutation Type | Triggering Condition | Log Message Format Example |
| :--- | :--- | :--- |
| `MAX_REWARD_DRIFT` | `max_bounty_usd` changed | `"MUTATION DETECTED [immunefi_aave-v3]: Max Bounty increased from $1,000,000 to $2,000,000 USDC."` |
| `LEGAL_ACCESS_DRIFT` | `primacy_model`, `kyc_required`, or `invite_only` changed | `"MUTATION DETECTED [hackenproof-dex]: Legal Drift updated kyc_required from '0' to '1'."` |
| `STRUCTURAL_SCOPE_DRIFT` | Added or removed assets detected | `"MUTATION DETECTED [cantina_morpho-blue]: Structural Scope Drift updated scope assets (Added assets: MorphoCore.sol)."` |

---

## 4. Automated Queue Eviction Mechanics

When any mutation is detected for a project (`slug`), the tracker daemon executes a surgical queue eviction:

```sql
UPDATE preflight_queue
SET dispatch_status = 'PENDING', error_log = NULL
WHERE source_identifier = :slug OR source_identifier LIKE '%' || :slug || '%';
```

This guarantees that:
- Previously dispatched or failed LLM preflight tasks for the project are reset.
- The 27B LLM cluster autopilot automatically re-extracts structural audit context on its next execution pass.

---

## 5. FastAPI Orchestration & Telemetry Hooks

### Non-Blocking Lifespan Orchestration
In `api/server.py`, the tracker loop is launched asynchronously during FastAPI startup:

```python
@app.on_event("startup")
def startup_db():
    init_unified_db()
    asyncio.create_task(run_state_differential_tracker_loop(interval_seconds=60.0))
```

To prevent blocking FastAPI's main HTTP thread during SQLite transaction scans, `run_state_differential_tracker_loop` offloads synchronous database pass execution to a thread pool via `await asyncio.to_thread(run_differential_ingestion_pass)`.

### SSE Event Stream Integration
The real-time telemetry stream at `GET /api/ingestion/stream` queries `bounty_state_mutations` for changes detected in the last 5 seconds and pushes them to clients:

```json
{
  "timestamp": "21:15:00",
  "ttft_ms": 14.5,
  "itl_ms": 8.6,
  "active_concurrency": 4,
  "max_concurrency": 8,
  "pending_queue_length": 12,
  "completed_dispatches": 180,
  "cluster_gpu_utilization_pct": 74.5,
  "vram_allocated_gb": 22.8,
  "mutation_alerts": [
    "MUTATION DETECTED [immunefi_mock-protocol]: Max Bounty increased from $1,000,000 to $2,000,000 USDC."
  ]
}
```

---

## 6. Empirical Verification Test Pass 8

Automated testing is integrated into `run_pipeline.py` under **Test Pass 8 (State Differential Validation)**:
1. Seed mock project `mock-protocol` with \$1,000,000 bounty cap and `mock_contract_v1.sol`.
2. Stage preflight queue item with status `DISPATCHED`.
3. Pass updated payload with \$2,000,000 bounty cap and `mock_contract_v2.sol`.
4. Assert:
   - Scalar row count in `bounty_state_mutations` increases by $\ge 2$.
   - Mutation types `MAX_REWARD_DRIFT` and `STRUCTURAL_SCOPE_DRIFT` are present.
   - Preflight queue entry status reverts from `DISPATCHED` to `PENDING`.
