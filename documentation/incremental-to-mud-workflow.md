# Incremental to MUD Character Workflow

## Overview

Players start in the Incremental game and transition to the MUD after character customization.

## Workflow Steps

### 1. Account Creation

- Player creates account via Incremental UI
- Cognito handles authentication
- Player record created in DynamoDB

### 2. Character Creation

- Player provides character name
- Name validated against shared bloom filter
- Player selects archetype
- Character created with `GameMode: "Incremental"`

### 3. Character Customization (Rapid Inactive)

- Player goes through story-based tutorial
- Character gains XP and equipment
- Skills are dynamically added as used
- Progress tracked in character record

### 4. MUD Transition

- At end of customization:
  - Room is selected based on archetype or player choice
  - Character `GameMode` updated to "MUD"
  - Character marked as MUD-enabled
  - Bloom filter updated with character name

### 5. MUD Entry

- Player can now access MUD client
- Character appears in selected room
- Full MUD gameplay available

## Shared Bloom Filter Design

### Storage Options

#### Option 1: DynamoDB Table

```
Table: shared-bloom-filters
- FilterName: "character-names" (PK)
- Version: number
- BitArray: binary data (base64 encoded)
- Metadata: {size, hash_functions, false_positive_rate}
- LastUpdated: timestamp
```

#### Option 2: S3 with Lambda

```
Bucket: eidolon-shared-data
Path: /bloom-filters/character-names/current.bloom
- Use S3 versioning for history
- Lambda function to update filter
- CloudFront for fast reads
```

### Update Mechanism

1. **Read Path** (Name Validation):
   - Lambda loads bloom filter from storage
   - Cache in Lambda memory for performance
   - Check name against filter

2. **Write Path** (Name Addition):
   - Queue name additions in DynamoDB
   - Periodic Lambda rebuilds filter
   - Updates both MUD and storage

### Implementation Steps

1. Create shared bloom filter storage
2. Update Incremental Lambda to check bloom filter
3. Create Lambda for bloom filter updates
4. Update MUD to read from shared storage
5. Implement transition logic for character state

## Security Considerations

- Bloom filter is read-only for most operations
- Only authorized Lambdas can update filter
- Use IAM roles for access control
- Consider encryption at rest for sensitive data

## Performance Optimization

- Cache bloom filter in Lambda memory
- Use CloudFront for global distribution
- Implement exponential backoff for updates
- Monitor false positive rates
