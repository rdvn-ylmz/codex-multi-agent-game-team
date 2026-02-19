Build a playable browser game vertical slice (not debug-sim only).

Mandatory gameplay outcomes:
- Real-time playable loop with meaningful input and challenge.
- Player movement and feel (acceleration, friction, responsiveness).
- Spawn system for collectibles and hazards.
- Collision + damage + recovery feedback.
- Core objective with win/lose states.
- Score + combo or progression signal.
- Pause, restart, and return-to-title flow.

Implementation constraints:
- Keep architecture modular: state, entities, systems, UI.
- Preserve low-spec strategy: minimal files, fast local checks, heavy tests in CI.
- Add at least one smoke test path for key gameplay loop.

Artifact expectations:
- Updated runnable game files (html/js/css as needed).
- docs/playtest_checklist.md
- docs/controls.md
- docs/gameplay_tuning.md
- QA smoke scenarios and expected outcomes.

Audio/visual support:
- If needed, generate placeholder assets through tool adapter jobs
  (`music_tone`, `image_svg`) and register them in `assets/manifest.json`.

Definition of done:
- A human can play 2-3 minute session without using debug buttons.
- Game-over and restart are reliable.
- At least one balancing pass documented.
