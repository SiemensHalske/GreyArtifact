# Datenbankentwurf für Recon-Ergebnisse

## Ziel und Grenzen

Die Anwendung sammelt, importiert, ordnet und durchsucht bereits erzeugte
Recon-Ergebnisse. Sie startet selbst keine Scanner oder sonstigen Recon-Tools.

PostgreSQL ist die zentrale Datenbank. Originalberichte bleiben unverändert als
Dateien erhalten; die Datenbank speichert deren Metadaten und normalisierte,
auswertbare Beobachtungen. Ein späterer Markdown-Export in einen Obsidian-Vault
ist möglich, aber nicht Teil des Datenmodells.

Die Basistabellen liegen im Schema `recon`. Erweiterungen werden ausschließlich
als neue, aufsteigend nummerierte Migrationen ergänzt; angewendete Migrationen
werden nicht nachträglich editiert. Scope und Pipelines kamen mit Migration
`002`, Registrierungsanfragen mit `003` und zusammensetzbare Rollen samt Audit
mit `004` hinzu.

## Modellierungsentscheidungen

- Ein **Scope** ist ein benannter Workspace und die oberste Grenze für
  Projekte, Daten und Pipelines. Hier bedeutet Scope ausdrücklich nicht die
  Menge erlaubter Scan-Ziele.
- **Berechtigungen** werden pro Scope über Principal-Mitgliedschaften und
  Rollen vergeben. Die Anwendung startet keine Recon-Scans.
- Ein **Projekt** gruppiert Daten zu einem Auftrag oder Untersuchungsziel
  innerhalb eines Scopes.
- Ein **Asset** ist eine global wiederverwendbare, typisierte Entität, z. B.
  Domain, IP-Adresse, URL, Zertifikat oder Service-Endpunkt.
- Eine **Beobachtung** ist eine einzelne Aussage aus einem importierten Bericht.
  Beobachtungen werden nicht durch einen aktuellen Wert überschrieben; so
  bleiben Quellen und zeitliche Änderungen nachvollziehbar.
- Beziehungen zwischen Assets werden als eigene Beobachtungen gespeichert.
- Ein **Import** verarbeitet genau ein Originalartefakt für genau ein Projekt.
  Mehrere Dateien werden als mehrere Importe angelegt.
- Die Rohdatei wird bytegetreu gespeichert. JSON-Ausgaben werden nicht als
  Ersatz für das normalisierte Datenmodell verwendet.

## Tabellen

`PK` = Primärschlüssel, `FK` = Fremdschlüssel, `UQ` = UNIQUE.

### `projects`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `project_id` | UUID | PK | Interne Projekt-ID |
| `scope_id` | UUID | FK → `scopes`, NOT NULL | Übergeordneter Workspace |
| `slug` | TEXT | UQ mit `scope_id`, NOT NULL | Stabiler URL-/CLI-tauglicher Bezeichner |
| `name` | TEXT | NOT NULL | Anzeigename |
| `description` | TEXT | NULL | Freitextbeschreibung |
| `created_at` | TIMESTAMPTZ | NOT NULL | Erstellungszeitpunkt |

`slug` ist innerhalb eines Scopes eindeutig; Projektnamen müssen nicht
eindeutig sein.

### `scopes`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `scope_id` | UUID | PK | Interne Scope-ID |
| `name` | TEXT | UQ, NOT NULL | Stabiler, eindeutiger Scope-Name |
| `description` | TEXT | NULL | Beschreibung des Workspace |
| `created_at` | TIMESTAMPTZ | NOT NULL | Erstellungszeitpunkt |

Die Migration legt einen `default`-Scope an und ordnet ihm bereits vorhandene
Projekte zu. Neue Projekte müssen explizit einem Scope angehören.

### `tools`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `tool_id` | UUID | PK | Interne Tool-ID |
| `name` | TEXT | UQ, NOT NULL | Kanonischer Toolname, z. B. `nmap` |
| `vendor` | TEXT | NULL | Herausgeber oder Projekt |

Toolversionen gehören zum Import, da ein Tool über die Zeit in mehreren
Versionen verwendet werden kann. Aliase werden bei Bedarf in einer separaten
`tool_aliases`-Tabelle abgelegt, nicht als kommaseparierter Text.

