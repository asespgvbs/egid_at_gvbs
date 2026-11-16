"use strict";

// Offline: keine Karte, kein Browserstart, keine echten Gebäude oder Dienste.
if (typeof require === "function") require("../zuordnung_static/egid_punkte.js");
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
    return {position, options, events: {}, bindTooltip(value) {this.tooltip = value;},
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
check(layer.markers[0].tooltip.textContent.includes("EGID 101"), "EGID im Tooltip");
check(layer.markers[0].tooltip.textContent.includes("GWR: Synthetischer Testweg 10a, 0000"), "Vorhandene GWR-Adresse im Tooltip");
check(!layer.markers[0].tooltip.textContent.includes("Swisstopo"), "Kein Näherungshinweis im Adress-Tooltip");
check(layer.markers[1].tooltip.textContent.includes("GWR: Adresse nicht verfügbar"), "Keine erfundene Adresse bei fehlender GWR-Adresse");
layer.markers[1].events.click();
check(selected.join() === "102", "Punktklick hebt die richtige EGID hervor");
points.update(index, "102", 21);
check(layer.markers[1].options.radius > layer.markers[0].options.radius, "Ausgewählte EGID ist grösser");
check(layer.markers[0].options.radius > points.style("1004", false, 13).radius, "Zoom verändert Punktgrösse");
check(layer.markers[0].options.fillColor === points.style("1004", false, 21).fillColor, "Auswahl erhält die GSTAT-Farbe");
points.update(index, null, 13);
check(layer.markers.every(marker => marker.options.radius === 3), "Zurückzoomen aktualisiert alle Punkte");
globalThis.egidPointAssertions = assertions;
