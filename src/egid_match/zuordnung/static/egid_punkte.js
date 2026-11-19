"use strict";

// Reines Leaflet: GeoJSON bleibt [Longitude, Latitude], Leaflet übernimmt LatLng.
globalThis.ReviewEgidPoints = {
  volumeText(volume) {
    return typeof volume === "number" && Number.isFinite(volume) && volume >= 0 ? `${volume} m³` : "";
  },

  label(egid, addresses = [], automaticallyAssigned = false, volume = null) {
    const label = document.createElement("span");
    label.className = automaticallyAssigned ? "egid-label egid-locked" : "egid-label";
    const values = [...new Set(addresses.map(value => String(value).replace(/\s+/g, " ").trim()).filter(Boolean))];
    const volumeText = this.volumeText(volume);
    label.textContent = `${egid} - ${values.join("; ") || "GWR-Adresse nicht verfügbar"}${automaticallyAssigned ? " (automatisch zugeteilt)" : ""}${volumeText ? " · " + volumeText : ""}`;
    return label;
  },

  style(gstat, selected, zoom, needsReview = false, automaticallyAssigned = false) {
    const colors = {1004: "#16796c", 1001: "#226db0", 1002: "#7763a1", 1003: "#cb8a12", 1005: "#bd5b3a", 1007: "#777777", 1008: "#5e668a"};
    const radius = zoom < 15 ? 3 : zoom < 18 ? 5 : zoom < 20 ? 7 : 9;
    if (automaticallyAssigned) return {radius: radius + (selected ? 3 : 0), color: "#7b858d",
      weight: selected ? 3 : 1.5, fillColor: "#a0a9b0", fillOpacity: .8};
    return {radius: radius + (selected ? 3 : 0), color: selected ? "#ffbe00" : needsReview ? "#a94400" : "#173d45",
      weight: selected ? 3 : 1.5, fillColor: colors[gstat] || "#465a78", fillOpacity: .95};
  },

  layer(L, features, {renderer, map, index, selected, onSelect, onPosition}) {
    return L.geoJSON(features, {
      pointToLayer: (feature, latlng) => {
        const properties = feature.properties, egid = String(properties.egid);
        const marker = L.circleMarker(latlng, {
          ...this.style(properties.gstat, egid === selected, map.getZoom(), properties.needs_review, properties.automatically_assigned), renderer
        });
        marker.reviewProperties = properties;
        if (!index.has(egid)) index.set(egid, []);
        index.get(egid).push(marker);
        marker.on("click", () => onSelect(egid));
        if (onPosition) onPosition(egid, latlng);
        return marker;
      }
    });
  },

  update(index, selected, zoom) {
    for (const [egid, markers] of index) for (const marker of markers) {
      const properties = marker.reviewProperties;
      marker.setStyle(this.style(properties.gstat, egid === selected, zoom, properties.needs_review, properties.automatically_assigned));
    }
  }
};