### Identitäten und Scope-Berechtigungen

`principals` enthält lokale Benutzeridentitäten (`username`, Passwort-Hash,
Aktivstatus und Anzeigename). Klartextpasswörter werden nie gespeichert.
JWT-Identitäten referenzieren `principal_id`.

`roles` und `permissions` sind getrennte Kataloge; `role_permissions` bildet
deren n:m-Zuordnung. `scope_memberships` verknüpft Principals mit Scopes und
Rollen. Ein Principal besitzt pro Scope genau eine Basisrolle und kann dort
zusätzlich `pipeline_operator` erhalten. Die Basisrollen sind `viewer`,
`researcher`, `analyst` und `owner`; Rollen und Berechtigungen sind keine
Benutzerattribute.

Die Rollen bauen fachlich aufeinander auf:

- `viewer`: `scope.read`, `data.read`
- `researcher`: Viewer-Rechte sowie `data.import`, `data.delete`
- `analyst`: Rechercheur-Rechte sowie `project.manage`
- `owner`: Analysten-Rechte sowie `scope.manage`, `membership.manage`,
  `pipeline.manage`
- `pipeline_operator`: optionale Zusatzrolle ausschließlich mit
  `pipeline.execute`

Keine Basisrolle darf ohne diese Zusatzrolle Pipelines ausführen. Auch Owner
müssen als Pipeline Operator ausdrücklich freigeschaltet werden. `data.delete`
gilt scopeweit und ist nicht auf eigene Uploads beschränkt. Der letzte Owner
eines Scopes darf nicht herabgestuft werden.

Die initiale Migration erzeugt keinen Benutzer und vergibt keine Mitgliedschaft.
Ein kontrollierter Bootstrap-Schritt muss den ersten Benutzer anlegen und ihm
die `owner`-Rolle im gewünschten Scope zuweisen.

### `permissions`

Vorgesehene Berechtigungen: `scope.read`, `scope.manage`,
`membership.manage`, `project.manage`, `data.read`, `data.import`,
`data.delete`, `pipeline.execute` und `pipeline.manage`.

Alle Abfragen und Änderungen an Scope-Daten müssen die Scope-Mitgliedschaft
und die erforderliche Berechtigung prüfen. Die globale Deduplizierung von
Assets ist ein internes Speicherdetail: APIs dürfen Assets nur über
projekt- und scopegefilterte Zuordnungen sichtbar machen.

Die erste Implementierung erzwingt diese Autorisierung in der Flask-Service-
Schicht. Die Tabellen allein erzwingen keine PostgreSQL Row-Level Security;
direkte Datenbankzugriffe mit dem App-Login dürfen daher nicht unkontrolliert
an Nutzer oder Plugins weitergereicht werden.

Rollenvergaben werden append-only in `role_assignment_audit` protokolliert.
Jeder Eintrag enthält Scope, betroffenes Mitglied, optional den handelnden
Principal, Ereignistyp, vorherige und neue Rollen sowie den Zeitpunkt. Die
Anwendungsrolle erhält kein `UPDATE` oder `DELETE` auf dieser Tabelle.

### `artifacts`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `artifact_id` | UUID | PK | Interne Artefakt-ID |
| `sha256` | CHAR(64) | UQ, NOT NULL | Prüfsumme des unveränderten Inhalts |
| `storage_key` | TEXT | UQ, NOT NULL | Interner relativer Speicherpfad/Objektschlüssel |
| `byte_size` | BIGINT | NOT NULL, CHECK `>= 0` | Größe des gespeicherten Inhalts |
| `created_at` | TIMESTAMPTZ | NOT NULL | Zeitpunkt der ersten Ablage |

Dateiname und gemeldeter MIME-Typ stehen am Import, nicht am Artefakt: Derselbe
Inhalt kann unter verschiedenen Namen oder mit unterschiedlichen
MIME-Angaben angeliefert werden.

