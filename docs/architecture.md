<!-- Architecture derived from source and schema; nodes name components/tables, messages name calls, and state labels describe computed posting eligibility. -->
# Architecture

Simplified PlantUML versions: [Components](components.puml),
[Database entities](database-entities.puml), [Daily run](daily-run.puml),
and [Posting lifecycle](posting-lifecycle.puml).

Built from [schema.sql](../schema.sql), the [CLI](../jagent/cli.py),
[runner](../jagent/runner.py), source adapters, matching, analysis, dashboard,
and [deployment files](../deploy/). Solid component arrows show implemented calls
or dependencies; dotted arrows show the requested external operating context.
The laptop collector, SSH tunnel setup, and TokenRouter deployment are not in
this checkout. The API clients accept configurable base URLs; `.env.example`
uses OpenAI URLs, so routing through TokenRouter is conditional on configuration.

## Components

```mermaid
flowchart LR
    subgraph feeds[Sources]
        api["API / RSS<br/>remoteok, remotive, arbeitnow<br/>himalayas, jobicy<br/>weworkremotely, hn_hiring"]
        html["HTML<br/>staffal, kosovajob, djinni"]
        ats["ATS APIs<br/>Greenhouse, Lever<br/>Ashby, SmartRecruiters"]
        laptopImport["Laptop import<br/>Duapune JSON"]
    end
    subgraph laptop[Laptop - external context]
        collector["Laptop collector<br/>implementation outside checkout"]
        browser[Browser]
        tunnel["SSH tunnel<br/>setup outside checkout"]
    end
    subgraph server[Server]
        timer["jagent.timer<br/>07:00 Europe/Tirane"]
        dailyService[jagent.service]
        daily[deploy/daily.sh]
        cli["CLI commands<br/>run, match, analyze, health<br/>init-db, profile set, filter-report, serve"]
        runner[runner.py and source adapters]
        matching[matching.py and embeddings.py]
        analysis[analysis.py]
        health[health.py]
        db[("Postgres 16 + pgvector<br/>127.0.0.1:5434 to container 5432")]
        webService[jagent-web.service]
        dashboard["FastAPI dashboard via serve<br/>127.0.0.1:8000<br/>Queue, Applied, Filters, reviews"]
        imported[imports/duapune.json]
    end
    router["TokenRouter - external context<br/>configurable OpenAI-compatible API"]
    collector -.->|collect and transfer| laptopImport
    laptopImport -->|file input| imported
    timer --> dailyService --> daily --> cli
    cli -->|run| runner
    runner -->|fetch| api
    runner -->|fetch| html
    runner -->|fetch registered boards| ats
    runner -->|read via duapune.fetch| imported
    runner -->|postings, source_runs, discovered ATS slugs| db
    cli -->|match| matching
    cli -->|analyze| analysis
    cli -->|health| health
    cli -->|init-db, profile set, filter-report| db
    matching --> db
    analysis --> db
    health --> db
    matching -.->|EMBEDDINGS_BASE_URL + /embeddings| router
    analysis -.->|LLM_BASE_URL + /chat/completions| router
    webService -->|uv run jagent serve| cli
    cli -->|serve| dashboard
    dashboard -->|read queue, write reviews and profile versions| db
    dashboard -->|health banner| health
    browser -.-> tunnel -.->|forward HTTP to server loopback| dashboard
```

The runner fetches eleven named sources, then boards registered in `ats_companies`; new postings can discover more ATS slugs.
Duapune reads a local JSON file and rejects missing imports, timezone-free collection times, or imports older than 36 hours.
The timer starts the daily oneshot service; the separate web service runs the dashboard continuously and restarts on failure.
Database connections force UTC; Docker publishes Postgres on loopback port 5434, and `serve` binds loopback port 8000.

## Database entities

