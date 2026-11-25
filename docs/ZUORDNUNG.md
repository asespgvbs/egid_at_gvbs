# Lokales GVBSID-EGID-Zuordnungswerkzeug

## Start

```powershell
cd C:\dev\repos\egid_match
.\.venv\Scripts\python.exe -m egid_match.zuordnung
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

Die bestehenden Programme `src/egid_match/matching.py` und `src/egid_match/abdeckung.py` bleiben
unverändert und unabhängig vom Zuordnungswerkzeug.

## Datenbank und Schritt 2

1. **Datenbank auswählen** öffnet den nativen Windows-Dialog. Alternativ legt
   **Neue erstellen** eine neue Datei an. Speicherorte ausserhalb des Repositories
   sind zur Laufzeit ausdrücklich möglich. Vorhandene Dateien werden bei der
   Neuerstellung auch nach einer Dialogbestätigung nicht überschrieben.
2. **Excel laden** übernimmt die Blätter `review_address_suffix`,
   `address_suffix_pair_lt4` und `review_suffix_1gvbsid_n_egid`, soweit vorhanden.
   Das zweite Blatt enthält orange Adress-Suffix-Paare mit Kubaturverhältnis
   unter 4 zur manuellen Prüfung. Das dritte Blatt enthält dunkelgelbe Prüffälle mit
   genau einer Importzeile `Kontrollnummer-0` an der Hauptadresse und einer oder
   mehreren zusätzlichen GWR-Suffixadressen. Diese Kontrollnummer kommt im
   gesamten Import nur einmal vor. In aktuellen Matching-Ausgaben wird der direkte
   Treffer automatisch zugeteilt und nicht als Prüffall importiert. Ältere, nicht
   automatisch zugeteilte Fälle bleiben importierbar.
   Die vollständige Kategorie heisst `review_suffix_single_gvbsid_multiple_egid`;
   der Blattname ist wegen der Excel-Grenze von 31 Zeichen verkürzt.
   Der alte Name `review_suffix_single_building` bleibt importierbar und wird
   wie die neue Kategorie als **Eine GVBSID mit mehreren EGIDs · Manuell prüfen**
   mit derselben dunkelgelben Farbe angezeigt. Originalwerte bleiben erhalten.
   Vollständige, gekürzte und alte Kategorieblattnamen werden ohne Beachtung
   von Gross-/Kleinschreibung und äusseren Leerzeichen erkannt.
   Das vollständige Gesamtblatt ist die bevorzugte Quelle; fehlende, leere oder
   unvollständige Kategorieblätter führen dadurch nicht zum Auslassen von Prüffällen.
   Hellbraun markierte Paare aus `address_suffix_pair_ge4` sind bereits automatisch
   zugeordnet und werden nicht als Prüffälle importiert; ihre EGID werden gesperrt.
   Die Prüffallblätter müssen dieselben
   Spalten enthalten. Originalspalten
   und Zellwerte werden in SQLite gespeichert. Pro GVBSID ist eine eindeutige
   Importzeile erforderlich. Alternativ aktiviert **Gespeicherte Daten
   aktivieren** die bereits importierten Fälle ohne erneutes Excel-Lesen.

Die Matching-Ausgabe enthält gegebenenfalls eindeutig korrigierte PLZ und
Suchadressen aus dem einmaligen PLZ-Korrekturlauf. Das Zuordnungstool übernimmt
diese fertigen Ergebnisse einschliesslich `PLZ ursprünglich` und `PLZ korrigiert`.
Es führt selbst keine weitere PLZ-Korrekturrunde durch. Der Import verwendet die
abschliessend über den gesamten Matching-Bestand neu berechneten Kategorien und
automatischen EGID-Zuordnungen.

Fälle der Kategorie `zuordnungskonflikt` werden ebenfalls zur Prüfung importiert.
EGIDs aus der Eingabespalte `EGID_zugeteilt` sind wie automatische Zuteilungen
für die manuelle Vergabe gesperrt. Die Kategorie `manuell_zugeteilt` wird nicht
als neuer Prüffall importiert. Bereits in der Datenbank vorhandene Fälle werden
beim erneuten Import nicht automatisch entfernt oder abgeschlossen.

Für den Import wird die **vollständige Matching-Datei mit dem Blatt `Matching`**
benötigt. Daraus übernimmt die App alle tatsächlich automatisch zugeteilten EGID
in eine globale Sperrliste, auch wenn die zugehörigen GVBSIDs keine Prüffälle
sind. Reine Prüffalldateien ohne diese Information werden zurückgewiesen.
Ein umbenanntes Gesamtblatt wird anhand der Spalten `GVBSID`, `Matching-Kategorie`,
`EGID`, `Automatische Zuordnung` und `EGID-Kandidaten` erkannt. Seine Gesamtzahl
und Kategorieanzahlen müssen zur exportierten Zusammenfassung (`Kategorie`,
`Anzahl`, `Gesamt`) passen. Einzelne Kategorieblätter gelten nicht als vollständige
Sperrliste. Auch beim Namen `Matching` werden Gross-/Kleinschreibung und äussere
Leerzeichen ignoriert.
Aktuelle App-Exporte enthalten die Sperrliste im Blatt `Automatische Zuordnungen`
und können ebenfalls importiert werden. Bereits bekannte Sperren bleiben bei
weiteren Importen erhalten.

Bei älteren Bearbeitungsständen ohne Sperrliste muss die vollständige
Matching-Datei einmal neu importiert werden. Bis dahin können Fälle angesehen,
aber keine Zuordnungen gespeichert werden. Bestehende manuelle Entscheidungen
bleiben beim Import erhalten.

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

Links füllt die Zuordnungsmatrix den verfügbaren Bereich bis zu den
Aktionsknöpfen aus. Rechts oben stehen EGRID, GVBSID-/EGID-Anzahlen, gemeinsame
Kategorie und die Auswahlfelder für Verhältnis, Warteliste und EGRID-Paket. Direkt darunter
liegt die Karte. Auf schmalen Bildschirmen stehen Paketkopf, Matrix und Karte
untereinander.

Die obere ausklappbare Bedienleiste schliesst sofort, sobald die Maus ihren
Bereich verlässt, ohne Wartezeit oder Ausblendanimation. Am oberen Fensterrand
lässt sie sich wieder einblenden. Während der Einrichtung bleibt die Leiste
sichtbar, bis die Prüffälle aktiviert sind.

Die Matrixzeilen sind nach GVBSID numerisch aufsteigend sortiert, zuerst nach
Kontrollnummer und dann nach Gebäudenummer: beispielsweise `1234-1`, `1234-2`,
`1234-4`, `1234-10`. Die EGID-Spalten stehen nach GWR-Kubatur (`GVOL`) absteigend,
mit dem grössten Gebäude zuerst. Bei gleichem Volumen entscheidet die EGID
numerisch aufsteigend. EGIDs ohne gültige Volumenangabe stehen am Ende;
`0 m³` gilt als vorhandene Angabe. Nachgeladene Volumen aktualisieren die
Spaltenreihenfolge. Bestehende Zuteilungen und Kommentare bleiben dabei erhalten.

Bei allen Verhältnisfiltern prüft die Matrix auch die GVBS-Kubaturen in der
angezeigten, numerisch aufsteigenden GVBSID-Reihenfolge.
Ist eine Kubatur grösser als die vorhergehende gültige Kubatur im EGRID-Paket,
erscheinen **alle Gebäudevolumenangaben des Pakets rot und fett**. Gleiche Werte sind zulässig;
fehlende oder ungültige Werte werden beim Vergleich übersprungen. Dezimalkomma
und Schweizer Tausendertrennzeichen werden berücksichtigt. Die GVBSIDs bleiben
aufsteigend sortiert. Die Volumenmarkierung gilt bei **Alle Verhältnisse**,
**Nur 1:1** und **ungleich 1:1**.

Ein gemeinsames Infofenster zeigt die jeweils zutreffenden Hinweise:

- **INFO: Die GVBSID-Nummerierung stimmt nicht mit der Sortierung der Kubatur überein.**
- **ACHTUNG: Mehrere Kontrollnummern auf der Parzelle.**
- **INFO: Die EGIDs auf der Parzelle haben unterschiedliche Hauptadressen.**
- **INFO: Die GVBSIDs auf der Parzelle haben unterschiedliche Hauptadressen.**

Das Fenster muss über **Verstanden** geschlossen werden; Escape und ein Klick
ausserhalb schliessen es nicht. Bestätigte Hinweise erscheinen beim Neuzeichnen
desselben geöffneten Pakets nicht erneut. Kommt durch nachgeladene Geodaten ein
neuer Hinweis hinzu, öffnet sich dasselbe Fenster mit den aktuellen Hinweisen.
Beim erneuten Öffnen eines Pakets werden die Hinweise wieder angezeigt.

Die Kontrollnummer kommt aus der Importspalte `Kontrollnummer`, ersatzweise aus
dem Teil der GVBSID vor der letzten Trennung zur Gebäudenummer. Für den
Adressvergleich zählen bekannte GWR-Adressen der im Paket angezeigten EGIDs.
Unterschiedliche Strassen oder Hauptnummern lösen den Hinweis aus, etwa
`Singstrasse 2` und `Singstrasse 4`. Nur Punkt-Zahl-Zusätze derselben Hauptadresse,
etwa `Singstrasse 2`, `Singstrasse 2.1` und `Singstrasse 2.2`, bleiben ohne Hinweis.
`Singstrasse 2`, `Singstrasse 2A` und `Singstrasse 2B` sind unterschiedliche
Adressen; allein Gross-/Kleinschreibung (`2a` und `2A`) erzeugt keinen Unterschied.
Fehlende Adressen, veraltete Geodaten und Adressen anderer
EGRID-Pakete werden nicht als Beleg für unterschiedliche Hauptadressen verwendet.
Für GVBSIDs werden die angezeigten Suchadressen verwendet, ersatzweise die
importierten Spalten `Strasse`, `Hausnummer`, `Hausnummer Zusatz` und
`Postleitzahl` einschliesslich ihrer Spaltenaliasnamen. Dieselben Regeln zum
Ignorieren reiner Hausnummernsuffixe gelten auch für GVBSIDs. Fehlende oder nicht
eindeutig zerlegbare Adressen lösen keinen Unterschiedshinweis aus.
Die Prüfung selbst löst keine zusätzlichen Datenabfragen aus und verändert
weder Checkboxen noch gespeicherte Zuteilungen.

Bei gleicher Anzahl GVBSIDs und EGIDs im EGRID-Paket erscheint oberhalb der
Matrix **Grössenzuordnung**, auch bei 2:2 oder 4:4. Die Grössenvorschläge sind
standardmässig eingeschaltet und umranden die Matrixfelder für EGID und GVBSID
mit demselben Grössenrang:
grösste GWR-Kubatur zur grössten GVBS-Kubatur, zweitgrösste zur zweitgrössten
usw. Beispielsweise werden GVBS-Kubaturen von 100 und 300 m³ mit GWR-Volumen von
90 und 310 m³ verbunden. Exakt gleiche Werte sind nicht erforderlich.
Bei gleichem Volumen entscheidet die jeweilige ID numerisch aufsteigend.

Die bisherige Zeilen- und Spaltenreihenfolge bleibt erhalten. Direkt im
umrandeten Feld steht der Quotient **m³ GVBSID/EGID**, beispielsweise **1.68**
für 1680 m³ GVBS und 1000 m³ GWR. Die Anzeige verwendet höchstens zwei
Nachkommastellen. Werte **über 2** erscheinen mit roter Schrift und roter
Umrandung; genau 2 bleibt unmarkiert. Für die Schwelle zählt der ungerundete
Quotient. Der Hinweis beim Darüberfahren nennt beide Volumenwerte.
Bei 0 m³ GWR ist das Verhältnis nicht bestimmbar.

Der Knopf blendet Umrandungen und Verhältnisangaben aus oder wieder ein. Die Funktion
verändert keine Checkboxen, Zuteilungen, Kommentare oder Bearbeitungsstatus und
speichert nichts. Sie löst keine zusätzlichen Datenabfragen aus. Auch bereits
automatisch zugeteilte EGIDs können verglichen werden und bleiben dabei gesperrt.
Fehlt die EGRID oder eine gültige Kubatur, ist der Knopf deaktiviert und nennt
den Grund. Nachgeladene Volumen aktualisieren die umrandeten Felder; ist die
Anzahl anschliessend ungleich, entfallen Vorschläge und Knopf. Beim Paketwechsel
werden die Vorschläge wieder standardmässig eingeschaltet. Fehlende Volumen
werden nach dem Laden automatisch berücksichtigt. Ein manuelles Ausblenden
bleibt bei weiteren Geodatenaktualisierungen desselben Pakets erhalten.

Haben alle GVBSIDs eines EGRID-Pakets dieselbe Kategorie, erscheint diese einmal
unter der EGRID-Überschrift. Die Wiederholungen an den einzelnen GVBSIDs entfallen,
und der Bearbeitungsbereich übernimmt die gemeinsame Matching-Kategoriefarbe.
Enthält das Paket unterschiedliche Kategorien, bleibt der Paketrahmen neutral;
jede GVBSID trägt dann ihre eigene Kategorie und Zeilenfarbe. Allgemeine Suffix-Prüffälle sind
hellgelb, einzelne Gebäude mit Suffixadressen dunkelgelb und manuell zu prüfende
Suffix-Paare orange. Bereits gespeicherte Fälle verwenden ihre importierte
`Matching-Kategorie`; fehlt diese Angabe, bleibt die Darstellung neutral.

Die Paketauswahl rechts oben enthält **einen Eintrag je EGRID-Paket**, mit EGRID,
Kontrollnummern und GVBSID-/EGID-Anzahlen. Alle importierten Prüffälle
derselben verlässlich bekannten EGRID werden gemeinsam angezeigt, auch bei
unterschiedlichen Kontrollnummern und Gebäudenummern. Eine GVBSID mit mehreren
EGRIDs kann zu mehreren Paketen gehören; jede EGRID bleibt ein eigener Eintrag.
Fehlt eine verlässliche EGRID, bleibt der Fall als eigener Klärungseintrag
sichtbar. Paketaktionen sind erst nach verlässlicher EGRID-Auflösung möglich,
damit keine einzelne GVBSID irrtümlich als vollständige Parzelle gespeichert wird.
Zweckbestimmung steht jeweils direkt hinter der GVBSID; darunter
erscheint das Gebäudevolumen aus der importierten Spalte `Kubatur` in m³.
Fehlt ein Wert, steht dort `Nicht angegeben`.

Über **Warteliste** wird zwischen **Offen**, **Sonderfälle** und **Abgeschlossen**
gewechselt. Der ausgewählte Bereich bestimmt die Fallauswahl und Paketnavigation.
Darüber steht der Filter **GVBSID:EGID - Verhältnis**:

- **Alle Verhältnisse** ist die Standardauswahl und zeigt alle Pakete der gewählten Warteliste.
- **Nur 1:1** zeigt gleiche Anzahlen unterschiedlicher GVBSIDs und EGIDs, also
  beispielsweise 1:1, 2:2 oder 4:4.
- **ungleich 1:1** zeigt unterschiedliche Anzahlen, auch Fälle ohne EGID wie 1:0.

Gezählt werden die eindeutigen IDs des Pakets: importierte Kandidaten,
gespeicherte Zuteilungen und zusätzliche verlässlich geladene Geodaten des Pakets.
Bereits zugeteilte, auf der Karte ausgegraute EGIDs zählen mit, auch wenn sie in der
Matrix ausgeblendet sind. Veraltete Geodaten
und Geodaten anderer EGRID-Pakete werden nicht als zusätzliche Kandidaten gezählt.
Das Filtern selbst löst keine weiteren Geodatenabfragen aus.

Nachgeladene Geodaten können das Verhältnis und die gefilterte Warteliste ändern.
Das aktuell geöffnete Paket bleibt dabei sichtbar, gegebenenfalls mit dem Hinweis
**Ausserhalb der Auswahl**. Weiter und Zurück berücksichtigen ausschliesslich die
gefilterte Warteliste. Auch bei einem Verhältniswechsel schützt die vorhandene
Rückfrage ungespeicherte Änderungen; bei Abbruch bleiben beide Filter erhalten.

Vor einem Listenwechsel fragt die App nach, falls ungespeicherte Änderungen
vorhanden sind. Ein Paket erscheint nur einmal: Sobald ein Mitglied Sonderfall
ist, steht es unter Sonderfälle; erst wenn alle Mitglieder abgeschlossen sind,
steht es unter Abgeschlossen. Sonst steht es unter Offen. Frühere Teilbearbeitungen
bleiben so sichtbar. Ein erneuter Klick auf Sonderfall oder Entscheidung speichern
setzt anschliessend alle Fälle dieses Pakets auf denselben Status.

**Weiter** und **Zurück** wechseln jeweils zum nächsten oder vorherigen Paket
der gewählten Warteliste und überspringen alle weiteren GVBSIDs des angezeigten
Pakets. Ein Paket umfasst genau die Fälle einer EGRID. Ohne verlässliche EGRID
ist jeder Fall ein eigenes Paket. Die Reihenfolge folgt
dem ersten Auftreten im Import, auch wenn die Mitglieder eines Pakets dort
verstreut standen. Anstelle der Paketnummer zeigt die Anzeige beispielsweise
**Noch 123 von 200 GVBSIDs ohne EGID · Alle Verhältnisse**. Beide Zahlen beziehen
sich auf den gewählten Verhältnisfilter: **Alle Verhältnisse**, **Nur 1:1** oder
**ungleich 1:1**. Die Gesamtzahl umfasst alle importierten Prüffälle dieser Gruppe;
die verbleibende Anzahl umfasst deren GVBSIDs ohne gespeicherte EGID-Zuteilung.
Beide Zahlen bleiben unabhängig vom Wartelistenstatus. Auch 2:2 oder 4:4 gehören
zu **Nur 1:1**, ein Paket mit 1:0 gehört zu **ungleich 1:1**.
Jede GVBSID zählt innerhalb jeder Ansicht einmal. Gehört sie zu Paketen beider
Verhältnisgruppen, zählt sie in beiden Teilansichten, im Gesamtbestand aber nur
einmal. Die beiden Teilansichten müssen deshalb zusammen nicht die Gesamtzahl ergeben. Fälle
mit Status Abgeschlossen oder Sonderfall ohne EGID zählen ebenfalls mit.
Mehrere gespeicherte EGIDs einer GVBSID gelten als eine zugeteilte GVBSID;
Kandidaten und Grössenvorschläge gelten nicht als gespeicherte Zuteilung.
Ungespeicherte Checkboxänderungen verändern den Zähler nicht; nach dem Speichern
wird er aktualisiert. Gespeicherte Zuteilungen und nachgeladene verlässliche
Geodaten können die Verhältnisgruppe eines Pakets und damit beide Zahlen ändern.
Die Zählung selbst löst keine zusätzlichen Geodatenabfragen aus.
**Ausserhalb der Auswahl** bleibt als separater Hinweis
sichtbar, wenn das geöffnete Paket nicht zur gefilterten Warteliste gehört. Einzelne GVBSIDs
bleiben über die Suche erreichbar; geöffnet wird ihr EGRID-Paket. Beim Blättern
bleibt die Rückfrage zu ungespeicherten Änderungen bestehen.

Jede Matrix-Checkbox stellt eine Beziehung dar. Eine GVBSID darf mehrere EGID
erhalten; dieselbe frei verfügbare EGID darf mehreren GVBSIDs zugeordnet werden. Status und
Kommentar werden je GVBSID geführt. Angezeigte ursprüngliche Kandidaten werden
niemals allein durch das Öffnen oder einen Kartenklick bestätigt.
Beim Anwählen einer Checkbox wird die zugehörige EGID, soweit auf der Karte
vorhanden, für 1,5 Sekunden gelb umrandet. Die Auswahl wird dadurch nicht
gespeichert; dafür bleibt **Entscheidung speichern** erforderlich.
Beim Klick auf eine EGID in der Matrix oder auf der Karte verschwindet die
Hervorhebung nach vier Sekunden. Ein erneuter Klick startet die Zeit erneut.

**Bereits zugeteilte EGID sind gesperrt und werden in der Matrix ausgeblendet.**
Auf der Karte sind sie bei Punkten, Gebäudegeometrien und Beschriftungen grau. Sie bleiben zur
Orientierung sichtbar und auf der Karte auswählbar, können aber keiner GVBSID
neu zugeordnet werden. Die Prüfung gilt auch für zusätzliche EGID aus dem
Geodienst und wird beim Speichern innerhalb derselben Transaktion erneut
durchgeführt. Ein unzulässiger Eintrag verwirft die gesamte Speicheraktion.

Wenn eine frühere manuelle Beziehung einer neuen automatischen Sperre
widerspricht, bleibt sie als Konflikt sichtbar. Mit **Gesperrte Zuordnung
entfernen** wird sie zur Entfernung vorgemerkt und erst durch **Entscheidung
speichern** tatsächlich geändert. Die betreffende EGID bleibt gesperrt.

**Entscheidung speichern** setzt **alle importierten Prüffälle der gesamten
EGRID** auf **Abgeschlossen**, auch ohne EGID-Zuordnung. Der rote Knopf
**Sonderfall** setzt ebenfalls **alle Fälle der EGRID** auf **Sonderfall**.
Dies gilt für sämtliche Kontrollnummern und Gebäudenummern des Pakets,
einschliesslich unveränderter oder zuvor anders markierter Zeilen. Zuordnungen
und Kommentare werden je GVBSID erhalten beziehungsweise mit den vorgenommenen
Änderungen gespeichert. Sonderfälle werden direkt an jeder GVBSID gekennzeichnet.

Die Änderungen werden gemeinsam in einer SQLite-Transaktion gespeichert.
Der Server weist unvollständige Pakete und gemischte Zielstatuswerte zurück.
Sind inzwischen weitere Fälle zur EGRID hinzugekommen, muss das Paket neu geladen
werden. Bei einer GVBSID, die zu mehreren EGRIDs gehört, ist ihr gespeicherter
Status auch in den anderen zugehörigen Paketen sichtbar.
Bei einem Versionskonflikt, zum Beispiel durch eine zweite
Browser-Registerkarte, wird der gesamte Speichervorgang zurückgerollt. Neu laden
und die Entscheidung auf Basis des aktuellen Stands erneut treffen.

- **Offen** zeigt noch nicht vollständig abgeschlossene Pakete ohne Sonderfall.
- **Sonderfälle** zeigt Pakete mit mindestens einem Sonderfall, mit oder ohne EGID-Zuordnung.
- **Abgeschlossen** zeigt vollständig abgeschlossene Pakete; der frühere Status Keine Zuordnung möglich zählt dabei als abgeschlossen.

Über **GVBSID eingeben → Bearbeiten** ist jeder gespeicherte Fall erreichbar,
auch ein abgeschlossener. Er kann dort bearbeitet und erneut abgeschlossen oder
als Sonderfall markiert werden. Nicht gespeicherte Änderungen werden beim Wechsel nicht
stillschweigend verworfen. Der Fortschritt zählt EGRID-Pakete.

## Karte und amtliche Geodaten

Die WMTS-Grundkarten bleiben reine Bildquellen. Parzellenpolygone kommen aus
amtlichen GeoBS-Vektordiensten. EGID-Punkte kommen unabhängig davon aus
der öffentlichen GWR-Publikation 100230. Profile stehen fest in `src/egid_match/zuordnung/quellen.py`; der
bisherige GeoBS-Dienste-Button und sein Dialog entfallen.

Nach Schritt 2 lädt die Karte Gebäudepunkte automatisch über die öffentliche
GWR-Quelle. Ein lokaler GWR-Dateiimport wird nicht angeboten. Alte gespeicherte
GWR-Snapshots werden nicht mehr genutzt und nicht automatisch gelöscht;
manuelle Entscheidungen und Excel-Originalwerte bleiben erhalten.

Die GWR-Adressen für Tabelle und Kartenbeschriftung liest die Anwendung direkt über die
bestehende `entrance.EGID`-Beziehung aus der GWR-Datenbank des Matchings.
Strassenname, Hausnummer mit Zusatz und Postleitzahl werden unverändert
übernommen. Links steht die GVBSID mit `(GVBSID)` und darunter `GVBS-Info:`
mit Adresse, Zweckbestimmung und Gebäudevolumen als Aufzählung. Die EGID-Spalten tragen
`(GWR)` und zeigen darunter die zugehörigen GWR-Adressen.
Vorhandene GWR-Adressen sind mit Google Maps verlinkt.
Ein Klick öffnet die Satellitenansicht in einem neuen Tab. Bei mehreren
GWR-Adressen ist jede Adresse separat verlinkt; fehlende Adressen bleiben
als nicht verfügbar gekennzeichnet. Die Verbindung zu Google Maps entsteht
erst durch den Klick.

Ist in der lokalen
GWR-Datenbank ein eindeutiger, nicht negativer Wert `building.GVOL` für die EGID
vorhanden, wird er als Zahl mit `m³` angehängt: beispielsweise
`101 (GWR) · 1250 m³`. Auch Kartenbeschriftungen und die EGID in den Klickdetails
erhalten diesen Zusatz. Ohne verfügbaren Wert entfällt er; die GVBS-Kubatur
wird dafür nicht als Ersatz verwendet. Die Abfrage erfolgt schreibgeschützt
und ausschliesslich für die betroffenen EGIDs bestehender Gebäude (`GSTAT = 1004`).
Die Quelle wird ausschliesslich
schreibgeschützt geöffnet; es gibt keine neue Adresszuordnung und keinen
Adressimport. Ein anderer GWR-Pfad lässt sich mit `--gwr-db` beim Start
angeben. Fehlt eine Adresse, bleibt sie ausdrücklich nicht verfügbar.

Pro EGID entsteht ein GeoJSON-Point mit String-ID und Koordinaten
`[Longitude, Latitude]`. Angezeigt werden die Kandidaten des Falls sowie Gebäude
mit passender bekannter EGRID, jeweils ausschliesslich mit GSTAT 1004. Die Punkte
bleiben auch bei Ausfall der Parzellenquelle darstellbar. Die EGID-Abfrage
setzt keinen Parzellentreffer voraus.

Leaflet zeichnet CircleMarker mit gemeinsamem Canvas-Renderer, Farben nach
Gebäudestatus und Punktgrössen nach Zoom. Die Kartenbeschriftung lautet
`EGID - GWR-Adresse`; Hoverinfos entfallen. Ein Klick hebt die EGID hervor
und zeigt Adresse und GSTAT, ohne den Kartenausschnitt zu verändern.
Die Anzeige erzeugt keine automatische Zuordnung.

Die obere Kartenleiste mit Parzellenauswahl, Neuladen, Statusauswahl und
Punktauswahl entfällt. Die Karte zeigt ausschliesslich bestehende Gebäude
(GSTAT 1004); der Hinweis steht klein bei den Quellenangaben unten. Dieser
Filter ist auch in der API fest vorgegeben. Gebäude mit anderem oder
unbekanntem Status werden nicht dargestellt.

Bei bekannter EGRID wird diese exakt abgefragt. Sonst sind Sektion und
Parzellennummer gemeinsam moeglich. Kein Kartenklick speichert eine manuelle
EGID-Zuordnung.

Polygon, MultiPolygon und Innenringe werden geprueft. Die geladenen Parzellen bleiben
hell, ihr Aussenbereich wird abgedunkelt. Der Ausschnitt zeigt die Parzellen
mit etwas Rand, bis maximal Zoomstufe 19; grosse Grundstücke werden passend
herausgezoomt. Grenze und Abdunkelung bleiben von EGID-Beschriftungen unabhängig.
Mehrere EGID werden nach Kennung
zusammengefuehrt, ohne unterschiedliche bekannte Positionen zu verlieren.
Eine raeumlich abgeleitete Beziehung wird ausdruecklich gekennzeichnet;
Grenzlagen und widerspruechliche Geometrien bleiben klaerungsbeduerftig.

Wenn vorhanden, transformiert `pyproj` LV95 mit `always_xy=True`. Ohne diese
optionale Bibliothek verwendet die Punktanzeige die dokumentierte Swisstopo-Näherung.
Die Methode bleibt intern im Geodatenkontext erhalten. Diese Punkte dienen ausschliesslich
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
4. **Sonderfälle**: alle Fälle mit Status Sonderfall.
5. **Abgeschlossene Fälle**: alle Fälle mit Status Abgeschlossen oder dem früheren
   Status Keine Zuordnung möglich.
6. **Automatische Zuordnungen**: die bekannte globale EGID-Sperrliste für einen
   erneuten Import. Bei Altbeständen ohne geladene Sperrliste fehlt dieses Blatt.

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
