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
      const matches = child => selector === "[data-egid]" ? child.dataset.egid !== undefined : ["INPUT", "SELECT", "TEXTAREA"].includes(child.tagName);
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
  const ui = new Function("document", "window", "fetch", "ReviewEgidPoints", "L", source.slice(0, startup) + "\nreturn {renderCase,renderGeo,selectEgid,applyState,configure(value,view,layers){current=value;selectedEgid=null;state={database:'synthetic',active:true,progress:{total:1}};queue=[{gvbsid:value.selected}];map=view;mapLayers=layers;}};")(document, window, () => {apiCalls++; throw new Error("Externe Zugriffe verboten");}, points, L);
  const value = {
    selected: "SYNTHETIC-1", egrids: ["CH-SYNTHETIC-1"], egids: ["101", "102"],
    records: [{gvbsid: "SYNTHETIC-1", address: "GVBS-Testweg 1, 0000", purpose: "Synthetisches Wohnhaus", raw: {"Matching-Kategorie": "review_address_suffix"}, candidates: ["101"], suffix_candidates: ["102"], grids: ["CH-SYNTHETIC-1"], assigned: [], status: "Offen", comment: ""}],
    geo: {parcels: [{key: "CH-SYNTHETIC-1", egrid: "CH-SYNTHETIC-1", geometry: {type: "Polygon", coordinates: [[[7.5,47.5],[7.6,47.5],[7.6,47.6],[7.5,47.5]]]}}], buildings: [
      {egid: "101", gstat: "1004", addresses: [["GWR-Testgasse", "9a", "0000"]], geometry: {type: "Point", coordinates: [7.55,47.52]}, relation: "Amtliche EGRID-Beziehung der Quelle", geometry_note: "Swisstopo-Näherung (nur Kartendarstellung, keine Grenzprüfung)", source_updated: "2020-01-01"},
      {egid: "102", gstat: "1004", addresses: [], geometry: {type: "Polygon", coordinates: [[[7.55,47.52],[7.56,47.52],[7.56,47.53],[7.55,47.52]]]}}
    ]}
  };
  const layers = {parcels: group(), buildings: group(), markers: group(), labels: group(), mask: group()};
  ui.configure(value, map, layers);
  ui.renderCase();
  const table = elements.matrix.children[0], header = table.children[0].children[0], identity = table.children[1].children[0].children[0];
  check(elements["case-title"].textContent === "SYNTHETIC-1 (GVBSID)", "GVBSID in der Fallüberschrift kennzeichnen");
  check(identity.children[0].textContent === "SYNTHETIC-1 (GVBSID)", "GVBSID in der Tabellenzeile kennzeichnen");
  check(identity.children[1].textContent === "GVBS-Info:", "GVBS-Info als eigenen Abschnitt anzeigen");
  check(identity.children[2].tagName === "UL" && identity.children[2].children.length === 2, "Zwei GVBS-Angaben als Aufzählung anzeigen");
  check(identity.children[2].children[0].textContent === "Adresse: GVBS-Testweg 1, 0000", "GVBS-Adresse ausschliesslich aus dem GVBS-Datensatz anzeigen");
  check(identity.children[2].children[1].textContent === "Zweckbestimmung: Synthetisches Wohnhaus", "Zweckbestimmung unterhalb der Adresse anzeigen");
  check(header.children[1].children[0].textContent === "101 (GWR)", "EGID als GWR kennzeichnen");
  check(header.children[1].children[1].textContent === "GWR-Testgasse 9a 0000", "Original-GWR-Adresse unter der EGID anzeigen");
  check(header.children[2].children[1].textContent === "GWR-Adresse nicht verfügbar", "GVBS-Adresse niemals als GWR-Ersatz anzeigen");
  check(elements["left-pane"].style.getPropertyValue("--category-color") === "#FFF2CC", "Bearbeitungsbereich in der Farbe des ausgewählten Falls darstellen");
  check(!elements["case-category"].hidden && elements["case-category"].textContent.includes("Allgemeine Prüfung"), "Kategorie zusätzlich als Text anzeigen");
  ui.renderGeo();
  check(layers.parcels.layers.length === 1 && layers.parcels.layers[0].options.pane === "parcel-boundaries", "Parzellengrenze in eigener Ebene darstellen");
  check(layers.mask.layers.length === 1 && layers.mask.layers[0].options.pane === "parcel-mask", "Abdunkelung getrennt von Grenzen und Gebäuden darstellen");
  check(viewCalls[viewCalls.length - 1][0] === "fitBounds" && viewCalls[viewCalls.length - 1][2].maxZoom === 19, "Auch eine einzelne grosse Parzelle vollständig zeigen und Zoom 19 als Obergrenze erhalten");
  check(viewCalls[viewCalls.length - 1][2].padding[0] > 0, "Rand für die Abdunkelung um die Parzelle freihalten");
  check(layers.labels.layers.length === 2, "Beide EGID auf der Karte beschriften");
  check(layers.labels.layers[0].options.icon.html.textContent === "101 - GWR-Testgasse 9a 0000", "Kartenbeschriftung enthält EGID und Originaladresse");
  check(layers.labels.layers[1].options.icon.html.textContent === "102 - GWR-Adresse nicht verfügbar", "Fehlende GWR-Adresse auch auf der Karte kenntlich machen");
  const previousViewCalls = viewCalls.length;
  layers.labels.layers[0].events.click();
  const details = elements["egid-details"].textContent;
  check(details.includes("GSTAT 1004"), "Gebäudestatus in den Klickdetails erhalten");
  check(details.includes("GWR: GWR-Testgasse 9a 0000"), "Originaladresse in den Klickdetails erhalten");
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
  check(elements["left-pane"].style.getPropertyValue("--category-color") === "#F4B183", "Bei gemischter Gruppe entscheidet die ausgewählte GVBSID über die Bereichsfarbe");
  const mixedRows = elements.matrix.children[0].children[1].children;
  check(mixedRows[0].style.getPropertyValue("--category-color") === "#E6C200" && mixedRows[1].style.getPropertyValue("--category-color") === "#F4B183", "Gruppierte Zeilen behalten jeweils ihre eigene Kategoriefarbe");
  for (const category of [undefined, "synthetic_unknown", "synthetic_invalid", "__proto__"]) {
    ui.configure({...value, records: [{...value.records[0], raw: {"Matching-Kategorie": category}}]}, map, layers);
    ui.renderCase();
    check(!elements["left-pane"].classList.contains("has-category"), "Fehlende oder unbekannte Kategorie neutral darstellen");
    check(elements["left-pane"].style.getPropertyValue("--category-color") === "#d9e2e6", "Vorherige Kategoriefarbe beim Wechsel zu unbekannter Kategorie entfernen");
  }
  ui.configure(value, map, layers); ui.renderCase();
  ui.applyState({database: "synthetic", active: false, progress: {total: 1, completed: 0, impossible: 0, remaining: 1}});
  check(elements["case-category"].hidden && !elements["left-pane"].classList.contains("has-category"), "Beim Datenbankwechsel die Kategoriefarbe und Beschriftung zurücksetzen");
  check(apiCalls === 0, "Der synthetische Test ruft keinen Dienst auf");
  return assertions;
}

if (typeof require === "function") {
  const fs = require("node:fs"), path = require("node:path");
  const sources = Object.fromEntries(["src/egid_match/zuordnung/static/egid_punkte.js", "src/egid_match/zuordnung/static/zuordnung.js", "src/egid_match/zuordnung/templates/zuordnung.html"].map(name => [name, fs.readFileSync(path.join(__dirname, "..", name), "utf8")]));
  runReviewUiTest(sources);
}
