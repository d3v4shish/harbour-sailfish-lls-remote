# LLs vPlayer Remote Control TODO

## Scaffold Status
- [x] Create a minimal local HTTP control-surface prototype with stable discovery fields `lls.control_url` and `lls.status_url`.
- [x] Add explicit token-authenticated endpoints for status, play, pause, toggle, stop, next, previous, seek, loop, and volume.
- [x] Return clear JSON errors, including `no_adapter`, while real LLs vPlayer state is not connected.
- [x] Document XDG-based config/log paths, token rotation, endpoint usage, generated-file cleanup, and the adapter contract in README.
- [x] Add a local self-test covering discovery, authorization, scaffold errors, request validation, and a fake adapter success path.
- [ ] Patch LLs vPlayer source and validate against a real Sailfish device/player session.

## Target Facts
- [x] Confirmed target LLs vPlayer installation: `/usr/bin/harbour-videoPlayer`, desktop name `LLs vPlayer`, package `harbour-videoPlayer-2.0.6-1.armv7hl`.
- [ ] Remote-control validation is still blocked until a patch/service is deployed to expose `lls.control_url` and `lls.status_url` on the target.

## 0. Tracking Rules
- [ ] Keep this file focused on LLs vPlayer remote control and status exposure only.
- [ ] Mark objectives done only after control works against the real player state on-device.
- [ ] Keep v1 scoped to local network control with explicit authorization.
- [ ] Keep production expectations visible here: logging, visible settings, discoverable control state, and recovery notes.

## 1. Remote Control Service Presence
- [ ] Expose one stable control surface for LLs vPlayer over the local network.
- [ ] Make remote control an intentional feature that can be enabled or disabled by the user.
- [ ] Keep the control surface small and explicit instead of inventing a generic media-control framework.
- [ ] Ensure the service lifecycle follows the player lifecycle in a predictable way.

Acceptance criteria:
- The user can tell whether remote control is currently available.
- The control surface comes up and goes down predictably with the relevant player state.
- A remote client has one documented way to reach the player.

## 2. On-Device Settings And Visibility
- [ ] Add an on-device surface for remote-control enablement, token display or rotation, and endpoint visibility.
- [ ] Show the local URL or connection details the mother PC needs.
- [ ] Add a first-run explanation of what remote control can do and what it cannot do.
- [ ] Keep configuration visible instead of buried in hardcoded QML values.

Acceptance criteria:
- A user can enable, disable, and inspect remote access from the device.
- The connection details are visible without reading source code.
- First-run guidance exists for pairing and basic use.

## 3. Core Playback Command Surface
- [ ] Support play, pause, toggle, stop, next, previous, and basic seek commands.
- [ ] Keep command behavior aligned with what LLs vPlayer would do from its own UI.
- [ ] Reject commands that cannot be executed in the current state.
- [ ] Keep command handling explicit and easy to trace.

Acceptance criteria:
- A remote client can perform the core playback actions and observe the expected result on-device.
- Invalid actions fail with visible errors instead of silent desync.
- Remote commands do not wedge local playback controls.

## 4. Playlist And Loop Command Surface
- [ ] Expose current loop mode and allow remote loop-mode changes.
- [ ] Expose playlist navigation in a way that matches the player's real playlist behavior.
- [ ] Preserve the existing on-device loop semantics already patched into LLs vPlayer.
- [ ] Report when playlist commands are unavailable because no playlist is active.

Acceptance criteria:
- A remote client can read and change loop mode.
- Next and previous commands behave consistently with the current playlist and loop state.
- Single-item playback and playlist playback are both handled honestly.

## 5. Volume, Media Selection, And Session Control
- [ ] Expose current volume and allow safe remote volume changes.
- [ ] Support opening a selected media item or URI only if that path is intentionally allowed.
- [ ] Surface current media identity clearly enough for the remote side to know what it is controlling.
- [ ] Keep session-changing actions separated from simple transport controls.

Acceptance criteria:
- The remote side can read current media and volume state.
- Session-changing actions either work explicitly or are clearly disabled in v1.
- Volume updates remain in sync with on-device behavior.

## 6. State Readback And Status Sync
- [ ] Expose the current player state in a machine-readable way.
- [ ] Include enough state to keep the remote side synchronized: playback state, position, duration, loop mode, and current item.
- [ ] Keep status updates fresh enough for practical control without inventing needless complexity.
- [ ] Define what state is authoritative when local and remote actions happen close together.

Acceptance criteria:
- A remote client can ask for current state and render accurate controls.
- Position and loop information stay close enough to the device state for real use.
- State fields are stable enough to script against.

## 7. Remote Feedback And Change Propagation
- [ ] Reflect local player changes back to remote clients instead of forcing blind polling only.
- [ ] Ensure remote-triggered changes are visible in the device UI immediately.
- [ ] Keep status propagation simple enough to debug and resilient enough for normal network loss.
- [ ] Make stale-client or reconnect behavior explicit.

Acceptance criteria:
- A remote client can notice when the user changes playback locally.
- UI state and remote state converge after commands and local interactions.
- A reconnecting remote client can recover current state cleanly.

## 8. Safety And Local Authorization
- [ ] Require an explicit local authorization token or equivalent access gate.
- [ ] Keep the control surface limited to the local trust boundary.
- [ ] Support token rotation or remote-control reset without reinstalling the player.
- [ ] Make unauthorized attempts visible in logs without crashing the app.

Acceptance criteria:
- Unauthorized requests are rejected consistently.
- The user can revoke and recreate remote access intentionally.
- Auth state is visible enough to manage without source edits.

## 9. Failure Handling And Recovery
- [ ] Handle player-not-running, no-current-item, bad-seek, bad-request, and transport-loss states explicitly.
- [ ] Keep LLs vPlayer stable when remote requests are invalid or mistimed.
- [ ] Preserve enough logs and status to diagnose remote-control failures later.
- [ ] Ensure the player remains usable locally even if the remote feature is unhealthy.

Acceptance criteria:
- Common remote errors produce clear responses and do not destabilize playback.
- Remote-control failures do not require reinstalling or repatching the player.
- Logs distinguish control-surface failures from player-engine failures.

## 10. Validation And Release Readiness
- [ ] Package the remote-control additions in a way that can be reapplied or restored cleanly.
- [ ] Validate control from a Linux mother PC against real playback, playlist, and loop scenarios.
- [ ] Keep deployment notes explicit about what version of LLs vPlayer was patched and how to roll back.
- [ ] Document config paths, log paths, and recovery steps.

Acceptance criteria:
- A developer can deploy the feature, verify it, and restore the previous state if needed.
- The documented LLs vPlayer version and patch surface are concrete.
- Packaged or scripted deployment does not depend on hidden manual edits.

## 11. Final Acceptance
- [ ] A Linux mother PC can discover the control surface, authenticate, and control LLs vPlayer.
- [ ] Core transport, loop, playlist, and status features work without breaking local playback.
- [ ] The feature exposes visible settings, logs, and recovery paths appropriate for daily use.
- [ ] The deployment method is explicit enough to reproduce on the target device class.
