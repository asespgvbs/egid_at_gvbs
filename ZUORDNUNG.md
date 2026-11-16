# Lokales GVBSID-EGID-Zuordnungswerkzeug

## Start

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe zuordnung_app.py
```

Das Programm öffnet `http://127.0.0.1:8765` im Standardbrowser. Das Terminal muss
geöffnet bleiben; Strg+C beendet den Server. Mit `--no-browser` wird kein Browser
geöffnet, mit `--port 8766` lässt sich ein anderer lokaler Port wählen.

Auf Wunsch werden ausschliesslich vorhandene Abhängigkeiten verwendet: Python-
Standardbibliothek, SQLite und das bereits vorhandene openpyxl. Der Webteil
verwendet daher den Standardbibliotheksserver statt Flask. Es sind weder ein
Download noch eine neue Installation für den lokalen Anwendungsteil nötig.
Leaflet 1.9.4 und sein Stylesheet werden erst vom Browser über unpkg.com geladen;
die GeoBS-Grundkarte lädt öffentliche Kacheln. Für die Karte ist Internet nötig.
Die Zuordnung und der Excel-Export benötigen keine Geodatenverbindung.

Die bestehenden Programme `gvbsid_matching.py` und `egid_abdeckung.py` bleiben
unverändert und unabhängig vom Zuordnungswerkzeug.

## Datenbank und Schritt 2

1. **Datenbank auswählen** öffnet den nativen Windows-Dialog. Alternativ legt
   **Neue erstellen** eine neue Datei an. Speicherorte ausserhalb des Repositories
   sind zur Laufzeit ausdrücklich möglich. Vorhandene Dateien werden bei der
   Neuerstellung auch nach einer Dialogbestätigung nicht überschrieben.
2. **Excel laden** erwartet das Blatt `review_address_suffix`. Originalspalten
   und Zellwerte werden in SQLite gespeichert. Pro GVBSID ist eine eindeutige
   Importzeile erforderlich. Alternativ aktiviert **Gespeicherte Daten
   aktivieren** die bereits importierten Fälle ohne erneutes Excel-Lesen.

Bis Schritt 1 abgeschlossen ist, sind nur die Datenbankaktionen aktiv. Auch nach
einem Neustart muss Schritt 2 bewusst bestätigt werden. Funktionen bleiben bis
dahin sichtbar, aber deaktiviert. Ein abgebrochener Dialog verändert nichts.

Sobald eine Datenbank ausgewählt und Schritt 2 abgeschlossen ist, klappt der
gesamte obere Bereich automatisch an den Fensterrand. Die Zuordnung und Karte
nutzen dadurch den frei gewordenen Platz. Mit der Maus am oberen Fensterrand
öffnet sich die Bedienleiste; nach dem Verlassen klappt sie nach einer Sekunde
wieder zu. Der schmale Griff am oberen Rand lässt sich auch anklicken oder per
Tastatur bedienen. Bei einem Datenbankwechsel bleibt die Einrichtung bis zur
erneuten Aktivierung sichtbar.

Der zuletzt verwendete Datenbankpfad wird unter
`%LOCALAPPDATA%\egid_match\zuordnung.json` gespeichert. Ist
LOCALAPPDATA nicht verfügbar, liegt der Ordner `egid_match` im Benutzerverzeichnis.
Die Anwendung öffnet diese Einstellungen erst beim Start, nicht beim Import
ihres Python-Moduls. Ist die letzte Datenbank nicht erreichbar, ist eine erneute
Auswahl erforderlich; eine fehlende Datenbank wird nicht automatisch neu angelegt.
Eine fremde, nicht leere SQLite-Datenbank wird zurückgewiesen und nicht erweitert.

Ein erneuter Import aktualisiert die Importinformationen, erzeugt keine doppelten
GVBSID und erhält Status, Kommentar und manuelle Beziehungen. Nicht in einem
erneuten Import enthaltene Fälle bleiben gespeichert. Die Datenbank ist damit
ein dauerhafter Bearbeitungsbestand; für eine andere, unabhängige Zuteilung sollte
eine separate neue Datenbank angelegt werden.

## Bearbeiten

