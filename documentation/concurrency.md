# Concurrency Guide

This document outlines the concurrency patterns and lock ordering hierarchy used in the Eidolon Engine to prevent deadlocks and ensure thread‑safe operations.

The engine is architecturally divided into two **independent domains**:

1. **System/Session Domain**: Manages network connections, I/O, and player sessions.
2. **Game World Domain**: Manages the internal state of the game simulation.

These domains operate independently and have their own locking hierarchies.

## Lock Ordering Hierarchy

To prevent deadlocks, all code must follow two primary rules: one for locking _within_ a domain, and one for operations that need to _interact between_ domains.

### The Cardinal Rule: The Two Domains are Separate

**A single goroutine must never hold locks from both the System/Session and Game World domains at the same time.**

Operations that need information from both (like executing a player command) must use a "bridge" pattern: lock the first domain, retrieve the necessary data, unlock it completely, and only then acquire locks in the second domain.

### 1. System/Session Domain Hierarchy

Within this domain, locks must be acquired in this order (from highest to lowest):

1. **Server** – System‑level operations and the SSH interface.
2. **Player** – Player‑specific connection and session state.

### 2. Game World Domain Hierarchy

Within this domain, locks must be acquired in this order (from highest to lowest):

1. **Game** – Game‑wide state and collections (e.g., global lookups).
2. **Room** – Room‑specific state and contents.
3. **Character** – Character state and attributes.
4. **Item** – Item properties and state.

### Golden Rules

- **Never hold locks from both the System and Game World domains simultaneously.**
- **Within a single domain, always acquire locks from high to low** in the hierarchy.
- **Use explicit unlocks for high‑level objects** (`Server`, `Game`) or long‑running functions to improve system responsiveness.
- **Use `defer` for simple, short functions** where lock scope matches function scope for safety.
- **Minimize lock hold time:** acquire late, release early.
- **Prefer `RLock()`** for read‑only operations.
- **Document complex locking** with inline comments.

## Mutex Usage by Component

### Server

```go
type Server struct {
    mutex sync.RWMutex  // Protects server state, player connections
}
```

### Player

```go
type Player struct {
    mutex sync.RWMutex  // Protects connection state, channels
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

### Item

```go
type Item struct {
    mutex sync.RWMutex  // Protects item properties
}
```

## Common Locking Patterns

### Pattern 1: Bridging the Domains (Command Execution)

This is the most critical pattern for handling player input. It safely passes control from the System/Session domain to the Game World domain.

```go
func executeCommand(game *Game, player *Player, command string) {
    // 1. Parse command without any locks.
    cmd, args := parseCommand(command)

    // 2. Bridge Step 1: Lock within the System Domain to get a reference.
    player.mutex.RLock()
    character := player.character
    player.mutex.RUnlock() // Explicitly unlock before touching the Game World.

    if character == nil {
        return
    }

    // 3. Bridge Step 2: Now, operate purely within the Game World domain.
    // No System/Session locks are held at this point.
    switch cmd {
    case "get":
        executeGet(game, character, args)
    case "look":
        executeLook(game, character)
    }
}
```

### Pattern 2: Broadcasting Messages from Game to Players

This shows the bridge in the other direction. We access data from the Game World, release the lock, and then interact with the System domain.

```go
func broadcastToRoom(room *Room, message string) {
    // 1. Lock within Game World to obtain the slice.
    room.mutex.RLock()
    characters := room.characters // reference – no defensive copy
    room.mutex.RUnlock() // Unlock Game World *before* interacting with players.

    // 2. Iterate over the slice. No Game World locks are held.
    for _, character := range characters {
        character.mutex.RLock()
        player := character.player
        character.mutex.RUnlock()

        if player != nil {
            // The sendMessage function will acquire its own Player lock.
            player.sendMessage(message)
        }
    }
}
```

### Pattern 3: Operations Entirely Within the Game World

When an operation (like an NPC moving) is self‑contained in the game world, only that domain's hierarchy applies.

```go
func moveCharacter(character *Character, fromRoom *Room, toRoom *Room) error {
    // 1. Lock rooms in a consistent order (e.g., by ID) to prevent deadlock
    // between sibling objects in the same hierarchy level.
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

    // 2. Lock character last, as it's lower in the hierarchy than Room.
    character.mutex.Lock()
    defer character.mutex.Unlock()

    // Perform movement operations
    return nil
}
```

### Pattern 4: Saving State (Avoiding I/O under lock)

I/O is a System‑level concern, so gather the data under lock, release, and then perform the save.

```go
func saveCharacter(character *Character) error {
    // 1. Lock in the Game World to obtain a snapshot.
    character.mutex.RLock()
    snapshot := *character // value snapshot without extra copying
    character.mutex.RUnlock() // Unlock before performing slow I/O.

    // 2. Perform the database save operation without holding any game locks.
    return database.SaveCharacter(snapshot)
}
```

## Helper Functions

### Lock Multiple Rooms

When locking multiple rooms (siblings in the hierarchy), always use consistent ordering to prevent deadlocks.

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

## Deadlock Prevention Strategies

### 1. Timeout‑based Lock Acquisition

For non‑critical operations that might block, consider using a timeout. This is an advanced technique and should be used sparingly.

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

### 2. Lock‑free Alternatives

For high‑throughput systems, channels can be used to serialize operations on a resource, managed by a single goroutine.

```go
type updateRequest struct {
    character *Character
    update    func(*Character)
    done      chan error
}

