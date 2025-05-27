# Ordinal Selection Examples

The ordinal selection utility allows players to specify which item they want when multiple items have the same name.

## Usage Examples

### Picking up items:

```
> look
You see:
  3 books
  2 swords

> get book
Which book? There are 3 here. Try 'get first book' or 'get second book'

> get second book
You pick up book.

> get third sword
There aren't that many swords here.
```

### Dropping items:

```
> inventory
You are carrying:
  5 torches
  2 potions

> drop torch
Which torch? You have 5. Try 'drop first torch' or 'drop second torch'

> drop third torch
You drop torch.
```

### Movement:

```
> look
Exits: north, north, east

> go north
Which way? There are 2 exits north. Try 'go first north' or 'go second north'

> go second north
You go north.
```

### Container operations:

```
> inventory
You are carrying:
  2 backpacks
  3 books

> put book in backpack
Which book? You have 3. Try 'put first book in backpack'
Which backpack? You have 2. Try 'put book in first backpack'

> put second book in first backpack
You put book in backpack.

> look in my second backpack
The backpack contains:
  torch
  potion
```

## Ordinal Words Supported

- first through twentieth

## Design Constraints

- Maximum of 20 items with same name supported
- If no ordinal specified, defaults to first item
- Clear error messages guide players to use ordinals when needed
