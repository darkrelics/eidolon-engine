# Eidolon Engine Incremental Game Technical Design Document

## 1. Executive Summary

This document provides the technical design specifications for implementing the Incremental Game component of the Eidolon Engine. It details the system architecture, data flows, API specifications, and integration patterns required to deliver a timer-based story progression system that seamlessly integrates with the existing MUD infrastructure.

## 2. System Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Flutter Web    │────▶│   API Gateway    │────▶│ Lambda Functions│
│  Application    │     │   (REST API)     │     │  (Python 3.12)  │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
         ┌─────────────────────────────────────────────────┼────────────────┐
         │                                                 │                │
   ┌─────▼──────┐          ┌───────────────┐     ┌───────▼──────┐  ┌──────▼──────┐
   │  DynamoDB  │◀─────────│ Fargate       │     │  DynamoDB    │  │ CloudWatch  │
   │  Tables    │ Streams  │ Timing Service│     │  Streams     │  │   Logs      │
   └────────────┘          └───────────────┘     └──────────────┘  └─────────────┘
```

### 2.2 Component Interactions

The Incremental Game system operates as a parallel gameplay mode to the MUD, sharing the same backend infrastructure but providing a distinct user experience through:

1. **Shared Data Layer**: Common DynamoDB tables for character data
2. **Mode Exclusivity**: Mutex-like locking preventing concurrent access
3. **Timing Service**: Fargate container managing story progression
4. **Stateless Compute**: Lambda functions for all user-initiated actions
5. **Stream Processing**: DynamoDB Streams triggering timing updates

## 3. Data Architecture

### 3.1 DynamoDB Table Designs

#### 3.1.1 Stories Table
```python
# Primary Key Structure
PK: STORY#{storyId}
SK: METADATA

# Attributes
{
    "PK": "STORY#adv_forest_001",
    "SK": "METADATA",
    "storyId": "adv_forest_001",
    "storyType": "daily",  # one-time|daily|repeatable
    "title": "The Whispering Woods",
    "description": "A mysterious force draws you into the ancient forest...",
    "estimatedDuration": 3600,  # seconds
    "prerequisites": {
        "minSkills": {
            "survival": 10,
            "combat": 5
        },
        "requiredItems": ["map_fragment"],
        "requiredRooms": ["town_square"]
    },
    "segments": [
        {
            "segmentId": "seg_001",
            "type": "decision",
            "content": "You stand at the forest edge. The path splits...",
            "imageUrl": "s3://bucket/images/forest_edge.jpg",
            "duration": 300,  # 5 minutes
            "options": [
                {
                    "id": "opt_left",
                    "text": "Take the moonlit path",
                    "skillChecks": ["perception", "nature"]
                },
                {
                    "id": "opt_right",
                    "text": "Follow the ancient markers",
                    "skillChecks": ["history", "navigation"]
                }
            ],
            "defaultDecisionLogic": "highest_skill:perception,nature,history,navigation"
        },
        {
            "segmentId": "seg_002",
            "type": "narrative",
            "duration": 600,  # 10 minutes
            "content": {
                "base": "You venture deeper into the woods...",
                "outcomes": {
                    "death": {
                        "text": "The forest claims another victim...",
                        "effects": {
                            "health": 0,
                            "room": "death_realm"
                        }
                    },
                    "failure": {
                        "text": "You stumble through brambles...",
                        "effects": {
                            "health": -20,
                            "experience": 10
                        }
                    },
                    "minimal": {
                        "text": "You make slow progress...",
                        "effects": {
                            "health": -5,
                            "experience": 25
                        }
                    },
                    "normal": {
                        "text": "You navigate successfully...",
                        "effects": {
                            "experience": 50,
                            "items": ["herb_bundle"]
                        }
                    },
                    "exceptional": {
                        "text": "Your expertise shines through...",
                        "effects": {
                            "experience": 100,
                            "items": ["rare_herb", "gold:50"],
                            "skills": {"survival": 1}
                        }
                    }
                }
            }
        }
    ],
    "created": "2025-01-15T10:00:00Z",
    "version": 1
}
```

#### 3.1.2 StoryParticipation Table
```python
# Primary Key Structure
PK: CHAR#{characterId}
SK: STORY#{storyId}#{timestamp}

# GSI for Active Stories
GSI1PK: ACTIVE#{characterId}
GSI1SK: STORY#{storyId}

# GSI for Timing Service
GSI2PK: COMPLETION#{YYYY-MM-DD-HH}
GSI2SK: {completionTimestamp}#{characterId}

