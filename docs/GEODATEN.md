# GeoBS- und GWR-Anbindung

Stand: 13.11.2026. Ausschliesslich offizielle Dokumentation, OpenAPI,
Capabilities, Collection-Beschreibungen und Feldschemata wurden online geprüft.
Es wurden **keine echten Items, Grundstücks- oder Gebäudedatensätze abgefragt**.
Eine erfolgreiche Live-Datenabfrage wird deshalb nicht behauptet. Die
Implementierung wird offline mit synthetischen Antworten geprüft.

Die ursprüngliche Meldung entstand durch leere Standard-URLs und einen
gemeinsamen Abbruch, sobald eine der beiden Quellen fehlte. Damit konnte eine
verfügbare Parzellenquelle durch eine fehlende Gebäudequelle blockiert werden.
Zusätzlich war CQL2 für den QGIS-Endpunkt nicht belegt; die WFS-Vorgabe 2.0
passte nicht zur gemeldeten Serverversion 1.1.0. WMS-Bilder wurden nicht als
Polygone verarbeitet; dieser Unterschied wird jetzt auch beim Antwortformat
explizit geprüft. Diese Ursachen werden getrennt behoben statt nur die
Fehlermeldung auszublenden.

## Fest hinterlegte öffentliche Quellen

Die Profile stehen in `src/egid_match/zuordnung/quellen.py`. Der bisherige Konfigurationsbutton,
sein Dialog und der schreibende Konfigurationsendpunkt wurden entfernt. Alte
Geo-Einstellungen in der lokalen Merkliste überschreiben die Profile nicht mehr.
Der gemerkte Datenbankpfad bleibt erhalten.

### Parzellen