### `imports`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `import_id` | UUID | PK | Importvorgang |
| `project_id` | UUID | FK → `projects`, NOT NULL | Zugehöriges Projekt |
| `artifact_id` | UUID | FK → `artifacts`, NOT NULL | Importierte Originaldatei |
| `tool_id` | UUID | FK → `tools`, NULL | Quelltool; NULL bei unbekannter/manueller Quelle |
| `tool_version` | TEXT | NULL | Version des Quelltools |
| `original_filename` | TEXT | NOT NULL | Angelieferter Dateiname |
| `media_type` | TEXT | NULL | Erkannter oder gemeldeter Medientyp |
| `parser_name` | TEXT | NULL | Verwendeter Importer/Parser |
| `parser_version` | TEXT | NULL | Parser-Version |
| `imported_at` | TIMESTAMPTZ | NOT NULL | Zeitpunkt der Ablage/Verarbeitung |
| `status` | TEXT | NOT NULL | `pending`, `completed` oder `failed` |
| `error_message` | TEXT | NULL | Fehlerdetails, falls fehlgeschlagen |

Ein erneuter Import desselben Artefakts darf einen eigenen Importvorgang
erzeugen, damit Verarbeitungshistorie und Parser-Version nachvollziehbar
bleiben. `status` erhält einen CHECK-Constraint für die erlaubten Werte.

### `asset_types`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `asset_type_id` | SMALLINT | PK | Interne Typ-ID |
| `code` | TEXT | UQ, NOT NULL | Stabiler Code, z. B. `domain`, `ipv4`, `url` |
| `label` | TEXT | NOT NULL | Anzeigename |

Mögliche Startwerte: `domain`, `ipv4`, `ipv6`, `network`, `url`, `email`,
`tls_certificate`, `service_endpoint`, `file_hash`. Die Liste kann erweitert
werden, ohne Tabellen zu ändern.

### `assets`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `asset_id` | UUID | PK | Interne Asset-ID |
| `asset_type_id` | SMALLINT | FK → `asset_types`, NOT NULL | Asset-Typ |
| `canonical_value` | TEXT | NOT NULL | Normalisierte Identität |
| `display_value` | TEXT | NOT NULL | Lesbare Original-/Anzeigenform |
| `created_at` | TIMESTAMPTZ | NOT NULL | Zeitpunkt der ersten Erfassung |

Zusätzliche Eindeutigkeit: `UNIQUE (asset_type_id, canonical_value)`.
Normalisierung muss typabhängig erfolgen (z. B. Domain-Kleinschreibung,
IP-Normalisierung, kanonische URL-Regeln). Der Anzeigenwert bleibt davon
getrennt.

### `project_assets`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `project_id` | UUID | PK, FK → `projects` | Projekt |
| `asset_id` | UUID | PK, FK → `assets` | Zugeordnetes Asset |
| `added_at` | TIMESTAMPTZ | NOT NULL | Zeitpunkt der Projektzuordnung |

Der zusammengesetzte Primärschlüssel verhindert doppelte Zuordnungen. Die
Zuordnung erlaubt auch manuell erfasste Assets, für die noch keine
Importbeobachtung existiert. Beim Import muss jede Beobachtung ein Asset
referenzieren, das dem Projekt des zugehörigen Imports zugeordnet ist. Diese
projektübergreifende Konsistenz ist innerhalb einer Transaktion zu prüfen
(Anwendungsservice oder später ein DB-Trigger); einzelne Fremdschlüssel auf
`imports` und `assets` können sie allein nicht ausdrücken.

### `property_types`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `property_type_id` | SMALLINT | PK | Interne Eigenschafts-ID |
| `code` | TEXT | UQ, NOT NULL | Stabiler Code, z. B. `http.title`, `dns.ttl` |
| `label` | TEXT | NOT NULL | Anzeigename |
| `value_kind` | TEXT | NOT NULL | `text`, `number` oder `boolean` |

`value_kind` ist Metadatum zur Validierung und Darstellung. Im ersten
Datenmodell wird der normalisierte Wert als Text gespeichert, damit
toolübergreifende Unterschiede ohne ein unkontrolliertes JSON-Schema
abbildbar bleiben. Parser validieren Werte anhand des Eigenschaftstyps.
Strukturierte JSON-Objekte werden in einzelne atomare Eigenschaften und
Beziehungen zerlegt; nicht unterstützte Originalstrukturen bleiben im
unveränderten Quellartefakt erhalten.