Die Liste links enthält offene, unklare und zurückgestellte Fälle. GVBSIDs mit
gemeinsamer importierter oder verlässlich ermittelter EGRID werden gemeinsam
angezeigt. Fehlt eine verlässliche Parzellenbeziehung, wird keine Gruppierung
erfunden. Zweckbestimmung steht jeweils direkt hinter der GVBSID.

Jede Matrix-Checkbox stellt eine Beziehung dar. Eine GVBSID darf mehrere EGID
erhalten; dieselbe EGID darf mehreren GVBSIDs zugeordnet werden. Status und
Kommentar werden je GVBSID geführt. Angezeigte ursprüngliche Kandidaten werden
niemals allein durch das Öffnen oder einen Kartenklick bestätigt.

**Entscheidung speichern** schreibt die geänderten GVBSIDs gemeinsam in einer
SQLite-Transaktion. Bei einem Versionskonflikt, zum Beispiel durch eine zweite
Browser-Registerkarte, wird der gesamte Speichervorgang zurückgerollt. Neu laden
und die Entscheidung auf Basis des aktuellen Stands erneut treffen.

- **Abgeschlossen** benötigt mindestens eine zugeteilte EGID.
- **Keine Zuordnung möglich** benötigt eine leere Zuordnung.
- Beide Status verschwinden aus der normalen Warteschlange.
- **Offen**, **Unklar** und **Zurückgestellt** bleiben in der Warteschlange.

Über **GVBSID eingeben → Bearbeiten** ist jeder gespeicherte Fall erreichbar,
auch ein abgeschlossener. Ein geänderter offener Status nimmt ihn wieder in die
Warteschlange auf. Nicht gespeicherte Änderungen werden beim Wechsel nicht
stillschweigend verworfen. Der Fortschritt zählt GVBSIDs, nicht Parzellen.

## Karte und amtliche Geodaten

Die WMTS-Grundkarten bleiben reine Bildquellen. Parzellenpolygone kommen aus
amtlichen GeoBS-Vektordiensten. EGID-Punkte kommen unabhängig davon aus
der öffentlichen GWR-Publikation 100230. Profile stehen fest in `zuordnung_quellen.py`; der
bisherige GeoBS-Dienste-Button und sein Dialog entfallen.

Nach Schritt 2 lädt die Karte Gebäudepunkte automatisch über die öffentliche
GWR-Quelle. Ein lokaler GWR-Dateiimport wird nicht angeboten. Alte gespeicherte
GWR-Snapshots werden nicht mehr genutzt und nicht automatisch gelöscht;
manuelle Entscheidungen und Excel-Originalwerte bleiben erhalten.

Die GWR-Adressen für die EGID-Tooltips liest die Anwendung direkt über die
bestehende `entrance.EGID`-Beziehung aus der GWR-Datenbank des Matchings.
Strassenname, Hausnummer mit Zusatz und Postleitzahl werden unverändert
übernommen und als `GWR:` angezeigt. Die Quelle wird ausschliesslich
schreibgeschützt geöffnet; es gibt keine neue Adresszuordnung und keinen
Adressimport. Ein anderer GWR-Pfad lässt sich mit `--gwr-db` beim Start
angeben. Fehlt eine Adresse, bleibt sie ausdrücklich nicht verfügbar.

Pro EGID entsteht ein GeoJSON-Point mit String-ID und Koordinaten
`[Longitude, Latitude]`. Angezeigt werden die Kandidaten des Falls sowie Gebäude
mit passender bekannter EGRID, jeweils ausschliesslich mit GSTAT 1004. Die Punkte
bleiben auch bei Ausfall der Parzellenquelle darstellbar. Die EGID-Abfrage
setzt keinen Parzellentreffer voraus.

Leaflet zeichnet CircleMarker mit gemeinsamem Canvas-Renderer, Farben nach
Gebäudestatus, Punktgrössen nach Zoom und EGID-Tooltip. Ein Klick hebt die EGID
hervor. Die Anzeige erzeugt keine automatische Zuordnung.

