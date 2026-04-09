# Loom Architecture Overview

This standalone overview mirrors the architecture now captured in `design.md`, but is formatted for quick reuse in presentations, reviews, and implementation discussions.

## Layered System Overview

```mermaid
flowchart TB
    IDE[Engineer's IDE<br/>Claude Code / Cursor / Kiro / VS Code / etc.]

    subgraph L3[Layer 3: LangGraph Orchestrator]
        MCP[Single MCP / Tool Entry Point]
        ROUTER[Request Classification<br/>domain / memory / code / coding_task / spec_session / general]
        WF[Workflow Engine<br/>Research -> Memory -> Code -> Draft -> Verify -> Output]
        POLICY[Compliance / Traceability / Audit]
        MCP --> ROUTER --> WF --> POLICY
    end

    subgraph L2A[Layer 2A: Loom]
        subgraph LS[Loom Services]
            API[REST / Service API]
            MIG[Seed Migration + Incremental Ingestion]
            TEMP[Temporal State Layer<br/>HAS_STATE / validFrom / validTo / txFrom / txTo]
            PROV[Provenance Resolver]
            RET[GraphRAG Retrieval Pipeline]
            COMM[Community Builder<br/>Leiden clustering + summaries]
            ART[Artifact Context / Lineage Hooks]
        end

        subgraph GL[Knowledge Layer]
            ADAPTER[Graphiti Adapter]
            FALKOR[(FalkorDB)]
            GRAPHITI[Graphiti Temporal Engine]
            CCACHE[(Community Cache Fallback)]
        end

        API --> TEMP
        API --> PROV
        API --> RET
        API --> ART
        MIG --> ADAPTER
        TEMP --> ADAPTER
        PROV --> ADAPTER
        RET --> ADAPTER
        COMM --> CCACHE
        ADAPTER <--> GRAPHITI
        GRAPHITI <--> FALKOR
        RET <--> FALKOR
    end

    subgraph L2B[Layer 2B: AMS Solver]
        AMS[Hindsight AMS<br/>per-engineer session memory<br/>retain / recall / reflect / resume]
    end

    subgraph L2C[Layer 2C: CMM]
        CMM[codebase-memory-mcp<br/>repo graph / call paths / impact / architecture]
    end

    subgraph SRC[Phase 1 Curated Sources]
        ASAM[ASAMKnowledgeDB<br/>structured + reference + audit + vectors]
        AUTOSAR[autosar-fusion<br/>structured + reference + audit + vectors]
    end

    subgraph OUT[Outputs]
        ANSWERS[Cited Domain Answers]
        CODEOUT[Grounded Coding Guidance]
        SPEC[Requirements / Design / Tasks Revisions]
        AUDIT[Audit / Lineage / Progress Tracking]
    end

    IDE -->|MCP / HTTP| MCP
    POLICY --> API
    POLICY --> AMS
    POLICY --> CMM

    ASAM --> MIG
    AUTOSAR --> MIG

    WF --> ANSWERS
    WF --> CODEOUT
    WF --> SPEC
    POLICY --> AUDIT
```

## Primary Use-Case Overview

