# Roadmap — Shelly Cloud DIY für Home Assistant

> 🇬🇧 **English:** The primary language of this project is English. See [`ROADMAP.md`](ROADMAP.md) for the English version.

## Projektziel

`shelly-cloud-diy-ha` ist eine Home-Assistant-Custom-Integration, die Home
Assistant über die **Cloud Control API** von Shelly anbindet — also über
den offiziellen Self-Service-Pfad, den Shelly ausdrücklich für DIY- und
Privat-User vorgesehen hat. Das Projekt existiert, weil die einzige
bisher verfügbare Community-Integration in diesem Themenfeld
([engesin/shelly-integrator-ha](https://github.com/engesin/shelly-integrator-ha))
die **Integrator API** nutzt, zu der Shelly wörtlich dokumentiert:
*"Licenses for personal use are not provided."* — dafür ist ein
kommerzieller Integrator-Freigabeprozess nötig, durch den die meisten
Privatanwender nie durchkommen.

Dieses Projekt ist ein Hard-Fork von oben genanntem Upstream, den wir nur
wegen Git-History-Nachvollziehbarkeit behalten. Weitere Upstream-Merges
sind nicht vorgesehen.

## Scope-Ziel

- **Kurzfristig:** Installierbar via **HACS** (zunächst als Custom
  Repository, später im HACS-Default-Store).
- **Kein Kurzfrist-Ziel:** Aufnahme in **Home Assistant Core**. Wir halten
  den Code stilistisch Core-kompatibel (keine Personennamen im Quellcode,
  englische Logmeldungen, ordentliche Exception-Typen, Übersetzungen) —
  aber wir bauen den vollen Core-Qualitätsstandard (umfangreiche Tests,
  Diagnostics-/Repairs-Platforms, quality_scale=gold) in den ersten
  Releases bewusst NICHT aus.

## Meilensteine

Status: ✅ fertig · 🔄 in Arbeit · ⏳ geplant · 💡 angestrebt

### Meilenstein 0 — Grundlage  ✅

- `engesin/shelly-integrator-ha` geforkt als `notDIRK/shelly-integrator-ha`.
- Security-Härtung: randomisierte Per-Install-Webhook-ID, SSRF-Schutz für
  Local-Gateway-URL, Webhook-Handler-Logging über `logger.exception`.
- Korrektheit: Deep-Merge bei partiellen StatusOnChange-Updates, toter
  30-s-Polling-Timer deaktiviert, WebSocket-Reconnect mit Jitter.
- Konsolidierte Codebase-Map unter `docs/CODEBASE_MAP.md` (Pre-Pivot-Stand).
- Zweisprachiger "Getting an API Token"-Abschnitt in der alten README
  (dokumentierte das Integrator-API-Beschaffungsproblem — nach dem Pivot
  weitgehend obsolet).
- Pivot-Recherche: verifiziert, dass die Shelly Cloud Control API
  geteilte Geräte sieht (mit einer echten ECOWITT WS90 getestet, die aus
  einem Fremd-Account geteilt ist); verifiziert, dass die
  Cloud-Control-API-WebSocket den `auth_key` ablehnt (`Token-Broken`,
  Close 4401) und OAuth braucht; bestätigt, dass HTTP-Polling mit
  `auth_key` den vollständigen Status aller Account-sichtbaren Geräte
  zurückgibt.
- Repo umbenannt zu `shelly-cloud-diy-ha`, Python-Domain zu
  `shelly_cloud_diy`, CLOUD-DIY-Branding in `images/icon.png`.
- Drei historische Release-Tags (`v0.1.0-notDIRK` … `v0.2.2-notDIRK`)
  bleiben auf ihren Integrator-API-Commits als Audit-Trail.

### Meilenstein 1 — Cloud Control API mit `auth_key` + HTTP-Polling  🔄 (als Nächstes)

**Ziel:** Das erste nutzbare HACS-Release für Privatanwender. Kein
Integrator-API-Token mehr, keine Support-Mail an Shelly, kein
Consent-Webhook. User kopiert `auth_key` + Server-URI aus der Shelly-App
rein und alles läuft.

Änderungen:
- Auth-Schicht ersetzen: `api/auth.py` (JWT/Integrator-Token-Austausch)
  löschen, `api/cloud_control.py` hinzufügen (HTTP-Client mit
  `POST /device/all_status`, `POST /device/status`,
  `POST /device/relay/control`, `POST /device/light/control`,
  `POST /device/relay/roller/control`, authentifiziert per
  `auth_key`-Form-Parameter).
- `config_flow.py` neu schreiben — User-Step fragt `auth_key` + `Server-URI`
  ab; kein Consent-Step mehr; Options-Flow entsprechend vereinfacht.
- `coordinator.py` auf Polling von `/device/all_status` umschreiben
  mit konfigurierbarem Intervall (3–60 s, Default 5 s), respektiert das
  dokumentierte 1-req/s-Rate-Limit (konsolidierter Single-Poll schlägt
  Per-Device-Fan-Out).
- Entfernen: Consent-Webhook-Flow (`services/webhook.py`,
  `core/consent.py`, Webhook-ID-Migrations-Logik in `__init__.py`),
  `api/websocket.py` (zurück in M2-Scope).
- Wiederverwenden: Device-State-Merge-Logik, Per-Platform-Entity-Klassen
  (sensor, switch, light, cover, button, binary_sensor),
  Entity-Descriptions, Historical-CSV-Service (Local-Gateway-Pfad bleibt
  unverändert).
- Hinzufügen: Entity-Mapping für BLE/Gateway-überbrückte Sensoren, die
  in `/device/all_status` mit `gen: "GBLE"` auftauchen
  (Shelly-BLU-Familie, Shelly BLU H&T, SBWS-90CM-Wetterstation etc. —
  eine Mapping-Tabelle, gekeyed auf `_dev_info.code`).
- Aktualisieren: Translations und `strings.json` für die neuen
  Config-Felder (`auth_key`, `server_uri` statt `integrator_token`);
  deutsche Übersetzung ergänzen (`translations/de.json`).
- Manifest: Bump auf `0.3.0`, `iot_class` auf `cloud_polling` umstellen
  (weil der Push-Mechanismus entfällt), ungenutzte
  `dependencies: ["webhook"]` entfernen.
- Release: `v0.3.0` getaggt ohne `-notDIRK`-Suffix — Ziel ist langfristig
  der HACS-Default-Store.

Nicht-Ziele in M1:
- Echtzeit / Sub-5-Sekunden-State-Update-Latenz (→ M2).
- OAuth-Authentifizierung (→ M2).
- Cloud-seitige historische Energiedaten (der bestehende
  Local-Gateway-Pfad bleibt; Cloud-Historie ist separater Spät-Scope,
  sofern machbar).

Ausdrücklich dokumentierte Einschränkungen, die User kennen müssen:
- **1 Request pro Sekunde** Rate-Limit pro Shelly-Account (Shelly-Offizial-Doku).
- **Polling-Latenz** von 5 s (Default) bedeutet: Sensor-Werte hinken der
  Realität um bis zu ~5 Sekunden hinterher; Schaltbefehle gehen sofort
  raus, die Latenz betrifft nur die State-*Beobachtung*.
- **HTTP-Endpunkte sind laut Shelly absichtlich nur grob dokumentiert**
  (Shelly behält sich Parameterformat-Änderungen vor) — wir pinnen auf
  die aktuelle v1-Endpunkt-Form und reagieren auf Änderungen reaktiv.

### Meilenstein 2 — OAuth + WebSocket-Realtime  ⏳

**Ziel:** Push-basierte Realtime-Updates für User, die bereit sind, sich
mit Mail + Passwort zu authentifizieren statt (oder zusätzlich zum)
`auth_key`.

Änderungen:
- OAuth-Code-Flow im `config_flow.py` ergänzen:
  `POST https://api.shelly.cloud/oauth/login` mit `email` +
  `sha1(password)` + `client_id=shelly-diy` → `code` empfangen →
  `POST https://<server>/oauth/auth` mit `code` → `access_token` empfangen.
- `api/websocket.py` zurückholen (architekturbekannt aus der
  Vor-Pivot-Integrator-API-Ära — die WSS-URL-Form ist identisch) und
  OAuth-`access_token` als `t=`-URL-Parameter nutzen.
- Coordinator-Polling-Loop durch WebSocket-Event-Subscription ersetzen
  (`Shelly:StatusOnChange`, `Shelly:Online`, `Shelly:CommandResponse`).
- Access-Token-Lifecycle: Ablauf tracken, proaktiv refreshen, Fallback
  auf Re-OAuth wenn Refresh scheitert.
- Options-Flow: Umschalten zwischen Simple (auth_key / Polling) und Full
  (OAuth / Realtime) ohne Neuinstallation.

Nicht-Ziele in M2:
- Per-Device-Webhook-Subscriptions (WebSocket liefert bereits alles).

### Meilenstein 3 — HACS-Default-Store-Aufnahme  💡

**Ziel:** Eintrag in der [HACS-Default-Integration-Liste](https://github.com/hacs/default),
damit User die Integration nicht mehr über Custom-Repository-URL
hinzufügen müssen.

Voraussetzungen:
- Logo-Submission an [home-assistant/brands](https://github.com/home-assistant/brands)
  als `core_integrations/shelly_cloud_diy/{icon.png,logo.png}` —
  bereinigte Varianten ohne `notDIRK`-Wordmark und Fork-Symbol werden zu
  diesem Zeitpunkt generiert.
- Erstes stabiles Release-Tag (ohne `-dev`).
- README finalisiert, besteht das HACS-Style-Review.
- Issue-Tracker mit mindestens ein paar geschlossenen / triagierten
  Issues (um aktive Wartung zu zeigen).
- Optional: simpler GitHub-Actions-CI, der Lint und vorhandene Tests bei
  Push / PR laufen lässt.

### Meilenstein 4 — Quality-Scale-Ausbau  💡

Pfad zu HA-Core-Quality-Scale `silver` / `gold`:
- `async_get_config_entry_diagnostics` für sanitisierten Export.
- `repairs`-Plattform für aktionable Fehlerkennzeichnungen
  (Rate-Limit-Erschöpfung, Token-Ablauf etc.).
- Testabdeckung ≥ 70 %.
- CI: Lint, Type-Check (mypy), Test-Matrix gegen unterstützte HA-Versionen.

(Kein fester Zeitplan — abhängig davon, ob Core-Submission wirklich
Ziel wird.)

## Abgrenzung zu bestehenden Projekten

| Projekt | Auth | Realtime | Shared Devices | Gepflegt | Notizen |
|---|---|---|---|---|---|
| **`notDIRK/shelly-cloud-diy-ha`** (dieses Repo) | `auth_key` (M1) / OAuth (M2) | HTTP-Poll 5 s (M1) / WebSocket-Push (M2) | ✅ | 🔄 aktiv | Volle Gen1- + Gen2- + BLE-Gateway-Abdeckung |
| [`engesin/shelly-integrator-ha`](https://github.com/engesin/shelly-integrator-ha) | Integrator-API-Token (von Shelly reglementiert) | WebSocket-Push | ❌ (Consent-Flow ist pro Besitzer) | ✅ aktiv | Privatanwender bekommen den Token typischerweise nicht |
| [`home-assistant/core` Shelly-Integration](https://www.home-assistant.io/integrations/shelly/) | Lokal per LAN (mDNS / direkte IP) | LAN-Push | ❌ (entfernte / geteilte Geräte übers LAN nicht erreichbar) | ✅ vom HA-Core-Team gepflegt | Mainstream; braucht LAN-Erreichbarkeit |
| [`StyraHem/ShellyForHASS`](https://github.com/StyraHem/ShellyForHASS) | Lokal per LAN | LAN-Push | ❌ | ❌ *"ShellyForHass will no longer receive further development updates"* laut eigener README | In HA Core aufgegangen |
| [`vincenzosuraci/hassio_shelly_cloud`](https://github.com/vincenzosuraci/hassio_shelly_cloud) | Username/Passwort (reverse-engineered Browser-Calls) | HTTP-Polling | ? | ❌ letzter Commit 2019 | Nur Switches; README warnt, dass HTTP-Parsing fragil ist |
| [HA-YAML-Blueprint](https://community.home-assistant.io/t/controlling-shelly-cloud-devices-in-home-assistant/928462) | `auth_key` (wie wir) | ❌ nur Commands | ? | ✅ Community-maintained | *"The device state is not updated from the cloud"* — State ist nicht lesbar |
| [`corenting/poc_shelly_cloud_control_api_ws`](https://github.com/corenting/poc_shelly_cloud_control_api_ws) | OAuth | WebSocket-Push | ? | Explizit als POC markiert, keine Integration | Referenz-Implementierung für unseren M2-OAuth-Flow |

Kurzfassung: Aktuell existiert **keine andere gepflegte HA-Integration,
die Cloud-Control-API-Zugriff MIT State-Read UND Shared-Device-Support
UND Gen1/Gen2/BLE-Abdeckung kombiniert**. Diese Lücke ist real und der
Grund, warum es dieses Projekt überhaupt gibt.

## Rate-Limits, Latenz, ehrliche Erwartungen

**Shellys dokumentiertes Rate-Limit:** 1 API-Request pro Sekunde pro
Account (Quelle: [Shelly Cloud Control API Docs, Getting Started](https://shelly-api-docs.shelly.cloud/cloud-control-api/)).

**Traffic-Profil in Meilenstein 1:**
- Ein einzelner `POST /device/all_status` liefert den kompletten State-
  Snapshot aller Geräte, die dein Account sieht (eigene + geteilte +
  BLE-überbrückte). Bei 58-Geräte-Accounts ca. 60 KB pro Request.
- Default-Poll-Intervall: 5 s → durchschnittlich ca. 12 KB/s
  Outbound-HTTPS. Konfigurierbar bis runter auf 3 s (24 KB/s bei 58
  Geräten) für snappieren State oder hoch bis 60 s für
  Low-Traffic-/Battery-Setups.
- User-initiierte Befehle (Schalter an/aus, Dimmen, Rollladen) werden
  sofort per separatem HTTP-POST abgesetzt, nicht erst beim nächsten
  Poll. Commands und Polls teilen sich das 1-req/s-Budget, das
  Default-5-s-Intervall lässt also ca. 4 req/s Command-Headroom.
- Beobachtete State-Change-Latenz: **p50 ≈ 2,5 s, p99 ≈ 5 s** bei
  Default-Poll. Für Wetterstation / Energie-Metering irrelevant; für
  Licht-Schalter-Feedback fühlt sich das gemütlich an.

**Traffic-Profil in Meilenstein 2 (Zukunft):**
- Outbound-Poll-Traffic: **0 Bytes** Steady State; Events werden von
  Shelly Cloud gepusht, wie sie passieren.
- Latenz: **< 100 ms** für State-Propagation vom Gerät → Shelly Cloud → HA.
- Kosten: Eine persistente WebSocket-Connection pro HA-Instanz; ein
  OAuth-Re-Auth ungefähr alle 24 Stunden.

## Security und Datenhaltung

- Der `auth_key` wird in `entry.data` gespeichert (Home-Assistant-
  Standard-Config-Entry-Storage, Klartext auf Disk unter
  `.storage/core.config_entries`). Der Key gibt weitreichende Kontrolle
  über deine Geräte — behandle ihn wie ein Passwort.
- Er wird in der Shelly-App unter **Benutzereinstellungen →
  Authorization cloud key** angezeigt. Ein Passwort-Wechsel bei Shelly
  invalidiert ihn serverseitig — das ist die vorgesehene
  Rotations-Methode.
- Meilenstein 1 speichert weder Mail noch Passwort.
- Meilenstein 2 (OAuth) sendet `sha1(passwort)` beim initialen Login an
  `api.shelly.cloud/oauth/login`; der resultierende `access_token` wird
  in `entry.data` gespeichert. Das Passwort selbst speichern wir nicht.
