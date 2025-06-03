# Concurrency Guide

This document outlines the concurrency patterns and lock ordering hierarchy used in the Eidolon Engine to prevent deadlocks and ensure thread-safe operations.

## Lock Ordering Hierarchy

To prevent deadlocks, all code must acquire locks in the following order (from highest to lowest):

1. **Server** - System-level operations and SSH interface
2. **Game** - Game-wide state and collections
3. **Room** - Room-specific state and contents
4. **Character** - Character state and attributes
5. **Player** - Player connection and session state
6. **Item** - Item properties and state

### Golden Rules

- **Always acquire locks from high to low** in the hierarchy
- **Never acquire a higher-level lock** while holding a lower-level lock
- **Use defer** for unlock operations to ensure cleanup
- **Minimize lock hold time** - acquire late, release early
- **Prefer RLock()** for read-only operations
- **Document complex locking** with inline comments

## Mutex Usage by Component

### Server
```go
type Server struct {
    mutex sync.RWMutex  // Protects server state
}
```

### Game
```go
type Game struct {
    mutex sync.RWMutex  // Protects rooms, characters, prototypes
}
```

### Room
```go
type Room struct {
    mutex sync.RWMutex  // Protects room state, exits, inventory
}
```

### Character
```go
type Character struct {
    mutex sync.RWMutex  // Protects character attributes, inventory
}
```

### Player
```go
type Player struct {
    mutex sync.RWMutex  // Protects connection state, channels
}
```

### Item
```go
type Item struct {
    mutex sync.RWMutex  // Protects item properties
}
```

## Common Locking Patterns

### Pattern 1: Character Movement

When moving a character between rooms, follow this order:

```go
func moveCharacter(game *Game, character *Character, fromRoom *Room, toRoom *Room) error {
    // 1. No game lock needed if rooms already resolved
    
    // 2. Lock rooms in consistent order (by ID) to prevent deadlock
    if fromRoom.RoomID < toRoom.RoomID {
        fromRoom.mutex.Lock()
        defer fromRoom.mutex.Unlock()
        toRoom.mutex.Lock()
        defer toRoom.mutex.Unlock()
    } else {
        toRoom.mutex.Lock()
        defer toRoom.mutex.Unlock()
        fromRoom.mutex.Lock()
        defer fromRoom.mutex.Unlock()
    }
    
    // 3. Lock character last
    character.mutex.Lock()
    defer character.mutex.Unlock()
    
    // Perform movement operations
    return nil
}
```

### Pattern 2: Item Transfer

When transferring items between containers (rooms, characters):

```go
func transferItem(fromRoom *Room, toCharacter *Character, item *Item) error {
    // 1. Lock room first (higher in hierarchy)
    fromRoom.mutex.Lock()
    defer fromRoom.mutex.Unlock()
    
    // 2. Lock character
    toCharacter.mutex.Lock()
    defer toCharacter.mutex.Unlock()
    
    // 3. Lock item last
    item.mutex.Lock()
    defer item.mutex.Unlock()
    
    // Perform transfer
    return nil
}
```

### Pattern 3: Broadcasting Messages

When broadcasting to multiple characters in a room:

```go
func broadcastToRoom(room *Room, message string) {
    // 1. Lock room to get character list
    room.mutex.RLock()
    characters := make([]*Character, len(room.characters))
    copy(characters, room.characters)
    room.mutex.RUnlock()
    
    // 2. Send messages without holding locks
    for _, character := range characters {
        character.mutex.RLock()
        player := character.player
        character.mutex.RUnlock()
        
        if player != nil {
            // Send message via player's channel
            player.sendMessage(message)
        }
    }
}
```

### Pattern 4: Saving Game State

When saving to database, minimize lock time:

```go
func saveCharacter(character *Character) error {
    // 1. Lock and copy data
    character.mutex.RLock()
    data := character.copyForSave()
    character.mutex.RUnlock()
    
    // 2. Save without holding locks
    return database.SaveCharacter(data)
}
```

### Pattern 5: Command Execution

Commands should acquire locks in the proper order:

```go
func executeCommand(game *Game, player *Player, command string) {
    // 1. Parse command without locks
    cmd, args := parseCommand(command)
    
    // 2. Get character reference
    player.mutex.RLock()
    character := player.character
    player.mutex.RUnlock()
    
    // 3. Execute with proper lock ordering
    switch cmd {
    case "get":
        // Room -> Character -> Item
        executeGet(character, args)
    case "look":
        // Room -> Character (for visibility)
        executeLook(character)
    }
}
```

## Helper Functions

### Lock Multiple Rooms

When locking multiple rooms, always use consistent ordering:

```go
func lockRoomsInOrder(rooms ...*Room) func() {
    // Sort rooms by ID to ensure consistent ordering
    sort.Slice(rooms, func(i, j int) bool {
        return rooms[i].RoomID < rooms[j].RoomID
    })
    
    // Lock all rooms
    for _, room := range rooms {
        room.mutex.Lock()
    }
    
    // Return unlock function
    return func() {
        for i := len(rooms) - 1; i >= 0; i-- {
            rooms[i].mutex.Unlock()
        }
    }
}

// Usage:
unlock := lockRoomsInOrder(room1, room2, room3)
defer unlock()
```

