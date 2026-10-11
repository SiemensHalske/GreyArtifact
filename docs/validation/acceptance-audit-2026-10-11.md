# Private-Demo-Abnahme vom 11. Oktober 2026

Diese Bestandsaufnahme trennt nachgewiesene Funktion von vorhandener, aber noch
nicht abgenommener Implementierung. Sie ist kein Abschluss des Acht-Wochen-Plans.

## Status

- **Bestätigt:** im aktuellen Stand mit einem konkreten Test nachgewiesen
- **Teilweise:** wesentliche Teile sind nachgewiesen, mindestens ein relevanter
  Abnahmeschritt fehlt
- **Offen:** noch nicht durchgeführt oder nicht vorhanden
- **Blockiert:** kann ohne externe Voraussetzung nicht sinnvoll abgenommen werden

## Technische Abnahme

| Kriterium | Status | Nachweis oder Restarbeit |
|---|---|---|
| Standard-Testlauf | Bestätigt | 36 Tests: 33 erfolgreich, 3 ausdrücklich optionale Infrastrukturtests übersprungen |
| PostgreSQL-/MinIO-Integration | Bestätigt | 3 von 3 Tests gegen disposable PostgreSQL und echtes MinIO erfolgreich |
| Frische Installation und Upgrade 004 → 005 | Bestätigt | Beide Pfade im Integrationstest erfolgreich |
| OpenAPI-Export und Redocly-Lint | Bestätigt | Spezifikation valide; 29 produktive API-Routen entsprechen exakt 29 OpenAPI-Operationen |
| Registrierung und Freigabe | Bestätigt | Registrierung, gesperrter Login, Owner-Freigabe, Analyst-Login und Audit-Eintrag im HTTP-End-to-End-Test erfolgreich |
| Projekt und manueller Evidence-Workflow | Bestätigt | Projekt, Upload, explizite Verarbeitung, Asset-Normalisierung, Provenienz und bytegleicher Originaldownload gegen PostgreSQL/MinIO erfolgreich |
| SHA-256-Deduplizierung | Bestätigt | Doppelter Upload nutzt denselben Hash und dasselbe Artefakt |
| Parser | Bestätigt | Subfinder, DNSx und ProjectDiscovery HTTPx mit sanitisierten JSONL-Daten erfolgreich verarbeitet |
| Fehlerhaftes JSONL | Bestätigt | Verarbeitung liefert einen verwertbaren Zeilenfehler; Rohartefakt bleibt abrufbar |
| Berechtigungen und Scope-Grenzen | Bestätigt | Owner-only Recon sowie Unit-Tests und ein Live-Test mit fremdem Scope; unzugängliche Ressourcen liefern `404` |
| Runner-Image und Toolchain | Bestätigt | Image baut; Subfinder v2.16.0, DNSx v1.3.1 und ProjectDiscovery HTTPx v1.12.0 im Container verifiziert |
| Runner-Ablauf und Abbruch | Teilweise | Feste Kette, Artefakte und Abbruch sind mit Fake-Prozessen getestet; der echte Runner blieb bei einer ausschließlich abgebrochenen Queue stabil |
| Echter autorisierter Recon-Lauf | Blockiert | Es wurde absichtlich kein externes Ziel berührt; ein eigenes Test-Lab oder ein aktuell ausdrücklich erlaubtes Ziel fehlt |
| Browserbasierter Demoablauf | Offen | HTTP-End-to-End ist bestätigt, aber Registrierung bis Evidence-Navigation wurde noch nicht vollständig im Browser abgenommen |
| Responsive/visuelle Abnahme | Offen | In dieser Umgebung stand kein steuerbarer Browser zur Verfügung; Desktop- und schmale Viewports müssen noch manuell geprüft werden |
| Normale lokale Compose-Konfiguration | Blockiert | Der lokalen, nicht versionierten `.env` fehlen derzeit die S3/MinIO-Werte; der disposable Abnahmestack war davon getrennt funktionsfähig |

Beim End-to-End-Test wurde ein echter Vertragsfehler gefunden und behoben:
`http_status` wurde trotz numerischem Property-Typ als String ausgegeben. Die
Evidence-API liefert ihn jetzt als Zahl; ein Regressionstest sichert das ab.

## Stand des Acht-Wochen-Plans

| Planbereich | Status | Einordnung |
|---|---|---|
| Woche 1: Interviewgrundlage | Teilweise | Leitfaden, Notizvorlage, Matrix und Kontakt-Tracker existieren; drei geführte Interviews sind nicht belegt |
| Woche 1: API-Vertrag | Bestätigt | Flask-Smorest/Marshmallow, Bearer-Schema, OpenAPI und Swagger UI sind vorhanden und lintbar |
| Woche 2: Registrierung, Projekte, Compose | Teilweise | Produktfunktionen und Compose sind vorhanden; die normale lokale MinIO-Konfiguration ist noch nicht betriebsbereit abgenommen |
| Woche 3: unveränderte Artefakte | Bestätigt | Streaming, Limit, Content Addressing, Deduplizierung sowie autorisierter Upload/Download sind getestet |
| Woche 4: manueller Import | Bestätigt | Drei Parser, Fehlerbehandlung, Normalisierung und Provenienz sind technisch nachgewiesen |
| Woche 5: interne End-to-End-Demo | Teilweise | HTTP-Ablauf ist nachgewiesen; vollständiger Browser- und Bedienablauf fehlt |
| Woche 6: Engagement und Runner | Bestätigt | Modelle, Rechte, PostgreSQL-Queue, separater Runner und festes Profil sind vorhanden und automatisiert getestet |
| Woche 7: kontrollierter Recon | Teilweise | Sicherheitsgrenzen und Fake-Prozesskette sind getestet; ein echter, autorisierter Lauf fehlt |
| Woche 8: private Abnahme | Offen | 3–5 Design-Partner-Demos und deren Auswertung wurden nicht durchgeführt |
| Marktvalidierung gesamt | Offen | 15 qualifizierte Interviews und die festgelegten Problem-/Design-Partner-Schwellen sind nicht erreicht beziehungsweise nicht belegt |

## Nächste Abnahme-Gates

1. Lokale S3/MinIO-Werte sicher in `.env` setzen und den normalen Compose-Start
   auf der Entwicklerumgebung prüfen.
2. Den Ablauf aus `private-demo-checklist.md` einmal vollständig im Browser auf
   Desktop und schmalem Viewport durchspielen und Bedienfehler protokollieren.
3. Ein eigenes Test-Lab bereitstellen oder die aktuellen Bedingungen eines
   geeigneten Ziels dokumentieren; erst danach einen echten Runner-Smoke-Test
   mit Start, Abbruch, Teilartefakten und Evidence-Navigation ausführen.
4. Die ersten drei Probleminterviews durchführen und anonymisiert auswerten.

Erst wenn die ersten drei Gates bestanden sind, ist der technische Slice als
private Demo abgenommen. Der Acht-Wochen-Plan als Ganzes ist erst mit den
Interviews und Design-Partner-Demos abgeschlossen.
