"use strict";

// Offline: keine Karte, kein Browserstart, keine echten Gebäude oder Dienste.
if (typeof require === "function") require("../src/egid_match/zuordnung/static/egid_punkte.js");
const points = globalThis.ReviewEgidPoints;
let assertions = 0;
function check(value, message) {
  assertions++;
  if (!value) throw new Error(message);
}

globalThis.document = {createElement: () => ({textContent: ""})};
const renderer = {syntheticCanvas: true}, index = new Map(), selected = [];
const positions = [];
const L = {
  circleMarker(position, options) {
    return {position, options, events: {}, bindTooltip() {throw new Error("EGID-Punkte dürfen keine Hoverinfo erhalten");},
      on(event, callback) {this.events[event] = callback;}, setStyle(value) {Object.assign(this.options, value);}};
  },
  geoJSON(collection, options) {
    return {markers: collection.features.map(feature => options.pointToLayer(feature,
      {lng: feature.geometry.coordinates[0], lat: feature.geometry.coordinates[1]}))};
  }
};
const features = {type: "FeatureCollection", features: [
  {type: "Feature", properties: {egid: "101", gstat: "1004", addresses: ["Synthetischer Testweg 10a, 0000"], position_method: "Swisstopo-Näherung"}, geometry: {type: "Point", coordinates: [7.5, 47.5]}},
  {type: "Feature", properties: {egid: "102", gstat: "1001"}, geometry: {type: "Point", coordinates: [7.6, 47.6]}},
  {type: "Feature", properties: {egid: "103", gstat: "1007"}, geometry: {type: "Point", coordinates: [7.7, 47.7]}}
]};
const layer = points.layer(L, features, {renderer, map: {getZoom: () => 17}, index,
  selected: "101", onSelect: id => selected.push(id), onPosition: (id, position) => positions.push(position)});
check(layer.markers.length === 3, "Jede EGID muss als CircleMarker erscheinen");
check(layer.markers.every(marker => marker.options.renderer === renderer), "Alle EGID teilen denselben Canvas-Renderer");
check(positions[0].lng === 7.5 && positions[0].lat === 47.5, "GeoJSON-Achsen bleiben Longitude/Latitude");
check(new Set(layer.markers.map(marker => marker.options.fillColor)).size === 3, "GSTAT hat unterschiedliche Farben");
const label = points.label("101", features.features[0].properties.addresses);
check(label.textContent === "101 - Synthetischer Testweg 10a, 0000", "EGID und Original-GWR-Adresse in der Kartenbeschriftung");
check(!label.textContent.includes("Swisstopo"), "Keine technischen Hinweise in der Kartenbeschriftung");
check(points.label("102").textContent === "102 - GWR-Adresse nicht verfügbar", "Keine erfundene Adresse bei fehlender GWR-Adresse");
check(points.label("103", ["<img src=x>"]).textContent === "103 - <img src=x>", "Adressangaben werden als Text übergeben");
check(points.label("101", ["Synthetischer Testweg 10a, 0000"], false, 1250).textContent === "101 - Synthetischer Testweg 10a, 0000 · 1250 m³", "GVOL als Zahl und m³ an die Kartenbeschriftung anhängen");
check(points.volumeText(0) === "0 m³" && points.volumeText(25.5) === "25.5 m³", "Null und Dezimalwerte ohne Rundung erhalten");
check([null, undefined, "", "<img src=x>", -1, Infinity, NaN, false].every(value => points.volumeText(value) === ""), "Fehlende oder ungültige Werte nicht als Volumen ausgeben");
layer.markers[1].events.click();
check(selected.join() === "102", "Punktklick hebt die richtige EGID hervor");
points.update(index, "102", 21);
check(layer.markers[1].options.radius > layer.markers[0].options.radius, "Ausgewählte EGID ist grösser");
check(layer.markers[0].options.radius > points.style("1004", false, 13).radius, "Zoom verändert Punktgrösse");
check(layer.markers[0].options.fillColor === points.style("1004", false, 21).fillColor, "Auswahl erhält die GSTAT-Farbe");
points.update(index, null, 13);
check(layer.markers.every(marker => marker.options.radius === 3), "Zurückzoomen aktualisiert alle Punkte");
const lockedIndex = new Map();
const locked = points.layer(L, {type: "FeatureCollection", features: [{...features.features[0],
  properties: {...features.features[0].properties, automatically_assigned: true}}]},
  {renderer, map: {getZoom: () => 17}, index: lockedIndex, selected: null, onSelect() {}});
check(locked.markers[0].options.fillColor === "#a0a9b0", "Automatisch zugeteilte EGID sind grau");
points.update(lockedIndex, "101", 21);
check(locked.markers[0].options.fillColor === "#a0a9b0" && locked.markers[0].options.color === "#7b858d", "Auswahl und Zoom heben die graue Sperrdarstellung nicht auf");
check(points.label("101", [], true).className.includes("egid-locked"), "Beschriftung erhält die graue Sperrdarstellung");
globalThis.egidPointAssertions = assertions;