### Safe Read Operations

For read-only operations that need multiple locks:

```go
func safeReadRoomCharacters(room *Room) []*Character {
    room.mutex.RLock()
    defer room.mutex.RUnlock()
    
    // Return a copy to avoid holding lock
    result := make([]*Character, len(room.characters))
    copy(result, room.characters)
    return result
}
```

## Deadlock Prevention Strategies

### 1. Timeout-based Lock Acquisition

For operations that might block:

```go
func tryLockWithTimeout(mu *sync.RWMutex, timeout time.Duration) bool {
    done := make(chan bool, 1)
    go func() {
        mu.Lock()
        done <- true
    }()
    
    select {
    case <-done:
        return true
    case <-time.After(timeout):
        return false
    }
}
```

### 2. Lock-free Alternatives

Use channels for some operations:

```go
// Instead of locking for updates
type updateRequest struct {
    character *Character
    update    func(*Character)
    done      chan error
}

// Process updates serially
func (g *Game) processUpdates(updates <-chan updateRequest) {
    for req := range updates {
        req.update(req.character)
        req.done <- nil
    }
}
```

## Testing Concurrent Code

### 1. Race Detection

Always test with race detection enabled:

```bash
go test -race ./...
```

### 2. Deadlock Detection

Use deadlock detection during development:

```go
// In development/test builds
import "github.com/sasha-s/go-deadlock"

// Replace sync.RWMutex with deadlock.RWMutex
type Game struct {
    mutex deadlock.RWMutex
}
```

### 3. Stress Testing

Create tests that stress concurrent operations:

```go
func TestConcurrentMovement(t *testing.T) {
    game := NewGame()
    
    // Create multiple goroutines moving characters
    var wg sync.WaitGroup
    for i := 0; i < 100; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            // Perform random movements
        }(i)
    }
    
    wg.Wait()
    // Verify no deadlocks occurred
}
```

## Common Pitfalls

### 1. Lock Inversion

**Wrong:**
```go
character.mutex.Lock()
room.mutex.Lock()  // BAD: Room is higher in hierarchy
```

**Correct:**
```go
room.mutex.Lock()
character.mutex.Lock()
```

### 2. Holding Locks During I/O

**Wrong:**
```go
character.mutex.Lock()
database.Save(character)  // BAD: I/O while holding lock
character.mutex.Unlock()
```

**Correct:**
```go
character.mutex.Lock()
data := character.copyData()
character.mutex.Unlock()
database.Save(data)
```

### 3. Nested Function Calls

Be careful with functions that acquire locks:

```go
// If function A locks X and calls B which locks Y,
// ensure X is higher than Y in the hierarchy
```

## Performance Considerations

### 1. Read vs Write Locks

- Use `RLock()` for read-only operations
- Multiple readers can hold RLock simultaneously
- Write locks are exclusive

### 2. Lock Granularity

- Don't lock entire game for character-specific operations
- Consider splitting large structures into smaller lockable units
- Balance between granularity and complexity

### 3. Lock Duration

- Hold locks for minimum time necessary
- Don't perform expensive operations while holding locks
- Copy data and process outside of critical sections

## Monitoring and Debugging

### 1. Lock Contention Metrics

Track lock contention in production:

```go
var (
    lockWaitTime = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "lock_wait_duration_seconds",
            Help: "Time spent waiting for locks",
        },
        []string{"lock_type"},
    )
)
```

### 2. Debugging Deadlocks

When debugging deadlocks:

1. Enable `GOTRACEBACK=all` for full goroutine dumps
2. Look for circular dependencies in stack traces
3. Verify lock ordering matches hierarchy
4. Check for locks held during blocking operations

### 3. Logging Lock Operations

In debug mode, log lock acquisitions:

```go
if debug {
    log.Printf("Acquiring lock: %s -> %s", currentLock, nextLock)
}
```

## Future Considerations

### 1. Lock-free Data Structures

Consider lock-free alternatives for hot paths:
- Atomic operations for counters
- Lock-free queues for message passing
- Copy-on-write for rarely modified data

### 2. Actor Model

Consider actor model for some subsystems:
- Each entity processes messages serially
- No shared state between actors
- Communication via message passing

### 3. STM (Software Transactional Memory)

For complex operations with multiple locks:
- Automatic retry on conflicts
- Composable transactions
- Simplified reasoning about concurrency

## References

- [Go Memory Model](https://golang.org/ref/mem)
- [Effective Go - Concurrency](https://golang.org/doc/effective_go#concurrency)
- [Go Concurrency Patterns](https://go.dev/blog/pipelines)
- [Deadlock Prevention Algorithms](https://en.wikipedia.org/wiki/Deadlock_prevention_algorithms)