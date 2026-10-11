# GreyArtifact – Businessplan

Stand: 10. Oktober 2026

## 1. Zusammenfassung

GreyArtifact wird als selbstgehostete Recon-Orchestrierungs- und
Evidence-Plattform für kleine Security-Teams entwickelt. Die Plattform führt
autorisierte, klar begrenzte Recon-Operationen aus, bewahrt deren Rohdaten
unverändert auf und überführt die Ergebnisse in eine gemeinsame, durchsuchbare
und nachvollziehbare Datenbasis.

Der zentrale Produktablauf ist:

```text
Ziele freigeben
  -> Recon ausführen
  -> Rohdaten unverändert speichern
  -> Ergebnisse normalisieren
  -> durchsuchen und vergleichen
  -> exportieren und weiterverarbeiten
```

GreyArtifact soll weder eine allgemeine Shell-Ausführungsplattform noch ein
Exploitation-Framework werden. Der Mehrwert liegt in der Verbindung von
kontrollierter Recon-Ausführung, reproduzierbaren Abläufen, unveränderten
Beweisdaten, normalisierten Erkenntnissen, Team-Rechten und Auditierbarkeit.

Der Geschäftsaufbau erfolgt zunächst bootstrapped. Als primäre Zielgruppe
gelten kleine Pentest-, OSINT- und Security-Teams mit etwa zwei bis zwanzig
Personen. Das bevorzugte Geschäftsmodell ist eine selbstgehostete
Open-Core-Lösung mit kostenpflichtigen Team- und Betriebsfunktionen.

## 2. Kundenproblem

Recon-Ergebnisse liegen in der Praxis häufig verteilt in Projektordnern,
Archiven, JSON-, XML-, CSV- und Textdateien, Markdown-Notizen sowie
individuellen Skripten. Daraus entstehen wiederkehrende Probleme:

- Ergebnisse verschiedener Werkzeuge lassen sich nur schwer gemeinsam
  durchsuchen und vergleichen.
- Die Herkunft einer Information ist später nicht mehr eindeutig
  nachvollziehbar.
- Rohdaten, normalisierte Erkenntnisse und Berichte entwickeln sich
  unabhängig voneinander weiter.
- Wiederholte Recon-Läufe sind nicht vollständig reproduzierbar.
- Wissen bleibt auf den Rechnern einzelner Mitarbeiter oder geht nach einem
  Projekt verloren.
- Kunden-, Projekt- und Engagement-Daten müssen sicher voneinander getrennt
  werden.
- Nicht jeder Mitarbeiter darf Recon-Läufe starten oder verändern.
- Bestehende Skripte bieten selten Rollen, Freigaben, Audit und eine gemeinsam
  nutzbare Datenbasis.

GreyArtifact soll diese Lücke schließen, ohne den Anwendern ihre vorhandenen
Werkzeuge oder Rohdatenformate zu nehmen.

## 3. Zielgruppe

### Primäre Zielkunden

- kleine und mittlere Pentest-Beratungen
- spezialisierte OSINT- und Security-Research-Teams
- selbstständige Pentester, die ein Team aufbauen
- interne Security-Teams mit hohen Datenschutzanforderungen

Der typische Käufer ist ein technischer Geschäftsführer, Teamleiter oder
Senior Pentester. Typische Nutzer sind Rechercheure, Analysten, Recon-Operatoren
und Scope-Owner.

Solonutzer können über eine kostenlose Community-Ausgabe erreicht werden. Die
größere Zahlungsbereitschaft wird bei Teams erwartet, die Zugriffskontrolle,
reproduzierbare Abläufe, Auditierbarkeit und eine gemeinsame Datenbasis
benötigen.

## 4. Positionierung

GreyArtifact wird nicht als allgemeines Vulnerability-Management-System und
nicht als vollständige Pentest-Reporting-Suite positioniert. Die
Produktkategorie lautet:

> Self-hosted Recon Orchestration and Evidence Management

Der Markt enthält bereits breite Produkte:

- DefectDojo konzentriert sich auf Vulnerability Management, Deduplizierung,
  Priorisierung und Remediation.