### `asset_property_observations`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `observation_id` | UUID | PK | Beobachtungs-ID |
| `import_id` | UUID | FK → `imports`, NOT NULL | Herkunftsimport |
| `asset_id` | UUID | FK → `assets`, NOT NULL | Betroffenes Asset |
| `property_type_id` | SMALLINT | FK → `property_types`, NOT NULL | Beobachtete Eigenschaft |
| `value_text` | TEXT | NOT NULL | Normalisierter Wert |
| `observed_at` | TIMESTAMPTZ | NULL | Zeitpunkt laut Quellbericht |
| `confidence` | NUMERIC(5,4) | NULL, CHECK `0..1` | Optionale Quellkonfidenz |
| `evidence_locator` | TEXT | NULL | Position im Bericht, z. B. JSON Pointer |

Diese Tabelle ist ereignis-/beobachtungsorientiert: Ein neuer Bericht fügt neue
Beobachtungen hinzu, statt frühere Werte zu überschreiben.

### `relationship_types`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `relationship_type_id` | SMALLINT | PK | Interne Beziehungstyp-ID |
| `code` | TEXT | UQ, NOT NULL | Stabiler Code, z. B. `resolves_to`, `hosts` |
| `label` | TEXT | NOT NULL | Anzeigename |

### `asset_relationship_observations`

| Spalte | Typ | Regeln | Bedeutung |
|---|---|---|---|
| `observation_id` | UUID | PK | Beobachtungs-ID |
| `import_id` | UUID | FK → `imports`, NOT NULL | Herkunftsimport |
| `source_asset_id` | UUID | FK → `assets`, NOT NULL | Ausgangsasset |
| `relationship_type_id` | SMALLINT | FK → `relationship_types`, NOT NULL | Beziehung |
| `target_asset_id` | UUID | FK → `assets`, NOT NULL | Zielasset |
| `observed_at` | TIMESTAMPTZ | NULL | Zeitpunkt laut Quellbericht |
| `confidence` | NUMERIC(5,4) | NULL, CHECK `0..1` | Optionale Quellkonfidenz |
| `evidence_locator` | TEXT | NULL | Position im Originalbericht |

CHECK: `source_asset_id <> target_asset_id`, außer wenn ein späterer
Beziehungstyp Selbstbeziehungen ausdrücklich benötigt.

### Pipelines (Datenverarbeitung, keine Scanner-Ausführung)

`pipelines` definiert einen benannten Ablauf innerhalb genau eines Scopes.
`pipeline_steps` ordnet ihm geordnete, erlaubte Operationen zu. Die
Operationen liegen in `pipeline_operations` als Allowlist mit einem
erforderlichen Berechtigungscode und einem Zugriffsmodus (`read`, `write`,
`read_write`).

Die ersten erlaubten Operationen sind:

- `artifact.validate`
- `report.parse`
- `observations.normalize`
- `markdown.export`

`pipeline_runs` protokolliert manuell bzw. per API ausgelöste Ausführungen und
den auslösenden Principal. `pipeline_run_steps` bewahrt Status und
Konfigurationssnapshot jedes Schritts auf, selbst wenn die Pipeline-Definition
später geändert wird. Es gibt absichtlich keine generische Shell-, Prozess-
oder Scanner-Operation. Neue Operationen müssen explizit implementiert,
allowgelistet und berechtigt werden.

Beim Start sind sowohl `pipeline.execute` als auch die für jeden Schritt
hinterlegte Operation-Berechtigung zu prüfen. Der `access_mode` dient zur
Autorisierungsentscheidung und ersetzt keine Scope-Mitgliedschaftsprüfung.
Ein Datei-Upload startet niemals automatisch eine Pipeline.

Die JSONB-Felder `pipeline_steps.configuration` und
`pipeline_run_steps.configuration_snapshot` enthalten operation-spezifische
Parameter bzw. einen unveränderlichen Audit-Snapshot. Als opake Einzelwerte
betrachtet, verletzen sie BCNF nicht automatisch; sobald ihre internen
Schlüssel-Wert-Paare als relationale Attribute ausgewertet werden, sind sie
jedoch nicht atomar und damit bewusst außerhalb einer strikt relationalen
1NF/BCNF-Modellierung. Die normalisierte relationale Kernstruktur bleibt
separat davon.

## Beziehungen im Überblick

