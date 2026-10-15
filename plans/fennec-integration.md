# Planungsrunde: Integration von `recon_pipeline` und `recon_ml`

Stand: 14. Oktober 2026

## Wiedereinstieg (Stand 14. Okt 2026, Abend)

Erledigt: Schritt 1 (Manifest-Schema) und Schritt 2 (Migration 011, Modelle,
Grants, Tests). Alles auf dem Server, Tests grün (Unit 53, Integration 3/3,
PG17 001-011 + Grants).

**Offen beim Entwickler (`sudo`, in `~/GreyArtifact`):** Migration 011 und
Grants einspielen, sonst fehlen die Tabellen in der echten DB:

```
sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1 -f database/migrations/011_fennec_import_batches.sql
set -o pipefail; PYTHONPATH=webserver/src .venv/bin/python webserver/scripts/grant_app_privileges.py | sudo -u postgres psql -d recon -X -v ON_ERROR_STOP=1
```

**Nächster Schritt:** Baureihenfolge Schritt 3 — Import-Endpunkt
`POST /projects/<id>/import-batches` und Parser `recon_ml_predictions_v1`, mit
Tests.

Arbeitsweise: nur auf dem Server arbeiten; Serverdateien per hochgeladenem
Python-Skript editieren (einfache Anführungszeichen brechen sonst das
ssh-Quoting).

---

## Kontext und Entscheidungen

GreyArtifact kann Rohartefakte, Assets, Findings und Provenienz verwalten.
Fennec (`recon_pipeline` mit `recon_ml`) erzeugt genau diese Daten bereits im
Alltag. Weil noch keine Demo-Termine bestehen, wird die Anbindung vorgezogen,
damit der Entwickler GreyArtifact mit echten Daten nutzt.

Grundregel: **Kein Fennec-Lauf ohne `recon_ml`.** Ein Lauf wird nur als
vollständiges Paket aus Recon-Rohausgaben und ML-Ergebnis übernommen. Fehlt der
ML-Teil oder ist er nicht abgeschlossen, wird das Paket abgelehnt.

Vom Entwickler entschieden:
- **Volle Ausbaustufe:** gleich inklusive ML-Vorhersagen, Datenmodell, Parser
  und der Ansicht „ML-Priorisierung“.
- **Übertragungsweg:** ein Export-Skript in Fennec liest `recon.sqlite3` und die
  `recon_ml`-Tabellen und schreibt pro Lauf ein Paket aus Rohdateien plus
  Manifest. Die beiden Systeme bleiben entkoppelt, die Rohartefakte unverändert.

## Fennec-Datenlage (geprüft am Schema)

- `recon.sqlite3` ist die einzige durable State. Rohausgaben liegen
  content-adressiert in `content_object` (sha256, byte_length, inline_data) und
  `artifact` (run_id, content_id, media_type).
- ML-Vorhersagen: `ml_prediction` (inference_run_id, sample_id,
  `numeric_value` **oder** predicted_class_id, explanation_content_id).
- `ml_sample` mit `sample_kind='entity'` zeigt über `subject_entity_id` auf
  genau eine `entity`; `domain_entity.ascii_name`, `ip_entity`, `url_entity`
  liefern den kanonischen Wert.
- `ml_inference_run` → `ml_model_version` (version, status:
  candidate/validated/approved/retired, pipeline_release_id).
- Erklärung je Vorhersage: `ml_prediction_feature_contribution`
  (feature, contribution_value, rank_number, direction) sowie optional
  `explanation_content_id`.
- Review: `ml_prediction_review.decision` ∈
  {accepted, rejected, needs_review, escalated}.

## Datenmapping Fennec → GreyArtifact

| Fennec | GreyArtifact |
|---|---|
| `content_object` + `artifact` | Rohartefakt im MinIO-Objektspeicher (`artifact_storage`) |
| `domain_entity.ascii_name` | Asset-Typ `domain` |
| `ip_entity` (v4/v6) | Asset-Typ `ipv4` / `ipv6` |
| `url_entity` | Asset-Typ `url` |
| `ml_prediction.numeric_value` | Anomalie-Perzentil der Vorhersage |
| aus `numeric_value` abgeleitete Ordnung | Rang |
| `ml_model_version.version` / `status` | Modellversion und -status an der Vorhersage |
| `ml_prediction_feature_contribution` | Erklärung (Top-Features) |

Kanonische Werte normalisiert GreyArtifact über die vorhandenen
`domain_asset` / `ip_asset` / `url_asset` in `services/parsers.py`; dadurch
greifen Deduplizierung und Verknüpfung mit bestehenden Assets automatisch.

## Teil A — Export-Skript in `recon_pipeline` (Fennec-Seite)