- Offizieller Einstieg: [GeoBS-API](https://api.geo.bs.ch/).
- [Collection-Beschreibung](https://api.geo.bs.ch/ogc/v1/wfs3/collections/ch.bs.av_parzellen_rechtliche_abgrenzungen_avpz.liegenschaft.json?MAP=Public_latest_published).
- [OpenAPI-Beschreibung](https://api.geo.bs.ch/ogc/v1/wfs3/api.json?MAP=Public_latest_published).
- Collection: `ch.bs.av_parzellen_rechtliche_abgrenzungen_avpz.liegenschaft`.
- Items-Pfad: diese Collection mit `/items.json`; Zusatzparameter
  `MAP=Public_latest_published`.
- Die OpenAPI dokumentiert direkte Attributparameter: `EGRID`, `Sektionsname`
  und `Parzellennummer`. Diese werden verwendet und anschliessend lokal
  nochmals verglichen. Ein generischer CQL2-Filter ist für diesen Dienst nicht
  belegt und wird hier nicht eingesetzt.
- Sektion und Parzellennummer werden nur zusammen verwendet. Bei einem
  Kartenpunkt liefert eine kleine BBOX Kandidaten, danach entscheidet die
  tatsächliche Polygongeometrie. Gemeinsame Ränder bleiben mehrdeutig.
- Die Beschreibung dokumentiert `limit` (maximal 10000), `offset`, `bbox`,
  `bbox-crs` und `crs`. Angefordert wird ausdrücklich CRS84, Longitude/Latitude.
  Die publizierte Collection-Ausdehnung dient zusätzlich als Plausibilitätsprüfung
  gegen widersprüchliche Achsen. Es wird kein CRS anhand der Zahlengrösse geraten.
- Der offizielle WFS meldet Version 1.1.0. WMS-/WMTS-Bilder sind ausschliesslich
  Kartendarstellung und werden nicht als Vektorgeometrie interpretiert.

Die Collection beschreibt publizierte Liegenschaften. Sie belegt nicht, dass
damit jede andere Grundstücksart, jedes selbständige Recht oder jede laufende
Mutation vollständig erfasst wäre. Polygon und MultiPolygon einschliesslich
Innenringen werden verarbeitet. Offene, selbstüberschneidende oder überlagerte
Geometrien werden nicht stillschweigend verwendet.

Parzellengrenzen und Aussenabdunkelung werden vor den EGID-Beschriftungen
gezeichnet und liegen in getrennten Kartenebenen. Der Kartenausschnitt zeigt
alle geladenen Parzellen mit einem Rand, bis maximal Zoomstufe 19. So bleiben
auch bei grossen Parzellen Grenze und Abdunkelung sichtbar. Mehrere Parzellen
und Innenringe werden in der Maske berücksichtigt. Fehlt eine Quellgeometrie,
steht der Grund im vorhandenen Detailfeld unter der Karte.

### EGID-Punkte aus dem öffentlichen GWR

Die Gebäudepunkte kommen ausschliesslich aus der öffentlichen GWR-Publikation
100230. Die Anwendung bietet keinen lokalen GWR-Import, keinen zugehörigen
Dateidialog und keinen Import-Endpunkt. Frühere GWR-Snapshot-Tabellen werden
nicht mehr genutzt und nicht automatisch gelöscht. Bestehende manuelle
Zuordnungen bleiben erhalten.

`src/egid_match/zuordnung/gwr.py` enthält die Koordinatentransformation für GKODE/GKODN und
die gezielte GWR-Adressabfrage. Beim Modulimport erfolgt kein Datenzugriff.
Die Skripte der Oberfläche werden in definierter Reihenfolge geladen.

Beim Laden der Karte liest die Anwendung die zur jeweiligen EGID bereits
gehörenden Adressen aus `entrance(EGID, STRNAME, DEINR, DPLZ4)` der bestehenden
GWR-Datenbank. Verwendet wird standardmässig der im Matching konfigurierte
`DEFAULT_GWR_DB`; ein anderer Pfad lässt sich beim Programmstart mit
`--gwr-db` angeben. Die Verbindung verwendet `mode=ro` und `query_only`.
Abgefragt werden ausschliesslich die vorhandenen Karten-EGID, per SQL-Parameter
und in begrenzten Gruppen. `DEINR` wird einschliesslich vorhandener Zusätze
unverändert übernommen. Mehrere GWR-Eingangsadressen einer EGID bleiben erhalten.
Es werden keine Adressen aus GVBS-Adressen, Nachbarschaft oder Importtexten
abgeleitet und keine bestehenden Beziehungen oder Datenbestände verändert.

Die Tabelle zeigt `EGID (GWR)` und darunter die Original-GWR-Adresse. Die
Karte beschriftet die Punkte dauerhaft mit `EGID - Adresse`; EGID-Hoverinfos
entfallen. Bei fehlenden Adressen gibt es keinen Ersatz durch eine andere EGID. Eine nicht lesbare
GWR-Adressquelle lässt die Kartenpositionen verfügbar und wird in den
EGID-Details gemeldet. Ein lokaler Import oder Snapshot wird nicht angelegt.

Mit `pyproj` wird `Transformer.from_crs("EPSG:2056", "EPSG:4326",
always_xy=True)` verwendet. Ohne diese Bibliothek bleibt die Anwendung ohne
Installation startbar: Die Anzeige nutzt Abschnitt 2 der offiziellen
[Swisstopo-Näherungsformeln, Dezember 2016](https://www.swisstopo.admin.ch/dam/en/sd-web/KLRCX9XIdXDu/ch1903wgs84-EN.pdf).
Swisstopo nennt Winkelgenauigkeiten von besser als 0.12 Bogensekunden in Länge
und 0.08 Bogensekunden in Breite innerhalb der Schweiz. Diese Näherung dient
ausschliesslich der Kartendarstellung; die Methode bleibt im Geodatenkontext
enthalten. In den Klickdetails werden Beziehungstext, Näherungshinweis und
Quellen-Exportdatum nicht angezeigt; Adresse und GSTAT bleiben sichtbar.
Sie wird niemals zum räumlichen Freischalten einer zusätzlichen EGID oder für
Grenzprüfungen verwendet. Der allgemeine Geometrieprüfer behält seine strikte
Transformationsanforderung.

Parzellen- und Gebäudequelle werden unabhängig ausgewertet. Auch bei einem
Parzellenfehler bleiben erfolgreich geladene öffentliche Gebäudepunkte nutzbar.
Beide Quellen unterliegen der unten beschriebenen Cache-Altersprüfung.

`src/egid_match/zuordnung/static/egid_punkte.js` verwendet Leaflet-GeoJSON mit `pointToLayer`,
einem gemeinsamen Canvas-Renderer, GSTAT-Farben, zoomabhängigen Radien und
dauerhafter EGID-/Adressbeschriftung. Der EGID-Canvas liegt über der Parzellenabdunkelung.

### Öffentliche Gebäudequelle

- [Öffentliche GWR-Datensatzbeschreibung 100230](https://data.bs.ch/explore/assets/100230/).
- [Verifiziertes Feldschema](https://data.bs.ch/api/explore/v2.1/catalog/datasets/100230).
- [Offizielle Explore-API-Dokumentation](https://data.bs.ch/api/explore/v2.1/swagger.json).
- Dokumentierter Records-Pfad: `/api/explore/v2.1/catalog/datasets/100230/records`.
- Verifizierte Felder: `egid`, `egrid`, `gstat`, `gkode`, `gkodn`, `gexpdat`.
- Verwendet werden dokumentierte `select`, `where`, `order_by`, `limit` und
  `offset`; die Gesamtsumme `total_count` wird gegen sämtliche Seiten geprüft.
  Es werden nur die benötigten Felder angefordert, keine vollständigen
  Gebäudedatensätze und keine GVBS-Inhalte übertragen.
- Das `egrid`-Feld ist der dokumentierte Grundstücksbezug der GWR-Publikation.
  Es wird bevorzugt und lokal kontrolliert. Sein Vorhandensein ist keine
  Zusicherung sämtlicher grundbuchlicher Mehrfachbeziehungen.
- Die [offiziellen GWR-Merkmalsdefinitionen](https://www.housing-stat.ch/catalog/index.html?final=true&lang=de&version=5.0)
  definieren GKODE/GKODN als Easting/Northing in LV95. Die Gebäudepunkte sind
  ausdrücklich von Gebäudeeingängen und Gebäudegrundrissen zu unterscheiden.
- Die GWR-Quelle liefert keine hier belegten vollständigen Grundrisspolygone
  oder Eingangsadressen. Aus der Punktsuche werden solche Informationen nicht
  abgeleitet oder erfunden. Das Exportdatum der Quelle wird erhalten.

Auch ohne passenden Parzellentreffer werden belegte EGRID beziehungsweise
EGID-Kandidaten unabhängig abgefragt. LV95-Punkte verwenden die oben beschriebene
Anzeigetransformation. Ohne bestätigten Grundstücksbezug
bleibt ein Punkt klärungsbedürftig. Parzellen werden bereits in CRS84 angefordert.

## Beziehung, Gebäudestatus und Darstellung

Die Karte zeigt ausschliesslich bestehende Gebäude (GSTAT 1004). Dieser Filter
ist in der Anwendungs-API fest vorgegeben; abweichende Statusangaben in einer
Anfrage erweitern ihn nicht. Gebäude ohne bestätigten GSTAT 1004 erscheinen
nicht auf der Karte. Der Hinweis steht klein bei den Quellenangaben unten;
die Karte hat keine obere Bedienleiste. Mehrere Eingänge/Geometrien derselben
EGID werden zusammengeführt, ohne Positionen und bekannte Adressen zu verlieren.

Für ein anderes belegtes Quellenprofil ohne EGRID-Beziehung unterstützt der
Adapter räumliche Kandidaten. Eine BBOX allein genügt nicht: Punkte und
vollständige Gebäudegeometrien werden gegen das genaue Polygon geprüft,
einschliesslich Innenringen. Ein Eingangspunkt beweist keine eindeutige
Gebäudezugehörigkeit. Grenzlagen, Grundstücksüberschreitungen und widersprüchliche
Geometrien bleiben klärungsbedürftig. Sie erzeugen keine neue freigeschaltete
Zuordnungsoption. Importierte Vorschläge und bereits gespeicherte manuelle
Entscheidungen werden dadurch nicht gelöscht oder automatisch verändert.

## Getrennte Zustände und begrenzte Abfragen

Parzellen und Gebäude haben jeweils eigene Zustände: nicht konfiguriert,
nicht erreichbar, ungültige Antwort, echte leere Antwort, mehrdeutig,
unvollständig oder vollständig innerhalb des dokumentierten Quellenumfangs.
Eine fehlende Gebäudequelle verhindert keine erfolgreiche Parzellenabfrage.
HTTP 200 allein bedeutet keinen Erfolg.

Grenzen: höchstens 20 Seiten, 12 MB je Antwort, 24 MB insgesamt und 45 Sekunden
je Kontextabfrage. Vorübergehende Verbindungsfehler werden höchstens einmal
wiederholt. Veränderte Gesamtsummen, fehlende nächste Seiten, Schleifen und
erreichte Grenzen werden ausdrücklich als unvollständig gemeldet.

Next-Links dürfen weder Quelle, Pfad noch Identifikator-/CRS-Filter verlieren.
QGIS liefert teilweise HTTP-Selbstlinks; nur derselbe freigegebene Host/Pfad wird
auf HTTPS angehoben, niemals eine HTTP-Datenabfrage ausgeführt. Weiterleitungen
auf andere Dienste werden nicht verfolgt. Ein Dienstfehler wird nicht als
erfolgreiche leere Trefferliste ausgegeben.

Abfragezustände und Einschränkungen bleiben im Geodatenkontext enthalten;
eine Statusleiste wird nicht eingeblendet. Nach fünf Minuten wird ein Cache
als veraltet markiert; neue Zusatzbeziehungen daraus werden bis zum Neuladen
nicht freigeschaltet. Eine ältere parallel laufende Kartenabfrage darf eine
neuere Auswahl nicht überschreiben.

## Nutzung und offene Prüfung

Quellenangabe: **Quelle: Geodaten Kanton Basel-Stadt**; für GWR zusätzlich
Statistisches Amt Basel-Stadt, Datensatz 100230 (Lizenzangabe: CC BY).
Die [kantonalen Nutzungsbedingungen](https://www.bs.ch/bvd/grundbuch-und-vermessungsamt/geo/anwendungen/agb)
und die [Bedingungen des Datenportals](https://data.bs.ch/terms/terms-and-conditions/)
gelten im jeweiligen Quellenumfang. Die Karte enthält die Quellenangabe.

Belegt sind Dienstbeschreibungen und Schemata, **nicht** die Qualität eines
bestimmten realen Grundstücks-/Gebäudefalls. Eine Live-Prüfung echter Features
bleibt ausgeschlossen, bis sie gesondert freigegeben würde. Kein API-Key,
keine privaten Quellen und keine vertraulichen Daten wurden verwendet.