```mermaid
erDiagram
    postings {
        serial id PK
        text source "Unique together with source_id"
        text source_id
        text title
        text dedupe_key
        timestamptz expires_at
    }
    ats_companies {
        text platform "Unique together with slug; no primary key"
        text slug
        timestamptz added_at
    }
    profile {
        serial id PK
        timestamptz created_at
        text text
        jsonb filters
    }
    profile_sections {
        serial id PK
        int profile_id FK
        text name
        text text
        vector embedding
        text embedding_model
    }
    matches {
        int posting_id FK "Unique together with profile_id; no primary key"
        int profile_id FK
        double similarity
        double percentile
        bool queued
        text explanation
    }
    source_runs {
        serial id PK
        text source
        timestamptz started_at
        text status
        int fetched
        text error
    }
    posting_analysis {
        int posting_id PK, FK
        text seniority
        text[] required_languages
        text[] employment_types
        jsonb salary
        text model
    }
    reviews {
        int posting_id PK, FK
        text action
        text reason
        text note
        timestamptz decided_at
    }
    profile |o..o{ profile_sections : has
    profile |o..o{ matches : ranks
    postings |o..o{ matches : receives
    postings ||..o| posting_analysis : has
    postings ||..o| reviews : has
```

All eight tables are shown with their keys and three to five selected non-key columns; the small `ats_companies` table has only three columns total.
`matches` and `ats_companies` have composite UNIQUE constraints, not primary keys; `postings` also uniquely identifies `(source, source_id)`.
Nullable foreign keys use optional parent cardinality; analysis and reviews share the posting ID as their primary and foreign key.
`source_runs.source` and `ats_companies` have no foreign-key relationship to postings; the greatest `profile.id` is the active version.

## Daily run

```mermaid
sequenceDiagram
    participant Timer as jagent.timer
    participant Service as jagent.service
    participant Daily as deploy/daily.sh
    participant Run as CLI run / runner
    participant Sources as API, RSS, HTML, laptop import, ATS
    participant DB as Postgres
    participant Match as CLI match
    participant Router as Configured API / TokenRouter
    participant Analyze as CLI analyze
    participant Health as CLI health

    Timer->>Service: 07:00 Europe/Tirane, catch missed activation
    Service->>Daily: ExecStart daily.sh
    Daily->>Run: uv run jagent run
    loop Eleven named sources, sequentially
        Run->>Sources: fetch()
        Sources-->>Run: Parsed postings or exception
        alt Fetch and persistence succeed
            Run->>DB: Merge duplicates or insert/update postings
            Run->>DB: Discover ATS slugs from newly inserted postings
            Run->>DB: Record source_runs status ok, commit
        else Source fails
            Run->>DB: Roll back source writes if needed, record error run
        end
    end
    Run->>DB: Read registered ATS platform/slug pairs
    DB-->>Run: Company boards
    loop Each registered ATS board
        Run->>Sources: ats.fetch(platform, slug)
        Sources-->>Run: Parsed postings or exception
        Run->>DB: Save postings and discoveries, record ok, or record error
    end
    Run-->>Daily: Exit 1 if any source failed, otherwise 0
    Daily->>Match: uv run jagent match, even if run failed
    Match->>DB: Load active profile, sections and postings
    loop Missing or different-model section vectors, batches up to 100
        Match->>Router: POST /v1/embeddings, up to two attempts
        Router-->>Match: Vectors or failure
        Match->>DB: Cache successful batch vectors and model, commit
    end
    Note over Match: Filter postings for activity, title and location eligibility
    loop Eligible postings needing vectors, batches up to 100
        Match->>Router: POST /v1/embeddings, up to two attempts
        Router-->>Match: Vectors or failure
        Match->>DB: Cache successful batch vectors and model, commit
    end
    Match->>DB: Clear active-profile queue flags, cosine score best section
    Match->>DB: Upsert percentiles and queue flags, commit
    Match-->>Daily: Exit status using failed batch fraction
    Daily->>Analyze: uv run jagent analyze, even if match failed
    Analyze->>DB: Load active profile and queued postings with missing/different analysis model
    loop Each selected posting in similarity order
        Analyze->>Router: POST /v1/chat/completions with whole profile and job
        Router-->>Analyze: JSON facts, evidence and explanation
        Note over Analyze: Validate schema and verbatim evidence, retry once on supported failures
        opt Valid result within two attempts
            Analyze->>DB: Upsert posting_analysis and match explanation, commit
        end
    end
    Analyze-->>Daily: Exit status using failed posting fraction
    Daily->>Health: uv run jagent health, even if analyze failed
    Health->>DB: Latest runs per source and seven-day median fetched
    DB-->>Health: Status, yield and freshness
    Health-->>Daily: Print problems, exit 1 if any, otherwise 0
    Daily-->>Service: Exit 1 if any command failed, otherwise 0
```