- Neuer CLI-Befehl `export` in `cli.py`, Muster der Befehle `artifact`,
  `provenance`, `report`. Er schreibt pro Lauf ein Verzeichnis aus:
  - unveränderte Rohausgaben aus `content_object`/`artifact`, je Datei mit
    SHA-256,
  - Laufdaten aus `recon_run`: Start, Ende, Status, Toolversionen aus
    `tool_release`,
  - das `recon_ml`-Ergebnis (siehe Teil B),
  - das Manifest `greyartifact-run-manifest/v1`.
- **Abschlussprüfung:** Der Export verlangt einen abgeschlossenen Inference-Run
  zum Lauf (`ml_inference_run.status = 'completed'`). Fehlt er oder ist er nicht
  abgeschlossen, bricht der Export mit klarer Meldung ab. Ein Paket ohne ML-Teil
  entsteht nie.
- **Redaktion und Ausschlüsse:** Fennec redigiert Worker-Ausgaben bereits
  (`pipeline._redact_json_stream`, Secret-Scan). Der Export übernimmt nur die
  committeten Artefakte und schließt Tor-, Proxychains-, Chaffing-Konfiguration,
  `DNSDUMPSTER_API_KEY` und lokale Pfade aus. Im Manifest wird je Artefakt
  vermerkt, ob roh oder redigiert.
- **Engagement-Referenz:** Fennecs `engagement` wird als Feld ins Manifest
  geschrieben; die Zuordnung zu einem GreyArtifact-Projekt erfolgt beim Import.
- **Tests:** Export gegen eine kleine SQLite-Fixture, Manifest-Validierung,
  Ablehnung ohne abgeschlossenen ML-Run.

## Teil B — Export der Vorhersagen aus `recon_ml`

- Export eines Inference-Runs als JSONL. Pro Zeile: Entity-Schlüssel und -Typ
  (aus `ml_sample` + `*_entity`), Perzentil (`numeric_value`), Rang, Erklärung
  (Top-`ml_prediction_feature_contribution`).
- Modellblock fürs Manifest: Modell und Version, Status, Pipeline-Release,
  Dataset- bzw. Feature-Set-Version, Inference-Run-ID.
- Nur Vorhersagen mit `sample_kind='entity'` in der ersten Stufe; Paare und
  Findings folgen später.

## Teil C — GreyArtifact-Seite

1. **Datenmodell** (neue Migration, Fortsetzung der 0xx-Reihe):
   - `import_batches`: Manifest-Snapshot, Toolversionen, ML-Modell und -Status,
     Engagement-Referenz, erstellt_at. `imports.batch_id` als optionaler
     Fremdschlüssel, damit bestehende Einzelimporte unverändert bleiben.
   - `ml_predictions`: batch_id, asset_id, model_version (Text), model_status,
     percentile (numeric), rank (int), explanation_json, evidence_locator,
     is_sensitive (Default false). Vorhersagen werden **nicht** automatisch zu
     Findings. Grants wie bei bestehenden Tabellen über
     `grant_app_privileges.py`.
2. **Import-Endpunkt** `POST /projects/<id>/import-batches` (multipart:
   Manifest + Dateien):
   - prüft das Manifest, den Pflicht-ML-Block und die SHA-256 jeder Datei,
   - speichert jede Datei über `artifact_storage` und verarbeitet sie mit dem
     vorhandenen `process_import()`,
   - erfordert `data.import`; die Ansicht später `data.read`.
3. **Parser** `recon_ml_predictions_v1` in `services/parsers.py`: ordnet die
   JSONL-Vorhersagen den über `domain_asset`/`ip_asset`/`url_asset`
   normalisierten Assets zu und füllt `ml_predictions`. Danach Parser für
   Waybackurls; Naabu und Nmap XML, sobald entsprechende Daten anfallen.
4. **Ansicht „ML-Priorisierung“** im Projektbereich (`project.js`,
   `project.html`): Queue nach Rang, Modellstatus immer sichtbar, Kandidaten als
   „nicht validiert“ markiert, Sprung zu Asset, Evidence und Findings.
5. **Feedback-Rückkanal** (nur anhängend): die Analysten-Entscheidung pro
   Vorhersage wird erfasst und als Datei exportiert, die Fennec in seine
   Label-Zuordnung übernimmt. Die Quality-Gates bleiben in `recon_ml`.
6. **Stage-8-Empfehlungen** werden nur angezeigt. Ausgeführt wird ausschließlich
   über Engagement und den kontrollierten Runner, nie direkt aus einer
   Empfehlung.

## Vor dem Bauen zu klären