```text
scopes 1 ─── n projects
   │
   ├── n ─── n principals       über scope_memberships / roles
   └── 1 ─── n pipelines

projects 1 ─── n imports n ─── 1 artifacts
                    │
                    └── 0..1 tools

projects n ─── n assets                 über project_assets

imports 1 ─── n asset_property_observations n ─── 1 assets
                         │
                         └── n ─── 1 property_types

imports 1 ─── n asset_relationship_observations
                         ├── 1 source asset
                         ├── 1 target asset
                         └── 1 relationship_type

pipelines 1 ─── n pipeline_steps n ─── 1 pipeline_operations
pipelines 1 ─── n pipeline_runs 1 ─── n pipeline_run_steps
```

## Normalisierung und BCNF

Die Tabellen sind so geschnitten, dass beschreibende Katalogdaten nicht in
Beobachtungszeilen wiederholt werden. Für jede fachliche Tabelle gilt:

- Projektschlüssel, Asset-Schlüssel, Import-Schlüssel und Katalogschlüssel
  identifizieren jeweils genau einen Datensatz.
- Die alternativen fachlichen Schlüssel (`projects.slug`,
  `tools.name`, Katalog-`code`, Artefakt-`sha256` sowie
  `(asset_type_id, canonical_value)`) werden eindeutig gemacht.
- Eigenschaften von Tools, Projekten, Asset-Typen oder Beziehungstypen liegen
  nicht redundant in Beobachtungstabellen.
- Die Beobachtungstabellen enthalten keine abgeleiteten `project_id`-,
  Toolnamen- oder Typnamen-Kopien; der Projektkontext ergibt sich über
  `observation → import → project`.
- Scope-Zugehörigkeit von Projektdaten wird über `project → scope` bestimmt,
  nicht durch redundante `scope_id`-Kopien in jeder Datentabelle.
- Benutzer-Rollen und Rollen-Berechtigungen sind eigene n:m-Relationen.

Unter den dokumentierten fachlichen Abhängigkeiten hängen
nicht-schlüsselbestimmende Attribute der relationalen Tabellen nur von
Schlüsseln ab; die relationalen Kernrelationen zielen auf BCNF. Eine formale
BCNF-Prüfung setzt die vollständige Menge fachlicher funktionaler
Abhängigkeiten voraus; zusätzliche Regeln könnten weitere Kandidatenschlüssel
ergeben und müssten dann separat geprüft werden. JSONB-Konfigurationen und
unveränderte Rohdateien werden als opake Erweiterungs-/Quellartefakte behandelt,
nicht als normalisierte relationale Fachtabellen.

## Importablauf

1. Datei entgegennehmen und sicher ablegen; SHA-256 berechnen.
2. `artifacts` anhand der Prüfsumme wiederverwenden oder neu anlegen.
3. `imports` für Projekt, Artefakt, Quelltool und Parserlauf anlegen.
4. Erkannte Assets typisieren und über `(asset_type_id, canonical_value)`
   deduplizieren.
5. Projektzuordnungen, Eigenschaftsbeobachtungen und
   Beziehungsbeobachtungen einfügen.
6. Importstatus setzen; Rohdatei und Importmetadaten für spätere Nachprüfung
   behalten.

Ein Import darf keine Recon-Prozesse ausführen. Der Parser verarbeitet nur die
vom Benutzer bereitgestellte Datei.

## Bewusst noch nicht festgelegt

- Aufbewahrungs-/Löschregeln und maximale Uploadgröße
- Umgang mit Geheimnissen oder personenbezogenen Daten in Rohberichten
- Konkrete Parser und unterstützte Dateiformate
- Ob Markdown-Dateien später nur exportiert oder bidirektional synchronisiert
  werden
- Ob feingranulare Objektberechtigungen zusätzlich zu Scope-Rollen nötig sind
- Ob die Scope-Autorisierung zusätzlich per PostgreSQL Row-Level Security
  abgesichert werden soll

Die Tabellen erlauben aktuell globale Asset-Identitäten und projektbezogene
Zuordnungen. APIs müssen deshalb Assets ausschließlich über autorisierte
Projektzuordnungen offenlegen. Falls Scopes eine harte physische
Mandantentrennung benötigen, muss die Eindeutigkeit der Assets stattdessen
scopebezogen sein.
