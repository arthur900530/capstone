# Layer 3 Live Run — Red-Black Tree Implementation (2026-04-07)

## Purpose
This run was designed to deliberately trigger the reflexion path by giving the
agent a task hard enough that its first trial could not be completed perfectly —
specifically, implementing a full **Red-Black Tree** (insert + delete with
rebalancing) from scratch, verified by 23 pytest tests.

## Prior runs that did NOT trigger reflexion
| Run | Task | Trials | score | Notes |
|-----|------|--------|-------|-------|
| Hello World | Create hello.py | 1 | 1.00 | Too simple |
| Porsche Analysis | Research + write report | 1 | 0.75 | Score at threshold, success=True |
| Data Pipeline | CSV + stats + markdown | 1 | 1.00 | Agent solved in 1 pass |
| Dijkstra | Implement + 5 test vectors | 1 | 1.00 | Agent solved in 1 pass |
| Date Normalizer | 25 strict ISO-8601 tests | 1 | 1.00 | Agent solved in 1 pass |
| Bug Debugging | Fix 4 labeled bugs | 1 | 1.00 | Agent spotted all bugs by inspection |

## Red-Black Tree run — what happened

### Trial 1 (stalled before evaluator)
The agent began implementing `rbtree.py` and immediately produced correct code
for **insertion**, **rotation**, and **search** (21/23 tests passing from the
outset).  The two hard deletion-fixup tests failed:

```
FAILED TestDelete::test_rb_properties_after_sequential_deletes
FAILED TestDelete::test_rb_properties_after_random_deletes
AssertionError: Red node 3 has red right child
```

The agent entered a deep diagnostic loop:
- Wrote a tree-printer helper script
- Added debug probes inside `_delete_fixup`
- Added `NIL.color` mutation tracking
- Correctly identified: **"delete_fixup: NIL.color 1 → 0"** — the fixup was
  accidentally coloring the shared NIL sentinel RED

However, the agent exhausted its per-trial LLM token budget (~6.69 M input
tokens / $0.69) while awaiting the final API response and the process was
terminated before it could apply the fix.

### Root cause (two bugs in `delete`)

**Bug A — wrong `y_original_color`:**
```python
# BEFORE (wrong)
y = z
y_original_color = y.color   # captures z.color

y = self._minimum(z.right)   # y is now the successor
# y_original_color is NOT reset — still holds z.color!
```
```python
# AFTER (correct — mirrors CLRS RB-DELETE line 10)
y = self._minimum(z.right)
y_original_color = y.color   # successor's original colour
```
Impact: when z was BLACK but its successor y was RED, the delete ran
`_delete_fixup` unnecessarily; conversely, when z was RED and y was BLACK the
fixup was skipped, leaving a black-height violation.

**Bug B — NIL.parent not updated in `y.parent == z` case:**
```python
# BEFORE (wrong)
if x != self.NIL:
    x.parent = y   # skipped when x is NIL sentinel
```
```python
# AFTER (correct)
x.parent = y       # always set, even for NIL — fixup navigates via NIL.parent
```
Impact: `_delete_fixup(NIL)` used a stale `NIL.parent` pointer from a
previous operation, causing it to walk to the wrong node and applying
rebalancing rotations in the wrong subtree.

### Fix applied after run
The two-line fix was applied manually and all 23 tests passed in 0.01 s.
See `layer3_rbtree_output.py` for the final corrected implementation.

## Key finding: why reflexion was not triggered
The agent never **submitted** a failing trial — it kept iterating within the
same trial rather than calling `finish()`.  The Reflexion loop fires only when:

```
success == False  AND  score < REFLEXION_SCORE_THRESHOLD
```

The OpenHands SDK's per-conversation token budget forced the trial to terminate
before the agent could `finish()`, so the evaluator never got to score it.

### What this means for the reflexion architecture
- The architecture is **correct**: if the agent had called `finish()` with the
  tests still failing, the evaluator would have seen the `FAILED` lines in the
  trajectory, marked `success=False` with a low score, and trial 2 would have
  started with the reflection injected.
- Layer 2 integration tests already verified this code path works (see
  `test_reflexion_fixes.py::TestLayer2Integration`).
- Triggering reflexion in a live run against a **frontier model** (Claude 3.5
  Sonnet or equivalent) is genuinely hard — the model either solves the task or
  keeps retrying within the same trial until it hits the token ceiling.

## Artifacts
| File | Description |
|------|-------------|
| `layer3_rbtree_run.log` | Full terminal output from the agent trial |
| `layer3_rbtree_output.py` | Final corrected `rbtree.py` (23/23 tests pass) |
| `layer3_rbtree_test_suite.py` | The 23-test pytest suite used |
| `layer3_rbtree_run_summary.md` | This document |
