## Planning Tool

#### Parameters

- **action**: `update`, `advance`
- **goal**: A concise high-level goal for the plan (Required for `update`).
- **phases**: List of phases (Required for `update`).
    - `id`: Integer
    - `title`: String
    - `capabilities`: Object (e.g., `{ "tool_name": true }`)
- **current_phase_id**: ID of the phase being completed (Required for `advance`).
- **next_phase_id**: ID of the next phase to start (Required for `advance`).

#### Behavior

- **Update (`action='update'`)**:
    - Creates a new plan or overwrites the existing one.
    - **Resets Progress**: The plan status is fully reset. The first phase is marked as `in_progress`, and all others as `pending`. Previous progress is NOT preserved.
    - Useful for replanning or refining the strategy.

- **Advance (`action='advance'`)**:
    - Marks `current_phase_id` as `completed`.
    - Marks `next_phase_id` as `in_progress`.
    - **Auto-Completion**: If `next_phase_id` is not the immediate next phase (i.e., skipping steps), all phases *between* the start and `next_phase_id` are automatically marked as `completed`.

#### Examples

**Create/Update Plan:**

```json
{
  "action": "update",
  "goal": "Plan a perfect weekend trip",
  "phases": [
    {
      "id": 1,
      "title": "Decide destination and weather",
      "capabilities": { "deep_research": true }
    },
    {
      "id": 2,
      "title": "Plan detailed itinerary and budget",
      "capabilities": { "data_analysis": true }
    }
  ]
}
```

**Advance Plan (Standard):**

```json
{
  "action": "advance",
  "current_phase_id": 1,
  "next_phase_id": 2
}
```

**Advance Plan (Skipping):**

```json
{
  "action": "advance",
  "current_phase_id": 1,
  "next_phase_id": 3
}
```
*Note: Phase 2 will be automatically marked as completed.*