# GreyArtifact – Roadmap

Stand: 16. Oktober 2026 (Fennec-Anbindung fertig, öffentlicher Betrieb seit 15. Okt; Fahrplan für die nächsten Tage in Block 6)

## Ziel

Die nächsten drei bis vier Wochen führen zur **abgenommenen privaten Demo**.

Die offenen Gates stammen aus
[acceptance-audit-2026-10-11.md](../docs/validation/acceptance-audit-2026-10-11.md):

1. MinIO/S3 ist betriebsbereit.
2. Die Browser-Abnahme ist durchgeführt.
3. Ein echter Runner-Lauf hat in einem Test-Lab stattgefunden.
4. Die Interviews sind geführt.

Weil noch keine Demo-Termine bestehen, wird die Fennec-Anbindung vorgezogen. Sie bindet `recon_pipeline` immer zusammen mit `recon_ml` an.

Leitlinien:

- In der Demo-Woche wird keine neue Funktion begonnen.
- Jeder Block endet mit drei Prüfungen:
  - Die Tests auf dem Server sind grün.
  - OpenAPI ist exportiert und der Lint ist grün.
  - Lokal und Server sind abgeglichen.
- `LICENSE.md` ist von Änderungen ausgenommen.

Legende: ✅ erledigt · 🟡 teilweise · ⏳ wartet auf den Entwickler · ⬜ offen

## Erledigt vor diesem Plan

- ✅ **HTTPS für LAN-Zugriff:** Caddy mit lokaler CA, siehe [docker/caddy/](../docker/caddy/).
- ✅ **Flask:** `FLASK_DEBUG=0`, Bindung nur an `127.0.0.1`.
- ✅ **Findings-Kern:** Nuclei-Parser, Findings-API und Findings-Ansicht.
- ✅ **Statuswechsel mit Audit:** Migration 008.
- ✅ **Sensible Rohartefakte:** Der Download erfordert `sensitive.read`. Das gilt auch für unverarbeitete Importe.

## Block 0 – Serverbetrieb

- ✅ **MinIO für den Host-Betrieb:**
  - [compose.host.yaml](../compose.host.yaml) veröffentlicht nur Loopback.
  - Die `S3_*`-Werte stehen in `.env`.
- ✅ **Integrations-Overlay:** Es kollidiert nicht mehr mit dem Host-MinIO.
- ✅ **Integrationstest:** Er deckt Neuinstallation und Upgrade bis Migration 009 ab.
- ✅ **Migrationen 008–010 plus Grants** sind auf dem Server eingespielt.
- ✅ **PostgreSQL 17:** vom LAN per nftables geblockt (5432 dicht), App nutzt localhost.
- ✅ **Firewall:** nftables (statt ufw/firewalld; sysvinit). Nur 22 (LAN), 80, 443 offen; Faraday/Redis/MinIO auf 127.0.0.1 gebunden; boot-persistent via rc.local. SSH key-only. Von außen verifiziert. Reboot-Test bestanden (15. Okt): Firewall und App-Autostart (cron `@reboot`) kommen ohne Eingriff hoch.
- ⏳ **Altlast:** `.env.bak-2026-10-13` löschen.

## Block 1 – Findings abschließen

- ✅ **Analystennotizen:** nur anhängend, 1–4000 Zeichen, Migration 009.
- ✅ **Verlauf:** Statusänderungen und Notizen in chronologischer Reihenfolge.
- ✅ **Detailansicht:** Statusauswahl, Verlauf und Notizfeld.
- ⏳ **Browser-Test:** Kurzer Test der Detailansicht unter `https://192.168.2.4`.

## Block 2 – Härtung für die externe Demo

- ✅ **Token-Widerruf:**
  - Neue Spalte `principals.credentials_version` (Migration 010). Sie steht als Claim im Token.
  - Eine Passwortänderung erhöht den Wert und macht damit alle älteren Tokens ungültig.
  - Die aktuelle Sitzung erhält ein neues Token.
  - Deaktivierte Konten wurden schon vorher abgelehnt.