- **Review-Klassen (GEKLÄRT, 15. Okt):** Kein Widerspruch, zwei Ebenen.
  `recon_ml/review.py` `DECISIONS` ist maßgeblich: der Analyst wählt eine der
  vier Stage-7-Klassen `expected` (Erwartbar), `data_artifact` (Datenartefakt),
  `review_worthy` (Prüfenswert), `confirmed_finding` (Bestätigter Befund). Die
  Werte `accepted/rejected/needs_review/escalated` in `ml_prediction_review` sind
  nur eine daraus abgeleitete Zusammenfassung, die Fennecs `submit_review` selbst
  erzeugt. `decision.py` (`approved/rejected/revoked`) ist Stage-8-Acquisition.
  **Festlegung:** GreyArtifact erfasst nur die vier Stage-7-Klassen (append-only,
  spätere Entscheidung ersetzt die frühere pro Analyst und Vorhersage) und
  exportiert Klassencode + Entity-Schlüssel + Lauf-Referenz; die Ableitung bleibt
  in Fennec.
- **`is_sensitive` für Vorhersagen:** ob eine Erklärung Secrets enthalten kann
  und ob der bestehende `sensitive.read`-Schutz auch hier greifen soll.
- **Codestand im Repo:** `recon_pipeline/New-project/` enthält viele
  Einmalskripte (`patch_*.py`, `check_recent_skips*.py`, `test_db*.py`). Für eine
  spätere Aufnahme ins Repo müsste ausgewählt werden; das ist kein Teil dieser
  Anbindung.

## Verifikation

- Export-Skript: Unit-Test gegen eine SQLite-Fixture, inkl. Ablehnung ohne
  ML-Run; Manifest gegen ein JSON-Schema prüfen.
- GreyArtifact: neue Migration mit allen Vorgängern und den Grants in einem
  Wegwerf-`postgres:17-alpine` einspielen (Muster wie bei 008–010).
- Import-Endpunkt und Parser: Unit-/API-Tests einschließlich Rechte-Negativtest,
  Manifest mit fehlendem ML-Block wird mit 4xx abgelehnt.
- End-to-End: ein kleines echtes Fennec-Paket exportieren, importieren und in der
  Ansicht prüfen.
- `npm run api:export && npm run api:lint`; UI im eingebauten Browser über
  `https://192.168.2.4`.

## Vorgeschlagene Baureihenfolge

1. ✅ Manifest-Format `greyartifact-run-manifest/v1` als JSON-Schema
   (`docs/greyartifact-run-manifest-v1.schema.json`).
2. ✅ GreyArtifact-Datenmodell: Migration 011 (`import_batches` +
   `imports.batch_id` + `ml_predictions`), Modelle, Grants, Tests.
3. ✅ Import-Endpunkt `POST /projects/<id>/import-batches` + Parser
   `recon_ml_predictions_v1`, mit Tests (Service `import_batches.py`).
4. ✅ Ansicht „ML-Priorisierung“ (Tab, GET-Endpunkte, Browser-geprüft).
5. ✅ Feedback-Rückkanal (GreyArtifact): Migration 012, Review-Endpunkt, JSONL-Export
   `review-feedback`, UI. ✅ Fennec-seitiger Import: `python -m recon_ml.review import-feedback <datei> --analyst <kürzel>` (übernimmt die Notiz, sonst Standardkommentar; überspringt unveränderte Entscheidungen; meldet unauflösbare Zeilen). Getestet, gegen Kopie der echten `recon.sqlite3` geprüft (15. Okt).
6. ✅ Stage-8 nur anzeigen (15. Okt): Claims, offene Kandidaten und Empfehlungen (mit Fennec-Entscheidung) als optionale Paketdatei `claims.jsonl` (`recon_ml_claims_v1`; pro Domain und Claim die höchste Definitionsversion, Belege nur als Richtung + Grund), Migration 013 `ml_claims` (SELECT+INSERT, PG17 geprüft), `GET …/import-batches/<id>/claims` (Zählung je Claim/Zustand, Detail pro Asset), Anzeige im ML-Detail ohne Auslöser. Echt geprüft mit witte-automotive.de und siemens.com (7.690 Claims, beide Empfehlungen). ⏳ Migration 013 + Grants auf dem Server einspielen (`sudo`).
7. ✅ Fennec-Export (Teile A/B): Parser `greyartifact_observations_v1` + Modul `export_greyartifact.py`/CLI `export`, pro Engagement, end-to-end gegen echte Daten geprüft. Rückkanal (Feedback) bleibt Schritt 5.
4. Fennec-Export (Teil A und B) gegen dieses Format.
5. Ansicht „ML-Priorisierung“.
6. Review-Klassen klären, dann Feedback-Rückkanal.
7. Stage-8-Empfehlungen anzeigen.
