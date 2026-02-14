# 1. Canonical rule
**Every new room gets indexed immediately, before any analysis expands.**

That means:

* file name first,
* internal title second,
* links normalized as I touch them,
* canvas nodes updated last.
Never "just jot a room and fix it later".

# 2. File naming
From this point forward, **all new room files** should be created as:

Z1 - Canonical Room Name.md

Examples:

* Z1 - Troll Room.md
* Z1 - Forest Path.md
* Z1 - Attic.md

Do not abbreviate, number, or decorate further. The prefix already does the work.

If Obsidian is still auto-creating files without the prefix, that's fine--rename it immediately after creation. Obsidian will update links.

# 3. Internal title discipline
Inside each room file, the top-level heading should be:

# 4. Canvas practice while indexing continues
Keep using **one canvas** for now:

Zork - World.canvas

On the canvas:
* Node titles should match the room title exactly
  (Z1 - Living Room)
* Do not abbreviate nodes even if it looks crowded
* Let density reveal structure; don't "tidy" yet

The canvas is a **live index with topology**, not a finished diagram.

# 5. Add a Numeric ID field
For maximum future-proofing (especially for Zork II-III comparisons), I add a *hidden numeric ID* inside each room file.

In the **Mapping notes** section only:

Internal ID: ZI-R-014

Rules:

* IDs are sequential, per game
* IDs never appear in filenames or canvas nodes
* IDs are never reused

This gives me a stable referent later if name changes or collide, without polluting readability