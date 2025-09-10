# Documentation Style Guide

This guide establishes consistent standards for all documentation in the Eidolon Engine project. Following these guidelines ensures clarity, maintainability, and professionalism across all documents.

## Data Naming Standards

### JSON Field Naming Convention

**All JSON fields use PascalCase with capitalized abbreviations:**

- **IDs**: `CharacterID`, `PlayerID`, `StoryID`, `ActiveSegmentID` (not `characterId` or `character_id`)  
- **Abbreviations**: `ClientID`, `APIKey`, `HTTPMethod`, `XMLData`, `JSONBody`
- **Standard Fields**: `GameMode`, `AvailableStories`, `CompletedStories`
- **Error Responses**: `{"Error": "message"}` (always PascalCase "Error" field)

**Rationale**: Matches DynamoDB schema field names for seamless data mapping across all system layers.

## Document Structure

### File Naming

- Use lowercase with hyphens: `incremental-design.md`, not `IncrementalDesign.md`
- Be descriptive but concise: `incremental-mud-workflow.md`, not `workflow.md`
- Group related documents with common prefixes: `incremental-*.md`

### Document Hierarchy

Each document should follow this structure:

1. **Title** (H1) - Single, descriptive title
2. **Overview/Purpose** - Brief introduction explaining the document's purpose
3. **Table of Contents** - For documents over 200 lines
4. **Main Content** - Organized with logical heading levels
5. **Related Documentation** - Links to relevant documents

### Heading Levels

- **H1 (#)**: Document title only (one per document)
- **H2 (##)**: Major sections
- **H3 (###)**: Subsections
- **H4 (####)**: Sub-subsections (use sparingly)
- Never skip heading levels (e.g., H2 to H4)

## Writing Style

### Voice and Tone

- Use clear, concise technical writing
- Write in present tense: "The system processes" not "The system will process"
- Use active voice: "The poller queries segments" not "Segments are queried by the poller"
- Be direct and avoid unnecessary words

### Technical Terminology

- Define acronyms on first use: "Global Secondary Index (GSI)"
- Use consistent terminology throughout all documents
- Prefer clarity over brevity when explaining complex concepts
- Include brief context before code examples

### Code Examples

Every code block should be preceded by 1-2 sentences explaining:

- What the code demonstrates
- Why it's important
- When to use this pattern

Example:

````
The Lambda handler pattern separates AWS concerns from business logic. This enables unit testing without AWS dependencies.

```python
def lambda_handler(event, context):
    # AWS-specific handling
    return business_logic(params)
````

## Formatting Standards

### Lists

Use consistent list formatting:

- **Bullet points**: For unordered items
- **Numbered lists**: For sequential steps or ranked items
- **Nested lists**: Indent with 2 spaces
- End list items with punctuation only if they're complete sentences

### Tables

- Use tables for structured data with 3+ attributes
- Include header row with bold formatting
- Align columns for readability
- Add descriptions below tables when needed

### Code Blocks

- Always specify the language: ` ```python `, ` ```json `, ` ```yaml `
- Keep examples concise and focused
- Remove unnecessary comments from code
- Use realistic but simplified data

### Field Names and Values

- **Database fields**: Use exact field names as they appear in the schema
- **JSON examples**: Maintain consistent casing (PascalCase for Eidolon)
- **Sample values**: Use realistic examples, not "foo/bar"

## Document Types

### Requirements Documents

Focus on WHAT the system needs to do:

- Use "SHALL" for mandatory requirements
- Number requirements for easy reference (FR-001, NFR-001)
- Avoid implementation details
- Include acceptance criteria

### Design Documents

Focus on HOW to implement requirements:

- Include architecture diagrams
- Provide technical specifications
- Reference requirements being implemented
- Explain design decisions and trade-offs

### Implementation Guides

Provide practical details for developers:

- Include complete code examples
- Show error handling patterns
- Provide testing approaches
- Include performance considerations

### API Documentation

- Show request/response examples
- List all parameters with types
- Include error responses
- Provide curl examples when helpful

## Cross-References

### Internal Links

- Use relative paths: `[Design](incremental-design.md)`
- Link to specific sections: `[Polling](#polling-system)`
- Verify links work before committing

### External References

- AWS services: Link to official documentation
- Third-party tools: Include version information
- Standards: Reference specific versions or RFCs

## Maintenance

### Document Lifecycle

- **Draft**: Work in progress, may have TODOs
- **Review**: Ready for team feedback
- **Published**: Official documentation
- **Deprecated**: Outdated but retained for reference

### Version Control

- Make atomic commits: One logical change per commit
- Write clear commit messages: "Update polling interval to 1 minute"
- Update related documents together
- Remove outdated information rather than marking as outdated

### Review Checklist

Before finalizing any document:

- [ ] Spelling and grammar check
- [ ] Technical accuracy verified
- [ ] Code examples tested
- [ ] Links verified
- [ ] Formatting consistent
- [ ] No duplicate information across documents

## Common Patterns

### Describing Workflows

1. Start with overview paragraph
2. Use numbered steps for sequential flows
3. Include decision points clearly
4. Show error handling paths
5. End with outcome description

### Explaining Architecture

1. Provide visual diagram first
2. Explain each component's purpose
3. Describe interactions between components
4. Include data flow direction
5. Note scaling considerations

### Documenting APIs

1. Endpoint and method
2. Purpose statement
3. Authentication requirements
4. Request format with example
5. Response format with example
6. Error cases
7. Rate limits or constraints

## Anti-Patterns to Avoid

### Documentation Smells

- **Duplication**: Same information in multiple places
- **Contradiction**: Conflicting information across documents
- **Staleness**: References to removed features
- **Vagueness**: "It should probably work"
- **Over-documentation**: Explaining obvious code
- **Under-documentation**: Missing critical context

### Writing Issues

- Passive voice overuse
- Unnecessarily complex sentences
- Undefined acronyms
- Missing examples
- Walls of text without breaks
- Inconsistent terminology

## Examples

### Good Section Header

```markdown
### 2.3 Segment Processing Implementation

This function handles the core segment processing logic for mechanical segments. It includes safeguards against duplicate processing, proper status tracking, and comprehensive error handling to ensure segments are processed exactly once with reliable outcome storage.
```

### Good Code Example

````markdown
DynamoDB transactions ensure atomic updates across multiple tables when starting a story. This prevents partial state where a character might be locked in Incremental mode without an active segment.

```python
def start_story_transaction(character_id, story_id, segment_data):
    return {
        'TransactItems': [
            # Update character state
            {'Update': {...}},
            # Create active segment
            {'Put': {...}}
        ]
    }
```
````

### Good Table

```markdown
| Segment Type | Description         | Processing Method | Duration Range |
| ------------ | ------------------- | ----------------- | -------------- |
| Decision     | Player makes choice | Immediate         | 1-60 minutes   |
| Mechanical   | Challenges/combat   | Queued to SQS     | 1-24 hours     |
| Rest         | Healing period      | Simple advance    | 1-24 hours     |
```

## Conclusion

Consistent documentation helps developers understand and maintain the system effectively. When in doubt, prioritize clarity and completeness over brevity. Remember that documentation is often the first thing new team members read, so make it welcoming and informative.