- Dradis und PlexTrac konzentrieren sich besonders auf Zusammenarbeit und
  Pentest-Reporting.
- Faraday bietet eine breitere offensive Security-Plattform für Unternehmen,
  MSSPs und AppSec-Teams.

GreyArtifact fokussiert stattdessen kleine Teams, selbstgehosteten Betrieb,
kontrolliertes Recon und die lückenlose Verbindung zwischen Lauf, Rohartefakt
und normalisierter Beobachtung.

Das zentrale Nutzenversprechen lautet:

> Autorisiertes Recon reproduzierbar ausführen und jedes Ergebnis bis zu
> seinem unveränderten Quellartefakt zurückverfolgen.

## 5. Differenzierungsmerkmale

- **Self-hosted:** Sensible Ziel- und Kundendaten verbleiben in der
  Infrastruktur des Anwenders.
- **Recon und Datenhaltung aus einem Ablauf:** Ergebnisse müssen nicht manuell
  zwischen Scanner, Dateisystem und Auswertung übertragen werden.
- **Evidence-first:** Originaldateien werden bytegetreu aufbewahrt.
- **Provenienz:** Beobachtungen referenzieren den erzeugenden Lauf, Import und
  das ursprüngliche Artefakt.
- **Toolübergreifendes Datenmodell:** Ergebnisse unterschiedlicher Werkzeuge
  werden als Assets, Eigenschaften und Beziehungen normalisiert.
- **Historische Nachvollziehbarkeit:** Neue Beobachtungen überschreiben alte
  Erkenntnisse nicht.
- **Least Privilege:** Datenrechte, Administration und Ausführungsrechte sind
  voneinander getrennt.
- **Begrenzte Ausführung:** Nur implementierte und freigegebene Operationen
  dürfen gestartet werden; es gibt keine beliebige Shell-Eingabe.
- **Exportierbarkeit:** Anwender behalten ihre Daten und können sie in offenen
  Formaten weiterverwenden.

Rollen und Audit sind wichtige Voraussetzungen für den professionellen
Einsatz, aber kein alleiniger Wettbewerbsvorteil. Der eigentliche Produktwert
entsteht durch den vollständigen Ablauf von der Recon-Ausführung bis zur
nachvollziehbaren Auswertung.

## 6. MVP-Umfang

### 6.1 Engagements und erlaubte Ziele

Der bestehende Begriff `Scope` bezeichnet einen Workspace und ausdrücklich
nicht die Menge erlaubter Scan-Ziele. Aktives Recon benötigt deshalb ein
separates fachliches Modell für Engagements und freigegebene Ziele.

Ein Engagement enthält mindestens:

- erlaubte Domains und Subdomains
- erlaubte IP-Adressen und CIDR-Netze
- optional explizit erlaubte URLs
- Ausschlüsse innerhalb der Zielmenge
- Gültigkeitszeitraum
- verantwortlichen Owner
- dokumentierten Autorisierungsbezug

Recon-Operationen müssen vor der Ausführung gegen diese Zielgrenzen geprüft
werden. Ziele außerhalb der Freigabe werden standardmäßig abgelehnt.

### 6.2 Begrenzter Recon-Katalog

Das MVP unterstützt einen kleinen, zusammenhängenden Satz fest integrierter
Operationen:

- passive Domain- und Subdomain-Ermittlung
- DNS-Auflösung und Erfassung von DNS-Metadaten
- Port-Erkennung innerhalb freigegebener IP-Ziele
- HTTP- und HTTPS-Erreichbarkeit samt grundlegender Metadaten
- TLS-Zertifikatsinformationen
- Import bereits vorhandener Recon-Ergebnisse

Die konkreten Werkzeuge und ersten Importformate werden durch Gespräche mit
Design-Partnern festgelegt. Entscheidend ist ein vollständiger Arbeitsablauf,
nicht eine möglichst große Werkzeugliste.

Nicht Bestandteil des MVP sind:

- Exploitation und Post-Exploitation
- Credential-Angriffe und Brute Force
- beliebige benutzerdefinierte Shell-Kommandos
- frei hochladbare oder nicht geprüfte Ausführungskomponenten
- vollständiges Vulnerability- und Remediation-Management
- eine umfassende Pentest-Reporting-Suite

