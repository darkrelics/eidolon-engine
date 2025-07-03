# Incremental Game System - Development TODO List

## Critical Priority (Blocking MVP)

### Backend Implementation

- [ ] **Create Lambda Functions**

  - [ ] `api_start_segment.py` - Start a new story segment
  - [ ] `api_conclude_segment.py` - Complete a segment and calculate outcomes
  - [ ] `api_create_character.py` - Create new incremental character
  - [ ] `api_get_stories.py` - Retrieve available stories
  - [ ] `api_abandon_story.py` - Abandon current story run
  - [ ] `api_character_rest.py` - Rest action for character

- [ ] **DynamoDB Table Creation**

  - [ ] Add `incremental_characters` table definition to CDK
  - [ ] Add `active_segments` table definition to CDK
  - [ ] Add `story_progress` table definition to CDK
  - [ ] Add `story_manifest` table definition to CDK
  - [ ] Deploy tables to AWS

- [ ] **Update CDK Infrastructure**
  - [ ] Uncomment and implement Lambda functions in `incremental_lambda_stack.py`
  - [ ] Add proper IAM roles and permissions
  - [ ] Configure environment variables for Lambda functions
  - [ ] Add Lambda-to-DynamoDB permissions

### Frontend Implementation

- [ ] **Character Management**

  - [ ] Create character selection screen
  - [ ] Implement character creation flow with archetype selection
  - [ ] Connect to backend character APIs
  - [ ] Add character switcher UI

- [ ] **Game Loop Implementation**
  - [ ] Replace placeholder timer with actual countdown system
  - [ ] Implement segment progression UI
  - [ ] Add outcome display screens
  - [ ] Create skill check visualization

## High Priority (Required for MVP)

### API Integration

- [ ] **Connect Flutter to Lambda**

  - [ ] Update API endpoints in `api_service.dart` to match Lambda functions
  - [ ] Add error handling for all API calls
  - [ ] Implement retry logic for failed requests
  - [ ] Add loading states during API calls

- [ ] **State Management**
  - [ ] Integrate CharacterProvider into main app
  - [ ] Create StoryProvider for active story state
  - [ ] Add SegmentProvider for timer management
  - [ ] Implement proper error state handling

### Story System

- [ ] **S3 Integration**

  - [ ] Create S3 bucket for story storage in CDK
  - [ ] Implement story upload pipeline
  - [ ] Add Lambda functions to read stories from S3
  - [ ] Create story manifest system

- [ ] **Story Content**
  - [ ] Convert example story to proper format
  - [ ] Create at least 3 stories for launch
  - [ ] Implement story validation pipeline
  - [ ] Add story metadata system

## Medium Priority (Post-MVP)

### Game Features

- [ ] **Character Progression**

  - [ ] Implement XP application system
  - [ ] Add skill advancement UI
  - [ ] Create attribute improvement mechanics
  - [ ] Add level-up notifications

- [ ] **Resource Management**
  - [ ] Implement resource persistence
  - [ ] Add resource trading/spending mechanics
  - [ ] Create resource visualization UI
  - [ ] Add resource rewards system

### Quality of Life

- [ ] **UI Polish**

  - [ ] Add animations for segment transitions
  - [ ] Implement proper loading screens
  - [ ] Create settings screen
  - [ ] Add sound effects toggle

- [ ] **Performance**
  - [ ] Implement offline mode with sync
  - [ ] Add caching for story content
  - [ ] Optimize API calls
  - [ ] Reduce Flutter app size

## Low Priority (Future Enhancement)

### Advanced Features

- [ ] **Social Features**

  - [ ] Add leaderboards
  - [ ] Implement friend system
  - [ ] Create guild mechanics
  - [ ] Add chat functionality

- [ ] **Monetization**
  - [ ] Design premium currency
  - [ ] Implement IAP
  - [ ] Create premium stories
  - [ ] Add cosmetic purchases

### Content Tools

- [ ] **Story Editor**
  - [ ] Create web-based story editor
  - [ ] Add Twine import tool
  - [ ] Implement story testing mode
  - [ ] Create balance calculator

## Technical Debt

### Testing

- [ ] **Unit Tests**
  - [ ] Add tests for all Lambda functions
  - [ ] Create Flutter widget tests
  - [ ] Add integration tests
  - [ ] Implement load testing

### Documentation

- [ ] **API Documentation**
  - [ ] Document all Lambda endpoints
  - [ ] Create API usage examples
  - [ ] Add error code reference
  - [ ] Write integration guide

### Security

- [ ] **Security Hardening**
  - [ ] Implement input validation in all Lambdas
  - [ ] Add rate limiting to APIs
  - [ ] Create security audit checklist
  - [ ] Implement data encryption

### Monitoring

- [ ] **Observability**
  - [ ] Create CloudWatch dashboards
  - [ ] Set up alerts for errors
  - [ ] Add custom metrics
  - [ ] Implement distributed tracing

## Known Issues to Fix

- [ ] CORS configuration using wildcard origins
- [ ] No error boundaries in Flutter app
- [ ] Missing null safety in some Flutter code
- [ ] Lambda functions missing structured logging
- [ ] No request validation in API Gateway
- [ ] Character name validation not matching backend
- [ ] No handling for concurrent segment starts

## Success Metrics to Implement

- [ ] Session length tracking
- [ ] Story completion rates
- [ ] Character progression metrics
- [ ] API performance metrics
- [ ] Error rate monitoring
- [ ] User retention tracking

## Launch Checklist

- [ ] All critical priority items complete
- [ ] At least 3 stories available
- [ ] Load testing completed
- [ ] Security audit passed
- [ ] Documentation complete
- [ ] Monitoring configured
- [ ] Beta testing feedback incorporated
- [ ] App store assets prepared
- [ ] Marketing materials ready
- [ ] Support documentation written

---

## Development Guidelines

1. **Commit Prefixes**:

   - `feat:` - New features
   - `fix:` - Bug fixes
   - `docs:` - Documentation updates
   - `test:` - Test additions/changes
   - `refactor:` - Code refactoring

2. **Branch Naming**:

   - `feature/incremental-[feature-name]`
   - `bugfix/incremental-[issue-number]`
   - `hotfix/incremental-[description]`

3. **Testing Requirements**:

   - All Lambda functions must have unit tests
   - Flutter screens must have widget tests
   - Integration tests for critical user flows

4. **Code Review Checklist**:
   - [ ] Follows project style guide
   - [ ] Includes appropriate tests
   - [ ] Updates documentation
   - [ ] No hardcoded values
   - [ ] Proper error handling
   - [ ] Security considerations addressed
