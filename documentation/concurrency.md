# Concurrency Guide

This document outlines the concurrency patterns and lock ordering hierarchy used in the Eidolon Engine to prevent deadlocks and ensure thread-safe operations. The architecture is divided into two primary domains: the **System/Session Domain** (handling connections and I/O) and the **Game World Domain** (handling the simulation state).

## Lock Ordering Hierarchy

To prevent deadlocks, locks must be acquired according to a strict ordering. The two domains have their own internal hierarchies, and there is a strict rule for acquiring locks *between* domains.

**The Cardinal Rule: Never acquire a System/Session lock while holding a Game World lock.**

This means you must always lock components from the System/Session domain *before* locking any components from the Game World domain.

### 1. System/Session Domain Hierarchy

This domain manages system-level operations, network connections, and player sessions. Locks must be acquired in this order:

1.  **Server** - System-level operations and SSH interface
2.  **Player** - Player connection and session state

### 2. Game World Domain Hierarchy

This domain manages the internal state of the game simulation. Locks must be acquired in this order:

1.  **Game** - Game-wide state and collections (e.g., character or room lookups)
2.  **Room** - Room-specific state and contents
3.  **Character** - Character state and attributes
4.  **Item** - Item properties and state

### Golden Rules

-   **Lock across domains from System/Session to Game World.** Never the other way around.
-   **Within a domain, always acquire locks from high to low** in the hierarchy.
-   **Use explicit unlocks for high-level or long-running functions** to improve responsiveness by minimizing lock duration.
-   **Use `defer` for simple, short functions** where lock scope matches function scope for safety and clarity.
-   **Minimize lock hold time:** acquire late, release early.
-   **Prefer `RLock()`** for read-only operations.
-   **Document complex locking** with inline comments.

## Mutex Usage by Component

### Server