### 6.3 Ausführungsarchitektur

Recon-Werkzeuge laufen nicht im Webserver. Die vorgesehene Trennung ist:

```text
Weboberfläche / API
        |
        v
Auftrag, Ziel- und Berechtigungsprüfung
        |
        v
Job-Queue
        |
        v
isolierter Recon-Runner
        |
        v
Rohartefakte und Laufprotokoll
        |
        v
Parser, Normalisierung und Suche
```

Der Recon-Runner benötigt mindestens:

- eine feste Allowlist unterstützter Operationen
- strukturierte und validierte Parameter statt Shell-Befehlszeilen
- Zeit-, Speicher-, Parallelitäts- und Ausgabegrenzen
- eine verlässliche Abbruchmöglichkeit
- unveränderliche Konfigurations-Snapshots pro Lauf
- vollständiges Audit von Auftrag, Akteur, Ziel, Parametern und Ergebnis
- isolierte Prozesse oder Container
- eine begrenzte und dokumentierte Netzwerksicht

Für das MVP kann der Runner zusammen mit GreyArtifact über eine lokale
Deployment-Konfiguration betrieben werden. Die technische Trennung vom
Webserver bleibt dennoch erhalten.

### 6.4 Datenverarbeitung und Auswertung

Ein verkaufbares MVP umfasst zusätzlich:

- Projekte und Scopes
- sichere Speicherung der erzeugten und hochgeladenen Rohartefakte
- Parser für die ausgewählten Recon-Operationen
- normalisierte Assets, Eigenschaften und Beziehungen
- Suche und grundlegende Filter
- Navigation von einer Beobachtung bis zur Quelldatei
- Vergleich wiederholter Läufe
- manuelle, erlaubnisgeprüfte Datenverarbeitungspipelines
- Export in offene Formate
- Mehrbenutzerbetrieb mit Rollen und Audit

Ein Datei-Upload darf nicht automatisch Recon starten. Datenverarbeitung und
aktives Recon bleiben unterscheidbare Vorgänge.

### 6.5 Rollen und Ausführungsrechte

Die vorhandenen Basisrollen bleiben:

| Rolle | Zweck |
|---|---|
| `viewer` | Ergebnisse und Daten lesen |
| `researcher` | Daten lesen, importieren und löschen |
| `analyst` | zusätzlich Projekte verwalten |
| `owner` | zusätzlich Scope, Mitglieder und Pipelines verwalten |

`pipeline_operator` ist derzeit die optionale Zusatzrolle für
`pipeline.execute`. Vor der Implementierung aktiven Recons ist zu entscheiden,
ob sie vorübergehend auch Recon-Ausführung erlaubt oder ob von Beginn an ein
eigenes Recht wie `recon.execute` und gegebenenfalls eine Zusatzrolle
`recon_operator` eingeführt werden.

Die fachlich sauberere Zielrichtung ist die Trennung von Datenverarbeitung und
aktivem Recon: Ein Export oder Parserlauf besitzt eine andere Risikoklasse als
ein Portscan. Unabhängig von der Rollenbezeichnung benötigt jeder Recon-Lauf
sowohl das Ausführungsrecht als auch die notwendigen Daten- und Zielrechte.

## 7. Beispiel für den ersten vollständigen Arbeitsablauf

Ein Benutzer legt ein Engagement an und trägt eine autorisierte Domain ein.
Ein Owner oder Operator startet ein vordefiniertes Recon-Profil. GreyArtifact
ermittelt Subdomains, löst sie auf, prüft erreichbare Webdienste und erfasst
TLS-Metadaten. Jeder Schritt erzeugt unveränderte Rohartefakte und
normalisierte Beobachtungen.

Anschließend kann das Team:

- alle gefundenen Assets durchsuchen
- Ergebnisse nach Quelle und Zeitpunkt filtern
- die Herkunft einzelner Beobachtungen öffnen
- Veränderungen zwischen zwei Läufen erkennen
- Daten für die weitere Analyse exportieren

