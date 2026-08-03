# NEXUS Cross-Device Product Specification V1

Do not implement apps in this track.

## Surfaces

- Desktop
- Tablet
- Mobile
- Responsive Web / PWA
- Future iOS
- Future Android

## Product invariants

- Single account
- Single Decision Object model
- Cloud sync of Decision Graph
- Same permissions model across devices

## Offline behavior

- Read last synced Decisions
- Queue local drafts for Context/Thesis/Decision notes
- Sync with conflict detection on reconnect

## Device handoff

- Continue an in-progress Decision from phone to desktop without duplicating IDs
- Preserve append-only event order via server timestamps + client UUIDs

## Version conflicts

- Last-write-wins forbidden for committed Decisions
- Conflicts create parallel draft branches or require explicit merge/correction events
- Replay remains possible for each committed version
