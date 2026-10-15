# Private-Demo-Abnahme vom 14. Oktober 2026

Fortschreibung von [acceptance-audit-2026-10-11.md](acceptance-audit-2026-10-11.md).
Diese Bestandsaufnahme trennt nachgewiesene Funktion von vorhandener, aber noch
nicht abgenommener Implementierung.

## Status

- **Bestätigt:** im aktuellen Stand mit einem konkreten Test nachgewiesen
- **Teilweise:** wesentliche Teile sind nachgewiesen, mindestens ein relevanter
  Abnahmeschritt fehlt
- **Offen:** noch nicht durchgeführt oder nicht vorhanden
- **Blockiert:** kann ohne externe Voraussetzung nicht sinnvoll abgenommen werden

## Technische Abnahme

| Kriterium | Status | Nachweis oder Restarbeit |
|---|---|---|
| Standard-Testlauf | Bestätigt | 53 Tests: 50 erfolgreich, 3 optionale Infrastrukturtests übersprungen; zusätzlich in frischer venv ohne `.env` wie in der CI |
| PostgreSQL-/MinIO-Integration | Bestätigt | 3 von 3 gegen disposable PostgreSQL 16 und MinIO, einschließlich Upgrade 004 → 010 |
| Migrationen auf PostgreSQL 17 | Bestätigt | 001–010 plus Grants fehlerfrei in einem Wegwerf-Container; App-Rolle hat auf Audit- und Notiztabellen nur SELECT/INSERT |
| Server-Datenbank | Bestätigt | Migrationen 008–010 und Grants auf dem Server eingespielt |
| MinIO im Host-Betrieb (Gate 1 vom 11.10.) | Bestätigt | MinIO nur auf Loopback, `S3_*` in `.env`; Speichern und Lesen über die echte App-Konfiguration erfolgreich |
| HTTPS für LAN-Zugriff | Bestätigt | Caddy mit lokaler CA; HTTP → HTTPS, direkter Zugriff auf Port 5000 aus dem LAN nicht möglich |
| Sicherheitsheader | Bestätigt | Strikte CSP ohne Inline-Code live über Caddy geprüft; Login, Registrierung, Theme-Wechsel und Swagger im Browser ohne CSP-Fehler |
| Login-Rate-Limit | Bestätigt | Live über Caddy: 5 × 401, danach 429 mit `Retry-After`; anderer Benutzer nicht betroffen; Client-IP kommt korrekt über `X-Forwarded-For` |
| Token-Widerruf nach Passwortänderung | Bestätigt | API-Test: altes Token 401, neues Token aus der Antwort gültig |
| Findings, Status, Notizen, Verlauf | Teilweise | API-Tests einschließlich Rechte-Negativtests bestätigt; Bedienung im Browser mit Login noch nicht abgenommen |
| Gesperrter Download sensibler Rohartefakte | Teilweise | API-Test: 403 ohne `sensitive.read`, 200 mit; im Browser noch nicht abgenommen |
| Backup und Restore | Bestätigt | Verschlüsselte Sicherung aus Wegwerf-Stack, Restore in frisches PostgreSQL 17 und zweiten Bucket; Zeilen-, Tabellen- und Objektzahlen gleich; manipuliertes Backup abgelehnt |
| Erste echte Sicherung | Offen | Schlüssel (GnuPG oder Passphrase-Datei) und Zeitplan festlegen |
| CI | Teilweise | Workflow lokal in frischer Umgebung simuliert; auf GitHub noch nicht gelaufen |
| Öffentliche Seiten im Browser | Bestätigt | Dashboard, Login, Registrierung und Projekt-Zugangssperre auf Desktop und 375 px ohne horizontalen Überlauf und ohne Konsolenfehler |
| Browserbasierter Demoablauf mit Login | Offen | Ablauf aus `private-demo-checklist.md` mit Owner- und Viewer-Konto durchspielen |
| Echter autorisierter Recon-Lauf | Blockiert | Eigenes Test-Lab bzw. eigene Domain mit dokumentierter Autorisierung fehlt |

## Bei der Abnahme gefundene Bedienfehler

| Fehler | Schwere | Einordnung |
|---|---|---|
| Auf schmalen Viewports (≤ 900 px) wird die Seitennavigation vollständig ausgeblendet, ohne Ersatz. Projekte, Administration und Systemstatus sind nur über Inhalte der Seite erreichbar; das Kontomenü bietet nur Profil und Abmelden. | Mittel | **Behoben:** Menü-Button in der Kopfleiste öffnet die Seitenleiste als ausklappbare Leiste; schließt per Escape, Klick daneben oder Linkauswahl. Im Browser auf 375 px und Desktop geprüft |

Feature-Wünsche werden getrennt davon gesammelt und sind hier bewusst nicht aufgeführt.

## Stand der Abnahme-Gates

1. **MinIO/S3 betriebsbereit:** Bestätigt.
2. **Browser-Abnahme:** Teilweise. Öffentliche Seiten und die mobile Navigation sind abgenommen. Den Ablauf mit Login führt der Entwickler mit zwei Konten durch.
3. **Echter Runner-Lauf im Test-Lab:** Blockiert bis zur Bereitstellung einer eigenen, autorisierten Domain.
4. **Interviews:** Offen.

Der technische Slice ist damit noch nicht als private Demo abgenommen. Gate 2 und 3 stehen aus.
