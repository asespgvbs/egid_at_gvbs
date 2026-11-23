"use strict";

// Nur Quellcode und synthetische DOM-/Leaflet-Objekte, kein Browser oder Dienst.
async function runReviewUiTest(sources) {
  let assertions = 0;
  function check(value, message) {assertions++; if (!value) throw new Error(message);}
  class Element {
    constructor(tag = "div") {
      this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attributes = {}; this.events = {}; this._text = "";
      this.open = false; this.showCount = 0;
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
    showModal() {if (this.open) throw new Error("Synthetischer Dialog ist bereits geöffnet"); this.open = true; this.showCount++;}
    close() {this.open = false;}
    contains(target) {return this === target || this.children.some(child => child.contains(target));}
    querySelectorAll(selector) {
      const matches = child => selector === "[data-egid]" ? child.dataset.egid !== undefined : ["INPUT", "SELECT", "TEXTAREA"].includes(child.tagName) || child.dataset.removeBlocked !== undefined;
      return this.children.flatMap(child => [...(matches(child) ? [child] : []), ...child.querySelectorAll(selector)]);
    }
  }
  const elements = Object.fromEntries([...sources["src/egid_match/zuordnung/templates/zuordnung.html"].matchAll(/\bid="([\w-]+)"/g)].map(match => [match[1], new Element()]));
  elements["review-config"].textContent = JSON.stringify({token: "synthetic-token", category_colors: {
    review_address_suffix: "FFF2CC", address_suffix_pair_lt4: "F4B183",
    review_suffix_single_gvbsid_multiple_egid: "E6C200", address_suffix_pair_ge4: "C4A484",
    synthetic_invalid: "url(https://synthetic.invalid/colour)",
  }, category_aliases: {review_suffix_single_building: "review_suffix_single_gvbsid_multiple_egid"}});
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
  const ui = new Function("document", "window", "fetch", "ReviewEgidPoints", "L", source.slice(0, startup) + "\nreturn {renderCase,renderGeo,selectEgid,applyState,packageNavigation,decisionPayload,changed,switchQueueView,switchQueueRatio,queueRequestPath,showEmptyQueue,refreshQueue,loadGeo,applyGeoCase,configure(value,view,layers,items,filter='open',ratio='all'){packageNotice.reset();current=value;selectedEgid=null;sizeGuidesShown=true;dirty.clear();queueView=filter;queueRatio=ratio;document.getElementById('queue-view').value=filter;document.getElementById('queue-ratio').value=ratio;state={database:'synthetic',active:true,progress:{total:200},unassigned_count:123,assignment_counts:{all:{total:200,unassigned:123},equal:{total:40,unassigned:23},different:{total:160,unassigned:100}}};queue=items||[{gvbsid:value.selected}];map=view;mapLayers=layers;}};")(document, window, (...args) => {if (syntheticApi) return syntheticApi(...args); apiCalls++; throw new Error("Externe Zugriffe verboten");}, points, L);
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
  ui.applyState({database: "synthetic", active: true, progress: {total: 1, completed: 0, remaining: 1}});
  elements["top-panel"].events.pointerenter();
  check(document.body.classList.contains("top-panel-open") && !elements["top-panel"].inert,
    "Obere Bedienleiste beim Hineinfahren einblenden");
  elements["top-panel"].events.pointerleave();
  check(!document.body.classList.contains("top-panel-open") && elements["top-panel"].inert &&
    elements["top-panel"].attributes["aria-hidden"] === "true",
    "Obere Bedienleiste beim Verlassen sofort ohne Ablauf eines Timers schliessen");
  elements["top-panel-trigger"].events.pointerenter();
  check(document.body.classList.contains("top-panel-open"), "Geschlossene Bedienleiste am oberen Rand wieder einblenden");
  ui.applyState({database: "synthetic", active: false, progress: {total: 1, completed: 0, remaining: 1}});
  elements["top-panel"].events.pointerleave();
  check(!elements["top-panel"].inert && elements["top-panel"].attributes["aria-hidden"] === "false",
    "Während der Einrichtung die benötigte Bedienleiste beim Verlassen sichtbar lassen");
  ui.configure(value, map, layers); ui.renderCase();
  check(ui.queueRequestPath() === "/api/queue?view=open&ratio=all", "Standardauswahl kombiniert offene Warteliste mit allen Verhältnissen");
  check(elements["queue-position"].textContent === "Noch 123 von 200 GVBSIDs ohne EGID · Alle Verhältnisse" && elements["queue-scope"].hidden,
    "Gesamtzahl ohne gespeicherte EGID statt Paketnummer anzeigen, auch wenn nur ein Paket geöffnet ist");
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
  for (const [category, colour] of [["address_suffix_pair_lt4", "#F4B183"], ["review_suffix_single_gvbsid_multiple_egid", "#E6C200"], ["address_suffix_pair_ge4", "#C4A484"]]) {
    ui.configure({...value, records: [{...value.records[0], raw: {"Matching-Kategorie": category}}]}, map, layers);
    ui.renderCase();
    check(elements["left-pane"].style.getPropertyValue("--category-color") === colour, "Fallwechsel übernimmt die neue Kategoriefarbe");
    check(elements["case-category"].title === category, "Importierte Kategorie im Kategorienhinweis erhalten");
  }
  const legacyCategoryRecords = ["review_suffix_single_building", "review_suffix_single_gvbsid_multiple_egid"].map(
    category => ({...value.records[0], raw: {"Matching-Kategorie": category}}));
  ui.configure({...value, records: legacyCategoryRecords}, map, layers); ui.renderCase();
  check(elements["case-category"].title === "review_suffix_single_gvbsid_multiple_egid" &&
    elements["case-category"].textContent === "Eine GVBSID mit mehreren EGIDs · Manuell prüfen" &&
    elements["left-pane"].style.getPropertyValue("--category-color") === "#E6C200",
    "Alte und neue Kategorie erhalten dieselbe Beschriftung und Farbe");
  check(legacyCategoryRecords[0].raw["Matching-Kategorie"] === "review_suffix_single_building",
    "Die Anzeige erhält die importierte Originalkategorie");
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
  check(elements["case-title"].textContent.includes("Sonderfälle") && elements["queue-position"].textContent === "Noch 100 von 160 GVBSIDs ohne EGID · ungleich 1:1", "Auch bei leerer Sonderfallwarteliste die Anzahl der gewählten Verhältnisgruppe anzeigen");
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
    check(elements["queue-position"].textContent === "Noch 123 von 200 GVBSIDs ohne EGID · Alle Verhältnisse", "Die globale Anzahl unzugeteilter GVBSIDs statt der Paketposition anzeigen");
  }
  ui.configure({...value, selected: "SYNTHETIC-3", package_id: "SYNTHETIC-3", package_index: 2}, map, layers, packageQueue);
  ui.renderCase();
  check(ui.packageNavigation().previous === "SYNTHETIC-1" && ui.packageNavigation().next === null, "Zurück springt zum ersten offenen Fall des vorherigen Pakets");
  check(!elements.previous.disabled && elements.next.disabled, "Am letzten Paket nur Zurück aktivieren");
  ui.configure({...value, selected: "SYNTHETIC-3", package_id: "SYNTHETIC-3", package_index: 2}, map, layers,
    [packageQueue[1]], "open", "equal"); ui.renderCase();
  check(elements.previous.disabled && elements.next.disabled && elements["queue-position"].textContent === "Noch 23 von 40 GVBSIDs ohne EGID · Nur 1:1", "Navigation und Zähler berücksichtigen den Verhältnisfilter; der Zähler bleibt unabhängig von der Warteliste");
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
  check(volumeWarnings().every(Boolean), "Bei falscher Reihenfolge alle GVBS-Kubaturen des Pakets markieren");
  check(elements.matrix.children[0].children[1].children.map(row => row.children[0].children[0].textContent).join() ===
    "1234-1 (GVBSID),1234-2 (GVBSID),1234-4 (GVBSID),1234-10 (GVBSID)", "Volumenwarnung verändert die numerisch aufsteigende GVBSID-Reihenfolge nicht");
  check(volumeItems()[2].textContent === "Gebäudevolumen: 150 m³" && volumeItems().every(item => item.title.includes("GVBSID-Nummerierung")),
    "Alle Kubaturen mit dem Hinweis auf die falsche Reihenfolge kennzeichnen");
  check(!elements.matrix.children[0].children[1].children[2].children[0].classList.contains("volume-order-warning"),
    "Nur die Volumenangabe und nicht die gesamte GVBSID rot markieren");
  check(JSON.stringify(volumeCase.records) === beforeVolumeWarning && elements.dirty.hidden,
    "Volumenprüfung verändert weder Zuteilungen noch Kommentare und erzeugt keine ungespeicherten Änderungen");
  for (const ratio of ["all", "different"]) {
    ui.configure(volumeCase, map, layers, undefined, "open", ratio); ui.renderCase();
    check(volumeWarnings().every(Boolean), "Alle Kubaturen auch bei allen Verhältnissen und ungleich 1:1 markieren");
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
  checkVolumeSequence([0, 1, 1, 2], [true, true, true, true], "Null als gültiges Volumen behandeln und bei einem Anstieg das ganze Paket markieren");
  checkVolumeSequence(["1'000,5", "1\u202f000,5", "1’000,6", "999,9"], [true, true, true, true],
    "Dezimalkomma, geschützte Leerzeichen und Schweizer Tausendertrennzeichen numerisch vergleichen");
  checkVolumeSequence(["100", "20", "3", "10"], [true, true, true, true], "Kubaturen als Zahlen vergleichen, damit 10 grösser als 3 ist");
  checkVolumeSequence([100, null, "", false, "synthetisch ungültig", -1, NaN, Infinity, 150, 0],
    [true, true, true, true, true, true, true, true, true, true],
    "Fehlende und ungültige Kubaturen überspringen und mit der vorhergehenden gültigen Kubatur vergleichen");
  checkVolumeSequence([undefined], [false], "Eine einzelne GVBSID ohne Kubatur hat keinen Sortierverstoss");

  const notice = elements["package-notice"], noticeList = elements["package-notice-list"], acknowledge = elements["package-notice-close"];
  const warningIds = () => noticeList.children.map(item => item.dataset.warning).join();
  ui.configure(volumeCase, map, layers); ui.renderCase();
  check(notice.open && warningIds() === "volume" && noticeList.textContent ===
    "INFO: Die GVBSID-Nummerierung stimmt nicht mit der Sortierung der Kubatur überein.",
    "Falsche Kubaturreihenfolge öffnet ein modales Fenster mit dem gewünschten Text");
  let cancelPrevented = false;
  notice.events.cancel({preventDefault() {cancelPrevented = true;}});
  check(cancelPrevented && notice.open, "Escape kann das zu bestätigende Infofenster nicht schliessen");
  const firstNoticeCount = notice.showCount;
  acknowledge.events.click(); ui.renderCase();
  check(!notice.open && notice.showCount === firstNoticeCount && volumeWarnings().every(Boolean),
    "Verstanden schliesst das Fenster; Neuzeichnen öffnet es nicht erneut und Kubaturen bleiben rot");
  ui.configure(volumeCase, map, layers); ui.renderCase();
  check(notice.open && notice.showCount === firstNoticeCount + 1, "Beim erneuten Öffnen eines Pakets erneut auf die Kubaturreihenfolge hinweisen");

  const noticeCase = {...value, selected: "1000-0", package_id: "egrid:CH-SYNTHETIC-1",
    records: [200, 100].map((volume, index) => ({...value.records[0], gvbsid: `1000-${index}`, raw: {...value.records[0].raw, Kubatur: volume}})),
    geo: {...value.geo, volumes: {"101": 200, "102": 100}, buildings: [
      {egid: "101", gstat: "1004", egrid: "CH-SYNTHETIC-1", addresses: [["Singstrasse", "2", "0000"]]},
      {egid: "102", gstat: "1004", egrid: "CH-SYNTHETIC-1", addresses: [["Singstrasse", "2.1", "0000"]]},
    ]}};
  ui.configure(noticeCase, map, layers); ui.renderCase();
  check(!notice.open && volumeWarnings().every(marked => !marked), "Richtige Kubaturreihenfolge, eine Kontrollnummer und reine Suffixadressen bleiben ohne Hinweis");
  const allWarnings = {...noticeCase,
    records: noticeCase.records.map((record, index) => ({...record, gvbsid: `${1000 + index}-0`,
      raw: {...record.raw, Kontrollnummer: 1000 + index, Kubatur: index ? 200 : 100}})),
    geo: {...noticeCase.geo, buildings: noticeCase.geo.buildings.map((building, index) =>
      ({...building, addresses: [["Singstrasse", index ? "4" : "2", "0000"]]}))}};
  const beforeNotices = JSON.stringify(allWarnings.records);
  ui.configure(allWarnings, map, layers); ui.renderCase();
  check(notice.open && warningIds() === "volume,controls,addresses", "Alle drei Hinweise gemeinsam in einem einzigen Infofenster anzeigen");
  check(noticeList.children[1].textContent === "Info: Mehrere Kontrollnummern auf der Parzelle." &&
    noticeList.children[1].className === "package-info",
    "Mehrere Kontrollnummern als neutralen Infohinweis ohne rote Warnklasse melden");
  check(volumeWarnings().every(Boolean) && JSON.stringify(allWarnings.records) === beforeNotices && elements.dirty.hidden,
    "Gesamtes Paket rot markieren, ohne Zuteilungen, Kommentare oder Status zu verändern");
  const combinedCount = notice.showCount;
  ui.renderCase();
  check(notice.open && notice.showCount === combinedCount && noticeList.children.length === 3,
    "Ein bereits offenes Fenster aktualisieren, ohne zusätzliche Dialoge zu öffnen");
  acknowledge.events.click(); ui.renderCase();
  check(!notice.open && notice.showCount === combinedCount, "Eine Bestätigung gilt für sämtliche gleichzeitig angezeigten Hinweise");

  const controlCases = [
    {records: noticeCase.records.map((record, index) => ({...record, gvbsid: `${1000 + index}-0`})), expected: true},
    {records: noticeCase.records.map((record, index) => ({...record, raw: {...record.raw, Kontrollnummer: index ? "2" : "0002"}})), expected: false},
    {records: noticeCase.records.map((record, index) => ({...record, raw: {...record.raw, Kontrollnummer: index ? 2 : 1}})), expected: true},
    {records: noticeCase.records.map(record => ({...record, raw: {...record.raw, Kontrollnummer: 0}})), expected: false},
  ];
  for (const item of controlCases) {
    ui.configure({...noticeCase, records: item.records}, map, layers); ui.renderCase();
    check(notice.open === item.expected && (!item.expected || warningIds() === "controls"),
      "Kontrollnummern aus Originalspalte oder GVBSID korrekt unterscheiden; führende Nullen und Gebäudenummern nicht mehrfach zählen");
    check(!item.expected || noticeList.children[0].className === "package-info",
      "Auch ein einzelner Kontrollnummernhinweis bleibt neutral");
  }
  const addressCases = [
    [["Singstrasse", "2", "0000"], ["Singstrasse", "4", "0000"], true],
    [["Peterstrasse", "23", "0000"], ["Rolfstrasse", "14", "0000"], true],
    [["Singstrasse", "2", "0000"], ["Singstrasse", "2.1", "0000"], false],
    [["Singstrasse", "2.1", "0000"], ["Singstrasse", "2.2", "0000"], false],
    [[" SINGSTRASSE ", "02a", "0000"], ["Singstrasse", "2b", "0000"], true],
    [["Singstrasse", "30", "0000"], ["Singstrasse", "30A", "0000"], true],
    [["Singstrasse", "30a", "0000"], ["Singstrasse", "30B", "0000"], true],
    [["Singstrasse", "30A", "0000"], ["Singstrasse", "30a", "0000"], false],
    [["Singstrasse", "30A", "0000"], ["Singstrasse", "30A.1", "0000"], false],
    [["Singstrasse", "30A.1", "0000"], ["Singstrasse", "30B.1", "0000"], true],
    [["Singstrasse", "30.3", "0000"], ["Singstrasse", "30.4", "0000"], false],
    [["Singstrasse", "2", "0000"], ["Singstrasse", "20", "0000"], true],
    [["Singstrasse", "2", "0000"], ["Singstrasse", "2/4", "0000"], true],
    [["Singstrasse", "2", "0000"], ["Singstrasse", "2a", ""], true],
    [["Singstrasse", "2", "0000"], ["Singstrasse", "2", "1111"], true],
    [["Singstrasse", "2", "0000"], ["", "", ""], false],
  ];
  for (const [first, second, expected] of addressCases) {
    const geo = {...noticeCase.geo, buildings: noticeCase.geo.buildings.map((building, index) => ({...building, addresses: [index ? second : first]}))};
    ui.configure({...noticeCase, geo}, map, layers); ui.renderCase();
    check(notice.open === expected && (!expected || warningIds() === "addresses"),
      "Unterschiedliche Hauptadressen melden, reine Suffixvarianten und unvollständige Adressen ausnehmen");
  }
  const shownAddress = parts => parts[0] && parts[1] ? `${parts[0]} ${parts[1]}${parts[2] ? ", " + parts[2] : ""}` : "";
  for (const [first, second, expected] of addressCases) {
    const records = noticeCase.records.map((record, index) => ({...record, address: shownAddress(index ? second : first)}));
    ui.configure({...noticeCase, records, geo: null}, map, layers); ui.renderCase();
    check(notice.open === expected && (!expected || warningIds() === "gvbs_addresses"),
      "GVBS-Suchadressen auch ohne Geodaten auf unterschiedliche Hauptadressen prüfen und reine Suffixe ausnehmen");
  }
  const rawGvbsCases = [
    [{Strasse: "Singstrasse", Hausnummer: 2, "Hausnummer Zusatz": "a", Postleitzahl: "0000"},
      {Strasse: "Singstrasse", Hausnummer: "2.1", Postleitzahl: "0000"}, true],
    [{Strassennamen: "Singstrasse", "Nr.": 30, "Hausnummer Zusatz": "A", PLZ: "0000"},
      {Strassennamen: "Singstrasse", "Nr.": 30, "Hausnummer Zusatz": "B", PLZ: "0000"}, true],
    [{Strassennamen: "Singstrasse", "Nr.": 2, PLZ: "0000"}, {Strassennamen: "Singstrasse", "Nr.": 4, PLZ: "0000"}, true],
    [{Suchadresse: "Peterstrasse 23,0000"}, {Suchadresse: "Rolfstrasse 14, 0000"}, true],
    [{"GVBS-Adresse": "Singstrasse 2 0000 Basel"}, {"GVBS-Adresse": "Singstrasse 2.1, 0000 Basel"}, false],
    [{}, {Strasse: "Singstrasse", Hausnummer: 2}, false],
    [{Suchadresse: "Synthetisch nicht zerlegbare Adresse"}, {Strasse: "Singstrasse", Hausnummer: 2}, false],
  ];
  for (const [first, second, expected] of rawGvbsCases) {
    const records = noticeCase.records.map((record, index) => ({...record, address: "", raw: {...record.raw, ...(index ? second : first)}}));
    ui.configure({...noticeCase, records}, map, layers); ui.renderCase();
    check(notice.open === expected && (!expected || warningIds() === "gvbs_addresses"),
      "Strukturierte GVBS-Importspalten und Aliasnamen als Rückfall nutzen; unvollständige Angaben nicht als unterschiedliche Adresse werten");
  }
  const differentGvbs = noticeCase.records.map((record, index) => ({...record, address: `Singstrasse ${index ? 4 : 2}, 0000`,
    raw: {...record.raw, Strasse: "Gemeinsame Testgasse", Hausnummer: 1, Postleitzahl: "0000"}}));
  for (const ratio of ["all", "equal", "different"]) {
    ui.configure({...noticeCase, records: differentGvbs}, map, layers, undefined, "open", ratio); ui.renderCase();
    check(notice.open && warningIds() === "gvbs_addresses" && noticeList.textContent ===
      "INFO: Die GVBSIDs auf der Parzelle haben unterschiedliche Hauptadressen.",
      "Angezeigte GVBS-Adressen haben Vorrang vor abweichenden Rohspalten und werden in allen Verhältnisfiltern geprüft");
  }
  ui.configure({...allWarnings, records: allWarnings.records.map((record, index) => ({...record, address: `Singstrasse ${index ? 4 : 2}, 0000`}))}, map, layers);
  ui.renderCase();
  check(notice.open && warningIds() === "volume,controls,addresses,gvbs_addresses" && noticeList.children.length === 4,
    "GVBS-Adresswarnung gemeinsam mit Kubatur-, Kontrollnummern- und EGID-Adresswarnungen im selben Fenster anzeigen");
  acknowledge.events.click(); ui.renderCase();
  check(!notice.open, "Auch die zusätzliche GVBS-Adresswarnung muss nur einmal je geöffnetem Paket bestätigt werden");
  const sameGvbsAddress = {...noticeCase, records: noticeCase.records.map(record => ({...record, address: "Singstrasse 2, 0000"}))};
  ui.configure(sameGvbsAddress, map, layers); ui.renderCase();
  sameGvbsAddress.records[0].comment = "Synthetischer erhaltener Kommentar"; ui.changed(sameGvbsAddress.records[0]);
  ui.applyGeoCase({...sameGvbsAddress, records: sameGvbsAddress.records.map((record, index) => ({...record, address: `Singstrasse ${index ? 4 : 2}, 0000`}))});
  check(notice.open && warningIds() === "gvbs_addresses" &&
    ui.decisionPayload("Abgeschlossen").decisions[0].comment === "Synthetischer erhaltener Kommentar" && !elements.dirty.hidden,
    "Neu festgestellte GVBS-Adressunterschiede anzeigen und dabei ungespeicherte Kommentare erhalten");
  const unrelatedAddresses = allWarnings.geo.buildings;
  for (const geo of [
    {...noticeCase.geo, buildings: unrelatedAddresses, sources: {buildings: {stale: true}}},
    {...noticeCase.geo, buildings: unrelatedAddresses, gwr_address_status: {code: "unreachable"}},
    {...noticeCase.geo, buildings: unrelatedAddresses.map((building, index) => index ? {...building, egrid: "CH-SYNTHETIC-OTHER", egrids: []} : building)},
    {...noticeCase.geo, buildings: unrelatedAddresses.map((building, index) => index ? {...building, egid: "999"} : building)},
    {...noticeCase.geo, buildings: unrelatedAddresses.map((building, index) => index ? {...building, gstat: "1007"} : building)},
    {...noticeCase.geo, buildings: [{...noticeCase.geo.buildings[0], addresses: [["Singstrasse", "2", "0000"], ["Andere Testgasse", "9", "0000"]]}]},
  ]) {
    ui.configure({...noticeCase, geo}, map, layers); ui.renderCase();
    check(!notice.open, "Nur bekannte Adressen mehrerer sichtbarer EGID des aktuellen Pakets aus gültigen Geodaten vergleichen");
  }
  const initialWarning = {...noticeCase, records: noticeCase.records.map((record, index) =>
    ({...record, raw: {...record.raw, Kubatur: index ? 200 : 100}}))};
  ui.configure(initialWarning, map, layers); ui.renderCase(); acknowledge.events.click();
  const acknowledgedCount = notice.showCount;
  initialWarning.records[0].comment = "Synthetischer ungespeicherter Kommentar"; ui.changed(initialWarning.records[0]);
  ui.applyGeoCase({...initialWarning, geo: {...initialWarning.geo, buildings: unrelatedAddresses}});
  check(notice.open && notice.showCount === acknowledgedCount + 1 && warningIds() === "volume,addresses",
    "Ein neuer Adresshinweis nach dem Nachladen öffnet dasselbe Fenster mit allen aktuellen Hinweisen");
  check(ui.decisionPayload("Abgeschlossen").decisions[0].comment === "Synthetischer ungespeicherter Kommentar" && !elements.dirty.hidden,
    "Ein nachgeladener Hinweis erhält ungespeicherte Kommentare");
  acknowledge.events.click(); ui.renderCase();
  check(!notice.open, "Auch der neue Hinweis wird nach Verstanden nicht bei jedem Neuzeichnen wiederholt");
  ui.configure(allWarnings, map, layers); ui.renderCase(); ui.showEmptyQueue();
  check(!notice.open && noticeList.children.length === 0, "Beim Verlassen des Pakets alte Hinweise und das Fenster entfernen");

  const guideValue = {...value, selected: "1000-1", package_id: "egrid:CH-SYNTHETIC-1",
    egids: ["102", "103", "101"], assignable_egids: ["101", "102", "103"],
    records: [["1000-10", 200, []], ["1000-2", 100, ["101"]], ["1000-1", 300, ["103"]]].map(([gvbsid, volume, assigned]) =>
      ({...value.records[0], gvbsid, raw: {...value.records[0].raw, Kubatur: volume}, assigned, comment: "Synthetischer Linienvergleich"})),
    geo: {...value.geo, volumes: {"101": 600, "102": 100, "103": 50}}};
  const guideButton = elements["size-assignment"];
  const guideTable = () => elements.matrix.children[0];
  const guideRows = () => guideTable().children[1].children;
  const guideHeads = () => guideTable().children[0].children[0].children.slice(1);
  const guideEndpoints = () => guideRows().flatMap(row => row.children.slice(1).filter(cell => cell.classList.contains("size-match"))
    .map(cell => `${row.children[0].children[0].textContent}=>${cell.dataset.egid}`)).join();
  const fieldRatio = element => element.children.find(child => child.className === "volume-ratio");
  ui.configure(guideValue, map, layers); ui.renderCase();
  check(!guideButton.hidden && !guideButton.disabled, "Grössenzuordnung bei tatsächlichem 3:3-Paket auch unter Alle Verhältnisse anzeigen");
  check(guideTable().classList.contains("has-size-guides") && guideButton.attributes["aria-pressed"] === "true",
    "Grössenvorschläge und Verhältnisangaben bei gleichem Verhältnis standardmässig ohne Knopfdruck anzeigen");
  const beforeGuidePayload = JSON.stringify(ui.decisionPayload("Abgeschlossen"));
  guideButton.events.click();
  check(!guideTable().classList.contains("has-size-guides") && guideRows().every(row => row.children.every(cell => !fieldRatio(cell))),
    "Erster Knopfdruck blendet die standardmässig aktiven Vorschläge aus");
  guideButton.events.click();
  check(guideTable().classList.contains("has-size-guides") && guideButton.attributes["aria-pressed"] === "true",
    "Knopf aktiviert die Umrandungen mit zugänglichem Zustand");
  check(guideEndpoints() === "1000-1 (GVBSID)=>101,1000-2 (GVBSID)=>103,1000-10 (GVBSID)=>102",
    "Grösste Kubatur zur grössten und zweitgrösste zur zweitgrössten verbinden, ohne die GVBSID-Zeilen umzusortieren");
  check(guideHeads().every(head => !head.classList.contains("size-guide-start")) &&
    guideRows().every(row => row.children.every(cell => !cell.classList.contains("size-guide"))),
    "Keine Linien am Spaltenkopf oder durch andere Matrixfelder zeichnen");
  check(guideHeads().every(head => !fieldRatio(head)) && guideRows().every(row => !fieldRatio(row.children[0])),
    "Verhältnisse direkt im Feld statt wiederholt an beiden Achsen anzeigen");
  check(fieldRatio(guideRows()[0].children[1]).textContent === "m³ GVBSID/EGID 0.5",
    "GVBS-zu-GWR-Verhältnis als einzelnen Quotienten im umrandeten Feld anschreiben");
  check(fieldRatio(guideRows()[2].children[2]).textContent === "m³ GVBSID/EGID 2",
    "Auch grössere GVBS-Kubatur als einzelne Zahl ohne Doppelpunkt anzeigen");
  check(fieldRatio(guideRows()[0].children[1]).title.includes("300 m³/600 m³"), "Beide Originalvolumen im Hinweis zum Verhältnis erhalten");
  check(guideRows().every(row => row.children.slice(1).every(cell => Boolean(fieldRatio(cell)) === cell.classList.contains("size-match"))),
    "Nur umrandete Trefferfelder erhalten eine Verhältnisangabe");
  check(JSON.stringify(ui.decisionPayload("Abgeschlossen")) === beforeGuidePayload && elements.dirty.hidden,
    "Vorschlagsknopf verändert weder Checkboxen, Zuteilungen, Kommentare, Status noch den gespeicherten Bearbeitungsstand");
  check(!guideRows()[0].children[1].children[0].checked && guideRows()[0].children[3].children[0].checked,
    "Bestehende manuelle Zuordnung bleibt auch bei abweichendem Grössenvorschlag unverändert angekreuzt");
  guideValue.records[0].comment = "Synthetische ungespeicherte Änderung"; ui.changed(guideValue.records[0]);
  const beforeGuideRefresh = JSON.stringify(ui.decisionPayload("Abgeschlossen"));
  guideValue.geo.volumes["103"] = 1000;
  ui.renderCase();
  check(guideEndpoints() === "1000-1 (GVBSID)=>103,1000-2 (GVBSID)=>102,1000-10 (GVBSID)=>101",
    "Geänderte Volumen aktualisieren die umrandeten Felder nach Grössenrang");
  check(guideValue.egids.join() === "102,103,101" && guideValue.records.map(record => record.gvbsid).join() === "1000-10,1000-2,1000-1",
    "Die Vorschlagsberechnung sortiert die ursprünglichen ID-Listen nicht um");
  guideButton.events.click();
  check(!guideTable().classList.contains("has-size-guides") && guideEndpoints() === "" &&
    guideRows().every(row => row.children.every(cell => !fieldRatio(cell))),
    "Erneuter Knopfdruck entfernt Umrandungen und Verhältnisangaben aus allen Feldern");
  check(JSON.stringify(ui.decisionPayload("Abgeschlossen")) === beforeGuideRefresh && !elements.dirty.hidden,
    "Auch das Ausblenden erhält sämtliche ungespeicherten Bearbeitungen");
  for (const ratio of ["equal", "different"]) {
    ui.configure(guideValue, map, layers, undefined, "open", ratio); ui.renderCase();
    check(!guideButton.hidden, "Die tatsächlichen Paketanzahlen bestimmen die Knopfsichtbarkeit, auch ausserhalb der Wartelistenauswahl");
  }
  ui.configure({...guideValue, egids: ["101", "102"]}, map, layers); ui.renderCase();
  check(guideButton.hidden, "Bei ungleicher Anzahl GVBSID und EGID keinen Grössenvorschlagsknopf anzeigen");
  const tiedGuides = {...value, selected: "1000-2", egids: ["10", "2"],
    records: ["1000-10", "1000-2"].map(gvbsid => ({...value.records[0], gvbsid, raw: {...value.records[0].raw, Kubatur: 100}})),
    geo: {...value.geo, volumes: {"10": 50, "2": 50}}};
  ui.configure(tiedGuides, map, layers); ui.renderCase();
  check(guideEndpoints() === "1000-2 (GVBSID)=>2,1000-10 (GVBSID)=>10", "Bei gleichen Kubaturen auf beiden Seiten numerisch aufsteigende IDs als stabile Reihenfolge verwenden");
  const nearbyGuides = {...value, selected: "1000-1", egids: ["101", "102"],
    records: [100, 300].map((volume, index) => ({...value.records[0], gvbsid: `1000-${index + 1}`, raw: {...value.records[0].raw, Kubatur: volume}})),
    geo: {...value.geo, volumes: {"101": 90, "102": 310}}};
  ui.configure(nearbyGuides, map, layers); ui.renderCase();
  check(guideEndpoints() === "1000-1 (GVBSID)=>101,1000-2 (GVBSID)=>102", "Bestätigtes Beispiel 100 zu 90 und 300 zu 310 auch ohne exakt gleiche Kubaturen verbinden");
  check(fieldRatio(guideRows()[1].children[1]).textContent === "m³ GVBSID/EGID 0.97", "Volumenverhältnisse auf höchstens zwei Nachkommastellen runden");
  for (const [gvbs, gwr, ratio, red] of [[1680, 1000, "1.68", false], [2400, 1200, "2", false],
    [1200, 2400, "0.5", false], [2500, 1000, "2.5", true], [20001, 10000, "2", true], [19999, 10000, "2", false],
    [0, 10, "0", false], [10, 0, "nicht bestimmbar", false], [0, 0, "nicht bestimmbar", false]]) {
    ui.configure({...value, egids: ["101"], records: [{...value.records[0], raw: {...value.records[0].raw, Kubatur: gvbs}}],
      geo: {...value.geo, volumes: {"101": gwr}}}, map, layers); ui.renderCase();
    const cell = guideRows()[0].children[1], label = fieldRatio(cell);
    check(label.textContent === `m³ GVBSID/EGID ${ratio}`, "Auch einzelne Paare und Nullvolumen mit korrektem GVBS/GWR-Quotienten anzeigen");
    check(label.classList.contains("volume-ratio-high") === red && cell.classList.contains("size-match-high") === red,
      "Text und Umrandung nur bei ungerundetem Verhältnis strikt über 2 rot markieren");
  }
  const changingRatio = {...value, egids: ["101"], records: [{...value.records[0], raw: {...value.records[0].raw, Kubatur: 500}}],
    geo: {...value.geo, volumes: {"101": 100}}};
  ui.configure(changingRatio, map, layers); ui.renderCase();
  check(fieldRatio(guideRows()[0].children[1]).classList.contains("volume-ratio-high"), "Hohes Verhältnis zunächst rot anzeigen");
  changingRatio.geo.volumes["101"] = 500; ui.renderCase();
  check(fieldRatio(guideRows()[0].children[1]).textContent === "m³ GVBSID/EGID 1" &&
    !fieldRatio(guideRows()[0].children[1]).classList.contains("volume-ratio-high") &&
    !guideRows()[0].children[1].classList.contains("size-match-high"),
    "Nach neuen Volumen alte rote Markierungen an Text und Umrandung entfernen");
  const missingVolumeCases = [
    {...guideValue, records: guideValue.records.map((record, index) => index ? record : {...record, raw: {...record.raw, Kubatur: null}})},
    {...guideValue, geo: {...guideValue.geo, volumes: {"101": null, "102": 100, "103": 50}, buildings: []}},
    {...guideValue, egrids: []},
  ];
  for (const incomplete of missingVolumeCases) {
    ui.configure(incomplete, map, layers); ui.renderCase();
    check(!guideButton.hidden && guideButton.disabled && Boolean(guideButton.title), "Fehlende EGRID oder Kubaturen deaktivieren den Knopf mit einer Erklärung");
    guideButton.events.click();
    check(!guideTable().classList.contains("has-size-guides") && elements.dirty.hidden,
      "Auch künstlicher Klick erstellt bei unvollständigen Volumen keine Vorschläge oder Änderungen");
  }
  const awaitingVolume = {...value, package_id: "egrid:CH-SYNTHETIC-1", egids: ["101"],
    geo: {...value.geo, volumes: {}, buildings: []}};
  ui.configure(awaitingVolume, map, layers); ui.renderCase();
  check(guideButton.disabled && !guideTable().classList.contains("has-size-guides"),
    "Während fehlender GWR-Volumen noch keine Vorschläge anzeigen");
  const loadedVolume = {...awaitingVolume, geo: {...awaitingVolume.geo, volumes: {"101": 1000}}};
  ui.applyGeoCase(loadedVolume);
  check(guideTable().classList.contains("has-size-guides") && !guideButton.disabled &&
    fieldRatio(guideRows()[0].children[1]).textContent === "m³ GVBSID/EGID 1.25",
    "Nachgeladene Volumen aktivieren die Vorschläge ohne zusätzlichen Knopfdruck");
  guideButton.events.click();
  ui.applyGeoCase({...loadedVolume, geo: {...loadedVolume.geo, volumes: {"101": 500}}});
  check(!guideTable().classList.contains("has-size-guides") && guideButton.attributes["aria-pressed"] === "false",
    "Manuelles Ausblenden bleibt nach Geodatenaktualisierungen desselben Pakets erhalten");
  ui.applyGeoCase({...loadedVolume, selected: "SYNTHETIC-NEXT", package_id: "egrid:CH-SYNTHETIC-2", egrids: ["CH-SYNTHETIC-2"],
    records: [{...loadedVolume.records[0], gvbsid: "SYNTHETIC-NEXT"}]});
  check(guideTable().classList.contains("has-size-guides") && guideButton.attributes["aria-pressed"] === "true" && elements.dirty.hidden,
    "Ein anderes EGRID-Paket erhält wieder standardmässige Vorschläge ohne Zuteilungen zu ändern");
  ui.configure({...guideValue, blocked_egids: ["101"], assignable_egids: ["102", "103"]}, map, layers); ui.renderCase();
  check(!guideButton.disabled, "Gesperrte EGID dürfen bei rein visuellen Grössenvergleichen berücksichtigt werden");
  const lockedGuideHead = guideHeads().find(head => head.children[0].dataset.egid === "101");
  check(lockedGuideHead.classList.contains("egid-locked") &&
    guideRows().some(row => row.children.some(cell => cell.dataset.egid === "101" && cell.classList.contains("size-match"))) &&
    guideRows().every(row => row.children.find(cell => cell.dataset.egid === "101").children[0].disabled),
    "Auch mit Grössenvorschlägen bleiben automatisch zugeteilte EGID grau und ihre Checkboxen gesperrt");
  ui.applyState({database: "synthetic", active: false, progress: {total: 1, completed: 0, remaining: 1}});
  check(guideButton.hidden && guideButton.disabled && guideButton.attributes["aria-pressed"] === "false",
    "Bei Deaktivierung der Datenbank auch den Vorschlagsknopf zurücksetzen und sperren");

  const dynamicValue = JSON.parse(JSON.stringify({...value, package_id: "egrid:CH-SYNTHETIC-1", package_index: 0,
    geo: {...value.geo, volumes: {"101": 2400, "102": 100}},
    records: [value.records[0], {...value.records[0], gvbsid: "SYNTHETIC-2"}]}));
  const refreshed = JSON.parse(JSON.stringify({...dynamicValue, egids: ["101", "102", "999"]}));
  ui.configure(dynamicValue, map, layers, [{gvbsid: "SYNTHETIC-1", package_id: dynamicValue.package_id, package_index: 0}], "open", "equal");
  dynamicValue.records[0].comment = "Synthetische ungespeicherte Bearbeitung";
  ui.changed(dynamicValue.records[0]);
  check(guideTable().classList.contains("has-size-guides"), "Grössenvorschläge vor einer Geodatenaktualisierung standardmässig anzeigen");
  const requests = [];
  syntheticApi = async path => {
    requests.push(path);
    const response = path === "/api/geo" ? refreshed.geo : path.startsWith("/api/case?") ? refreshed :
      path === "/api/queue?view=open&ratio=equal" ? {records: [], assignment_counts: {
        all: {total: 2, unassigned: 2}, equal: {total: 0, unassigned: 0}, different: {total: 2, unassigned: 2}
      }} : null;
    if (!response) throw new Error("Unerwartete synthetische Anfrage");
    return {ok: true, json: async () => response};
  };
  await ui.loadGeo();
  check(requests.length === 3 && requests[2] === "/api/queue?view=open&ratio=equal", "Nachgeladenen Geodaten folgt eine Aktualisierung der gefilterten Liste");
  check(elements["case-title"].textContent === "EGRID CH-SYNTHETIC-1" && !elements["case-content"].hidden,
    "Nicht mehr passendes geöffnetes Paket bleibt nach dem Nachladen sichtbar");
  check(!elements["queue-scope"].hidden && elements["queue-position"].textContent === "Noch 0 von 0 GVBSIDs ohne EGID · Nur 1:1", "Nach Geodatenänderung beide Zahlen des Verhältnisfilters aktualisieren und das geöffnete Paket als ausserhalb der Auswahl kennzeichnen");
  check(elements["case-counts"].textContent === "(2 GVBSID/3 EGID)" && elements.previous.disabled && elements.next.disabled,
    "Nach dem Nachladen neue Matrixanzahlen und gefilterte Navigation verwenden");
  check(ui.decisionPayload("Abgeschlossen").decisions[0].comment === "Synthetische ungespeicherte Bearbeitung" && !elements.dirty.hidden,
    "Nachladen und Listenaktualisierung erhalten ungespeicherte Kommentare");
  check(elements.queue.children.length === 1 && elements.queue.children[0].textContent.includes("Keine Fälle"),
    "Paketauswahl enthält keine vom Verhältnisfilter ausgeschlossenen Pakete");
  check(guideButton.hidden && !guideTable().classList.contains("has-size-guides") && guideEndpoints() === "",
    "Nachgeladene zusätzliche EGID entfernen Vorschläge und Knopf, sobald das Paket nicht mehr 1:1 ist");

  ui.configure(value, map, layers, [], "special", "different");
  syntheticApi = async path => {
    requests.push(path);
    if (path !== "/api/queue?view=special&ratio=equal") throw new Error("Unerwartete synthetische Filteranfrage");
    return {ok: true, json: async () => ({records: []})};
  };
  await ui.switchQueueRatio("equal");
  check(ui.queueRequestPath() === "/api/queue?view=special&ratio=equal" && elements["queue-view"].value === "special",
    "Erfolgreicher Verhältniswechsel behält den Wartelistenstatus");
  check(elements["queue-position"].textContent === "Noch 23 von 40 GVBSIDs ohne EGID · Nur 1:1",
    "Beim Verhältniswechsel verbleibende Anzahl und Gesamtzahl der gewählten Gruppe verwenden");
  check(elements["empty-note"].textContent.includes("Nur 1:1") && elements["case-content"].hidden,
    "Erfolgreicher Filterwechsel zeigt die zugehörige leere Auswahl");
  syntheticApi = null;

  for (const [ratio, text] of [
    ["all", "Noch 123 von 200 GVBSIDs ohne EGID · Alle Verhältnisse"],
    ["equal", "Noch 23 von 40 GVBSIDs ohne EGID · Nur 1:1"],
    ["different", "Noch 100 von 160 GVBSIDs ohne EGID · ungleich 1:1"],
  ]) {
    for (const view of ["open", "special", "completed"]) {
      ui.configure(value, map, layers, [], view, ratio); ui.showEmptyQueue();
      check(elements["queue-position"].textContent === text,
        "Zähler je Verhältnisgruppe bleibt auch bei leerer oder anderer Warteliste unverändert");
    }
  }
  ui.configure(value, map, layers, [], "open", "equal");
  ui.applyState({database: "synthetic", active: true, progress: {total: 200}, unassigned_count: 123});
  check(elements["queue-position"].textContent === "Anzahl ohne EGID nicht verfügbar",
    "Fehlende Teilgruppenzahlen nicht durch die globale Anzahl ersetzen");
  ui.applyState({database: "synthetic", active: true, progress: {total: 200}, unassigned_count: 123,
    assignment_counts: {equal: {total: 40, unassigned: 22}}});
  check(elements["queue-position"].textContent === "Noch 22 von 40 GVBSIDs ohne EGID · Nur 1:1",
    "Gespeicherte Änderungen aktualisieren auch die aktive Verhältnisgruppe sofort");
  syntheticApi = async () => {throw new Error("Synthetisch fehlgeschlagener Filterwechsel");};
  let failedFilter = false;
  try {await ui.switchQueueRatio("different");} catch (_) {failedFilter = true;}
  check(failedFilter && elements["queue-ratio"].value === "equal" &&
    elements["queue-position"].textContent === "Noch 22 von 40 GVBSIDs ohne EGID · Nur 1:1",
    "Fehlgeschlagener Filterwechsel stellt Auswahl und Zähler wieder her");
  syntheticApi = null;

  ui.configure(value, map, layers); ui.renderCase();
  ui.applyState({database: "synthetic", active: false, progress: {total: 1, completed: 0, impossible: 0, remaining: 1}});
  check(elements["case-category"].hidden && !elements["left-pane"].classList.contains("has-category"), "Beim Datenbankwechsel die Kategoriefarbe und Beschriftung zurücksetzen");
  check(elements["case-counts"].hidden && elements["case-counts"].textContent === "", "Alte Paketanzahlen beim Datenbankwechsel entfernen");
  check(!elements["case-counts"].classList.contains("is-unbalanced"), "Beim Datenbankwechsel die rote Kennzeichnung entfernen");
  const countState = count => ({database: "synthetic", active: true, unassigned_count: count,
    progress: {total: 3, completed: 0, special: 0, remaining: 3},
    package_progress: {total: 2, completed: 0, special: 0, remaining: 2}});
  const unsavedCountRecord = {...value.records[0], assigned: []};
  ui.configure({...value, records: [unsavedCountRecord]}, map, layers); ui.applyState(countState(3)); ui.renderCase();
  const unsavedCountInput = elements.matrix.children[0].children[1].children[0].children[1].children[0];
  unsavedCountInput.checked = true; unsavedCountInput.events.change();
  check(elements["queue-position"].textContent === "Noch 3 von 3 GVBSIDs ohne EGID · Alle Verhältnisse" && !elements.dirty.hidden,
    "Ungespeicherte Checkboxänderungen verändern den Zähler nicht");
  ui.applyState(countState(2));
  check(elements["queue-position"].textContent === "Noch 2 von 3 GVBSIDs ohne EGID · Alle Verhältnisse", "Ein aktualisierter gespeicherter Stand aktualisiert den Zähler sofort");
  ui.applyState(countState(1));
  check(elements["queue-position"].textContent === "Noch 1 von 3 GVBSIDs ohne EGID · Alle Verhältnisse", "Bei einer verbleibenden GVBSID die ursprüngliche Gesamtzahl erhalten");
  ui.applyState(countState(0));
  check(elements["queue-position"].textContent === "Noch 0 von 3 GVBSIDs ohne EGID · Alle Verhältnisse", "Null verbleibende Zuteilungen eindeutig anzeigen");
  ui.showEmptyQueue();
  check(elements["queue-position"].textContent === "Noch 0 von 3 GVBSIDs ohne EGID · Alle Verhältnisse" && elements["queue-scope"].hidden,
    "Auch ohne geöffnetes Paket die Gesamtzahl anzeigen und den Hinweis ausserhalb der Auswahl ausblenden");
  ui.applyState(countState(undefined));
  check(elements["queue-position"].textContent === "Anzahl ohne EGID nicht verfügbar", "Fehlende Zählerdaten nicht als null verbleibende GVBSIDs darstellen");
  ui.applyState({...countState(1), progress: {total: 1}});
  check(elements["queue-position"].textContent === "Noch 1 von 1 GVBSID ohne EGID · Alle Verhältnisse", "Bei insgesamt einer GVBSID die Einzahl verwenden");
  ui.applyState({...countState(0), progress: {total: 0}});
  check(elements["queue-position"].textContent === "Noch 0 von 0 GVBSIDs ohne EGID · Alle Verhältnisse", "Eine leere Gesamtmenge eindeutig anzeigen");
  ui.applyState({...countState(1), progress: {}});
  check(elements["queue-position"].textContent === "Anzahl ohne EGID nicht verfügbar", "Fehlende Gesamtzahl nicht durch die Paketanzahl ersetzen");
  ui.applyState({...countState(0), active: false});
  check(elements["queue-position"].textContent === "Gesperrt" && elements["queue-scope"].hidden,
    "Vor Aktivierung der Datenbank keine veraltete Anzahl oder Paketzugehörigkeit anzeigen");
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