Die obere Kartenleiste mit Parzellenauswahl, Neuladen, Statusauswahl und
Punktauswahl entfällt. Die Karte zeigt ausschliesslich bestehende Gebäude
(GSTAT 1004); der Hinweis steht klein bei den Quellenangaben unten. Dieser
Filter ist auch in der API fest vorgegeben. Gebäude mit anderem oder
unbekanntem Status werden nicht dargestellt.

Bei bekannter EGRID wird diese exakt abgefragt. Sonst sind Sektion und
Parzellennummer gemeinsam moeglich. Kein Kartenklick speichert eine manuelle
EGID-Zuordnung.

Polygon, MultiPolygon und Innenringe werden geprueft. Die aktive Parzelle bleibt
hell, ihr Aussenbereich wird abgedunkelt. Mehrere EGID werden nach Kennung
zusammengefuehrt, ohne unterschiedliche bekannte Positionen zu verlieren.
Eine raeumlich abgeleitete Beziehung wird ausdruecklich gekennzeichnet;
Grenzlagen und widerspruechliche Geometrien bleiben klaerungsbeduerftig.

Wenn vorhanden, transformiert `pyproj` LV95 mit `always_xy=True`. In der
bestehenden Umgebung fehlt diese optionale Bibliothek. Ohne Installation
verwendet die Punktanzeige deshalb die dokumentierte Swisstopo-Näherung.
Tooltip und EGID-Details kennzeichnen dies. Diese Punkte dienen ausschliesslich
der Anzeige, nicht einer Grenzprüfung oder Vermessung. Zusätzliche auswählbare
EGID beruhen auf den importierten EGRID-Beziehungen, nicht auf Näherungspunkten.
Fehlende oder ungültige Koordinaten werden gemeldet und nicht erfunden.

[Gepruefte Dienstinformationen, Profile, Tests und offene Punkte](GEODATEN.md)
sind separat dokumentiert. Online wurden nur die ausdruecklich freigegebenen
Dienstbeschreibungen und Schemata geprueft, keine echten Geodatensaetze.

## Export

**Gesamte Zuteilung als Excel exportieren** liest einen konsistenten gespeicherten
SQLite-Stand und öffnet den Windows-Speicherdialog. Ein erneuter Excel-Import ist
nicht erforderlich. Die Ausgabe enthält:

1. **review_address_suffix**: alle importierten GVBSID mit Originalspalten und
   Werten, manuell zugeteilten EGID, Status, Kommentar und Bearbeitungszeitpunkt.
2. **Zuordnungen**: eine Zeile je gespeicherter GVBSID-EGID-Beziehung, inklusive
   Zweckbestimmung, Status und Kommentar.
3. **Offene Fälle**: alle Fälle mit Status Offen, Unklar oder Zurückgestellt.

Mehrere EGID werden vollständig aufgelistet. Abgeschlossene Fälle und solche
ohne mögliche Zuordnung bleiben im Gesamtblatt enthalten. Bereits vorhandene
gleichnamige Zusatzspalten werden erhalten; neue Zusatzspalten erhalten einen
eindeutigen Namen. Kommentare werden als Text exportiert, ursprüngliche Formeln
aus dem Excel-Import dagegen beibehalten. Ungespeicherte Browseränderungen sind
nicht Bestandteil eines Exports.

## Synthetische Prüfungen

```powershell
.\.venv\Scripts\python.exe -I -B tests\test_zuordnung_store.py
.\.venv\Scripts\python.exe -I -B tests\test_zuordnung_app.py
.\.venv\Scripts\python.exe -I -B tests\test_zuordnung_geo.py
.\.venv\Scripts\python.exe -I -B tests\test_zuordnung_gwr.py
```

`tests/test_egid_punkte.js` prüft die Leaflet-Punktlogik mit reinen JavaScript-
Attrappen. Falls Node bereits vorhanden ist: `node tests/test_egid_punkte.js`.
Es wird dafür keine Software installiert.

Die Tests verwenden ausschliesslich selbst erzeugte SQLite-Datenbanken,
Excel-Arbeitsmappen und HTTP-Anfragen im Arbeitsspeicher. Dateidialoge,
Einstellungsdateien, Exportdateien und externe Dienste werden ersetzt. Es werden
weder ein Server noch ein Browser gestartet und keine produktiven Dateien oder
Netzwerkdienste geöffnet.