// Process updates serially in a dedicated goroutine
func (g *Game) processUpdates(updates <-chan updateRequest) {
    for req := range updates {
        // No lock needed here as this is the only goroutine modifying characters
        req.update(req.character)
        req.done <- nil
    }
}
```

## Testing Concurrent Code

### 1. Race Detection

Always run tests with the `-race` flag to automatically detect race conditions.

```bash
go test -race ./...
```

### 2. Deadlock Detection

During development and testing, consider using a deadlock detection library to find lock ordering violations.

```go
import "github.com/sasha-s/go-deadlock" // In development/test builds

type Game struct {
    mutex deadlock.RWMutex // Use deadlock detection version in tests
}
```

### 3. Stress Testing

Create dedicated tests that simulate high contention on shared resources to uncover subtle bugs.

```go
func TestConcurrentMovement(t *testing.T) {
    game, room1, room2 := NewTestWorld()

    var wg sync.WaitGroup
    for i := 0; i < 100; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            // Create a character and move it back and forth
            // between room1 and room2 hundreds of times.
        }()
    }

    wg.Wait()
    // Verify final state and that no deadlocks or panics occurred
}
```

## Common Pitfalls

### 1. Holding Locks Across Domains

This is the primary violation of the architecture. It creates an implicit, dangerous dependency between the two independent domains and is the most likely cause of a major deadlock.

```go
func adminAnnounce(server *Server, game *Game, message string) {
    server.mutex.RLock()
    players := server.players // access without copying
    server.mutex.RUnlock()

    for _, player := range players {
        player.sendMessage(message) // Player lock acquired and released internally.
    }
}
```

### 2. Holding Locks During I/O

Holding any lock during I/O can cause cascading performance issues.

```go
character.mutex.Lock()
database.Save(character) // BAD: I/O while holding a Game World lock.
character.mutex.Unlock()
```

Use the snapshot pattern from **Pattern 4** instead.

### 3. Nested Function Calls Violating Hierarchy

Ensure that a function holding a lock only calls other functions that acquire locks _lower_ in the _same domain's hierarchy_, or functions that acquire no locks at all.

```go
// If function A locks a Room and calls function B,
// function B must not attempt to lock the Game or another Room.
// It may only lock Characters or Items within that Room.
```

## Monitoring and Debugging

### 1. Lock Contention Metrics

In a production environment, use metrics to track how much time goroutines spend waiting for locks. This helps identify bottlenecks.

```go
var (
    lockWaitTime = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "lock_wait_duration_seconds",
            Help: "Time spent waiting for locks",
        },
        []string{"lock_name"}, // e.g., "game", "room", "player"
    )
)
```

### 2. Debugging Deadlocks

If a deadlock occurs, get a full goroutine stack dump to analyze it.

1. Set the environment variable `GOTRACEBACK=all`.
2. Send a `SIGQUIT` signal to your running process (`kill -QUIT <pid>`).
3. Examine the stack traces for circular lock dependencies.

## Future Considerations

### 1. Lock‑free Data Structures

For performance‑critical hot paths, explore using specialized lock‑free data structures or atomic operations from the `sync/atomic` package.

### 2. Actor Model

For certain subsystems, an actor‑based model (where each component is a goroutine processing messages from a channel) can eliminate the need for explicit locks entirely by serializing access.

## References

- [Go Memory Model](https://golang.org/ref/mem)
- [Effective Go – Concurrency](https://golang.org/doc/effective_go#concurrency)
- [Go Concurrency Patterns](https://go.dev/blog/pipelines)
- [Deadlock Prevention Algorithms](https://en.wikipedia.org/wiki/Deadlock_prevention_algorithms)
