"use strict";

// Nur Quellcode und synthetische DOM-/Leaflet-Objekte, kein Browser oder Dienst.
function runReviewUiTest(sources) {
  let assertions = 0;
  function check(value, message) {assertions++; if (!value) throw new Error(message);}
  class Element {
    constructor(tag = "div") {
      this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attributes = {}; this.events = {}; this._text = "";
      const styles = new Map();
      this.style = {setProperty(name, value) {styles.set(name, value);}, getPropertyValue(name) {return styles.get(name) || "";}};
      const classes = new Set();
      this.classList = {toggle(name, force) {if (force) classes.add(name); else classes.delete(name);}, contains(name) {return classes.has(name);}};
    }
    set textContent(value) {this._text = String(value); this.children = [];}
    get textContent() {return this._text + this.children.map(child => child.textContent).join("");}
    append(...children) {this.children.push(...children);}
    replaceChildren(...children) {this._text = ""; this.children = children;}
    setAttribute(name, value) {this.attributes[name] = String(value);}
    removeAttribute(name) {delete this.attributes[name];}
    addEventListener(name, callback) {this.events[name] = callback;}
    contains(target) {return this === target || this.children.some(child => child.contains(target));}
    querySelectorAll(selector) {
      const matches = child => selector === "[data-egid]" ? child.dataset.egid !== undefined : ["INPUT", "SELECT", "TEXTAREA"].includes(child.tagName) || child.dataset.removeBlocked !== undefined;
      return this.children.flatMap(child => [...(matches(child) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
  }
  const elements = Object.fromEntries([...sources["src/egid_match/zuordnung/templates/zuordnung.html"].matchAll(/\bid="([\w-]+)"/g)].map(match => [match[1], new Element()]));
  elements["review-config"].textContent = JSON.stringify({token: "synthetic-token", category_colors: {
    review_address_suffix: "FFF2CC", address_suffix_pair_lt4: "F4B183",
    review_suffix_single_building: "E6C200", address_suffix_pair_ge4: "C4A484",
    synthetic_invalid: "url(https://synthetic.invalid/colour)",
  }});
  elements["case-content"].append(elements.matrix);
  const document = {body: new Element("body"), documentElement: new Element("html"), createElement: tag => new Element(tag), getElementById(id) {if (!elements[id]) throw new Error("Unbekannte DOM-ID"); return elements[id];}, addEventListener() {}};
  const window = {addEventListener() {}, setTimeout() {return 1;}, clearTimeout() {}, innerWidth: 1200, innerHeight: 800, requestAnimationFrame(callback) {callback();}};
  function group() {return {layers: [], clearLayers() {this.layers = [];}, getLayers() {return this.layers;}};}
  const viewCalls = [];
  const map = {getZoom() {return 19;}, setView(...args) {viewCalls.push(args);}, fitBounds(...args) {viewCalls.push(["fitBounds", ...args]);}, invalidateSize() {}};
  function bounds() {return {extend() {return this;}, isValid() {return true;}, getCenter() {return {lat: 47.52, lng: 7.55};}};}
  function layer(options = {}) {return {options, events: {}, addTo(target) {target.layers.push(this); return this;}, on(event, callback) {this.events[event] = callback; return this;}, setStyle() {}, getBounds: bounds, bindTooltip() {throw new Error("Unerwartete Karten-Hoverinfo");}};}
  const L = {
    latLngBounds: bounds,
    geoJSON(value, options = {}) {
      const result = layer(options);
      if (value.type === "FeatureCollection") result.markers = value.features.map(feature => options.pointToLayer(feature, {lng: feature.geometry.coordinates[0], lat: feature.geometry.coordinates[1]}));
      return result;
    },
    circleMarker(position, options) {return layer(options);},
    marker(position, options) {return layer(options);},
    divIcon(options) {return options;},
    polygon(coordinates, options) {const result = layer(options); result.coordinates = coordinates; return result;}
  };
  let apiCalls = 0;
  const points = new Function("document", sources["src/egid_match/zuordnung/static/egid_punkte.js"] + "\nreturn globalThis.ReviewEgidPoints;")(document);
  const source = sources["src/egid_match/zuordnung/static/zuordnung.js"];
  const startup = source.lastIndexOf('\naction(async () => {\n  const initial = await api("/api/state");');
  check(startup > 0, "Automatischen Anwendungsstart für den isolierten Test abtrennen");
  const ui = new Function("document", "window", "fetch", "ReviewEgidPoints", "L", source.slice(0, startup) + "\nreturn {renderCase,renderGeo,selectEgid,applyState,packageNavigation,decisionPayload,changed,switchQueueView,showEmptyQueue,configure(value,view,layers,items,filter='open'){current=value;selectedEgid=null;dirty.clear();queueView=filter;document.getElementById('queue-view').value=filter;state={database:'synthetic',active:true,progress:{total:1}};queue=items||[{gvbsid:value.selected}];map=view;mapLayers=layers;}};")(document, window, () => {apiCalls++; throw new Error("Externe Zugriffe verboten");}, points, L);
  const value = {
    selected: "SYNTHETIC-1", egrids: ["CH-SYNTHETIC-1"], egids: ["101", "102"],
    automatic_assignments_loaded: true, blocked_egids: [], assignable_egids: ["101", "102"],
    records: [{gvbsid: "SYNTHETIC-1", address: "GVBS-Testweg 1, 0000", purpose: "Synthetisches Wohnhaus", raw: {"Matching-Kategorie": "review_address_suffix", Kubatur: 1250}, candidates: ["101"], suffix_candidates: ["102"], grids: ["CH-SYNTHETIC-1"], assigned: [], status: "Offen", comment: ""}],
    geo: {volumes: {"101": 2400}, parcels: [{key: "CH-SYNTHETIC-1", egrid: "CH-SYNTHETIC-1", geometry: {type: "Polygon", coordinates: [[[7.5,47.5],[7.6,47.5],[7.6,47.6],[7.5,47.5]]]}}], buildings: [
      {egid: "101", gstat: "1004", addresses: [["GWR-Testgasse", "9a", "0000"]], geometry: {type: "Point", coordinates: [7.55,47.52]}, relation: "Amtliche EGRID-Beziehung der Quelle", geometry_note: "Swisstopo-Näherung (nur Kartendarstellung, keine Grenzprüfung)", source_updated: "2020-01-01"},
      {egid: "102", gstat: "1004", addresses: [], geometry: {type: "Polygon", coordinates: [[[7.55,47.52],[7.56,47.52],[7.56,47.53],[7.55,47.52]]]}}
    ]}
  };
  const layers = {parcels: group(), buildings: group(), markers: group(), labels: group(), mask: group()};
  ui.configure(value, map, layers);
  ui.renderCase();
  const table = elements.matrix.children[0], header = table.children[0].children[0], identity = table.children[1].children[0].children[0];
  check(elements["case-title"].textContent === "EGRID CH-SYNTHETIC-1", "Das EGRID-Paket in der Fallüberschrift kennzeichnen");
  check(elements["case-counts"].textContent === "(1 GVBSID/2 EGID)" && !elements["case-counts"].hidden, "Paketanzahlen direkt unter der EGRID anzeigen");
  check(identity.children[0].textContent === "SYNTHETIC-1 (GVBSID)", "GVBSID in der Tabellenzeile kennzeichnen");
  check(identity.children[1].textContent === "GVBS-Info:", "GVBS-Info als eigenen Abschnitt anzeigen");
  check(identity.children[2].tagName === "UL" && identity.children[2].children.length === 3, "Adresse, Zweckbestimmung und Gebäudevolumen als Aufzählung anzeigen");
  check(identity.children[2].children[0].textContent === "Adresse: GVBS-Testweg 1, 0000", "GVBS-Adresse ausschliesslich aus dem GVBS-Datensatz anzeigen");
  check(identity.children[2].children[1].textContent === "Zweckbestimmung: Synthetisches Wohnhaus", "Zweckbestimmung unterhalb der Adresse anzeigen");
  check(identity.children[2].children[2].textContent === "Gebäudevolumen: 1250 m³", "Importierte Kubatur unterhalb der Zweckbestimmung anzeigen");
  check(header.children[1].children[0].textContent === "101 (GWR) · 2400 m³", "GVOL direkt an die EGID-Beschriftung anhängen");
  check(header.children[2].children[0].textContent === "102 (GWR)", "Bei fehlendem GVOL kein Volumen ergänzen und keine GVBS-Kubatur übernehmen");
  check(header.children[1].children[1].textContent === "GWR-Testgasse 9a 0000", "Original-GWR-Adresse unter der EGID anzeigen");
  check(header.children[2].children[1].textContent === "GWR-Adresse nicht verfügbar", "GVBS-Adresse niemals als GWR-Ersatz anzeigen");
  check(elements["left-pane"].style.getPropertyValue("--category-color") === "#FFF2CC", "Bearbeitungsbereich in der Farbe des ausgewählten Falls darstellen");
  check(!elements["case-category"].hidden && elements["case-category"].textContent.includes("Allgemeine Prüfung"), "Kategorie zusätzlich als Text anzeigen");
  check(!identity.children.some(child => child.className === "row-category-label"), "Einheitliche Kategorie nicht zusätzlich an jeder GVBSID wiederholen");
  ui.renderGeo();
  check(layers.parcels.layers.length === 1 && layers.parcels.layers[0].options.pane === "parcel-boundaries", "Parzellengrenze in eigener Ebene darstellen");
  check(layers.mask.layers.length === 1 && layers.mask.layers[0].options.pane === "parcel-mask", "Abdunkelung getrennt von Grenzen und Gebäuden darstellen");
  check(viewCalls[viewCalls.length - 1][0] === "fitBounds" && viewCalls[viewCalls.length - 1][2].maxZoom === 19, "Auch eine einzelne grosse Parzelle vollständig zeigen und Zoom 19 als Obergrenze erhalten");
  check(viewCalls[viewCalls.length - 1][2].padding[0] > 0, "Rand für die Abdunkelung um die Parzelle freihalten");
  check(layers.labels.layers.length === 2, "Beide EGID auf der Karte beschriften");
  check(layers.labels.layers[0].options.icon.html.textContent === "101 - GWR-Testgasse 9a 0000 · 2400 m³", "Kartenbeschriftung enthält EGID, Originaladresse und GVOL");
  check(layers.labels.layers[1].options.icon.html.textContent === "102 - GWR-Adresse nicht verfügbar", "Fehlende GWR-Adresse auch auf der Karte kenntlich machen");
  const previousViewCalls = viewCalls.length;
  layers.labels.layers[0].events.click();
  const details = elements["egid-details"].textContent;
  check(details.includes("GSTAT 1004"), "Gebäudestatus in den Klickdetails erhalten");
  check(details.includes("GWR: GWR-Testgasse 9a 0000"), "Originaladresse in den Klickdetails erhalten");
  check(details.includes("EGID 101 · 2400 m³"), "GVOL auch an die EGID in den Klickdetails anhängen");
  check(!details.includes("Amtliche EGRID") && !details.includes("Swisstopo") && !details.includes("Quellen-Exportdatum") && !details.includes("2020-01-01"), "Beziehungstext, Näherungshinweis und Exportdatum nicht anzeigen");
  check(viewCalls.length === previousViewCalls, "EGID-Klick verändert den Kartenausschnitt nicht");
  layers.buildings.layers[0].events.click();
  check(elements["egid-details"].textContent.includes("EGID 102") && elements["egid-details"].textContent.includes("GSTAT 1004"), "Gebäudegeometrie bleibt ohne Hoverinfo anklickbar");
  check(viewCalls.length === previousViewCalls, "Klick auf Gebäudegeometrie verändert den Kartenausschnitt nicht");
  const multi = {...value, geo: {...value.geo, parcels: [...value.geo.parcels,
    {key: "CH-SYNTHETIC-2", egrid: "CH-SYNTHETIC-2", geometry: {type: "Polygon", coordinates: [[[7.57,47.52],[7.58,47.52],[7.58,47.53],[7.57,47.52]]]}}
  ]}};
  ui.configure(multi, map, layers);
  ui.renderGeo();
  check(layers.parcels.layers.length === 2, "Alle Parzellengrenzen erhalten");
  check(layers.mask.layers.length === 1 && layers.mask.layers[0].coordinates.length === 3, "Auch bei mehreren Parzellen den gemeinsamen Aussenbereich abdunkeln");
  check(viewCalls[viewCalls.length - 1][0] === "fitBounds", "Mehrere Parzellen gemeinsam im Ausschnitt zeigen");
  const hole = [[7.55,47.51],[7.56,47.51],[7.56,47.52],[7.55,47.52],[7.55,47.51]];
  const withHole = {...value, geo: {...value.geo, parcels: [{...value.geo.parcels[0], geometry: {type: "Polygon", coordinates: [...value.geo.parcels[0].geometry.coordinates, hole]}}]}};
  ui.configure(withHole, map, layers);
  ui.renderGeo();
  check(layers.mask.layers.length === 1 && layers.mask.layers[0].coordinates.length === 3, "Innenring im selben Abdunkelungspfad erhalten");
  check(layers.mask.layers[0].coordinates[2][0][0] === 47.51 && layers.mask.layers[0].coordinates[2][0][1] === 7.55, "Innenring mit unvertauschter Leaflet-Achsenreihenfolge darstellen");
  const icon = L.divIcon;
  L.divIcon = () => {throw new Error("Synthetischer Beschriftungsfehler");};
  ui.configure(value, map, layers);
  const beforeLabelFailure = viewCalls.length;
  try {ui.renderGeo();} catch (error) {check(error.message === "Synthetischer Beschriftungsfehler", "Nur den absichtlich ausgelösten Beschriftungsfehler abfangen");}
  L.divIcon = icon;
  check(layers.parcels.layers.length === 1 && layers.mask.layers.length === 1, "Beschriftungsfehler entfernen weder Grenze noch Abdunkelung");
  check(viewCalls.length > beforeLabelFailure, "Parzelle vor der Beschriftung zentrieren");
  const unavailable = {...value, geo: {...value.geo, parcels: [], sources: {parcels: {message: "Synthetischer Geometriefehler"}}}};
  ui.configure(unavailable, map, layers);
  ui.renderGeo();
  check(elements["egid-details"].textContent.includes("Keine Parzellengrenze verfügbar.") && elements["egid-details"].textContent.includes("Synthetischer Geometriefehler"), "Fehlende Quellgeometrie im vorhandenen Detailfeld erklären");
  for (const [category, colour] of [["address_suffix_pair_lt4", "#F4B183"], ["review_suffix_single_building", "#E6C200"], ["address_suffix_pair_ge4", "#C4A484"]]) {
    ui.configure({...value, records: [{...value.records[0], raw: {"Matching-Kategorie": category}}]}, map, layers);
    ui.renderCase();
    check(elements["left-pane"].style.getPropertyValue("--category-color") === colour, "Fallwechsel übernimmt die neue Kategoriefarbe");
    check(elements["case-category"].title === category, "Importierte Kategorie im Kategorienhinweis erhalten");
  }
  const mixed = {...value, selected: "SYNTHETIC-2", records: [
    {...value.records[0], raw: {"Matching-Kategorie": "review_suffix_single_building"}},
    {...value.records[0], gvbsid: "SYNTHETIC-2", raw: {"Matching-Kategorie": "address_suffix_pair_lt4"}},
  ]};
  ui.configure(mixed, map, layers); ui.renderCase();
  check(elements["left-pane"].style.getPropertyValue("--category-color") === "#d9e2e6" && elements["case-category"].hidden, "Bei gemischten Kategorien keine einheitliche Paketkategorie vorgeben");
  const mixedRows = elements.matrix.children[0].children[1].children;
  check(mixedRows[0].style.getPropertyValue("--category-color") === "#E6C200" && mixedRows[1].style.getPropertyValue("--category-color") === "#F4B183", "Gruppierte Zeilen behalten jeweils ihre eigene Kategoriefarbe");
  check(mixedRows.every(row => row.children[0].children.some(child => child.className === "row-category-label")), "Bei gemischten Kategorien jede GVBSID einzeln beschriften");
  for (const category of [undefined, "synthetic_unknown", "synthetic_invalid", "__proto__"]) {
    ui.configure({...value, records: [{...value.records[0], raw: {"Matching-Kategorie": category}}]}, map, layers);
    ui.renderCase();
    check(!elements["left-pane"].classList.contains("has-category"), "Fehlende oder unbekannte Kategorie neutral darstellen");
    check(elements["left-pane"].style.getPropertyValue("--category-color") === "#d9e2e6", "Vorherige Kategoriefarbe beim Wechsel zu unbekannter Kategorie entfernen");
  }
  const locked = {...value, blocked_egids: ["101", "102"], assignable_egids: [],
    records: [{...value.records[0], assigned: []}]};
  ui.configure(locked, map, layers); ui.renderCase();
  const lockedTable = elements.matrix.children[0], lockedHeader = lockedTable.children[0].children[0];
  const lockedCell = lockedTable.children[1].children[0].children[1], lockedInput = lockedCell.children[0];
  check(lockedHeader.children[1].classList.contains("egid-locked") && lockedCell.classList.contains("egid-locked"), "Automatisch zugeteilte Spalten und Zellen als gesperrt kennzeichnen");
  check(lockedInput.disabled && lockedHeader.children[1].textContent.includes("Automatisch zugeteilt"), "Gesperrte EGID deaktivieren und die Sperre erklären");
  lockedInput.checked = true; lockedInput.events.change();
  check(!lockedInput.checked && locked.records[0].assigned.length === 0, "Auch ein künstliches Änderungsereignis kann keine gesperrte EGID vergeben");
  ui.renderGeo();
  check(layers.markers.layers[0].markers.every(marker => marker.options.fillColor === "#a0a9b0"), "Automatisch zugeteilte Kartenpunkte grau darstellen");
  check(layers.buildings.layers[0].options.style.fillColor === "#a0a9b0", "Automatisch zugeteilte Gebäudegeometrien grau darstellen");
  check(layers.labels.layers[0].options.icon.html.textContent.includes("automatisch zugeteilt"), "Gesperrte Kartenbeschriftungen erklären die automatische Zuteilung");
  const conflict = {...value, blocked_egids: ["101"], assignable_egids: ["102"],
    records: [{...value.records[0], assigned: ["101"]}]};
  ui.configure(conflict, map, layers); ui.renderCase();
  check(conflict.records[0].assigned.join() === "101", "Bestehende manuelle Konflikte beim Anzeigen erhalten");
  const conflictIdentity = elements.matrix.children[0].children[1].children[0].children[0];
  const conflictNote = conflictIdentity.children.find(child => child.className === "assignment-conflict");
  conflictNote.children[1].events.click();
  check(conflict.records[0].assigned.length === 0, "Gesperrte Altzuordnung erst nach ausdrücklichem Klick entfernen");
  check(elements.matrix.children[0].children[1].children[0].children[1].children[0].disabled, "Nach Entfernen des Konflikts bleibt die EGID gesperrt");
  ui.configure({...value, automatic_assignments_loaded: false}, map, layers); ui.renderCase();
  check(elements.save.disabled && elements.matrix.children[0].children[1].children[0].children[1].children[0].disabled, "Ohne bekannte automatische Zuordnungen bleiben Vergabe und Speichern gesperrt");
  check(!elements["assignment-lock-note"].hidden && elements["assignment-lock-note"].textContent.includes("Matching-Datei"), "Bei Altbeständen den nötigen vollständigen Import erklären");
  check(elements.special.disabled, "Auch Sonderfälle erst mit bekannter automatischer Sperrliste speichern");
  ui.configure({...value, egrids: []}, map, layers); ui.renderCase();
  check(elements.save.disabled && elements.special.disabled, "Ohne bekannte EGRID keine einzelne GVBSID als vollständiges Paket abspeichern");
  const statusRecords = [
    {...value.records[0], status: "Sonderfall", version: 7},
    {...value.records[0], gvbsid: "SYNTHETIC-2", status: "Offen", version: 3},
    {...value.records[0], gvbsid: "SYNTHETIC-3", status: "Abgeschlossen", version: 2},
  ];
  ui.configure({...value, package_id: "egrid:CH-SYNTHETIC-1", records: statusRecords}, map, layers); ui.renderCase();
  check(!elements.save.disabled && !elements.special.disabled, "Bei gemischten Statuswerten beide Paketaktionen zum Vereinheitlichen anbieten");
  const statusIdentity = elements.matrix.children[0].children[1].children[0].children[0];
  check(statusIdentity.children.some(child => child.className === "record-status is-special" && child.textContent.includes("Sonderfall")), "Sonderfall als sichtbaren Status an der GVBSID kennzeichnen");
  ui.changed(statusRecords[1]);
  const completedPayload = ui.decisionPayload("Abgeschlossen");
  check(completedPayload.decisions.length === 3 && completedPayload.decisions.every(record => record.status === "Abgeschlossen"), "Speichern schliesst sämtliche Fälle des EGRID-Pakets gemeinsam ab");
  check(completedPayload.decisions[0].assigned.length === 0 && completedPayload.decisions[0].version === 7, "Abschluss ohne EGID erhält die Versionsprüfung");
  check(completedPayload.decisions.some(record => record.gvbsid === "SYNTHETIC-3"), "Auch unbearbeitete weitere Paketmitglieder werden einbezogen");
  check(completedPayload.package_id === "egrid:CH-SYNTHETIC-1", "Beim Speichern die genaue EGRID-Paketauswahl übermitteln");
  check(ui.decisionPayload("Sonderfall").decisions.every(record => record.status === "Sonderfall"), "Sonderfall-Aktion setzt einen ausdrücklichen Status");
  window.confirm = () => false;
  elements["queue-view"].value = "completed";
  ui.switchQueueView("completed");
  check(elements["queue-view"].value === "open", "Abgebrochener Wartelistenwechsel stellt die bisherige Auswahl wieder her");
  check(ui.decisionPayload("Abgeschlossen").decisions.length === 3, "Abgebrochener Wartelistenwechsel erhält ungespeicherte Bearbeitungen");
  ui.configure({...value, records: statusRecords.map(record => ({...record, status: "Sonderfall"}))}, map, layers); ui.renderCase();
  check(elements.special.disabled && !elements.save.disabled, "Ein vollständig als Sonderfall markiertes Paket kann gemeinsam abgeschlossen werden");
  ui.configure({...value, records: [{...value.records[0], status: "Abgeschlossen"}]}, map, layers); ui.renderCase();
  check(elements.save.disabled && !elements.special.disabled, "Abgeschlossenen Fall als Sonderfall umtaggen können");
  ui.configure(value, map, layers, [], "special"); ui.showEmptyQueue();
  check(elements["case-title"].textContent.includes("Sonderfälle") && elements["queue-position"].textContent === "0 Pakete", "Leere Sonderfallwarteliste eindeutig benennen");
  check(sources["src/egid_match/zuordnung/templates/zuordnung.html"].includes('id="special" class="danger"'), "Sonderfall-Knopf erhält die rote Darstellung");
  const packageQueue = [
    {gvbsid: "SYNTHETIC-1", package_id: "SYNTHETIC-1", package_index: 0},
    {gvbsid: "SYNTHETIC-3", package_id: "SYNTHETIC-3", package_index: 2},
    {gvbsid: "SYNTHETIC-2", package_id: "SYNTHETIC-1", package_index: 0},
  ];
  for (const selected of ["SYNTHETIC-1", "SYNTHETIC-2"]) {
    ui.configure({...value, selected, package_id: "SYNTHETIC-1", package_index: 0}, map, layers, packageQueue);
    ui.renderCase();
    const navigation = ui.packageNavigation();
    check(navigation.next === "SYNTHETIC-3" && navigation.previous === null, "Weiter überspringt alle Mitglieder des aktuellen Pakets, auch bei verstreuten Warteschlangeneinträgen");
    check(elements.previous.disabled && !elements.next.disabled, "Am ersten Paket nur Weiter aktivieren");
    check(elements["queue-position"].textContent === "Paket 1 / 2", "Die Paketposition statt einer einzelnen GVBSID-Position anzeigen");
  }
  ui.configure({...value, selected: "SYNTHETIC-3", package_id: "SYNTHETIC-3", package_index: 2}, map, layers, packageQueue);
  ui.renderCase();
  check(ui.packageNavigation().previous === "SYNTHETIC-1" && ui.packageNavigation().next === null, "Zurück springt zum ersten offenen Fall des vorherigen Pakets");
  check(!elements.previous.disabled && elements.next.disabled, "Am letzten Paket nur Zurück aktivieren");
  ui.configure({...value, package_id: "egrid:SYNTHETIC-A", package_index: 0}, map, layers, [
    {gvbsid: "SYNTHETIC-1", package_id: "egrid:SYNTHETIC-A", package_index: 0},
    {gvbsid: "SYNTHETIC-1", package_id: "egrid:SYNTHETIC-B", package_index: 1},
  ]);
  check(ui.packageNavigation().next === "SYNTHETIC-1" && ui.packageNavigation().nextPackage === "egrid:SYNTHETIC-B", "Auch bei derselben GVBSID die EGRID-Pakete getrennt navigieren");
  ui.configure({...value, selected: "SYNTHETIC-CLOSED", package_id: "SYNTHETIC-CLOSED", package_index: 1}, map, layers, packageQueue);
  check(ui.packageNavigation().previous === "SYNTHETIC-1" && ui.packageNavigation().next === "SYNTHETIC-3", "Ein über Suche geöffnetes abgeschlossenes Paket behält passende Nachbarpakete");
  ui.configure(value, map, layers, []); ui.renderCase();
  check(elements.previous.disabled && elements.next.disabled, "Ohne offene Pakete beide Richtungen sperren");
  ui.configure({...value, records: Array.from({length: 4}, (_, index) => ({...value.records[0], gvbsid: `SYNTHETIC-${index + 1}`})),
    egids: ["101", "102", "103"]}, map, layers); ui.renderCase();
  check(elements["case-counts"].textContent === "(4 GVBSID/3 EGID)", "Anzahlen beim Paketwechsel aktualisieren");
  check(!elements["case-category"].hidden && elements.matrix.children[0].children[1].children.every(row =>
    !row.children[0].children.some(child => child.className === "row-category-label")), "Auch bei mehreren Gebäuden eine gemeinsame Kategorie nur einmal oben anzeigen");
  ui.configure(value, map, layers); ui.renderCase();
  ui.applyState({database: "synthetic", active: false, progress: {total: 1, completed: 0, impossible: 0, remaining: 1}});
  check(elements["case-category"].hidden && !elements["left-pane"].classList.contains("has-category"), "Beim Datenbankwechsel die Kategoriefarbe und Beschriftung zurücksetzen");
  check(elements["case-counts"].hidden && elements["case-counts"].textContent === "", "Alte Paketanzahlen beim Datenbankwechsel entfernen");
  check(apiCalls === 0, "Der synthetische Test ruft keinen Dienst auf");
  return assertions;
}

if (typeof require === "function") {
  const fs = require("node:fs"), path = require("node:path");
  const sources = Object.fromEntries(["src/egid_match/zuordnung/static/egid_punkte.js", "src/egid_match/zuordnung/static/zuordnung.js", "src/egid_match/zuordnung/templates/zuordnung.html"].map(name => [name, fs.readFileSync(path.join(__dirname, "..", name), "utf8")]));
  runReviewUiTest(sources);
}