# Attributes
{
    "PK": "CHAR#abc123",
    "SK": "STORY#adv_forest_001#1737000000",
    "GSI1PK": "ACTIVE#abc123",  # Only for active stories
    "GSI1SK": "STORY#adv_forest_001",
    "GSI2PK": "COMPLETION#2025-01-15-10",  # Hour bucket for timing service
    "GSI2SK": "1737003600#abc123",  # Next completion time
    "characterId": "abc123",
    "storyId": "adv_forest_001",
    "status": "active",  # active|completed|abandoned
    "currentSegment": "seg_002",
    "segmentStartTime": 1737000300,
    "nextCompletionTime": 1737003600,  # When current segment completes
    "storyStartTime": 1737000000,
    "lastActivityTime": 1737000300,
    "decisions": {
        "seg_001": {
            "choice": "opt_left",
            "timestamp": 1737000250,
            "automated": false
        }
    },
    "outcomes": [
        {
            "segmentId": "seg_002",
            "result": "normal",
            "timestamp": 1737000900,
            "effects": {
                "experience": 50,
                "items": ["herb_bundle"]
            }
        }
    ],
    "ttl": 1737086400  # 24 hours for active, indefinite for completed
}
```

#### 3.1.3 Character Table Updates
```python
# Existing character record with incremental additions
{
    "PK": "CHAR#abc123",
    "SK": "PROFILE",
    # ... existing MUD fields ...
    
    # Incremental Game additions
    "gameMode": {
        "mode": "Incremental",  # MUD|Incremental|None
        "lastTransition": 1737000000,
        "activeStoryId": "adv_forest_001",
        "lockExpiration": 1737003600,  # 1 hour timeout
        "lockToken": "uuid-v4-token"  # For distributed lock verification
    },
    "availableStories": [
        "adv_forest_001",
        "daily_patrol_001",
        "tutorial_001"
    ],
    "storyStats": {
        "completed": 15,
        "abandoned": 3,
        "lastDaily": "2025-01-15"
    }
}
```

### 3.2 Data Access Patterns

#### 3.2.1 Primary Access Patterns
1. **Get Available Stories**: Query character's availableStories list
2. **Check Story Participation**: Query StoryParticipation by characterId + storyId
3. **Get Active Story**: GSI query for ACTIVE#{characterId}
4. **Update Segment Progress**: Transactional write to StoryParticipation
5. **Mode Transition**: Conditional update on Character gameMode
6. **Timing Queue**: GSI2 query by completion hour bucket

#### 3.2.2 Secondary Access Patterns
1. **Daily Reset**: Batch update for daily story availability
2. **Timeout Processing**: Query GSI2 for expired segments
3. **Analytics Aggregation**: Stream processing of completion events

## 4. API Design

### 4.1 RESTful Endpoints

#### 4.1.1 Story Management APIs

**GET /incremental/stories/available**
```
Purpose: Retrieve stories available to the character
Headers: Authorization: Bearer {cognito-jwt-token}
Response: List of available stories with cooldowns and prerequisites
```

**POST /incremental/stories/start**
```
Purpose: Initialize a new story participation
Request: { "storyId": "adv_forest_001" }
Response: Current segment details and timing information
Error Cases: CHARACTER_MODE_CONFLICT, STORY_NOT_AVAILABLE
```

**GET /incremental/stories/current**
```
Purpose: Get current story state and progress
Response: Active story details, current segment, time remaining
```

#### 4.1.2 Segment Management APIs

**POST /incremental/segments/decision**
```
Purpose: Submit player decision for current segment
Request: { "decision": "opt_left" }
Response: Processing time until next segment
```

**GET /incremental/segments/result**
```
Purpose: Retrieve completed segment outcome
Query Parameters: segmentId
Response: Outcome narrative, effects, and next segment info
```

**POST /incremental/stories/abandon**
```
Purpose: Abandon current story
Response: Confirmation and character state reset
```

**POST /incremental/stories/rest**
```
Purpose: Pause story progression
Response: Rest duration and recovery effects
```

#### 4.1.3 Equipment Management APIs

**GET /incremental/equipment**
```
Purpose: Retrieve character inventory and equipped items
Response: Full inventory list with equipment slots
```

**POST /incremental/equipment/equip**
```
Purpose: Change equipped item
Request: { "itemId": "sword_steel_001", "slot": "weapon" }
Response: Success confirmation with previous item
```

**POST /incremental/equipment/purchase**
```
Purpose: Buy trivial items from shop
Request: { "itemId": "health_potion", "quantity": 5 }
Response: Purchase confirmation and remaining gold
```

### 4.2 Client Polling Strategy

The Flutter client implements intelligent polling based on game state:

1. **Active Segment Polling**
   - Start polling 30 seconds before expected completion
   - Exponential backoff: 30s, 15s, 5s, 2s, 1s
   - Immediate poll after segment completes

2. **Idle State**
   - Check every 5 minutes for story unlocks
   - Check on app resume/focus
   - No polling when no active story

3. **Decision Windows**
   - Poll every 30 seconds during decision segments
   - Immediate update after decision submission

## 5. Core Service Specifications

### 5.1 Lambda Functions

#### 5.1.1 StoryManager Lambda
**Purpose**: Handle story discovery, validation, and initialization

**Operations**:
- List available stories based on character state
- Validate story prerequisites and cooldowns
- Initialize story participation with mode locking
- Create DynamoDB Stream record for timing service

**Key Behaviors**:
- Performs transactional updates to ensure mode exclusivity
- Validates character not in MUD mode before starting
- Sets initial timing information for first segment
- Handles one-time/daily/repeatable story logic

#### 5.1.2 SegmentProcessor Lambda
**Purpose**: Process player decisions and retrieve outcomes

**Operations**:
- Record player decisions with timestamps
- Return calculated outcomes from timing service
- Handle decision timeouts with default logic
- Update story progression state

**Key Behaviors**:
- Validates decisions against current segment
- Caches character state for segments < 120 minutes
- Ensures progression rate doesn't exceed MUD speed
- Updates GSI2 timing indexes for next segment

#### 5.1.3 EquipmentManager Lambda
**Purpose**: Handle equipment and inventory operations

**Operations**:
- Retrieve current equipment and inventory
- Process equipment changes
- Handle trivial item purchases
- Validate equipment requirements

**Key Behaviors**:
- Prevents equipment changes during active combat
- Validates character owns items before equipping
- Maintains transaction logs for all changes

### 5.2 Fargate Timing Service

#### 5.2.1 Service Architecture

The timing service runs as a containerized application in ECS Fargate:

**Container Specifications**:
- Language: Python 3.12 or Go 1.24
- Memory: 4GB (for in-memory queue)
- vCPU: 1.0
- Desired Count: 2 (for redundancy)
- Auto-scaling: Based on queue depth

**Core Components**:
1. **Timing Queue Manager**: Maintains priority queue of upcoming completions
2. **DynamoDB Stream Processor**: Receives new stories and decisions
3. **Batch Processor**: Handles segment completions in batches
4. **State Checkpointer**: Periodically saves queue state
5. **Metrics Publisher**: Emits CloudWatch metrics

#### 5.2.2 Processing Flow

**Initialization**:
1. On startup, query GSI2 for all pending completions
2. Load into in-memory priority queue
3. Start DynamoDB Streams consumer
4. Begin processing loop

**Main Processing Loop**:
1. Every 10 seconds, check for due completions
2. Batch all completions within window
3. For each completion:
   - Retrieve story and segment data
   - Calculate outcome based on character stats
   - Apply effects to character
   - Update participation record
   - Add next segment to queue if applicable
4. Batch write all updates to DynamoDB
5. Emit metrics on processing performance

**Stream Processing**:
1. New story starts add first segment to queue
2. Player decisions update completion times
3. Story abandonment removes from queue
4. Mode changes trigger queue updates

**High Availability**:
- Two containers run simultaneously
- Partition work by character ID hash
- Use DynamoDB conditional writes to prevent double processing
- Checkpoint queue state every 5 minutes

#### 5.2.3 Outcome Calculation

The timing service implements the core game mechanics:

**Skill Check System**:
- Aggregate all relevant skills for the segment
- Apply equipment modifiers
- Calculate success probabilities
- Ensure outcomes align with MUD progression rates

**Default Decision Logic**:
- For timeouts, evaluate all options
- Select based on character's highest relevant skill
- Consider safety vs reward based on character state
- Log automated decisions for analytics

**Batch Optimization**:
- Group characters by similar segments
- Reuse calculated probabilities
- Minimize DynamoDB reads via caching
- Write results in 25-item batches

### 5.3 Daily Reset Process

A scheduled Lambda function handles daily resets:

1. **Trigger**: CloudWatch Events rule at midnight UTC
2. **Process**:
   - Query for all daily story completions
   - Reset completion flags for new day
   - Update character lastDaily timestamps
   - Clear daily story cooldowns
3. **Optimization**: Process in batches of 100 characters

## 6. Flutter Client Architecture

### 6.1 State Management

The Flutter app uses Riverpod for state management:

**Key Providers**:
- `characterProvider`: Current character state
- `storyProvider`: Active story and segment
- `timerProvider`: Local countdown timers
- `inventoryProvider`: Equipment and items

**State Synchronization**:
1. Initial load fetches all state
2. Actions trigger immediate API calls
3. Polling updates state based on timers
4. Local timers provide UI updates between polls

### 6.2 Polling Implementation

```
Polling Strategy:
- Use Timer.periodic for countdown displays
- HTTP polling based on expected completion
- Exponential backoff near completion time
- Immediate fetch after user actions
- Cancel timers when app backgrounds
```

### 6.3 Offline Handling

**Local Storage**:
- Cache current story state
- Store last known timers
- Queue actions when offline

**Reconnection**:
- Sync state on app resume
- Process queued actions
- Update timers from server

## 7. Security Considerations

### 7.1 Mode Lock Implementation

**Lock Acquisition Process**:
1. Check current mode is None or expired
2. Atomically update with conditional write
3. Set expiration time and generate token
4. Return token for subsequent operations

**Lock Validation**:
- All incremental operations verify mode
- MUD login checks for incremental lock
- Automatic cleanup of expired locks

### 7.2 Input Validation

**API Gateway Validation**:
- Request schemas for all endpoints
- Parameter format validation
- Rate limiting per character

**Lambda Validation**:
- Character ownership verification
- Story availability checks
- Decision option validation
- Timing window enforcement

## 8. Performance Optimization

### 8.1 Fargate Service Optimization

**Memory Management**:
- Use efficient data structures for queue
- Implement queue size limits
- Periodic garbage collection
- Memory profiling in production

**Batch Processing**:
- Group similar operations
- Minimize DynamoDB API calls
- Use parallel processing where safe
- Implement circuit breakers

### 8.2 DynamoDB Optimization

**Index Design**:
- GSI2 enables efficient time-based queries
- Partition timing data by hour buckets
- Project only necessary attributes

**Write Optimization**:
- Batch writes up to 25 items
- Use conditional writes sparingly
- Implement exponential backoff
- Monitor for hot partitions

### 8.3 Caching Strategy

**Lambda Caching**:
- Story definitions cached for 5 minutes
- Character state for active segments < 2 hours
- Use Lambda container reuse

**Client Caching**:
- Story list cached for session
- Timer states persisted locally
- Image assets cached indefinitely

## 9. Monitoring and Observability

### 9.1 Metrics

**Timing Service Metrics**:
- Queue depth
- Processing latency
- Completions per second
- Error rates by type
- Memory utilization

**API Metrics**:
- Request rates by endpoint
- Response times
- Error rates
- Active stories count

### 9.2 Logging

**Structured Log Format**:
- Timestamp
- Service name
- Operation
- Character ID
- Story ID
- Outcome
- Processing time

**Log Aggregation**:
- CloudWatch Logs for all services
- Log Insights for querying
- Alarms on error patterns

### 9.3 Tracing

**X-Ray Integration**:
- Trace requests across services
- Identify performance bottlenecks
- Monitor DynamoDB latency
- Track timing service processing

## 10. Deployment Strategy

### 10.1 Multi-Account Setup

**Account Structure**:
- DEV: Full stack, reduced scale
- QA: Production configuration
- PROD: Full scale with redundancy

**Deployment Process**:
1. CDK deploys infrastructure
2. Lambda functions via SAM
3. Fargate service via ECS
4. API Gateway stages

### 10.2 Testing Approach

**DEV Environment**:
- Single Fargate container
- Reduced polling intervals
- Synthetic test data
- Open CORS for testing

**QA Environment**:
- Production-like configuration
- Load testing capabilities
- Full monitoring stack
- Performance baselines

**Production Safeguards**:
- Blue-green deployments
- Canary releases for Lambda
- Automated rollback triggers
- Change approval process

## 11. Cost Optimization

### 11.1 Service Costs

**Primary Cost Drivers**:
- Fargate containers (24/7 operation)
- DynamoDB reads/writes
- Lambda invocations
- Data transfer

**Optimization Strategies**:
- Right-size Fargate containers
- Use DynamoDB on-demand pricing
- Implement efficient caching
- Minimize polling frequency

### 11.2 Scaling Considerations

**At 10,000 concurrent users**:
- ~100 segment completions/minute
- ~1000 API requests/minute
- 2-3 Fargate containers needed
- ~$500-800/month estimated cost

## 12. Future Enhancements

### 12.1 Potential Improvements

1. **Push Notifications**: Add SNS for mobile alerts
2. **Predictive Caching**: Pre-calculate likely outcomes
3. **Story Analytics**: Detailed player behavior tracking
4. **A/B Testing**: Framework for story variants

### 12.2 Scalability Path

1. **Horizontal Scaling**: Add Fargate containers
2. **Regional Distribution**: Multi-region deployment
3. **Caching Layer**: Add ElastiCache if needed
4. **Queue Service**: Consider SQS for extreme scale

## 13. Conclusion

This technical design provides a robust, scalable architecture for the Eidolon Engine Incremental Game. The combination of serverless Lambda functions for user interactions and a persistent Fargate service for timing creates an efficient system that can handle 10,000 concurrent users while maintaining sub-second response times and ensuring progression rates align with MUD gameplay.

Key architectural benefits:
- Simplified client with REST-only communication
- Efficient batch processing in Fargate
- Cost-effective timing management
- Clear separation of concerns
- Strong consistency guarantees