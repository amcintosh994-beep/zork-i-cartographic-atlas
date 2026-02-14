# Z1 - Behind House

## Description (verbatim)
You are behind the White House. A path leads into the Forest to the east. In one corner of the House there is a small window which is slightly ajar.

## Exits (as reported)
- N → [[Z1 - North of House]]
- E → [[Z1 - Clearing A]]
- S → [[Z1 - South of House]]
- SW → [[Z1 - South of House]]
- W → [[Z1 - Kitchen]] (once window is open)
- NW → [[Z1 - North of House]]

## Blocked movements
- ...

## Hidden/conditional transitions
- W → "The Kitchen window is closed."
-  ENTER WINDOW → [[Room - Kitchen]] (requires window open)

## Objects present
- ...

## Hazards/NPCs
- ...

## Key parser interactions
- OPEN WINDOW → window state changes to open; entry enabled.

## State notes
- Window state: initially closed; can be opened.
- Lit

## Mapping notes
**Internal ID**: Z1-R-003
**First mapped**: 2026 Feb. 3
**Revisions**:

- First room where a non-directional entry affordance (window) enables interior access.
