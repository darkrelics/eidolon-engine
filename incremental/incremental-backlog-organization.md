# Incremental Game Backlog Organization

## Step 1: GitHub Backlog Trimming

### Keep in Alpha Milestone (Basic Stability)
These issues are essential for system stability and should remain prioritized:

1. **#498** - Implement Heartbeat, Stale Session Detection, and Dead Socket Reaping ✓
2. **#496** - Implement a Command Queue with proper serialization ✓
3. **#511** - Implement Core Smoke Test Script ✓
4. **#512** - Create Makefile for Build Automation and Testing (move from Incremental)
5. **#505** - Implement Player Privilege System for Administrative Access ✓
6. **#506** - Implement @shutdown Administrative Command ✓
7. **#507** - Implement @broadcast Administrative Command ✓

### Create New Incremental-MVP Epic
Consolidate incremental game essentials:

1. **#595** - Create /idle directory structure for incremental module
2. **#597** - Define story blob JSON schema with validation
3. **#599** - Implement StartSegment Lambda function
4. **#600** - Implement ConcludeSegment Lambda function
5. **#601** - Create DynamoDB tables for story blobs and character sheets
6. **#602** - Build minimal Flutter idle game client
7. **#604** - Build Git-to-S3 content publication pipeline (modified for Twine)

### Downgrade Priority (Future Enhancements)
Move these to a "Future Features" milestone:

- All MUD-specific issues (#620-639: combat, NPCs, crafting, etc.)
- Advanced incremental features (#609-611: prestige, branching, rest mechanics)
- Performance optimizations (#613: provisioned concurrency)
- Extended monitoring (#614: CloudWatch Synthetics)
- Security hardening beyond MVP (#616)

### New Issues to Create
For the Twine integration:

1. **Create twine2idle converter tool** - Parse Twee files with metadata blocks
2. **Design story.schema.json** - Define JSON schema for story validation
3. **Implement GitHub Action for Twine conversion** - Automated Twee to JSON pipeline
4. **Configure S3 bucket for story storage** - Set up stories/<storyId>/<revision>.json structure
5. **Create StoryManifest DynamoDB table** - Lightweight metadata storage
6. **Update Lambda functions for S3 retrieval** - Modify to fetch from S3 instead of DynamoDB
7. **Configure Cognito identity pool** - Set up authenticated S3 access