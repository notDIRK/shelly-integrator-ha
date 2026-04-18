# Roadmap — Shelly Cloud DIY for Home Assistant

> 🇩🇪 **Deutsch:** Eine deutschsprachige Fassung dieses Dokuments findest du in [`ROADMAP.de.md`](ROADMAP.de.md).

## Project intent

`shelly-cloud-diy-ha` is a Home Assistant custom integration that connects
Home Assistant to the Shelly Cloud using the **Cloud Control API**, the
self-service API path that Shelly explicitly documents as being available
to DIY / private users. The project exists because the only pre-existing
community integration in the same space ([engesin/shelly-integrator-ha](https://github.com/engesin/shelly-integrator-ha))
uses the **Integrator API**, which Shelly documents as *"Licenses for
personal use are not provided."* — it requires a commercial-integrator
approval flow that most private users never get through.

This project is a hard fork of that upstream, retained for git-history
traceability only. No upstream merges are expected.

## Scope target

- **Short term:** installable via **HACS** (currently as a custom repository,
  subsequently in the HACS default store).
- **Not a short-term goal:** submission to **Home Assistant Core**. Code is
  kept Core-compatible in style (no personal references in source, English
  log messages, proper exception types, translations), but we are not
  building out the full Core quality-scale requirements (heavy test
  coverage, diagnostics/repairs platforms, quality_scale=gold) in the
  initial releases.

## Milestones

Status key: ✅ done · 🔄 in progress · ⏳ planned · 💡 aspirational

### Milestone 0 — Foundation  ✅

- Forked `engesin/shelly-integrator-ha` as `notDIRK/shelly-integrator-ha`.
- Security hardening: randomised per-install webhook id, local-gateway-URL
  SSRF guard, webhook-handler logging uses `logger.exception`.
- Correctness: deep-merge partial StatusOnChange updates, disabled dead 30 s
  polling timer, jittered WebSocket reconnect backoff.
- Consolidated codebase map at `docs/CODEBASE_MAP.md` (pre-pivot snapshot).
- Bilingual "Getting an API Token" section in the old README — now largely
  obsolete post-pivot.
- Pivot research: verified the Shelly Cloud Control API sees shared
  devices (tested against a real ECOWITT WS90 shared from another
  account); verified the Cloud Control API WebSocket rejects `auth_key`
  (`Token-Broken` close 4401) and requires OAuth; confirmed HTTP polling
  via `auth_key` returns full device status for all account-visible
  devices.
- Repo rename to `shelly-cloud-diy-ha`, Python domain to `shelly_cloud_diy`,
  CLOUD DIY branding applied to `images/icon.png`.
- Three historical release tags (`v0.1.0-notDIRK` … `v0.2.2-notDIRK`) kept
  on their Integrator-API commits for audit trail.

### Milestone 1 — Cloud Control API with `auth_key` + HTTP polling  🔄 (next)

**Goal:** First usable HACS release for private users. No Integrator-API
token, no Shelly support email, no consent webhook. User pastes their
`auth_key` + server URI from the Shelly App and everything works.

Changes:
- Replace auth layer: delete `api/auth.py` (JWT / integrator-token
  exchange), add `api/cloud_control.py` (HTTP client wrapping
  `POST /device/all_status`, `POST /device/status`, `POST /device/relay/control`,
  `POST /device/light/control`, `POST /device/relay/roller/control`, all
  authenticated via the `auth_key` form parameter).
- Rewrite `config_flow.py` — user step asks for `auth_key` + `server URI`;
  no consent step; options flow simplified accordingly.
- Rewrite `coordinator.py` to poll `/device/all_status` at a configurable
  interval (3–60 s, default 5 s), respecting the documented 1 req/s rate
  limit (a single consolidated poll beats per-device fan-out).
- Remove: consent webhook flow (`services/webhook.py`, `core/consent.py`,
  webhook-id migration logic in `__init__.py`), `api/websocket.py` (moved
  to M2 scope).
- Keep reusable: device-state merge logic, per-platform entity classes
  (sensor, switch, light, cover, button, binary_sensor), entity
  descriptions, historical CSV service (local-gateway path is unchanged).
- Add: entity mapping for BLE / gateway-bridged sensors seen in
  `/device/all_status` with `gen: "GBLE"` (Shelly BLU family, Shelly BLU
  H&T, SBWS-90CM weather station, etc. — one mapping table keyed by
  `_dev_info.code`).
- Update: translations and `strings.json` for the new config fields
  (`auth_key`, `server_uri` replacing `integrator_token`); German
  translation added (`translations/de.json`).
- Manifest: bump to `0.3.0`, update `iot_class` to `cloud_polling`
  (because push is no longer the mechanism), drop unused `dependencies: ["webhook"]`.
- Release: `v0.3.0` tagged without the `-notDIRK` suffix going forward —
  targeting HACS-default-store submission eventually.

Non-goals in M1:
- Real-time / sub-5-second update latency (that is M2).
- OAuth authentication (that is M2).
- Cloud-sourced historical energy data (the existing local-gateway path is
  preserved; cloud historical is a separate later scope if feasible).

Explicitly documented limitations users must know:
- **1 request per second** rate limit per Shelly account (Shelly official
  doc).
- **Polling latency** at default 5 s means sensor values lag reality by up
  to ~5 seconds; switch actions fire immediately, latency only applies to
  state *observation*.
- **HTTP endpoints are documented by Shelly as intentionally
  underdocumented** (they reserve the right to change parameter formats)
  — we pin to the v1 endpoint shape and will track changes reactively.

### Milestone 2 — OAuth + WebSocket realtime  ⏳

**Goal:** Push-based realtime updates for users willing to authenticate
with email + password instead of (or in addition to) the `auth_key`.

Changes:
- Add OAuth code flow to `config_flow.py`:
  `POST https://api.shelly.cloud/oauth/login` with `email` +
  `sha1(password)` + `client_id=shelly-diy` → receive `code` →
  `POST https://<server>/oauth/auth` with `code` → receive `access_token`.
- Bring back `api/websocket.py` (architecturally reused from the
  pre-pivot Integrator-API era — the WSS endpoint format is identical)
  and use OAuth `access_token` as the `t=` URL parameter.
- Swap coordinator's polling loop for WebSocket event subscription
  (`Shelly:StatusOnChange`, `Shelly:Online`, `Shelly:CommandResponse`).
- Access-token lifecycle: track expiry, refresh proactively, fall back to
  re-OAuth if refresh fails.
- Options flow: let the user switch between Simple (auth_key / polling)
  and Full (OAuth / realtime) modes without reinstalling.

Non-goals in M2:
- Per-device webhook subscriptions (the WebSocket delivers everything).

### Milestone 3 — HACS default-store submission  💡

**Goal:** Entry in the [HACS default integration list](https://github.com/hacs/default),
so that users no longer need to add this as a custom repository URL.

Prerequisites:
- Logo submission to [home-assistant/brands](https://github.com/home-assistant/brands)
  as `core_integrations/shelly_cloud_diy/{icon.png,logo.png}` — clean
  variants without the `notDIRK` wordmark and fork symbol will be
  generated at this point.
- First stable (non-`-dev`) release tag.
- README finalised and passing the HACS style review.
- Issue tracker with at least a few closed / triaged issues (to show
  active maintenance).
- Optional: simple GitHub Actions CI that runs lint and any existing
  tests on push / PR.

### Milestone 4 — Quality-scale improvements  💡

Path to HA Core quality-scale `silver` / `gold`:
- `async_get_config_entry_diagnostics` for sanitized export.
- `repairs` platform for actionable issue flags (rate-limit exhaustion,
  token expiry, etc.).
- Test coverage target ≥ 70 %.
- CI: lint, type-check (mypy), test matrix against supported HA versions.

(Not committed to a timeline — gated on whether a Core submission
materialises as a goal.)

## Differentiation vs existing projects

| Project | Auth method | Realtime | Shared devices | Maintained | Notes |
|---|---|---|---|---|---|
| **`notDIRK/shelly-cloud-diy-ha`** (this repo) | `auth_key` (M1) / OAuth (M2) | HTTP poll 5 s (M1) / WebSocket push (M2) | ✅ | 🔄 active | Full Gen1 + Gen2 + BLE-gateway coverage |
| [`engesin/shelly-integrator-ha`](https://github.com/engesin/shelly-integrator-ha) | Integrator API token (gated by Shelly) | WebSocket push | ❌ (consent-flow is per-owner) | ✅ active | Private users typically cannot obtain the token |
| [`home-assistant/core` Shelly integration](https://www.home-assistant.io/integrations/shelly/) | Local LAN (mDNS / direct IP) | LAN push | ❌ (remote / shared devices not reachable over LAN) | ✅ maintained by HA Core | Mainstream; requires LAN reachability |
| [`StyraHem/ShellyForHASS`](https://github.com/StyraHem/ShellyForHASS) | Local LAN | LAN push | ❌ | ❌ *"ShellyForHass will no longer receive further development updates"* per README | Folded into HA Core |
| [`vincenzosuraci/hassio_shelly_cloud`](https://github.com/vincenzosuraci/hassio_shelly_cloud) | Username/password (reverse-engineered browser calls) | HTTP polling | ? | ❌ last push 2019 | Switches only; README warns HTTP parsing is fragile |
| [HA YAML Blueprint](https://community.home-assistant.io/t/controlling-shelly-cloud-devices-in-home-assistant/928462) | `auth_key` (same as us) | ❌ command-only | ? | ✅ community-maintained | *"The device state is not updated from the cloud"* — cannot read state back |
| [`corenting/poc_shelly_cloud_control_api_ws`](https://github.com/corenting/poc_shelly_cloud_control_api_ws) | OAuth | WebSocket push | ? | Explicitly labelled POC, not an integration | Reference implementation for our M2 OAuth flow |

The short version: there is currently **no other maintained HA
integration that combines Cloud-Control-API-based access with state
reading AND shared-device support AND Gen1/Gen2/BLE coverage**. The gap
is real, which is why this project exists.

## Rate limits, latency, and honest expectations

**Shelly's documented rate limit:** 1 API request per second per account
(source: [Shelly Cloud Control API docs, Getting Started](https://shelly-api-docs.shelly.cloud/cloud-control-api/)).

**Milestone 1 traffic profile:**
- A single `POST /device/all_status` returns the complete state snapshot
  of every device your account can see (owned + shared + BLE-bridged).
  58-device accounts return ≈ 60 KB per request.
- Default poll interval: 5 s → average traffic ≈ 12 KB/s outbound HTTPS.
  Configurable down to 3 s (24 KB/s at 58 devices) for snappier state or
  up to 60 s for low-traffic / battery-sensitive setups.
- User-initiated commands (switch on/off, dim, roller) are dispatched
  immediately via separate HTTP POSTs; they do not wait for the next
  poll cycle. Commands and polls share the 1 req/s budget, so the
  default 5 s interval leaves ~4 req/s of command headroom.
- Observed state-change latency: **p50 ≈ 2.5 s, p99 ≈ 5 s** at default
  poll interval. For weather station / energy metering use cases this is
  a non-issue; for light-switch feedback it can feel gentle.

**Milestone 2 traffic profile (future):**
- Outbound poll traffic: **0 bytes** steady state; events push from
  Shelly Cloud as they happen.
- Latency: **< 100 ms** for state propagation from device → Shelly Cloud
  → HA.
- Cost: single persistent WebSocket connection per HA instance; one
  OAuth re-auth roughly every 24 hours.

## Security and data handling

- The `auth_key` is stored in `entry.data` (Home Assistant standard
  config-entry storage, plaintext at rest in `.storage/core.config_entries`).
  The key grants broad device control — treat it like a password.
- It is displayed by the Shelly App under **User settings → Authorization
  cloud key**. Changing your Shelly password invalidates it
  server-side, which is the intended rotation mechanism.
- Milestone 1 does not store email or password.
- Milestone 2 (OAuth) sends `sha1(password)` to
  `api.shelly.cloud/oauth/login` during the initial login; the resulting
  `access_token` is stored in `entry.data`. We do not store the password
  itself.
