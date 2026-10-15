# Checkliste für eine private Design-Partner-Demo

## Vor dem Termin

- Aktuelle Programmbedingungen oder eigene Autorisierung prüfen.
- Automatisiertes Subdomain-, DNS- und HTTP-Probing muss ausdrücklich erlaubt
  sein; andernfalls ausschließlich Fixtures oder eigenes Test-Lab verwenden.
- Autorisierungs-URL, Gültigkeitszeitraum, erlaubte Domains, Ausschlüsse und
  feste Limits im Engagement erfassen.
- Sanitisiertes Demo-Projekt und die JSONL-Fixtures für Subfinder, DNSx, HTTPx
  und Nuclei vorbereiten. Die Nuclei-Fixture enthält nur Test-Secrets.
- Zwei Konten bereithalten: einen Owner (mit `sensitive.read`) und einen
  Viewer oder Researcher ohne dieses Recht.
- Zugriff ausschließlich über `https://<server>` mit importiertem Caddy-Root-
  Zertifikat; der Browser darf keine Zertifikatswarnung zeigen.
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
8. Nuclei-Report importieren und verarbeiten. In der Findings-Ansicht nach
   Schweregrad und Status filtern und ein sensibles Finding öffnen: Der
   Treffer ist markiert, extrahierte Werte und Token aus URLs fehlen.
9. Status des Findings ändern (zum Beispiel auf „Bestätigt“), eine
   Analystennotiz hinzufügen und den Verlauf mit Benutzer und Zeit zeigen.
10. Als Viewer bzw. Researcher den Download des Nuclei-Originals versuchen:
    Er wird mit Hinweis auf `sensitive.read` verweigert. Als Owner gelingt er.
11. Ein Viewer sieht den Verlauf, kann aber weder Status noch Notizen ändern.

## Nicht zeigen

- Die Inhalte eines echten sensiblen Rohartefakts, auch nicht als Owner.
- `.env`, Backup-Dateien, das Caddy-CA-Verzeichnis oder Server-Logs.

## Nach dem Termin

- Beobachtete Verständnishürden und Fehler getrennt von Feature-Wünschen
  erfassen.
- Zweite Runde und sanitisiertes Feedback konkret vereinbaren.
- Keine neue Funktion während Woche 8 beginnen; nur Sicherheits-, Installations-
  und Bedienfehler beheben.