```go
type Server struct {
    mutex sync.RWMutex  // Protects server state
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

### Pattern 1: Command Execution (Entry Point)

Commands from a player are the primary entry point where the two domains interact.

```go
func executeCommand(game *Game, player *Player, command string) {
    // 1. Parse command without any locks.
    cmd, args := parseCommand(command)

    // 2. Lock the Player (System Domain) to get the character reference.
    // Release this lock as soon as possible to not block I/O.
    player.mutex.RLock()
    character := player.character
    player.mutex.RUnlock() // Explicit unlock for responsiveness

    if character == nil {
        // Handle case where player has no character
        return
    }

    // 3. Now, acquire locks in the Game World Domain as needed.
    switch cmd {
    case "get":
        // This function will lock Room -> Character -> Item
        executeGet(game, character, args)
    case "look":
        // This function will lock Room -> Character
        executeLook(game, character)
    }
}
```

### Pattern 2: Item Transfer (Game World Only)

When transferring items between containers, the hierarchy is entirely within the Game World.

```go
func transferItem(fromRoom *Room, toCharacter *Character, item *Item) error {
    // 1. Lock room first (higher in Game World hierarchy)
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

### Pattern 3: Character Movement (Game World Only)

When moving a character, lock rooms in a consistent order (e.g., by ID) to prevent deadlocks between sibling `Room` locks.

```go
func moveCharacter(character *Character, fromRoom *Room, toRoom *Room) error {
    // 1. Lock rooms in a consistent order (by ID) to prevent deadlock.
    // This is an operation on sibling locks within the same level of the hierarchy.
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

    // 2. Lock character last (lower in hierarchy than Room).
    character.mutex.Lock()
    defer character.mutex.Unlock()

    // Perform movement operations
    return nil
}
```

### Pattern 4: Broadcasting Messages

To avoid holding locks during I/O, copy the necessary data first.

```go
func broadcastToRoom(room *Room, message string) {
    // 1. Lock room to safely get the list of characters.
    room.mutex.RLock()
    characters := make([]*Character, len(room.characters))
    copy(characters, room.characters)
    room.mutex.RUnlock() // Release Room lock immediately

    // 2. Iterate through the copy. For each character, get their player reference.
    // This is safe because we only acquire a brief Character lock and do not
    // acquire a Player lock, avoiding an inversion.
    for _, character := range characters {
        character.mutex.RLock()
        player := character.player
        character.mutex.RUnlock()

        if player != nil {
            // The sendMessage function will handle its own Player lock internally
            // without holding any Game World locks.
            player.sendMessage(message)
        }
    }
}
```

### Pattern 5: Saving Game State

Minimize lock duration by copying data before performing slow I/O operations.

```go
func saveCharacter(character *Character) error {
    // 1. Acquire read lock on the character to create a data snapshot.
    character.mutex.RLock()
    data := character.copyForSave()
    character.mutex.RUnlock() // Unlock immediately after copying.

    // 2. Perform the database save operation without holding any locks.
    return database.SaveCharacter(data)
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

### Safe Read Operations

For read-only operations, copy data to release locks quickly and prevent race conditions with the returned slice.

```go
func safeReadRoomCharacters(room *Room) []*Character {
    room.mutex.RLock()
    defer room.mutex.RUnlock()

    // Return a copy to avoid holding lock while the caller processes the data.
    result := make([]*Character, len(room.characters))
    copy(result, room.characters)
    return result
}
```

## Deadlock Prevention Strategies

### 1. Timeout-based Lock Acquisition

For non-critical operations that might block, consider using a timeout. This is an advanced technique and should be used sparingly.

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

For high-throughput systems, channels can be used to serialize operations on a resource, managed by a single goroutine.

```go
// Instead of locking for updates
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
// In development/test builds
import "github.com/sasha-s/go-deadlock"

// Replace sync.RWMutex with deadlock.RWMutex
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

### 1. Lock Inversion (Game World -> System)

This is the most critical error to avoid in this architecture.

**Wrong:**

```go
character.mutex.Lock()
// ... do some work ...
player.mutex.Lock() // BAD: Acquiring System lock while holding Game World lock
```

**Correct:**

```go
player.mutex.Lock()
character.mutex.Lock()
// ... do work ...
character.mutex.Unlock()
player.mutex.Unlock()
```

### 2. Holding Locks During I/O

Never perform slow operations like network or disk I/O while holding a lock.

**Wrong:**

```go
character.mutex.Lock()
database.Save(character)  // BAD: Slow I/O operation while holding a lock
character.mutex.Unlock()
```

**Correct:** (As shown in Pattern 5)

```go
character.mutex.RLock()
data := character.copyData()
character.mutex.RUnlock()
database.Save(data)
```

### 3. Unlocking Too Late

Using `defer` can sometimes hold a lock for longer than necessary, impacting responsiveness.

**Acceptable (but can be improved):**

```go
func processPlayerAndGame(player *Player, game *Game) {
    player.mutex.Lock()
    defer player.mutex.Unlock() // Lock held for the entire function

    character := player.character
    // Player lock is no longer needed after this point.

    game.mutex.Lock()
    defer game.mutex.Unlock()
    // ... perform complex operations on the game state ...
}
```

**Better (for responsiveness):**

```go
func processPlayerAndGame(player *Player, game *Game) {
    player.mutex.RLock()
    character := player.character
    player.mutex.RUnlock() // Explicit unlock as soon as reference is obtained

    game.mutex.Lock()
    // ... perform complex operations on the game state ...
    game.mutex.Unlock()
}
```

## Performance Considerations

### 1. Read vs Write Locks

-   Use `RLock()` whenever possible for read-only operations to allow multiple readers to proceed concurrently.
-   A `Lock()` for writing is exclusive and will block all other readers and writers.

### 2. Lock Granularity

-   The separation of System and Game World locks is a form of high-level granularity that prevents I/O from blocking the game simulation.
-   Avoid locking the entire `Game` object when a `Room` or `Character` lock will suffice.

### 3. Lock Duration and Explicit Unlocks

-   High-level locks (`Server`, `Game`) are points of high contention. Hold them for the shortest possible duration.
-   In functions that interact with these objects, acquire the lock, get the data you need, and release the lock explicitly. Do not hold the lock while performing logic that doesn't depend on the protected state.

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
1.  Set the environment variable `GOTRACEBACK=all`.
2.  Send a `SIGQUIT` signal to your running process (`kill -QUIT <pid>`).
3.  Examine the stack traces for circular lock dependencies.

### 3. Logging Lock Operations

In a debug build, adding logs for lock acquisition and release can help trace complex interactions.

```go
func (r *Room) Lock() {
    log.Printf("Acquiring lock for Room %d", r.ID)
    r.mutex.Lock()
    log.Printf("Acquired lock for Room %d", r.ID)
}
```

## Future Considerations

### 1. Lock-free Data Structures

For performance-critical hot paths, explore using specialized lock-free data structures or atomic operations from the `sync/atomic` package.

### 2. Actor Model

For certain subsystems, an actor-based model (where each component is a goroutine processing messages from a channel) can eliminate the need for explicit locks entirely by serializing access.

### 3. Software Transactional Memory (STM)

For very complex operations involving many objects, STM libraries can simplify development by making multi-object transactions appear atomic, though they may come with a performance overhead.

## References

-   [Go Memory Model](https://golang.org/ref/mem)
-   [Effective Go - Concurrency](https://golang.org/doc/effective_go#concurrency)
-   [Go Concurrency Patterns](https://go.dev/blog/pipelines)
-   [Deadlock Prevention Algorithms](https://en.wikipedia.org/wiki/Deadlock_prevention_algorithms)