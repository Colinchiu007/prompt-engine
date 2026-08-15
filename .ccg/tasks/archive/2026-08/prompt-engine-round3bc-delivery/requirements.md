# Requirements - Standalone Higgsfield Round3 B/C engine delivery

- Validate and cache-isolate bounded cross-scene state (prev_final_frame and
  planned final_frame) and use it for advisory continuity-aware selection.
- Preserve an optional, bounded 12-block director shape in the refined tier
  while retaining legacy rendering for callers that omit blocks.
- Keep trailer removal structurally safe, FAIL CHECK instruction-only, and
  coverage/gated findings advisory and negation-aware.
- Publish reproducible corpus assets, focused regression coverage, and a V4
  format cache salt compatible with the desktop contract.

## Acceptance

- pytest tests/ -q and focused Round3 tests pass.
- The changed modules compile without syntax errors.
- External dual-model review is attempted and documented accurately.
- The companion Multi-Publish contract PR merges before task archive.
