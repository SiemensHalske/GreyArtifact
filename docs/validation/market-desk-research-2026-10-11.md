# GreyArtifact: webbasierte Markt- und Problemrecherche

Stand: 11. Oktober 2026  
Methode: Desk Research ohne Interviews, Umfragen oder Kontaktaufnahme

## Kurzurteil

Die Recherche liefert ausreichend Belege dafür, dass Recon- und
Pentest-Ergebnisse in der Praxis fragmentiert sind und Anwender eigene
Skripte, Ordner, Notizen, Tabellen und Datenbanken als Workaround verwenden.
Es existiert außerdem nachweisbare Zahlungsbereitschaft für angrenzende
Produkte rund um Pentest-Zusammenarbeit, Reporting, Scanner-Normalisierung,
Attack-Surface-Management und kontrollierte Security-Automatisierung.

Sie widerlegt jedoch eine zu breite Positionierung als "Recon-Tools mit
Dashboard": Dieser Markt ist sowohl mit populären Open-Source-Projekten als
auch mit kommerziellen Plattformen stark besetzt. Auch Evidence-Provenienz,
Scope-Governance und reproduzierbare Artefakte sind kein unbesetztes Feld mehr.
[OWASP APTS](https://github.com/OWASP/APTS/blob/main/standard/Introduction.md)
formuliert solche Eigenschaften inzwischen als Governance-Anforderungen für
autonome Pentest-Plattformen; [Pentr](https://pentr.sh/) verkauft bereits
signierte Evidence-Locker.

Das belastbarste verbleibende Marktfenster lautet deshalb:

> Eine selbstgehostete, human-kontrollierte Evidence- und Governance-Schicht
> für bestehende Recon-Werkzeuge kleiner Security-Teams – mit unveränderten
> Rohartefakten, normalisierten Beobachtungen, strikter Autorisierung und
> offenen Exporten in vorhandene Reporting- oder Finding-Systeme.

Das ist eine **plausible Produktthese**, aber noch kein Nachweis, dass kleine
Teams GreyArtifact installieren, wechseln oder bezahlen würden.

## Forschungsfragen und Grenzen

Untersucht wurden:

1. Werden verstreute Recon-Daten und manuelle Workarounds öffentlich als
   Problem beschrieben?
2. Welche direkten und angrenzenden Lösungen existieren bereits?
3. Wofür verlangen vergleichbare Anbieter Geld?
4. Welche Merkmale sind differenzierend und welche bereits Marktstandard?
5. Welche Aussagen des Businessplans werden gestützt, geschwächt oder
   widerlegt?

Die Recherche verwendet 40 Quellen. Bevorzugt wurden offizielle
Produktdokumentationen, Preislisten und Quellcode-Repositories. Reddit-Threads
dienen nur als qualitative Hinweise auf Arbeitsweisen und Probleme. Einzelne
Posts, GitHub-Sterne und Anbieterangaben sind keine repräsentative
Marktstatistik. Das vollständige Register steht in
[`market-source-log.csv`](market-source-log.csv).

Nicht durch Webrecherche beweisbar sind insbesondere:

- tatsächliche Wechsel- und Zahlungsbereitschaft für GreyArtifact;
- Häufigkeit und wirtschaftlicher Schaden des Problems in der Zielgruppe;
- Installations- und Supportaufwand unter realen Kundenbedingungen;
- wiederkehrende Nutzung nach vier oder acht Wochen.

## Nachfragesignale

### 1. Fragmentierte Daten und Eigenbau-Workflows sind real

Mehrere unabhängige öffentliche Diskussionen beschreiben Recon-Daten in
Ordnern, Notizen, Textdateien, Obsidian, Tabellen und eigenen Datenbanken.
Ein Anwender nennt fehlende Normalisierung in einer Datenbank ausdrücklich als
Problem; ein anderer beschreibt seinen Teamprozess als Mischung aus Obsidian,
Tabellen und zufälligen Textdateien. Weitere Threads behandeln verlorenen
Kontext zwischen Sessions und die schwierige Organisation großer
Attack-Surfaces.

- [Fehlende Normalisierung von Recon-Daten](https://www.reddit.com/r/bugbounty/comments/1fc0naw)
- [Pentest-Organisation mit Ordnern, Tabellen und Dateien](https://www.reddit.com/r/Pentesting/comments/1pche24/pentesting_organization/)
- [Organisation einer wachsenden Attack-Surface](https://www.reddit.com/r/bugbounty/comments/1uuxihi/organizing_your_attack_surface_how_do_you_do_it/)
- [Recon-Notizen und Datenbanken](https://www.reddit.com/r/bugbounty/comments/1uhptle/how_do_you_use_obsidian_for_bug_bounty/)
- [Vom Recon-Fund zum strukturierten Bericht](https://www.reddit.com/r/bugbounty/comments/1s41ffx/struggling_to_turn_recon_findings_into_structured/)

Bewertung: **Problemexistenz stark gestützt**, aber die Threads stammen
überwiegend aus Bug-Bounty- und Einzelanwender-Kontexten. Daraus folgt nicht
automatisch ein Budget kleiner Beratungen.

### 2. Open-Source-Nachfrage ist groß

Mehrere freie Projekte haben erhebliche sichtbare Nutzungssignale:

| Projekt | Öffentliches Signal | Relevanz |
|---|---:|---|
| [BBOT](https://github.com/blacklanternsecurity/bbot) | ca. 10.700 GitHub-Sterne | Recon-Engine, Scope-Kontrolle, viele strukturierte Ausgaben |
| [reNgine](https://github.com/yogeshojha/rengine) | ca. 8.800 Sterne | Recon-Dashboard, Korrelation, Historie und Automatisierung |
| [Faraday](https://github.com/infobyte/faraday) | ca. 6.700 Sterne | Multiuser-Normalisierung von Security-Tool-Ergebnissen |
| [Osmedeus](https://github.com/j3ssie/osmedeus) | ca. 6.600 Sterne | deklarative und verteilte Security-Workflows |
| [DefectDojo](https://github.com/DefectDojo/django-DefectDojo) | ca. 5.000 Sterne | Finding-Import, Deduplizierung und Vulnerability Management |
| [SysReptor](https://github.com/Syslifters/sysreptor) | ca. 2.600 Sterne | selbstgehostetes Pentest-Reporting |
| [Ghostwriter](https://github.com/GhostManager/Ghostwriter) | ca. 1.900 Sterne | Projekte, Assets, Evidence und Reporting für Red Teams |
| [Reconmap](https://github.com/reconmap/reconmap) | ca. 940 Sterne | Engagement-Management, Command-Automatisierung und Reporting |

GitHub-Sterne sind ein Aufmerksamkeits-, kein Umsatzsignal. Die Breite der
Projekte beweist trotzdem, dass die Problemklasse dauerhaft Entwickler und
Anwender anzieht.

### 3. Kommerzielle Zahlungsanker existieren

| Anbieter | Öffentlich sichtbarer Einstieg | Verkaufter Schwerpunkt |
|---|---:|---|
| [SysReptor](https://offsec.sysreptor.com/pricing) | 65 USD/Nutzer/Monat | Rollen, Zusammenarbeit, Historie, Backups, Self-hosting |
| [Dradis](https://dradis.com/pricing.html) | 69 EUR/Nutzer/Monat, mindestens 3 Sitze | Self-hosted Reporting und Zusammenarbeit |
| [AttackForge](https://attackforge.app/pricing) | 50 USD solo; 150 USD/Monat für 5 Tester | Pentest-Management, QA und Reporting |
| [DefectDojo Pro](https://defectdojo.com/pricing) | 100 USD/Monat plus 0,15 USD pro Finding | Finding-System, Deduplizierung und Workflows |
| [Pentr](https://pentr.sh/) | 150 EUR/Monat; Team 1.200 EUR/Monat | autonome Tests und signierte Evidence-Locker |
| [ProjectDiscovery](https://projectdiscovery.io/pricing) | ab 200 USD/Nutzer/Monat | automatisierte Security-Workflows und Attack-Surface-Discovery |
| [Detectify](https://detectify.com/pricing) | ab 2.500 EUR Jahresgrundgebühr, Assets zusätzlich | DAST und Attack-Surface-Monitoring |

Diese Preise belegen, dass Organisationen für benachbarte Ergebnisse zahlen.
Sie belegen nicht, dass GreyArtifacts geplanter Preis von 149–249 EUR für
kleine Teams akzeptiert wird. Positiv ist, dass dieser Korridor nicht
offensichtlich außerhalb des Marktes liegt.

## Wettbewerbslandschaft

### Direkte Recon- und Orchestrierungsalternativen

| Produkt | Stärke | Konsequenz für GreyArtifact |
|---|---|---|
| reNgine | Web-Recon, anpassbare Scan-Engines, Korrelation und Datenorganisation | Ein allgemeines Recon-Dashboard wäre keine Differenzierung |
| Reconner | Self-hosted, feste Toolchain, Verlauf, reproduzierbare Evidence und portable Bundles | Direkter Wettbewerber zur bisherigen Kurzpositionierung |
| Reconmap | Projekte, Teams, Command-Automatisierung, Parser und Reporting | Deckt bereits einen großen Teil des Engagement-Lebenszyklus ab |
| BBOT | starke Scope-Regeln, modulare Engine, JSON/CSV/SQL/Neo4j-Ausgaben | GreyArtifact sollte BBOT eher integrieren als dessen Engine nachbauen |
| Osmedeus | deklarative, auditierbare und verteilte Workflows | Freie Workflow-Flexibilität ist etabliert; GreyArtifact kann durch engere Sicherheitsgrenzen abweichen |
| ProjectDiscovery | Tool-Stack, Cloud-Workflows, Logs und Enterprise-Governance | Starker kommerzieller Anbieter mit derselben technischen Ausgangsbasis |
| Pentr | Eigentumsprüfung, isolierte Runs, Hash-Ketten und signierte Evidence | Evidence-first ist ein Markt, aber kein Alleinstellungsmerkmal |

### Angrenzende Daten-, Reporting- und Teamplattformen

| Produktgruppe | Beispiele | Abgrenzung |
|---|---|---|
| Vulnerability-/Finding-Management | DefectDojo, Faraday | breiter, remediation-orientiert, sehr viele Parser |
| Pentest-Reporting | Dradis, SysReptor, PwnDoc-ng | Bericht und Finding-Bibliothek statt Recon-Provenienz |
| Offensive-Security-Management | AttackForge, PlexTrac, Ghostwriter | kompletter Engagement- und Reporting-Lebenszyklus |
| EASM/DAST | Detectify, Intruder | kontinuierliche externe Angriffsfläche und Vulnerability Testing |

GreyArtifact sollte nicht gleichzeitig Reporting-Suite, Vulnerability Manager
und EASM werden. Sinnvoller erscheint eine Export- und Integrationsstrategie:
GreyArtifact erzeugt den nachvollziehbaren Recon-Datensatz; andere Systeme
verwalten Findings, Remediation und den finalen Kundenbericht.

## Sichtbare Schwächen bestehender Lösungen

Die öffentlichen Quellen zeigen drei wiederkehrende Angriffsflächen für ein
neues Produkt:

1. **Parser- und Update-Zuverlässigkeit.** reNgine-Nutzer berichten von leeren
   Reports, nicht erkannten Nuclei-Ergebnissen und manuellen Fork-Fixes.
   ([leerer Report](https://github.com/yogeshojha/rengine/issues/1536),
   [nicht erkannte Ergebnisse](https://github.com/yogeshojha/rengine/issues/1480),
   [inoffizieller Fix-Fork](https://github.com/yogeshojha/rengine/issues/1546))
2. **Betriebs- und Wartungsaufwand.** Selbstgehostete Plattformen brauchen
   Updates, Migrationen, Backups und Diagnose. Dass Anbieter Support,
   Onboarding und verwaltete Updates monetarisieren, ist ein wiederkehrendes
   Muster bei Dradis, SysReptor und DefectDojo.
3. **Vertrauen in sensible Daten.** Anwender diskutieren Cloud-Speicherung von
   Kundendaten kritisch und nennen Self-hosting beziehungsweise lokale
   Verarbeitung als Voraussetzung.
   ([SaaS-Diskussion](https://www.reddit.com/r/Pentesting/comments/1u4lm9k/how_do_you_feel_about_saas_pentest_apps_for/),
   [Post-Assessment-Tools](https://www.reddit.com/r/Pentesting/comments/dg0lje),
   [selbstgehosteter Team-Workspace](https://www.reddit.com/r/Pentesting/comments/1wasc7f/we_built_a_fully_selfhosted_ai_pentesting/))

GreyArtifact kann daraus einen belastbaren Produktgrundsatz ableiten:
**wenige Formate, laut scheitern, Rohdaten behalten, Parser versionieren und
Updates reproduzierbar testen**. Diese Zuverlässigkeit ist wahrscheinlich
wertvoller als eine schnell wachsende Tool-Liste.

## Bewertung der Businessplan-Thesen

Bewertungsskala: 0 = widersprochen, 1 = schwach, 2 = unklar, 3 = plausibel,
4 = gut gestützt, 5 = stark gestützt.

| These | Wert | Urteil |
|---|---:|---|
| Recon-Ergebnisse sind fragmentiert und schwer wiederzufinden | 4/5 | Mehrere unabhängige Workarounds und Produktversprechen stützen das Problem |
| Toolübergreifende Normalisierung ist nützlich | 5/5 | BBOT, Faraday und DefectDojo investieren stark in strukturierte Ausgaben, Parser und Deduplizierung |
| Self-hosting ist für sensible Pentest-Daten relevant | 4/5 | Anbieterpositionierung und Anwenderdiskussionen stützen dies deutlich |
| Kleine Teams zahlen für Teamfunktionen und Betrieb | 3/5 | Preisanker existieren; tatsächliche Conversion der GreyArtifact-Zielgruppe bleibt unbekannt |
| Evidence-Provenienz ist ein eigenständiger Wert | 4/5 | OWASP APTS, Pentr und Reconner stützen den Wert |
| Evidence-Provenienz ist ein Alleinstellungsmerkmal | 1/5 | Mehrere neue Angebote und Standards besetzen das Thema bereits |
| Ein fest begrenzter Runner ist differenzierend | 3/5 | Gegenüber freien Shell-Workflows ja; BBOT, ProjectDiscovery, Pentr und APTS besitzen ebenfalls Guardrails |
| 149–249 EUR/Monat sind marktgerecht | 3/5 | Preis liegt im sichtbaren Korridor, ist aber nicht validiert |
| Open Core ist für diese Kategorie plausibel | 4/5 | DefectDojo, Dradis und SysReptor zeigen funktionierende Community-/Pro-Muster |
| Subfinder → DNSx → HTTPx genügt als kaufbares Produkt | 0/5 | Zahlreiche freie Tools und Plattformen decken dies bereits ab |

Gesamtbewertung:

- **Problem:** belegt
- **Marktaktivität:** belegt
- **Zahlungsfähige Nachbarkategorien:** belegt
- **Aktuelle Differenzierung:** noch zu schwach
- **GreyArtifact-spezifische Zahlungsbereitschaft:** unbekannt

## Empfohlene Positionierung

### Beibehalten

- Self-hosted und exportierbar
- unveränderte, content-addressed Rohartefakte
- Navigation von Beobachtung zu Parser, Import, Run und Original
- explizite Engagement-Autorisierung und feste Zielgrenzen
- versionierte, streng getestete Parser
- getrennte Ausführungsrechte und sicherer Runner
- Import vorhandener Ergebnisse als gleichwertiger Einstieg

### Nicht zum Produktkern machen

- möglichst viele Recon-Werkzeuge
- allgemeiner Workflow-Builder oder freie Shell-Ausführung
- vollständiges Pentest-Reporting
- Remediation- und Ticket-Management
- "alles in einem" als Nutzenversprechen

### Schärferer Satz

> GreyArtifact macht bestehende Recon-Läufe kleiner Security-Teams
> autorisierbar, reproduzierbar und bis zum unveränderten Rohartefakt
> nachweisbar – ohne die verwendeten Tools oder Berichtssysteme zu ersetzen.

Dieser Satz grenzt GreyArtifact besser gegen reNgine und Osmedeus ab und
vermeidet einen direkten Funktionskrieg mit Faraday, DefectDojo, Dradis oder
AttackForge. Gegen Reconner und Pentr muss weiterhin konkret bewiesen werden,
dass human-kontrolliertes, import-first und vollständig selbstgehostetes
Evidence-Management für kleine Teams ausreichend anders ist.

## Webbasierte Entscheidungskriterien

Die weitere Entwicklung sollte pausiert oder neu positioniert werden, falls
eine vertiefte zweite Recherche Folgendes zeigt:

- direkte Wettbewerber bieten dieselbe import-first Provenienz bereits stabil
  und kostenlos;
- relevante Projekte exportieren bereits standardisierte Evidence-Pakete, die
  GreyArtifact ohne zusätzlichen Wert nur erneut speichert;
- kleine Teams bevorzugen nachweislich einfache Ordner-/Obsidian-Workflows und
  bezahlen nur für finale Reports;
- Betrieb und Parserpflege übersteigen den Preis, den kleine Teams tragen.

Ein positives Signal wäre dagegen:

- wiederkehrende Issues zu verlorener Herkunft, kaputten Parsern, fehlender
  Run-Vergleichbarkeit oder unsicherer Scope-Ausführung;
- Nachfrage nach Exporten aus Recon-Tools in Dradis, SysReptor, DefectDojo oder
  kundeneigene Systeme;
- sichtbare Nutzung eines kostenlosen Import-/Evidence-Kerns;
- schriftliche Testanfragen oder wiederholte Installationen, auch ohne
  Gespräche.

## Fazit

GreyArtifact ist nach dieser Recherche **keine offensichtlich marktlose Idee**.
Die zugrunde liegenden Probleme, die Open-Source-Nachfrage und kommerzielle
Budgets sind sichtbar. Die Recherche ist aber ebenso deutlich darin, dass der
ursprüngliche Markt breiter und umkämpfter ist als angenommen.

Die vernünftige Konsequenz ist weder Aufgeben noch blindes Weiterbauen. Der
technische Kern sollte als schmale Evidence- und Governance-Schicht fertig
werden. Danach kann Nachfrage zunächst kontaktarm über eine nachvollziehbare
Demo, GitHub-Nutzung, schriftliches Feedback und Import-/Export-Interesse
gemessen werden. Ein vollständiger Recon-, Reporting- und
Vulnerability-Management-Baukasten wäre durch diese Recherche nicht
gerechtfertigt.
