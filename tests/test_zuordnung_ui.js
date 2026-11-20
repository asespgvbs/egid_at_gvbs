"use strict";

// Nur Quellcode und synthetische DOM-/Leaflet-Objekte, kein Browser oder Dienst.
async function runReviewUiTest(sources) {
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
  let syntheticApi = null;
  const points = new Function("document", sources["src/egid_match/zuordnung/static/egid_punkte.js"] + "\nreturn globalThis.ReviewEgidPoints;")(document);
  const source = sources["src/egid_match/zuordnung/static/zuordnung.js"].replace(/\r\n/g, "\n");
  const startup = source.lastIndexOf('\naction(async () => {\n  const initial = await api("/api/state");');
  check(startup > 0, "Automatischen Anwendungsstart für den isolierten Test abtrennen");
  const ui = new Function("document", "window", "fetch", "ReviewEgidPoints", "L", source.slice(0, startup) + "\nreturn {renderCase,renderGeo,selectEgid,applyState,packageNavigation,decisionPayload,changed,switchQueueView,switchQueueRatio,queueRequestPath,showEmptyQueue,refreshQueue,loadGeo,configure(value,view,layers,items,filter='open',ratio='all'){current=value;selectedEgid=null;dirty.clear();queueView=filter;queueRatio=ratio;document.getElementById('queue-view').value=filter;document.getElementById('queue-ratio').value=ratio;state={database:'synthetic',active:true,progress:{total:1}};queue=items||[{gvbsid:value.selected}];map=view;mapLayers=layers;}};")(document, window, (...args) => {if (syntheticApi) return syntheticApi(...args); apiCalls++; throw new Error("Externe Zugriffe verboten");}, points, L);
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
  check(ui.queueRequestPath() === "/api/queue?view=open&ratio=all", "Standardauswahl kombiniert offene Warteliste mit allen Verhältnissen");
  check(!elements["queue-ratio"].disabled, "Verhältnisfilter bei aktiver Bearbeitung freischalten");
  const markup = sources["src/egid_match/zuordnung/templates/zuordnung.html"];
  check(markup.indexOf('id="queue-ratio-bar"') < markup.indexOf('id="queue-filter-bar"'), "Verhältnisfilter oberhalb der Warteliste anzeigen");
  check(markup.includes('for="queue-ratio">GVBSID:EGID - Verhältnis</label>') &&
    markup.includes('<option value="all">Alle Verhältnisse</option><option value="equal">Nur 1:1</option><option value="different">ungleich 1:1</option>'), "Gewünschte Beschriftung und alle drei Auswahltexte anzeigen");
  const table = elements.matrix.children[0], header = table.children[0].children[0], identity = table.children[1].children[0].children[0];
  check(elements["case-title"].textContent === "EGRID CH-SYNTHETIC-1", "Das EGRID-Paket in der Fallüberschrift kennzeichnen");
  check(elements["case-counts"].textContent === "(1 GVBSID/2 EGID)" && !elements["case-counts"].hidden, "Paketanzahlen direkt unter der EGRID anzeigen");
  check(elements["case-counts"].classList.contains("is-unbalanced"), "Ungleiche GVBSID- und EGID-Anzahlen rot kennzeichnen");
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
  check(elements["parcel-panel"].style.getPropertyValue("--category-color") === "#FFF2CC", "Paketkopf rechts verwendet dieselbe gemeinsame Kategoriefarbe");
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
  check(!elements["parcel-panel"].classList.contains("has-category"), "Bei gemischten Kategorien auch den rechten Paketkopf neutral darstellen");
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
  elements["queue-ratio"].value = "equal";
  await ui.switchQueueRatio("equal");
  check(elements["queue-ratio"].value === "all" && ui.queueRequestPath() === "/api/queue?view=open&ratio=all", "Abgebrochener Verhältniswechsel erhält beide bisherigen Filter");
  check(ui.decisionPayload("Abgeschlossen").decisions.length === 3 && !elements.dirty.hidden, "Abgebrochener Verhältniswechsel erhält ungespeicherte Paketbearbeitung");
  ui.configure({...value, records: statusRecords.map(record => ({...record, status: "Sonderfall"}))}, map, layers); ui.renderCase();
  check(elements.special.disabled && !elements.save.disabled, "Ein vollständig als Sonderfall markiertes Paket kann gemeinsam abgeschlossen werden");
  ui.configure({...value, records: [{...value.records[0], status: "Abgeschlossen"}]}, map, layers); ui.renderCase();
  check(elements.save.disabled && !elements.special.disabled, "Abgeschlossenen Fall als Sonderfall umtaggen können");
  ui.configure(value, map, layers, [], "special", "different"); ui.showEmptyQueue();
  check(elements["case-title"].textContent.includes("Sonderfälle") && elements["queue-position"].textContent === "0 Pakete", "Leere Sonderfallwarteliste eindeutig benennen");
  check(elements["empty-note"].textContent.includes("ungleich 1:1"), "Bei leerer Auswahl auch den aktiven Verhältnisfilter erklären");
  check(ui.queueRequestPath() === "/api/queue?view=special&ratio=different", "Verhältnisfilter mit der gewählten Warteliste kombinieren");
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
  ui.configure({...value, selected: "SYNTHETIC-3", package_id: "SYNTHETIC-3", package_index: 2}, map, layers,
    [packageQueue[1]], "open", "equal"); ui.renderCase();
  check(elements.previous.disabled && elements.next.disabled && elements["queue-position"].textContent === "Paket 1 / 1", "Navigation berücksichtigt ausschliesslich die gefilterten Pakete");
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
  check(elements["case-counts"].classList.contains("is-unbalanced"), "Auch Verhältnis 4 zu 3 rot kennzeichnen");
  check(!elements["case-category"].hidden && elements.matrix.children[0].children[1].children.every(row =>
    !row.children[0].children.some(child => child.className === "row-category-label")), "Auch bei mehreren Gebäuden eine gemeinsame Kategorie nur einmal oben anzeigen");
  ui.configure({...value, records: Array.from({length: 4}, (_, index) => ({...value.records[0], gvbsid: `SYNTHETIC-${index + 1}`})),
    egids: ["101", "102", "103", "104"]}, map, layers); ui.renderCase();
  check(!elements["case-counts"].classList.contains("is-unbalanced"), "Beim Wechsel zu Verhältnis 4 zu 4 die rote Kennzeichnung entfernen");
  ui.configure({...value, egids: ["101"]}, map, layers); ui.renderCase();
  check(!elements["case-counts"].classList.contains("is-unbalanced"), "Verhältnis 1 zu 1 normal darstellen");
  ui.configure({...value, egids: []}, map, layers); ui.renderCase();
  check(elements["case-counts"].classList.contains("is-unbalanced"), "Fehlende EGID bei vorhandener GVBSID ebenfalls rot kennzeichnen");

  const unsortedIds = ["1234-10", "1234-4", "10-2", "2-10", "1234-2", "2-2", "1234-1"];
  const unsortedEgids = ["12", "10", "7", "5", "11", "2", "9", "6", "8"];
  const sortedValue = {...value, egids: [...unsortedEgids], assignable_egids: unsortedEgids.filter(egid => egid !== "5"), blocked_egids: ["5"],
    records: unsortedIds.map(gvbsid => ({...value.records[0], gvbsid, assigned: gvbsid === "1234-10" ? ["10"] : [], comment: `Kommentar ${gvbsid}`})),
    geo: {...value.geo, volumes: {"2": 500, "10": 500, "6": 0, "7": null, "8": -1, "9": NaN, "11": Infinity, "12": "10000"},
      buildings: [{egid: "5", gstat: "1004", volume: 1000, addresses: []}]}};
  ui.configure(sortedValue, map, layers); ui.renderCase();
  const sortedTable = elements.matrix.children[0];
  const columnOrder = () => elements.matrix.children[0].children[0].children[0].children.slice(1).map(th => th.children[0].dataset.egid).join();
  check(columnOrder() === "5,2,10,6,7,8,9,11,12", "EGID nach GWR-Volumen absteigend sortieren, bei Gleichstand numerisch und ungültige oder fehlende Werte zuletzt");
  check(sortedTable.children[1].children.map(row => row.children[0].children[0].textContent).join() ===
    "2-2 (GVBSID),2-10 (GVBSID),10-2 (GVBSID),1234-1 (GVBSID),1234-2 (GVBSID),1234-4 (GVBSID),1234-10 (GVBSID)",
    "Kontrollnummer und Gebäudenummer numerisch aufsteigend sortieren, damit 10 hinter 2 steht");
  const lastSortedRow = sortedTable.children[1].children[6];
  check(lastSortedRow.children[3].dataset.egid === "10" && lastSortedRow.children[3].children[0].checked,
    "Sortierte Checkbox bleibt mit der ursprünglichen GVBSID-EGID-Beziehung verbunden");
  check(sortedTable.children[0].children[0].children[1].classList.contains("egid-locked") &&
    sortedTable.children[1].children.every(row => row.children[1].children[0].disabled),
    "Automatisch gesperrte EGID bleiben auch nach der Volumensortierung grau und deaktiviert");
  check(sortedValue.egids.join() === unsortedEgids.join() && sortedValue.records.map(record => record.gvbsid).join() === unsortedIds.join(),
    "Anzeigesortierung verändert weder die Eingabereihenfolge noch die gespeicherten Beziehungen");
  const sortedComment = lastSortedRow.children[0].children.find(child => child.className === "record-editor").children[1].children[0].children[0];
  sortedComment.value = "Synthetischer Kommentar nach Sortierung"; sortedComment.events.input();
  check(ui.decisionPayload("Abgeschlossen").decisions.find(record => record.gvbsid === "1234-10").comment === sortedComment.value,
    "Kommentar nach der Zeilensortierung weiterhin der richtigen GVBSID zuordnen");
  sortedValue.geo.volumes["2"] = 2000;
  ui.renderCase();
  check(columnOrder() === "2,5,10,6,7,8,9,11,12", "Neue Volumenwerte aktualisieren die EGID-Reihenfolge beim Neuzeichnen");
  check(ui.decisionPayload("Abgeschlossen").decisions.find(record => record.gvbsid === "1234-10").assigned.join() === "10" && !elements.dirty.hidden,
    "Eine geänderte Spaltenreihenfolge erhält Zuteilungen und ungespeicherte Bearbeitungen");
  ui.configure({...sortedValue, geo: null}, map, layers); ui.renderCase();
  check(columnOrder() === "2,5,6,7,8,9,10,11,12", "Ohne geladene Volumen EGID vorläufig numerisch sortieren");

  const volumeCase = {...value, selected: "1234-1", egids: ["101", "102", "103", "104"],
    records: [["1234-10", 50], ["1234-4", 150], ["1234-1", 200], ["1234-2", 100]].map(([gvbsid, volume]) =>
      ({...value.records[0], gvbsid, raw: {...value.records[0].raw, Kubatur: volume}, assigned: ["101"], comment: "Synthetischer Volumenhinweis"}))};
  const beforeVolumeWarning = JSON.stringify(volumeCase.records);
  const volumeItems = () => elements.matrix.children[0].children[1].children.map(row => row.children[0].children[2].children[2]);
  const volumeWarnings = () => volumeItems().map(item => item.classList.contains("volume-order-warning"));
  ui.configure(volumeCase, map, layers, undefined, "open", "equal"); ui.renderCase();
  check(volumeWarnings().join() === "false,false,true,false", "Die Kubatur markieren, die gegenüber dem Vorgänger ansteigt");
  check(elements.matrix.children[0].children[1].children.map(row => row.children[0].children[0].textContent).join() ===
    "1234-1 (GVBSID),1234-2 (GVBSID),1234-4 (GVBSID),1234-10 (GVBSID)", "Volumenwarnung verändert die numerisch aufsteigende GVBSID-Reihenfolge nicht");
  check(volumeItems()[2].textContent === "Gebäudevolumen: 150 m³" && volumeItems()[2].title.includes("100 m³"),
    "Warnung an der GVBS-Kubatur anzeigen und den Vergleichswert im Hinweis nennen");
  check(!elements.matrix.children[0].children[1].children[2].children[0].classList.contains("volume-order-warning"),
    "Nur die Volumenangabe und nicht die gesamte GVBSID rot markieren");
  check(JSON.stringify(volumeCase.records) === beforeVolumeWarning && elements.dirty.hidden,
    "Volumenprüfung verändert weder Zuteilungen noch Kommentare und erzeugt keine ungespeicherten Änderungen");
  for (const ratio of ["all", "different"]) {
    ui.configure(volumeCase, map, layers, undefined, "open", ratio); ui.renderCase();
    check(volumeWarnings().join() === "false,false,true,false", "Volumenwarnung auch bei allen Verhältnissen und ungleich 1:1 anzeigen");
  }
  function checkVolumeSequence(volumes, expected, message) {
    const records = volumes.map((volume, index) => ({...value.records[0], gvbsid: `1000-${index + 1}`,
      raw: {...value.records[0].raw, Kubatur: volume}})).reverse();
    ui.configure({...value, records, egids: volumes.map((_, index) => String(101 + index))}, map, layers, undefined, "open", "equal");
    ui.renderCase();
    check(volumeWarnings().join() === expected.join(), message);
  }
  checkVolumeSequence([300, 200, 100], [false, false, false], "Bereits absteigende GVBS-Kubaturen nicht markieren");
  checkVolumeSequence([300, 300, 100], [false, false, false], "Gleiche aufeinanderfolgende Kubaturen sind zulässig");
  checkVolumeSequence([0, 1, 1, 2], [false, true, false, true], "Null als gültiges Volumen behandeln und jeden lokalen Anstieg markieren");
  checkVolumeSequence(["1'000,5", "1\u202f000,5", "1’000,6", "999,9"], [false, false, true, false],
    "Dezimalkomma, geschützte Leerzeichen und Schweizer Tausendertrennzeichen numerisch vergleichen");
  checkVolumeSequence(["100", "20", "3", "10"], [false, false, false, true], "Kubaturen als Zahlen vergleichen, damit 10 grösser als 3 ist");
  checkVolumeSequence([100, null, "", false, "synthetisch ungültig", -1, NaN, Infinity, 150, 0],
    [false, false, false, false, false, false, false, false, true, false],
    "Fehlende und ungültige Kubaturen überspringen und mit der vorhergehenden gültigen Kubatur vergleichen");
  checkVolumeSequence([undefined], [false], "Eine einzelne GVBSID ohne Kubatur hat keinen Sortierverstoss");

  const dynamicValue = JSON.parse(JSON.stringify({...value, package_id: "egrid:CH-SYNTHETIC-1", package_index: 0,
    records: [value.records[0], {...value.records[0], gvbsid: "SYNTHETIC-2"}]}));
  const refreshed = JSON.parse(JSON.stringify({...dynamicValue, egids: ["101", "102", "999"]}));
  ui.configure(dynamicValue, map, layers, [{gvbsid: "SYNTHETIC-1", package_id: dynamicValue.package_id, package_index: 0}], "open", "equal");
  dynamicValue.records[0].comment = "Synthetische ungespeicherte Bearbeitung";
  ui.changed(dynamicValue.records[0]);
  const requests = [];
  syntheticApi = async path => {
    requests.push(path);
    const response = path === "/api/geo" ? refreshed.geo : path.startsWith("/api/case?") ? refreshed :
      path === "/api/queue?view=open&ratio=equal" ? {records: []} : null;
    if (!response) throw new Error("Unerwartete synthetische Anfrage");
    return {ok: true, json: async () => response};
  };
  await ui.loadGeo();
  check(requests.length === 3 && requests[2] === "/api/queue?view=open&ratio=equal", "Nachgeladenen Geodaten folgt eine Aktualisierung der gefilterten Liste");
  check(elements["case-title"].textContent === "EGRID CH-SYNTHETIC-1" && !elements["case-content"].hidden,
    "Nicht mehr passendes geöffnetes Paket bleibt nach dem Nachladen sichtbar");
  check(elements["queue-position"].textContent === "Ausserhalb der Auswahl", "Entferntes Paket als ausserhalb der Auswahl kennzeichnen");
  check(elements["case-counts"].textContent === "(2 GVBSID/3 EGID)" && elements.previous.disabled && elements.next.disabled,
    "Nach dem Nachladen neue Matrixanzahlen und gefilterte Navigation verwenden");
  check(ui.decisionPayload("Abgeschlossen").decisions[0].comment === "Synthetische ungespeicherte Bearbeitung" && !elements.dirty.hidden,
    "Nachladen und Listenaktualisierung erhalten ungespeicherte Kommentare");
  check(elements.queue.children.length === 1 && elements.queue.children[0].textContent.includes("Keine Fälle"),
    "Paketauswahl enthält keine vom Verhältnisfilter ausgeschlossenen Pakete");

  ui.configure(value, map, layers, [], "special", "different");
  syntheticApi = async path => {
    requests.push(path);
    if (path !== "/api/queue?view=special&ratio=equal") throw new Error("Unerwartete synthetische Filteranfrage");
    return {ok: true, json: async () => ({records: []})};
  };
  await ui.switchQueueRatio("equal");
  check(ui.queueRequestPath() === "/api/queue?view=special&ratio=equal" && elements["queue-view"].value === "special",
    "Erfolgreicher Verhältniswechsel behält den Wartelistenstatus");
  check(elements["empty-note"].textContent.includes("Nur 1:1") && elements["case-content"].hidden,
    "Erfolgreicher Filterwechsel zeigt die zugehörige leere Auswahl");
  syntheticApi = null;

  ui.configure(value, map, layers); ui.renderCase();
  ui.applyState({database: "synthetic", active: false, progress: {total: 1, completed: 0, impossible: 0, remaining: 1}});
  check(elements["case-category"].hidden && !elements["left-pane"].classList.contains("has-category"), "Beim Datenbankwechsel die Kategoriefarbe und Beschriftung zurücksetzen");
  check(elements["case-counts"].hidden && elements["case-counts"].textContent === "", "Alte Paketanzahlen beim Datenbankwechsel entfernen");
  check(!elements["case-counts"].classList.contains("is-unbalanced"), "Beim Datenbankwechsel die rote Kennzeichnung entfernen");
  check(elements["queue-ratio"].value === "all" && elements["queue-view"].value === "open" && elements["queue-ratio"].disabled,
    "Beim Datenbankwechsel beide Filter zurücksetzen und sperren");
  check(apiCalls === 0, "Der synthetische Test ruft keinen Dienst auf");
  return assertions;
}

if (typeof require === "function") {
  const fs = require("node:fs"), path = require("node:path");
  const sources = Object.fromEntries(["src/egid_match/zuordnung/static/egid_punkte.js", "src/egid_match/zuordnung/static/zuordnung.js", "src/egid_match/zuordnung/templates/zuordnung.html"].map(name => [name, fs.readFileSync(path.join(__dirname, "..", name), "utf8")]));
  runReviewUiTest(sources).catch(error => {process.stderr.write(error.message + "\n"); process.exitCode = 1;});
}
