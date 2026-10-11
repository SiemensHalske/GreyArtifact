# Checkliste für eine private Design-Partner-Demo

## Vor dem Termin

- Aktuelle Programmbedingungen oder eigene Autorisierung prüfen.
- Automatisiertes Subdomain-, DNS- und HTTP-Probing muss ausdrücklich erlaubt
  sein; andernfalls ausschließlich Fixtures oder eigenes Test-Lab verwenden.
- Autorisierungs-URL, Gültigkeitszeitraum, erlaubte Domains, Ausschlüsse und
  feste Limits im Engagement erfassen.
- Sanitisiertes Demo-Projekt und die drei JSONL-Fixtures vorbereiten.
- Keine Provider-Schlüssel, JWTs oder MinIO-Zugangsdaten in Bildschirm,
  Artefakten oder Logs zeigen.

## Geführter Ablauf

1. Registrierung und Owner-Freigabe zeigen.
2. Projekt anlegen und ein unverändertes JSONL-Artefakt hochladen.
3. Den expliziten Import starten und einen absichtlich fehlerhaften Import
   samt erhaltenem Rohartefakt erklären.
4. Assets filtern und eine Beobachtung bis zu Parser, Import, Hash und Original
   zurückverfolgen.
5. Engagement mit Autorisierung, Gültigkeit, Allow- und Exclude-Zielen zeigen.
6. `domain_basic_v1` starten, Schritte beobachten und einen Lauf abbrechen.
7. Gesicherte Teilartefakte und normalisierte Ergebnisse öffnen.

## Nach dem Termin

- Beobachtete Verständnishürden und Fehler getrennt von Feature-Wünschen
  erfassen.
- Zweite Runde und sanitisiertes Feedback konkret vereinbaren.
- Keine neue Funktion während Woche 8 beginnen; nur Sicherheits-, Installations-
  und Bedienfehler beheben.