Dieser End-to-End-Ablauf ist wichtiger als eine große Anzahl nur teilweise
integrierter Recon-Werkzeuge.

## 8. Geschäftsmodell

Das bevorzugte Modell ist eine selbstgehostete Open-Core-Lösung. Die genauen
Grenzen zwischen Community- und kommerzieller Ausgabe sind vor einer
Veröffentlichung gemeinsam mit der Softwarelizenz festzulegen.

| Paket | Inhalt | Preis-Hypothese |
|---|---|---:|
| Community | lokaler Runner, manuelle Recon-Läufe, Kernimporte und Suche | kostenlos |
| Team | mehrere Nutzer, RBAC, Audit, Zeitplanung und parallele Läufe | 149–249 EUR/Monat |
| Business | mehrere Runner, SSO, zentrale Policies, Support und Aufbewahrungsregeln | ab 499 EUR/Monat |
| Enterprise | verteilte Runner, SLA und individuelle Integrationen | individuelles Angebot |

Preise sind zunächst Hypothesen. Sie werden nicht durch unverbindliches
Interesse, sondern durch bezahlte Piloten validiert.

Ein mögliches Pilotangebot:

- sechs bis acht Wochen Laufzeit
- Einrichtung und Begleitung eines realen Workflows
- Integration eines priorisierten Eingabeformats oder Recon-Werkzeugs
- einmalig 500 bis 1.500 EUR
- anschließend 99 bis 249 EUR monatlich

Runner-Anzahl, Parallelität, Zeitplanung, zentrale Policies und professioneller
Support eignen sich besser zur kommerziellen Differenzierung als künstliche
Beschränkungen grundlegender Datensuche.

## 9. Markteintritt

Der Markteintritt erfolgt zunächst über direkten, persönlichen Vertrieb:

1. 15 bis 20 Gespräche mit kleinen Pentest-, OSINT- und Security-Teams führen.
2. Aktuelle Recon-, Ablage- und Auswertungsprozesse beobachten.
3. Die meistgenutzten Werkzeuge und Formate bestimmen.
4. Drei bis fünf Design-Partner gewinnen.
5. Für jeden Partner einen realen End-to-End-Workflow abbilden.
6. Mindestens drei bezahlte Pilotkunden erreichen.
7. Erst danach öffentliche Pakete und endgültige Preise festlegen.

Geeignete erste Kanäle sind persönliche Kontakte, gezielte Ansprache kleiner
Beratungen, Security-Meetups, technische Demonstrationen, nachvollziehbare
Beispieldatensätze und eine mögliche Community-Ausgabe.

Der Vertrieb kommuniziert konkrete Arbeitsergebnisse, beispielsweise:

> Einen autorisierten Recon-Lauf starten und anschließend jedes gefundene
> Asset samt Quelle und Laufhistorie durchsuchen.

## 10. Zwölfmonatsplan

### Monat 1 bis 2: Problem- und Workflow-Validierung

- 15 qualifizierte Kundeninterviews
- drei wiederkehrende Kernprobleme bestätigen
- ersten zusammenhängenden Recon-Workflow bestimmen
- relevante Werkzeuge und Ausgabeformate auswählen
- drei bis fünf Design-Partner gewinnen

### Monat 3 bis 5: Technischer End-to-End-Kern

- Engagement- und Zielmodell
- isolierter Recon-Runner
- erster vollständiger Domain- oder Netzwerk-Workflow
- automatische Speicherung der Rohartefakte
- Parser, Normalisierung und Suche
- nachvollziehbare Laufhistorie

### Monat 6 bis 8: Bezahlte Pilotphase

- mindestens drei bezahlte Piloten
- Rollen, Audit, Zielgrenzen und Abbruch im Praxiseinsatz
- Installation und Onboarding dokumentieren
- wiederkehrende Nutzung mit echten Projekten messen
- Sicherheitsgrenzen und Runner-Isolation prüfen

### Monat 9 bis 12: Erste Produktversion

- reproduzierbare und signierte Releases
- klar definierte Community- und Team-Ausgabe
- Update-, Backup- und Supportprozess
- zehn zahlende Teams als Orientierungsziel
- Entscheidung über weiteres Bootstrapping oder Vollzeitausbau