`daily.sh` logs each command in UTC and attempts all four commands even when an earlier command fails.
Each source is isolated; a failed source records an error run while later sources continue, including registered ATS boards.
Matching reuses vectors by model, scores the best compatible profile section, and queues similarity ≥ 0.55 with percentile ≥ 97.
Analysis reuses results by model; matching and analysis fail the CLI when all attempts fail or failures exceed 10%, while health flags source errors, stale non-ATS runs, and low full-feed yield.
The API participant uses the configured base URLs; health exempts incremental Himalayas/Djinni from yield checks and aggregates ATS board errors.

## Posting lifecycle

```mermaid
stateDiagram-v2
    state "Posting processing and review" as Live {
        state "Fetched" as Fetched
        state "Merged as duplicate" as Merged
        state "Stored canonical posting" as Stored
        state "Filtered out" as Filtered
        state "Embedded" as Embedded
        state "Ranked" as Ranked
        state "Queued" as Queued
        state "Analysed" as Analysed
        state "Reviewed" as Reviewed
        state "Apply" as Apply
        state "Skip" as Skip
        state "Later" as Later
        [*] --> Fetched: Source returns a validated Posting
        Fetched --> Merged: Nonempty normalized company plus title key already exists
        Merged --> Stored: Continue with earliest canonical row, union URLs and locations, OR remote
        Fetched --> Stored: No key match, insert or update by source and source_id
        Stored --> Filtered: Active but excluded title or remote term, or location not allowed
        Filtered --> Stored: Later matching or saved filters make posting eligible
        Stored --> Embedded: Active and passes filters, current model vector cached or embedding succeeds
        Stored --> Stored: Embedding batch fails twice, retry missing vector next match
        Embedded --> Ranked: Compatible current model section exists, best cosine score and percentile computed
        Ranked --> Queued: Percentile at least 97 AND similarity at least 0.55
        Ranked --> Ranked: Below either threshold, remains unqueued
        Queued --> Ranked: Next match clears flags and rescoring misses either threshold
        Queued --> Filtered: Next match finds active posting fails profile filters
        Queued --> Analysed: Missing or different analysis model, JSON and evidence validate within two attempts
        Queued --> Queued: Analysis fails twice, no new analysis saved, retry next analyze
        Analysed --> Analysed: Same analysis model cached, analyze does not call API
        Analysed --> Reviewed: User submits valid review action
        Queued --> Reviewed: Review endpoint accepts valid action even without analysis
        Reviewed --> Apply: Submitted action is apply
        Reviewed --> Skip: Submitted action is skip with an allowed reason
        Reviewed --> Later: Submitted action is later
        Later --> Queued: Still queued for active profile, later remains in queue after unreviewed rows
        Apply --> Reviewed: Another valid review overwrites previous decision
        Skip --> Reviewed: Another valid review overwrites previous decision
    }
    state "Expired / inactive" as Expired
    [*] --> Live: Source fetch begins
    Live --> Expired: expires_at is at or before now, otherwise posted_at or first_seen is over 30 days old
    note right of Expired
        Computed activity, not a stored status.
        Missing or future fallback dates are also inactive.
        Next match clears queued, rows and reviews remain.
    end note
```

These are logical stages across `postings`, `matches`, `posting_analysis`, and `reviews`; duplicate merging retains the earliest canonical posting rather than creating another row.
Filters reject excluded terms, then accept remote postings without locations or require allowed countries/remote regions; activity uses the explicit deadline before the 30-day fallback.
Ranking uses the recent 30-day scored cohort for percentiles; failed embedding/analysis work can retry on later runs, and existing vectors/results are reused by model.
Reviews require no analysis; apply moves to Applied, skip requires a reason and leaves the queue, and later stays queued subject to dashboard view filters (seniority, languages, contract).
Expiry is evaluated during filtering, not by a background state transition; the dashboard relies on stored queue flags, and Applied retains reviews even after expiry.
