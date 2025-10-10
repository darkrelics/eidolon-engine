# Incremental Subsystem Architecture Diagrams

This document provides visual architecture diagrams for the Eidolon Engine incremental subsystem using Mermaid.js.

## Table of Contents

1. [System Context (C4 Level 1)](#system-context-c4-level-1)
2. [Container Architecture (C4 Level 2)](#container-architecture-c4-level-2)
3. [Component Architecture (C4 Level 3)](#component-architecture-c4-level-3)
4. [State Machines](#state-machines)
5. [Hot Path Flows](#hot-path-flows)
6. [Data Flow Diagrams](#data-flow-diagrams)

---

## System Context (C4 Level 1)

The system context diagram shows how players interact with both game subsystems through a unified authentication layer.

```mermaid
graph TB
    Player[Player<br/>Web Browser]

    subgraph "Eidolon Engine"
        Incremental[Incremental Game System<br/>Timer-based Story Progression]
        MUD[MUD System<br/>Real-time Text Adventure]
    end

    Auth[AWS Cognito<br/>Authentication]

    Player -->|Plays Stories| Incremental
    Player -->|Plays MUD| MUD
    Player -->|Authenticates| Auth

    Incremental -.->|Shares Character Data| MUD
    MUD -.->|Shares Character Data| Incremental

    Auth -->|Validates| Incremental
    Auth -->|Validates| MUD

    style Incremental fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
    style MUD fill:#7B68EE,stroke:#5248B8,stroke-width:2px,color:#fff
    style Player fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style Auth fill:#F39C12,stroke:#C87F0A,stroke-width:2px,color:#000
```

---

## Container Architecture (C4 Level 2)

The container architecture shows the major AWS services and how they interact to provide the incremental game system.

```mermaid
graph TB
    subgraph "Client Layer"
        Flutter[Flutter Web App<br/>Incremental UI]
    end

    subgraph "AWS Cloud"
        subgraph "API Layer"
            APIGW[API Gateway<br/>REST Endpoints]
            Cognito[Cognito User Pool<br/>Authentication]
        end

        subgraph "Compute Layer"
            APILambda[API Lambda Functions<br/>16 Functions]
            OpsLambda[Operational Lambdas<br/>Poller, Process, Advance]
        end

        subgraph "Event Layer"
            EventBridge[EventBridge<br/>1-min Story Poller]
            ProcessQ[SQS: Processing Queue<br/>Mechanical Segments]
            AdvanceQ[SQS: Advancement Queue<br/>Completed Segments]
        end

        subgraph "Data Layer"
            DynamoDB[(DynamoDB<br/>14 Tables)]
            S3[(S3<br/>Story Content)]
        end

        subgraph "Observability"
            CloudWatch[CloudWatch<br/>Logs & Metrics]
        end
    end

    Flutter -->|HTTPS| APIGW
    APIGW -->|Authorize| Cognito
    APIGW -->|Invoke| APILambda

    APILambda -->|Read/Write| DynamoDB
    APILambda -->|Enqueue| ProcessQ

    EventBridge -->|Every 1 min| OpsLambda
    ProcessQ -->|Trigger| OpsLambda
    AdvanceQ -->|Trigger| OpsLambda

    OpsLambda -->|Read/Write| DynamoDB
    OpsLambda -->|Enqueue| AdvanceQ
    OpsLambda -->|Load Content| S3

    APILambda -.->|Log| CloudWatch
    OpsLambda -.->|Log| CloudWatch

    style Flutter fill:#02569B,stroke:#014B87,stroke-width:2px,color:#fff
    style APIGW fill:#FF9900,stroke:#CC7A00,stroke-width:2px,color:#000
    style DynamoDB fill:#4053D6,stroke:#2E3B99,stroke-width:2px,color:#fff
    style EventBridge fill:#E7157B,stroke:#B8115F,stroke-width:2px,color:#fff
    style CloudWatch fill:#FF4F8B,stroke:#CC3F6F,stroke-width:2px,color:#fff
```

---

## Component Architecture (C4 Level 3)

### Lambda Functions & Eidolon Library

The component architecture details how Lambda functions interact with the shared eidolon library modules to implement game logic.

```mermaid
graph TB
    subgraph "API Lambda Functions"
        StoryStart[api-story-start<br/>POST /story/start]
        StoryAbandon[api-story-abandon<br/>POST /story/abandon]
        SegmentDecision[api-segment-decision<br/>POST /segment/decision]
        SegmentStatus[api-segment-status<br/>GET /segment/status]
        SegmentHistory[api-segment-history<br/>GET /segment/history]
        CharGet[api-character-get<br/>GET /character]
    end

    subgraph "Operational Lambda Functions"
        Poller[ops-segment-poller<br/>EventBridge Triggered]
        Process[ops-segment-process<br/>SQS Triggered]
        Advance[ops-story-advance<br/>SQS Triggered]
    end

    subgraph "Eidolon Library Modules"
        subgraph "State Management"
            SegState[segment_state.py<br/>ProcessingStatus FSM]
            StoryActive[story_active.py<br/>Story Activation]
            StoryComp[story_completion.py<br/>Story Completion]
        end

        subgraph "Processing Logic"
            SegProc[segment_processing.py<br/>Outcome Calculation]
            SegCombat[segment_combat.py<br/>Combat Resolution]
            SegChal[segment_challenges.py<br/>Skill Checks]
            Branching[branching.py<br/>Weighted Branching]
        end

        subgraph "Data Access"
            CharData[character_data.py<br/>Character CRUD]
            StoryRet[story_retrieval.py<br/>Story Loading]
            Items[items.py<br/>Inventory Mgmt]
            Dynamo[dynamo.py<br/>DDB Wrapper]
        end

        subgraph "Core Mechanics"
            Mechanics[mechanics.py<br/>XP & Skill System]
        end
    end

    StoryStart --> StoryActive
    StoryStart --> SegState
    StoryStart --> CharData

    Poller --> SegState
    Poller --> Dynamo

    Process --> SegProc
    Process --> SegCombat
    Process --> SegChal

    Advance --> StoryComp
    Advance --> Branching
    Advance --> Items

    SegProc --> Mechanics
    SegCombat --> Mechanics
    SegChal --> Mechanics

    style StoryStart fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    style Poller fill:#E74C3C,stroke:#C0392B,stroke-width:2px,color:#fff
    style Process fill:#E67E22,stroke:#CA6F1E,stroke-width:2px,color:#fff
    style Advance fill:#16A085,stroke:#138D75,stroke-width:2px,color:#fff
```

---

## State Machines

### Character GameMode State Machine

The GameMode state machine enforces exclusive access to characters, preventing simultaneous play in both MUD and Incremental modes.

```mermaid
stateDiagram-v2
    [*] --> None: Character Created

    None --> Incremental: api-story-start
    None --> MUD: MUD Login

    Incremental --> None: Story Complete
    Incremental --> None: Story Abandoned
    Incremental --> None: Death Outcome

    MUD --> None: MUD Logout

    None --> [*]: Character Deleted

    note right of Incremental
        No direct transition
        between MUD and Incremental
        Must return to None first
    end note

    note left of None
        Default fail-safe state
        Ensures exclusive mode access
    end note
```

### Segment ProcessingStatus State Machine

The ProcessingStatus state machine uses atomic DynamoDB conditional writes to prevent duplicate processing of segments.

```mermaid
stateDiagram-v2
    [*] --> pending: Mechanical Segment Created
    [*] --> processed: Decision Segment Created

    pending --> processing: claim_segment_for_processing
    processing --> processed: Outcomes Calculated

    processed --> archived: ops-story-advance
    archived --> [*]: Copied to SegmentHistory

    note right of processing
        Atomic conditional write
        prevents duplicate processing
    end note

    note left of processed
        Segments wait here until
        EndTime expires
    end note
```

### Story Lifecycle State Machine

Stories transition from available to active when started, and eventually move to completed or abandoned based on player actions and outcomes.

```mermaid
stateDiagram-v2
    [*] --> Available: Story Defined

    Available --> Active: api-story-start<br/>Prerequisites Met
    Available --> Available: Prerequisites Not Met

    Active --> Completed: Final Segment<br/>Any Outcome
    Active --> Abandoned: api-story-abandon<br/>Player Quit

    Completed --> [*]: Moved to StoryHistory
    Abandoned --> [*]: Moved to StoryHistory

    note right of Active
        Character ActiveStoryID set
        GameMode = Incremental
    end note

    note left of Completed
        Includes: success, failure,
        death, minimal, normal,
        exceptional outcomes
    end note
```

---

## Hot Path Flows

### Story Start Flow

The story start flow validates prerequisites, creates the first segment, and queues mechanical processing immediately.

```mermaid
sequenceDiagram
    participant C as Client
    participant API as API Gateway
    participant Lambda as api-story-start
    participant DDB as DynamoDB
    participant SQS as Processing Queue

    C->>API: POST /story/start<br/>CharacterID, StoryID
    API->>Lambda: Invoke

    Lambda->>DDB: Get Character
    DDB-->>Lambda: Character Data

    Lambda->>Lambda: Validate Prerequisites<br/>Check GameMode = None

    Lambda->>DDB: Get Story and First Segment
    DDB-->>Lambda: Story Definition

    Lambda->>Lambda: Calculate Segment EndTime<br/>Create ActiveSegmentID

    Lambda->>DDB: Transaction:<br/>Update Character GameMode, ActiveStoryID<br/>Create ActiveSegment pending
    DDB-->>Lambda: Success

    alt Mechanical Segment
        Lambda->>SQS: Enqueue for Processing
    end

    Lambda->>Lambda: Enable Poller SSM

    Lambda-->>API: Segment Details<br/>ID, Type, EndTime
    API-->>C: 200 OK with Segment
```

### Segment Processing Flow (Mechanical)

Mechanical segments are claimed atomically, processed to calculate outcomes, and marked as processed with results stored.

```mermaid
sequenceDiagram
    participant SQS as Processing Queue
    participant Process as ops-segment-process
    participant DDB as DynamoDB
    participant Mech as mechanics.py

    SQS->>Process: Trigger ActiveSegmentID

    Process->>DDB: Claim Segment<br/>pending to processing

    alt Claim Success
        DDB-->>Process: Segment Data

        Process->>Mech: ResolveStaticCheckWithXP<br/>for each Challenge
        Mech-->>Process: success, sigma, xp

        Process->>Mech: ResolveOpposedCheckWithXP<br/>for Combat
        Mech-->>Process: attacker_dmg, defender_dmg, xp

        Process->>Process: Calculate Outcome<br/>death, failure, minimal, normal, exceptional

        Process->>Process: Generate ClientEvents<br/>Generate CharacterUpdates

        Process->>DDB: Update ActiveSegment<br/>processing to processed<br/>with Outcomes and Events
        DDB-->>Process: Success
    else Already Claimed
        DDB-->>Process: Conditional Write Failed
        Process->>Process: Idempotent Exit (OK)
    end
```

### Story Advancement Flow

The advancement flow finds completed segments via polling, applies character updates, and creates the next segment or completes the story.

```mermaid
sequenceDiagram
    participant EB as EventBridge
    participant Poller as ops-segment-poller
    participant DDB as DynamoDB
    participant SQS as Advancement Queue
    participant Advance as ops-story-advance

    EB->>Poller: Trigger Every 1 min

    Poller->>DDB: Query EndTimeIndex<br/>EndTime less than or equal Now
    DDB-->>Poller: Completed Segments

    loop For Each Segment
        Poller->>SQS: Enqueue to Advancement Queue
    end

    SQS->>Advance: Trigger ActiveSegmentID

    Advance->>DDB: Get ActiveSegment and Character
    DDB-->>Advance: Segment and Character Data

    Advance->>Advance: Apply CharacterUpdates<br/>XP, Wounds, Items, Room

    alt Story Continues
        Advance->>Advance: Select Next Branch<br/>Weighted Random
        Advance->>DDB: Create Next ActiveSegment
    else Story Ends
        Advance->>DDB: Update Character<br/>GameMode = None, Clear ActiveStory
        Advance->>DDB: Write StoryHistory<br/>FinalOutcome, Totals
    end

    Advance->>DDB: Delete ActiveSegment
    Advance->>DDB: Write SegmentHistory
```

---

## Data Flow Diagrams

### DynamoDB Table Relationships

The entity relationship diagram shows how the 14 DynamoDB tables connect to support character progression and story tracking.

```mermaid
erDiagram
    PLAYERS ||--o{ CHARACTERS : owns
    CHARACTERS ||--o| ACTIVE_SEGMENTS : has_active
    CHARACTERS ||--o{ STORY_HISTORY : completed
    CHARACTERS ||--o{ SEGMENT_HISTORY : played
    CHARACTERS ||--o{ ITEMS : owns

    STORY ||--o{ SEGMENTS : contains
    SEGMENTS ||--o| ACTIVE_SEGMENTS : instantiated_as

    ARCHETYPES ||--o{ CHARACTERS : defines
    PROTOTYPES ||--o{ ITEMS : created_from
    OPPONENTS ||--o{ SEGMENTS : used_in

    PLAYERS {
        string PlayerID PK
        list CharacterList
        string Email
    }

    CHARACTERS {
        string CharacterID PK
        string PlayerID FK
        string GameMode
        string ActiveStoryID
        string ActiveSegmentID
        map Skills
        map Attributes
        list Wounds
        string RoomID
    }

    STORY {
        string StoryID PK
        string Title
        string StoryType
        string FirstSegmentID
        map Prerequisites
    }

    SEGMENTS {
        string StoryID PK
        string SegmentID SK
        string SegmentType
        number SegmentDuration
        map Results
        list Challenges
        map Combat
    }

    ACTIVE_SEGMENTS {
        string ActiveSegmentID PK
        string CharacterID GSI
        string ProcessingStatus
        number StartTime
        number EndTime GSI
        list ClientEvents
        map CharacterUpdates
        string Outcome
        map BranchMetadata
    }

    STORY_HISTORY {
        string CharacterID PK
        string StoryInstanceID SK
        string StoryID
        string FinalOutcome
        list SegmentHistory
        map SkillXPAwarded
        map AttributeXPAwarded
    }

    SEGMENT_HISTORY {
        string CharacterID PK
        string ActiveSegmentID SK
        string StoryInstanceID
        map CharacterUpdates
        string Outcome
        number ProcessedAt
        map BranchMetadata
    }
```

### Event Flow Architecture

The event-driven architecture uses EventBridge for time-based triggers and SQS queues for asynchronous processing of segments.

```mermaid
graph LR
    subgraph "Event Sources"
        API[API Calls]
        Timer[EventBridge<br/>1-min Timer]
    end

    subgraph "Event Processors"
        APILambda[API Lambdas]
        Poller[ops-segment-poller]
    end

    subgraph "Processing Queues"
        ProcessQ[Processing Queue<br/>Mechanical Segments]
        AdvanceQ[Advancement Queue<br/>Completed Segments]
    end

    subgraph "Workers"
        Process[ops-segment-process]
        Advance[ops-story-advance]
    end

    subgraph "State Store"
        DDB[(DynamoDB)]
    end

    API -->|Invoke| APILambda
    Timer -->|Trigger| Poller

    APILambda -->|Enqueue| ProcessQ
    APILambda -->|Write| DDB

    Poller -->|Query| DDB
    Poller -->|Enqueue| AdvanceQ

    ProcessQ -->|Trigger| Process
    AdvanceQ -->|Trigger| Advance

    Process -->|Update| DDB
    Advance -->|Update| DDB
    Advance -->|Enqueue| ProcessQ

    style ProcessQ fill:#FF6B6B,stroke:#CC5555,stroke-width:2px,color:#fff
    style AdvanceQ fill:#4ECDC4,stroke:#3EA39C,stroke-width:2px,color:#fff
    style DDB fill:#4053D6,stroke:#2E3B99,stroke-width:2px,color:#fff
```

### Weighted Branching Flow

The weighted branching system filters branches by prerequisites, renormalizes weights, and uses cryptographic randomness for selection.

```mermaid
flowchart TD
    Start([Segment Complete]) --> GetOutcome[Get Outcome Result<br/>death, failure, minimal, normal, exceptional]

    GetOutcome --> GetBranches[Load Results Outcome Branches]

    GetBranches --> HasBranches{Branches<br/>Defined?}

    HasBranches -->|No| UseFallback[Use FallbackSegmentID]
    HasBranches -->|Yes| FilterPrereq[Filter by Prerequisites<br/>MinSkills, MinAttributes, RequiredItems]

    FilterPrereq --> AnyAvail{Any Available<br/>Branches?}

    AnyAvail -->|No| UseFallback
    AnyAvail -->|Yes| Renormalize[Renormalize Weights<br/>Sum to 1.0]

    Renormalize --> RandomSelect[Cryptographic Random Selection<br/>secrets.randbelow]

    RandomSelect --> RecordMeta[Record BranchMetadata<br/>SelectionMethod, BranchLabel]

    RecordMeta --> CreateNext[Create Next ActiveSegment]

    UseFallback --> CreateNext

    CreateNext --> End([Continue Story])

    style GetOutcome fill:#FFD93D,stroke:#CCB031,stroke-width:2px,color:#000
    style FilterPrereq fill:#6BCB77,stroke:#56A360,stroke-width:2px,color:#fff
    style RandomSelect fill:#4D96FF,stroke:#3D78CC,stroke-width:2px,color:#fff
    style RecordMeta fill:#FF6B9D,stroke:#CC567E,stroke-width:2px,color:#fff
```

---

## Deployment Architecture

The deployment architecture shows the complete AWS infrastructure created by CDK and the CI/CD pipeline for story validation.

```mermaid
graph TB
    subgraph "Developer"
        Dev[Developer<br/>Workstation]
    end

    subgraph "CI/CD"
        GH[GitHub Actions<br/>Story Validation]
        CDK[AWS CDK<br/>Infrastructure as Code]
    end

    subgraph "AWS Account"
        subgraph "Compute"
            Lambda[16 Lambda Functions<br/>Python 3.12]
            Layer[Lambda Layer<br/>eidolon Library]
        end

        subgraph "Storage"
            Tables[(14 DynamoDB Tables<br/>On-Demand)]
            Bucket[S3 Buckets<br/>Content & Artifacts]
        end

        subgraph "Networking"
            APIGW[API Gateway<br/>REST API]
            CF[CloudFront<br/>CDN]
        end

        subgraph "Security"
            Cognito[Cognito User Pool]
            IAM[IAM Roles & Policies]
        end

        subgraph "Monitoring"
            CW[CloudWatch<br/>Logs & Metrics]
            EB[EventBridge<br/>Poller Rule]
        end
    end

    Dev -->|Push Code| GH
    GH -->|Validate Stories| GH
    GH -->|Deploy| CDK

    CDK -->|Create/Update| Lambda
    CDK -->|Create/Update| Tables
    CDK -->|Create/Update| APIGW
    CDK -->|Create/Update| Cognito

    Lambda -->|Use| Layer
    Lambda -->|Access| Tables
    Lambda -->|Read| Bucket
    Lambda -->|Log to| CW

    APIGW -->|Authorize| Cognito
    APIGW -->|Invoke| Lambda

    CF -->|Serve UI| Bucket
    EB -->|Trigger| Lambda

    style Dev fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style CDK fill:#FF9900,stroke:#CC7A00,stroke-width:2px,color:#000
    style Lambda fill:#FF9900,stroke:#CC7A00,stroke-width:2px,color:#000
    style Tables fill:#4053D6,stroke:#2E3B99,stroke-width:2px,color:#fff
```

---

## Failure Recovery Patterns

The failure recovery pattern uses atomic claims, idempotent processing, and exponential backoff to handle errors gracefully.

```mermaid
flowchart TD
    Start([Request Initiated]) --> Lambda[Lambda Invoked]

    Lambda --> Claim{Atomic Claim<br/>Success?}

    Claim -->|Yes| Process[Process Work]
    Claim -->|No| AlreadyClaimed[Already Claimed<br/>by Another]

    AlreadyClaimed --> IdemExit[Idempotent Exit<br/>Return Success]

    Process --> Update{Update State<br/>Success?}

    Update -->|Yes| Complete[Work Complete]
    Update -->|No| Retry{Retryable?}

    Retry -->|Yes| Backoff[Exponential Backoff]
    Retry -->|No| DLQ[Send to DLQ]

    Backoff --> Lambda

    Process -->|Timeout| Timeout[Lambda Timeout]
    Timeout --> Requeue[Auto-Retry via SQS]
    Requeue --> Lambda

    Process -->|Exception| Exception[Unhandled Error]
    Exception --> Logged[Log to CloudWatch]
    Logged --> Requeue

    Complete --> Cleanup[Delete from Queue]
    IdemExit --> Cleanup

    Cleanup --> End([Success])
    DLQ --> Alert[CloudWatch Alarm]

    style Claim fill:#FFD93D,stroke:#CCB031,stroke-width:2px,color:#000
    style IdemExit fill:#6BCB77,stroke:#56A360,stroke-width:2px,color:#fff
    style DLQ fill:#FF6B6B,stroke:#CC5555,stroke-width:2px,color:#fff
    style Alert fill:#FF4757,stroke:#CC3946,stroke-width:2px,color:#fff
```

---

## Summary

These diagrams provide multiple views of the incremental subsystem architecture:

1. **C4 Diagrams** - System, Container, and Component levels for different audiences
2. **State Machines** - Formal state transition diagrams for GameMode, ProcessingStatus, and Story lifecycle
3. **Sequence Diagrams** - Hot path flows showing exact interaction patterns
4. **Entity Relationship** - DynamoDB table structure and relationships
5. **Data Flow** - Event-driven architecture and processing pipelines
6. **Deployment** - AWS infrastructure and CI/CD pipeline
7. **Failure Recovery** - Error handling and retry patterns

Each diagram uses Mermaid.js syntax and can be rendered in GitHub, documentation tools, or any Mermaid-compatible viewer.