## 11. Erfolgsmessung

Relevante Produkt- und Geschäftssignale sind:

- Zeit von der Installation bis zum ersten erfolgreichen Recon-Lauf
- Zeit vom Lauf bis zum ersten durchsuchbaren Ergebnis
- wöchentlich aktive Teams
- Recon-Läufe und importierte Artefakte pro Projekt
- wiederkehrende Nutzung nach vier und acht Wochen
- Anteil bezahlender Design-Partner
- Zeitersparnis beim Wiederfinden und Prüfen einer Beobachtung
- abgelehnte Läufe aufgrund unzulässiger Ziele oder fehlender Rechte
- Installations- und Supportaufwand pro Kunde
- Kündigungsgründe

Ein erstes belastbares Validierungssignal sind mindestens drei von fünf
Design-Partnern, die das Produkt mit realen Projekten wiederholt nutzen und
nach dem Pilot weiter bezahlen.

## 12. Risiken und Gegenmaßnahmen

### Unklarer Nutzen gegenüber Skripten

GreyArtifact darf nicht nur vorhandene Befehle hinter Buttons verstecken. Der
Mehrwert muss aus Reproduzierbarkeit, Provenienz, Normalisierung, Vergleich,
Team-Rechten und Audit entstehen.

### Sicherheits- und Haftungsrisiken

Aktives Recon darf nur innerhalb dokumentierter Zielgrenzen stattfinden.
Allowlist, Eingabevalidierung, Limits, Isolation, Audit und Abbruch sind Teil
des MVP und keine nachträglichen Enterprise-Funktionen.

### Zu großer Werkzeugumfang

Jedes weitere Werkzeug verursacht Integrations-, Parser- und Wartungsaufwand.
Neue Werkzeuge werden anhand realer Kundenworkflows priorisiert.

### Installation und Betrieb

Self-hosting kann hohen Supportaufwand verursachen. Installation, Updates,
Runner-Diagnose und Backups müssen deshalb früh mit Design-Partnern getestet
werden.

### Unkontrollierte Produktausweitung

GreyArtifact darf im MVP nicht gleichzeitig vollständiges Recon-Framework,
Exploitation-Plattform, Reporting-Suite, Ticket-System und Vulnerability
Manager werden. Der Fokus bleibt:

```text
autorisieren -> ausführen -> beweissicher speichern -> normalisieren
              -> durchsuchen -> vergleichen -> exportieren
```

### Open-Core-Vertrauen

Vor einer Veröffentlichung müssen Lizenz und Produktgrenzen verständlich und
stabil sein. Sicherheitsgrundlagen und Datenportabilität dürfen nicht von
einem kostenpflichtigen Paket abhängig gemacht werden.

## 13. Offene Produktentscheidungen

Vor Beginn der Recon-Implementierung sind insbesondere folgende Punkte zu
entscheiden:

1. Beginnt der erste Workflow ausschließlich mit Domain- und Web-Recon oder
   umfasst er bereits IP-Netze und Port-Erkennung?
2. Erhält aktives Recon ein eigenes Recht `recon.execute` und eine eigene
   Zusatzrolle?
3. Welche konkreten Werkzeuge und Ausgabeformate werden anhand der
   Design-Partner priorisiert?
4. Wie werden Autorisierungsnachweis und Gültigkeitszeitraum eines Engagements
   abgebildet?
5. Welche Isolation und Netzwerkrichtlinien gelten für den ersten Runner?
6. Welche Softwarelizenz und welche Open-Core-Grenze werden verwendet?

## 14. Marktbeispiele

- DefectDojo: <https://defectdojo.com/>
- DefectDojo Pricing: <https://defectdojo.com/pricing>
- Dradis Pricing: <https://www.dradis.org/pricing.html>
- PlexTrac Pentest Reporting: <https://plextrac.com/solutions/pentest-reporting/>
- Faraday: <https://faradaysec.com/pricing/>

Diese Produkte dienen als Markt- und Positionierungsvergleich. GreyArtifact
soll sie im MVP nicht in ihrem vollständigen Funktionsumfang nachbilden.