- ✅ **Login-Rate-Limit:**
  - In-Process-Limit: 5 Fehlversuche pro Benutzername bzw. 20 pro Client-IP in 15 Minuten, danach 429 mit `Retry-After`.
  - Weitergeleitete Client-Adressen werden nur mit `TRUSTED_PROXY_COUNT` übernommen. Auf dem Server ist der Wert 1, weil Caddy davorsitzt.
  - Live über Caddy geprüft: 5 × 401, dann 429 mit `Retry-After`; andere Benutzer sind nicht betroffen.
- ✅ **Sicherheitsheader:**
  - Strikte CSP ohne Inline-Code, dazu `nosniff`, `X-Frame-Options: DENY` und `Referrer-Policy: no-referrer`.
  - Theme- und Swagger-Init sind in statische Dateien ausgelagert. Nur `/api/docs` darf zusätzlich jsDelivr laden.
  - Im Browser geprüft: Login, Registrierung, Theme-Wechsel und Swagger, ohne CSP-Fehler.
  - ✅ HSTS: jetzt in nginx (Block 5).
- ✅ **Backup und Restore:**
  - `webserver/scripts/backup.sh` und `restore.sh`, verschlüsselt per GnuPG, mit SHA-256-Prüfung jedes Objekts.
  - Sicherung außerhalb des Repos; ein Restore über die Live-Datenbank wird abgelehnt.
  - Der Wiederherstellungstest mit Wegwerf-Containern ist bestanden.
  - ✅ Schlüssel: GnuPG-Schlüsselpaar `F4C14362…92E84CC6` (15. Okt). Auf dem Server nur der öffentliche Schlüssel; der private liegt auf bnd-surveillance-station (`~/greyartifact-keys/`, plus Widerrufszertifikat). Probe Server-verschlüsselt → dort entschlüsselt bestanden.
  - ✅ Zeitplan: stündliche Prüfung per crontab (`backup_if_due.sh`, PR #9): gesichert wird, sobald die letzte vollständige Sicherung älter als 24 h ist – auch wenn der Server nachts aus war. Ziel `/srv/data/greyartifact-backups` (eigene SSD), Log `backup.log` dort. sudoers erlaubt nur `pg_dump --format=custom recon` als postgres. Erste Sicherung und ein echter cron-Lauf geprüft (SHA256SUMS OK, Dump entschlüsselbar).
  - ⬜ Aufbewahrung: alte Sicherungen werden nicht gelöscht. ⏳ Frist festlegen (auch für die Datenschutzerklärung), dann Aufräumen bauen. Kopie außer Haus fehlt noch.
- ✅ **CI:** `.github/workflows/test.yml` mit Unittests, Shell-Syntax, OpenAPI-Diff und Lint. Lokal in einer frischen Umgebung simuliert, auf GitHub noch nicht gelaufen (dafür braucht es Commit und Push).
- ⬜ **Optional:** Audit für Profil- und Engagement-Änderungen.

## Block 3 – Demo-Gates abnehmen

- ✅ **Demo-Checkliste** um Nuclei-Import, Statuswechsel, Notizen, Verlauf und gesperrten Download ergänzt, mit Owner- und Viewer-Konto.
- 🟡 **Browser-Abnahme:**
  - ✅ Öffentliche Seiten auf Desktop und 375 px: kein Überlauf, keine Konsolenfehler.
  - ✅ Mobile Navigation: Menü-Button öffnet die Seitenleiste als ausklappbare Leiste, im Browser geprüft.
  - ⏳ Den Ablauf mit Login führt der Entwickler mit zwei Konten durch.
- ⏳ **Test-Lab:** Der Entwickler stellt eine eigene Domain mit dokumentierter Autorisierung bereit.
- ⬜ **Echter Runner-Lauf:** Start, Abbruch, Teilartefakte und Evidence prüfen.
- ✅ **Audit:** [acceptance-audit-2026-10-14.md](../docs/validation/acceptance-audit-2026-10-14.md).
- ⏳ **Interviews:** Der Entwickler führt die ersten drei Probleminterviews.

## Block 4 – Demo-Woche (verschoben)

Es gibt noch keine Termine mit Design-Partnern. Die Demos folgen, sobald
GreyArtifact mit echten Fennec-Daten im eigenen Alltag genutzt wird.

- ⬜ Kontakte parallel aufbauen: Kanäle aus der Zielgruppe ableiten, kurze Gesprächsanfrage (kein Verkauf), [contact-tracker.csv](../docs/validation/contact-tracker.csv) pflegen. Die Nachrichten schreibt und verschickt der Entwickler.
- ⬜ Design-Partner-Demos; in dieser Woche nur Sicherheits-, Installations- und Bedienfehler beheben.

## Block 5 – Öffentlicher Betrieb (seit 15. Okt)

GreyArtifact ist unter `https://greyartifact.dynv6.net` aus dem Internet erreichbar.

- ✅ **DynDNS:** `~/bin/dynv6-update.sh` (außerhalb des Repos), alle 6 h per cron und 90 s nach jedem Start (`@reboot`), `ipv4=auto`/`ipv6=auto` über HTTPS; Token nur in `~/.config/dynv6/token`.
- ✅ **Reverse Proxy:** nginx statt Caddy, Zertifikat von Let's Encrypt per certbot-Webroot (gültig bis 13.01.2027, Verlängerung per certbot-Cron mit nginx-Reload). Fremde Hostnamen und nackte IPs bekommen keine Antwort. HSTS vorerst 1 Tag. Caddy gestoppt (`restart=no`).
- ✅ **Router:** 80/443 für IPv4 und IPv6 freigegeben, SSH bleibt im LAN.
- ✅ **CrowdSec** mit Firewall-Bouncer (vom Entwickler eingerichtet); wertet `/var/log/nginx/access.log` und `error.log` aus. ⏳ Startet beim Booten zu früh und bricht ab (Netz noch nicht da): verzögerter Start per `rc.local` (Zeilen liegen vor).
- ✅ **gunicorn** statt Flask-Entwicklungsserver: 1 Worker × 8 Threads (die Login-Drosselung zählt im Prozess), Timeout 300 s, kein Control-Socket. Start weiterhin über `host_serve.sh` und cron.
- ✅ **Systemstatus-Seite** `/status`, nur für Owner/Admins: App, Datenbank, MinIO, Backup, Zertifikat, DynDNS, Plattenplatz.
- ⏳ **Öffentliche Registrierung:** offen lassen oder für den Internetzugang abschalten.
- ✅ **GitHub-Token:** `.github_key.txt` bleibt (Entscheidung des Entwicklers), ist in `.gitignore`. Empfohlen: Rechte 600, später ein repo-gebundener Token.
- ✅ **Stabilität von mx:** die Ausfälle waren manuelle Abschaltungen/Starts, keine Abstürze. Folge: Nacht-Jobs liefen nicht → DynDNS beim Start und stündliche Backup-Prüfung eingeführt.
- ✅ Reboot-Test mit gunicorn: am 16. Okt 18:57 bestanden (App 51 s nach dem Start oben).
- ✅ **Öffentliche Seiten** (PRs #4–#8): Startseite `/` (Dashboard nach `/dashboard`), Hilfe `/hilfe` mit Ablaufgrafik, Glossar nach Themen, Suche und Sprungmarken; erklärende Texte und Leerzustände in den Projekt-Tabs; einheitliche Begriffe („Arbeitsbereich“, kein „lokal“).
- 🟡 **Impressum und Datenschutz:** Seiten `/impressum`, `/datenschutz` mit Markdown-Unterstützung fertig, Texte liegen außerhalb des Repos (`IMPRINT_FILE`/`PRIVACY_FILE`). ⏳ Platzhalter (Name, Anschrift, Telefon, Aufsichtsbehörde, Backup-Frist) füllen, dann freischalten.
- ✅ **Log-Rotation:** `app.log` wird nach 14 Tagen gelöscht (logrotate im Benutzerkontext, cron 00:15), wie die nginx-Logs.
- ⬜ HSTS auf ein Jahr, sobald der Betrieb stabil ist.

## Block 6 – Fahrplan ab 17. Okt

1. **Betrieb festziehen:** ✅ Backup-Cron umgestellt, ✅ Roadmap nachgezogen; ⏳ CrowdSec-Start per `rc.local`, `.env.bak-2026-10-13` löschen.
2. **Rechtliches komplettieren:** ⏳ Platzhalter und Backup-Frist → Texte freischalten, Backup-Aufräumen bauen; ⏳ Entscheidung öffentliche Registrierung.
3. **Echte Nutzung:** erster echter Import aus `recon_db` (witte-automotive.de, dann siemens.com) in die produktive Instanz; ⏳ Browser-Abnahme mit `admin` und `bortex`; Feedback-Rückweg einmal echt (nur mit ausdrücklichem Go, schreibt in `recon_db`).
4. **Entscheidungen und Gates:** Fennec ins Repo (zwei abweichende Kopien), GitHub-Actions-Abrechnung, Test-Lab und echter Runner-Lauf, Interviews.

## Als Nächstes – Integration von `recon_pipeline` und `recon_ml`

Grundregel: **Kein `recon_pipeline`-Lauf ohne `recon_ml`.** Ein Lauf gilt erst als übernahmefähig, wenn der zugehörige ML-Job fertig ist. Ist der ML-Job fehlgeschlagen oder steht er noch aus, wird nichts übernommen.

### A/B – Fennec-Export (✅ umgesetzt, 15. Okt)

Code: `recon_pipeline/New-project/recon_pipeline/export_greyartifact.py` + CLI
`export` in `cli.py`. (Liegt in der gitignorierten Fennec-Kopie, nicht im
GreyArtifact-Repo.)

- ✅ **Export-Einheit:** pro Engagement, neuester abgeschlossener Inference-Run
  (`ml_inference_run` + `ml_sample.engagement_id`). Kein execution-Bezug, weil
  Vorhersagen engagement-weit sind.
- ✅ **Teil A – Observations statt Rohartefakten:** Fennecs Rohausgaben passen
  (außer subfinder) nicht zu GreyArtifacts Parsern, die reichen Daten liegen in
  Fennecs normalisierten Tabellen. Daher neues Format `greyartifact_observations_v1`
  (GreyArtifact-Parser) + Export aus `http_observation`, `tls_endpoint_observation`,
  `dns_ip_answer` und dem Entity-Inventar: Assets mit Properties (http_status, TLS,
  Titel) und Relationships (resolves_to, hosts).
- ✅ **Teil B – Vorhersagen:** JSONL je Entity (Typ, Wert, Perzentil, Rang,
  Erklärung aus `ml_prediction_feature_contribution`); Modell/Version/Status,
  Pipeline-Release und Inference-Run im Manifest-ML-Block (Pflicht).
- ✅ **Ausschlüsse:** Proxy-/Tor-/Secret-Daten und Loopback-Adressen nie im Paket.
- ✅ **PostgreSQL (`recon_db`, Fennecs echte DB):** Export läuft auch dort (15. Okt). Behoben: bytea-IPs kommen als `memoryview` (Abbruch bei jeder IP); `_link_hosts` scannte alle URLs der DB statt nur die des Engagements (21 s → 0,3 s, Ausgabe identisch). Neuer Test `tests/test_export_greyartifact.py`. End-to-end mit witte-automotive.de: Export (nur lesend) → Wegwerf-GreyArtifact (38 Vorhersagen, Observations, Review, Feedback-Export) → `import-feedback` gegen `recon_db` in zurückgerollter Transaktion. Export braucht den Fennec-venv unter `~/Dokumente/ChatGPT/New project` (Postgres-Treiber).
- ✅ **End-to-end geprüft** gegen echte `recon.sqlite3` (Engagement
  germany-compliance): Paket gebaut → über `/import-batches` importiert → 76
  Vorhersagen, 80 Assets, Properties und Relationships persistiert.
- ✅ **Rückkanal (GreyArtifact-Seite):** Erfassung + JSONL-Export fertig (C5). ✅ Fennec-seitiger Import: `python -m recon_ml.review import-feedback <datei> --analyst <kürzel>` (übernimmt die Notiz, sonst Standardkommentar; überspringt unveränderte Entscheidungen; meldet unauflösbare Zeilen). Getestet, gegen Kopie der echten `recon.sqlite3` geprüft (15. Okt).

### C – GreyArtifact-Seite

1. ✅ **Datenmodell:** Migration 011 mit `import_batches`, `imports.batch_id` und `ml_predictions`; Modelle, Grants und Tests (PG16-Integration und PG17) grün. Manifest-Schema `greyartifact-run-manifest/v1` in `docs/`. Migration 011 + Grants auf dem Server eingespielt.
2. ✅ **Import-Endpunkt** `POST /projects/<id>/import-batches`: prüft Manifest, Pflicht-ML-Block und SHA-256, speichert und verarbeitet jede Datei; Dedupe per `(project, source, external_ref)` → 409. Service `import_batches.py`, Tests grün.
3. ✅ **Parser** `recon_ml_predictions_v1` (Vorhersagen → `ml_predictions`, Asset-Mapping über `domain/ip/url_asset`). ⬜ Waybackurls, dann Naabu/Nmap XML, sobald Daten vorliegen.
4. ✅ **Ansicht „ML-Priorisierung“:** Tab mit Lauf-Auswahl, Rangliste, Detail (Modellstatus „Kandidat – nicht validiert“, Erklärung) und Sprung zur Evidenz. GET-Endpunkte für Batches und Vorhersagen. Im Browser mit Wegwerf-Instanz end-to-end geprüft (Desktop + mobil).
5. ✅ **Feedback-Erfassung:** Migration 012 (`ml_prediction_reviews`, append-only), POST-Review-Endpunkt (vier Stage-7-Klassen), Anzeige der letzten Bewertung pro Vorhersage, JSONL-Export `review-feedback` für Fennecs `submit_review`, UI-Auswahl im Detail. Tests grün.
6. ✅ **Stage-8-Empfehlungen:** werden nur angezeigt. Ausgeführt wird ausschließlich über Engagement und kontrollierten Runner. Claims, offene Kandidaten und Empfehlungen (mit Fennec-Entscheidung) als optionale Paketdatei `claims.jsonl` (`recon_ml_claims_v1`; pro Domain und Claim die höchste Definitionsversion, Belege nur als Richtung + Grund), Migration 013 `ml_claims` (SELECT+INSERT, PG17 geprüft), `GET …/import-batches/<id>/claims` (Zählung je Claim/Zustand, Detail pro Asset), Anzeige im ML-Detail ohne Auslöser. Echt geprüft mit witte-automotive.de und siemens.com (7.690 Claims, beide Empfehlungen). Migration 013 + Grants auf dem Server eingespielt (15. Okt).

### Offene Entscheidungen vor dem Start

- **Repo:** Soll `recon_pipeline` mit `recon_ml` ins GreyArtifact-Repo, inklusive Tests und CI? Bisher ist es per `.gitignore` ausgeschlossen. Einmalskripte wie `test_db*.py`, `patch_*.py` und `fix_zombies*.py` müssten dann aussortiert werden.
- **Starten aus GreyArtifact:** Soll GreyArtifact Fennec-Läufe später selbst starten dürfen? Dann gilt: nur aus einem gültigen Engagement heraus, mit Scope-, Ausschluss- und Abbruchregeln. Oder bleibt es bei Export und Import?
