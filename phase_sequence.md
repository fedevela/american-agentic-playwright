# Phase Sequence

The system implements an 11-phase SDLC workflow in strict sequential order:

**Sequence**: 1 → 2a → 2b → 2c → 3 → 4 → 5 → 6 → 7 → 8 → 9

Each phase hands off to exactly one next phase in the chain.

## Phase Mapping (Tree of Life)

| Phase | Name | Numeric Position |
|-------|------|------------------|
| 1 | Keter | 1 |
| 2a | Chokhmah | 2 |
| 2b | Binah | 3 |
| 2c | Chesed | 4 |
| 3 | Gevurah | 5 |
| 4 | Tiferet | 6 |
| 5 | Netzach | 7 |
| 6 | Hod | 8 |
| 7 | Yesod-Orchestration | 9 |
| 8 | Yesod-Embodiment | 10 |
| 9 | Malkhut | 11 |

## Flow

```
1 (Keter)
  ↓
2a (Chokhmah)
  ↓
2b (Binah)
  ↓
2c (Chesed)
  ↓
3 (Gevurah)
  ↓
4 (Tiferet)
  ↓
5 (Netzach)
  ↓
6 (Hod)
  ↓
7 (Yesod-Orchestration)
  ↓
8 (Yesod-Embodiment)
  ↓
9 (Malkhut)
```

## Implementation

The `trigger.py` file defines `NEXT_LABEL_MAP` with single-label transitions:
- `phase:keter` → `phase:chokhmah`
- `phase:chokhmah` → `phase:binah`
- `phase:binah` → `phase:chesed`
- `phase:chesed` → `phase:gevurah`
- `phase:gevurah` → `phase:tiferet`
- ... and so on

The `determine_phase_from_label()` function maps labels to numeric positions 1-11.