```mermaid
sequenceDiagram
    participant IDE as Engineer IDE
    participant Orch as Orchestrator
    participant Loom as Loom Services
    participant Temporal as Temporal/Provenance
    participant Retrieval as Retrieval Pipeline
    participant AMS as AMS Solver
    participant CMM as CMM
    participant Graph as FalkorDB + Graphiti

    rect rgb(235, 245, 255)
        Note over IDE,Graph: 1. Domain Knowledge Query
        IDE->>Orch: ask("What are XCP timing constraints?")
        Orch->>Loom: /api/v1/query
        Loom->>Retrieval: global search -> local search -> rerank
        Retrieval->>Graph: graph + vector retrieval
        Loom->>Temporal: provenance + optional temporal resolution
        Temporal->>Graph: evidence chain lookup
        Loom-->>Orch: cited results + warnings
        Orch-->>IDE: answer with evidence chain
    end

    rect rgb(245, 255, 240)
        Note over IDE,Graph: 2. Coding Task
        IDE->>Orch: ask("Implement XCP CONNECT handler")
        Orch->>Loom: standards / artifact context
        Orch->>AMS: recall prior decisions
        Orch->>CMM: search symbols / trace call paths / impact
        Loom->>Graph: provenance-grounded domain lookup
        CMM-->>Orch: code structure context
        AMS-->>Orch: session memory
        Orch-->>IDE: grounded coding guidance
    end

    rect rgb(255, 247, 235)
        Note over IDE,Graph: 3. Spec Session
        IDE->>Orch: generate_spec_artifact("design" or "tasks")
        Orch->>Loom: retrieve standards-grounded context
        Orch->>AMS: objective / steering / unresolved questions
        Loom->>Graph: domain + provenance + temporal lookup
        Orch-->>IDE: revised artifact + citations + lineage intent
    end

    rect rgb(250, 240, 255)
        Note over IDE,Graph: 4. Seed / Admin Migration
        IDE->>Loom: /admin/migration/structured/run
        Loom->>Graph: create domain nodes + provenance + state anchors
        IDE->>Loom: /admin/migration/vector/run
        Loom->>Graph: import 384-d embeddings + document linkage
        IDE->>Loom: /admin/temporal/bootstrap
        Loom->>Graph: create HAS_STATE edges
        IDE->>Loom: /admin/retrieval/communities/refresh
        Loom->>Retrieval: regenerate community summaries/cache
    end
```

## Deployment and Runtime Topology

```mermaid
flowchart LR
    subgraph DEV[Developer Machine]
        IDE[IDE / MCP Client]
        subgraph DOCKER[Docker Compose]
            ORCH[Orchestrator Container]
            LOOM[Loom Services Container]
            FDB[FalkorDB Container]
            AMSC[Hindsight Container<br/>Phase 2+]
        end
        CMM[CMM Native Binary]
        CACHE[(Community Cache File)]
    end

    subgraph DATA[Persisted Data]
        FDATA[(falkordb_data)]
        HDATA[(hindsight_data)]
    end

    IDE -->|MCP / HTTP| ORCH
    ORCH --> LOOM
    ORCH --> AMSC
    ORCH --> CMM
    LOOM --> FDB
    LOOM --> CACHE
    FDB --- FDATA
    AMSC --- HDATA
```

## Curated Data Flow

```mermaid
flowchart LR
    subgraph SOURCES[Curated Sources]
        ASQL[ASAM fused SQLite]
        ACV[ASAM Chroma vectors]
        AUSQL[AUTOSAR fused SQLite]
        AUCV[AUTOSAR Chroma vectors]
    end

    subgraph LOADERS[Load / Normalize]
        SCAN[Curated Scanner]
        DMIG[Deterministic Migrator]
        VIMP[Vector Importer]
        TBOOT[Temporal Bootstrap]
    end

    subgraph KNOWLEDGE[Knowledge Graph]
        SS[SourceSystem / SourcePipeline / SourceDocument]
        DOM[Domain Nodes]
        TXT[TextChunk embeddings]
        AUD[MigrationRun / AuditEvent / FusionAssessment]
        STATE[State Nodes + HAS_STATE]
        FDB[(FalkorDB)]
        GRAPHITI[Graphiti]
    end

    subgraph RETRIEVE[Retrieval]
        COMM[Community Builder / Cache]
        GLOB[Global Search]
        LOC[Local Search]
        RER[MMR Reranker]
        OUT[Cited Answers]
    end

    ASQL --> SCAN
    AUSQL --> SCAN
    ASQL --> DMIG
    AUSQL --> DMIG
    ACV --> VIMP
    AUCV --> VIMP
    DMIG --> SS
    DMIG --> DOM
    DMIG --> AUD
    VIMP --> TXT
    VIMP --> SS
    DOM --> TBOOT
    TBOOT --> STATE
    DOM --> GRAPHITI
    STATE --> GRAPHITI
    GRAPHITI <--> FDB
    SS --> FDB
    TXT --> FDB
    AUD --> FDB
    COMM --> GLOB
    FDB --> LOC
    GLOB --> LOC
    LOC --> RER --> OUT
```

## Notes

- `design.md` remains the main architecture source of truth.
- This file is a reusable snapshot for communication and review.
- The current implementation uses a local cache fallback for community summaries because live `CommunitySummary` writes are still timing out in FalkorDB.
