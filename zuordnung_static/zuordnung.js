"use strict";

const token = JSON.parse(document.getElementById("review-config").textContent).token;
const $ = id => document.getElementById(id);
let state = null, current = null, queue = [], dirty = new Set(), busy = false, generation = 0;
let map = null, mapLayers = null, markerIndex = new Map(), geometryIndex = new Map(), selectedEgid = null;
let geoRequestId = 0;
let egidRenderer = null;
const DEFAULT_MAP_ZOOM = 19;

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function createTopPanel() {
  const panel = $("top-panel"), trigger = $("top-panel-trigger");
  let ready = false, opened = true, pointerInside = false, closeTimer = null;

  function cancelClose() {
    if (closeTimer !== null) window.clearTimeout(closeTimer);
    closeTimer = null;
  }

  function setOpen(value) {
    opened = value;
    document.body.classList.toggle("top-panel-open", ready && value);
    panel.inert = ready && !value;
    panel.setAttribute("aria-hidden", String(ready && !value));
    trigger.setAttribute("aria-expanded", String(ready && value));
  }

  function reveal() {
    if (!ready) return;
    cancelClose(); setOpen(true);
  }

  function scheduleClose() {
    cancelClose();
    if (!ready || !opened || pointerInside) return;
    closeTimer = window.setTimeout(() => {
      closeTimer = null;
      if (!ready || pointerInside || busy) return;
      setOpen(false);
    }, 1000);
  }

  function setReady(value) {
    if (ready === value) return;
    cancelClose(); ready = value; pointerInside = false;
    document.body.classList.toggle("top-panel-ready", value);
    trigger.hidden = !value;
    setOpen(!value);
    window.requestAnimationFrame(() => {if (map) map.invalidateSize({pan: false});});
  }

  panel.addEventListener("pointerenter", () => {pointerInside = true; reveal();});
  panel.addEventListener("pointerleave", () => {pointerInside = false; scheduleClose();});
  panel.addEventListener("focusin", reveal);
  panel.addEventListener("focusout", event => {
    if (!panel.contains(event.relatedTarget)) scheduleClose();
  });
  trigger.addEventListener("pointerenter", reveal);
  trigger.addEventListener("pointerleave", scheduleClose);
  trigger.addEventListener("click", () => {
    cancelClose();
    if (opened) setOpen(false); else reveal();
  });
  document.addEventListener("pointerdown", event => {
    if (!panel.contains(event.target) && !trigger.contains(event.target)) scheduleClose();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && ready && opened) {
      cancelClose(); setOpen(false); trigger.focus({preventScroll: true});
    }
  });
  return {setReady, reveal, scheduleClose};
}

const topPanel = createTopPanel();

function message(text, error = false) {
  $("message").textContent = text;
  $("message").className = error ? "message error" : "message";
  $("message").hidden = !text;
  if (error) topPanel.reveal();
}

async function api(path, data) {
  const options = {cache: "no-store", headers: {}};
  if (data !== undefined) {
    options.method = "POST";
    options.headers = {"Content-Type": "application/json", "X-Review-Token": token};
    options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options);
  let result;
  try { result = await response.json(); }
  catch (_) { throw new Error("Die lokale Anwendung antwortet nicht. Bitte Verbindung und Programmstart prüfen."); }
  if (!response.ok) throw new Error(result.error || "Die Aktion konnte nicht ausgeführt werden.");
  return result;
}

function gates() {
  const database = Boolean(state?.database), active = Boolean(state?.active);
  for (const id of ["select-db", "new-db"]) $(id).disabled = busy;
  $("import").disabled = busy || !database;
  $("activate").disabled = busy || !database || !state?.progress.total;
  for (const id of ["search", "search-button", "export", "queue"]) $(id).disabled = busy || !active;
  $("save").disabled = busy || !active || !current || !dirty.size;
  const position = current ? queue.findIndex(record => record.gvbsid === current.selected) : -1;
  $("previous").disabled = busy || !active || position <= 0;
  $("next").disabled = busy || !active || !queue.length || position >= queue.length - 1;
  for (const input of $("case-content").querySelectorAll("input,select,textarea")) input.disabled = busy || !active;
  $("dirty").hidden = !dirty.size;
}

async function action(callback) {
  if (busy) return;
  busy = true; gates();
  try { await callback(); }
  catch (error) { message(error.message, true); }
  finally { busy = false; gates(); topPanel.scheduleClose(); }
}

function applyState(value) {
  state = value;
  topPanel.setReady(Boolean(value.database && value.active));
  $("map").style.pointerEvents = value.active ? "" : "none";
  $("database-path").textContent = value.database || "Keine Datenbank ausgewählt";
  const p = value.progress;
  $("progress").replaceChildren();
  for (const [label, count] of [["Gesamt", p.total], ["Abgeschlossen", p.completed], ["Keine Zuordnung möglich", p.impossible], ["Noch zu bearbeiten", p.remaining]]) {
    const span = node("span", label + " "); span.append(node("b", String(count))); $("progress").append(span);
  }
  if (!value.active) {
    generation++; current = null; dirty.clear();
    $("case-content").hidden = true; $("empty-note").hidden = false;
    $("empty-note").textContent = value.database ? "Schritt 2 bestätigen: Excel laden oder gespeicherte Daten aktivieren." : "Zuerst eine Datenbank auswählen oder neu erstellen.";
    $("case-title").textContent = "Prüffälle laden";
    $("queue-position").textContent = "Gesperrt";
    $("queue").replaceChildren(node("option", "Noch keine Daten aktiviert"));
    clearMap();
  }
  if (value.warning) message(value.warning, true);
  gates();
}

function canLeave() {
  return !dirty.size || window.confirm("Nicht gespeicherte Änderungen verwerfen und den Fall verlassen?");
}

async function refreshQueue() {
  queue = (await api("/api/queue")).records;
  $("queue").replaceChildren();
  if (!queue.length) $("queue").append(node("option", "Keine Fälle in der Warteschlange"));
  for (const record of queue) {
    const option = node("option", `${record.gvbsid} – ${record.purpose || "Zweckbestimmung fehlt"} · ${record.status}`);
    option.value = record.gvbsid; $("queue").append(option);
  }
  if (current && queue.some(record => record.gvbsid === current.selected)) $("queue").value = current.selected;
  gates();
}

function changed(record) { dirty.add(record.gvbsid); gates(); }

function gwrAddresses(building) {
  return [...new Set((building?.addresses || [building?.address || []]).map(address =>
    (Array.isArray(address) ? address.filter(Boolean).join(" ") : String(address ?? "")).replace(/\s+/g, " ").trim()
  ).filter(Boolean))];
}

function createRecordInfo() {
  const tooltip = node("div", undefined, "record-tooltip");
  tooltip.id = "record-tooltip"; tooltip.setAttribute("role", "tooltip"); tooltip.hidden = true;
  document.body.append(tooltip);
  let anchor = null, closeTimer = null;

  function cancelClose() {
    if (closeTimer !== null) window.clearTimeout(closeTimer);
    closeTimer = null;
  }

  function hide() {
    cancelClose();
    if (anchor) anchor.removeAttribute("aria-describedby");
    anchor = null; tooltip.hidden = true; tooltip.replaceChildren();
  }

  function scheduleClose() {
    cancelClose(); closeTimer = window.setTimeout(hide, 180);
  }

  function show(trigger, record) {
    hide(); anchor = trigger;
    const title = node("div", undefined, "record-tooltip-title");
    title.append(node("span", "GVBSID"), node("strong", record.gvbsid));
    const fields = node("dl"), raw = record.raw || {};
    for (const [label, value] of [
      ["GVBS-Adresse", record.address],
      ["Vorgeschlagene EGID", record.candidates.join(", ")],
      ["Zusatz-EGID", record.suffix_candidates.join(", ")],
      ["EGRID", record.grids.join(", ")],
      ["Weitere GWR-Adressen", raw["GWR-Adressen mit Hausnummernzusatz"]],
      ["GWR-Adressen direkte EGID", raw["Anzahl GWR-Adressen pro EGID"] ?? "Nicht im Import enthalten"],
    ]) {
      const row = node("div", undefined, "record-tooltip-row");
      const text = value === null || value === undefined ? "" : String(value).replace(/\s+/g, " ").trim();
      row.append(node("dt", label), node("dd", text || "–")); fields.append(row);
    }
    tooltip.append(title, fields); tooltip.hidden = false;
    trigger.setAttribute("aria-describedby", tooltip.id);
    const rect = trigger.getBoundingClientRect(), gap = 8, margin = 12;
    const width = tooltip.offsetWidth, height = tooltip.offsetHeight;
    const left = Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin));
    const preferredTop = rect.bottom + gap + height <= window.innerHeight - margin ? rect.bottom + gap : rect.top - height - gap;
    const top = Math.max(margin, Math.min(preferredTop, window.innerHeight - height - margin));
    tooltip.style.left = left + "px"; tooltip.style.top = top + "px";
  }

  tooltip.addEventListener("pointerenter", cancelClose);
  tooltip.addEventListener("pointerleave", scheduleClose);
  document.addEventListener("keydown", event => {if (event.key === "Escape") hide();});
  document.addEventListener("pointerdown", event => {
    if (anchor && !anchor.contains(event.target) && !tooltip.contains(event.target)) hide();
  });
  window.addEventListener("resize", hide);
  document.addEventListener("scroll", event => {if (!tooltip.contains(event.target)) hide();}, true);
  return {
    hide,
    attach(trigger, record) {
      trigger.setAttribute("aria-label", `Informationen zu GVBSID ${record.gvbsid}`);
      trigger.addEventListener("pointerenter", event => {if (event.pointerType !== "touch") show(trigger, record);});
      trigger.addEventListener("pointerleave", scheduleClose);
      trigger.addEventListener("focus", () => show(trigger, record));
      trigger.addEventListener("blur", scheduleClose);
      trigger.addEventListener("click", () => show(trigger, record));
    }
  };
}

const recordInfo = createRecordInfo();

function renderCase() {
  recordInfo.hide();
  $("case-content").hidden = false; $("empty-note").hidden = true;
  const selected = current.records.find(record => record.gvbsid === current.selected);
  $("case-title").textContent = `${current.selected} · GVBS: ${String(selected?.address || "–").replace(/\s+/g, " ").trim()}`;
  $("egrids").textContent = current.egrids.join(", ") || "Keine verlässliche EGRID vorhanden";
  const position = queue.findIndex(record => record.gvbsid === current.selected);
  $("queue-position").textContent = position < 0 ? "Über Suche geöffnet" : `${position + 1} / ${queue.length}`;
  if (position >= 0) $("queue").value = current.selected;
  const table = node("table"), head = node("thead"), headings = node("tr");
  headings.append(node("th", "GVBSID / GVBS-Adresse"));
  for (const egid of current.egids) {
    const th = node("th"), button = node("button", egid, "egid-button");
    button.type = "button"; button.dataset.egid = egid;
    button.addEventListener("click", () => selectEgid(egid)); th.append(button); headings.append(th);
  }
  head.append(headings); table.append(head);
  const body = node("tbody");
  for (const record of current.records) {
    const tr = node("tr"); if (["Abgeschlossen", "Keine Zuordnung möglich"].includes(record.status)) tr.className = "row-finished";
    const identity = node("td"), trigger = node("button", record.gvbsid, "gvbsid-info");
    trigger.type = "button"; recordInfo.attach(trigger, record);
    const heading = node("div", undefined, "record-heading");
    heading.append(trigger, node("span", `GVBS: ${String(record.address || "–").replace(/\s+/g, " ").trim()}`, "gvbs-address"));
    identity.append(heading, node("span", record.purpose || "Zweckbestimmung fehlt", "record-purpose"));
    tr.append(identity);
    for (const egid of current.egids) {
      const td = node("td"), checkbox = document.createElement("input");
      td.dataset.egid = egid; checkbox.type = "checkbox"; checkbox.checked = record.assigned.includes(egid);
      checkbox.setAttribute("aria-label", `${record.gvbsid} der EGID ${egid} zuordnen`);
      checkbox.addEventListener("change", () => {
        const values = new Set(record.assigned);
        if (checkbox.checked) values.add(egid); else values.delete(egid);
        record.assigned = [...values]; changed(record);
      });
      td.append(checkbox); tr.append(td);
    }
    body.append(tr);
    const editor = node("details", undefined, "record-editor"), summary = node("summary", "Kommentar");
    editor.append(summary);
    const fields = node("div", undefined, "edit-fields");
    const commentLabel = node("label", "Kommentar"), comment = document.createElement("textarea");
    comment.value = record.comment; comment.maxLength = 20000;
    comment.addEventListener("input", () => {record.comment = comment.value; changed(record);}); commentLabel.append(comment);
    fields.append(commentLabel); editor.append(fields); identity.append(editor);
  }
  table.append(body); $("matrix").replaceChildren(table);
  if (!current.egids.length) $("matrix").append(node("p", "Keine verlässlich verfügbaren EGID. Geodatenquelle und Kandidaten prüfen.", "hint"));
  if (selectedEgid) selectEgid(selectedEgid);
  gates();
}

async function openCase(gvbsid, check = true) {
  if (check && !canLeave()) { if (current) $("queue").value = current.selected; return; }
  const value = await api("/api/case?gvbsid=" + encodeURIComponent(gvbsid));
  current = value; dirty.clear(); selectedEgid = null; generation++;
  renderCase(); renderGeo();
  loadGeo().catch(error => message(error.message, true));
}

async function activate(value) {
  applyState(value); current = null; dirty.clear(); generation++;
  $("case-content").hidden = true; clearMap(); await refreshQueue();
  if (queue.length) await openCase(queue[0].gvbsid, false);
  else {
    $("case-title").textContent = "Warteschlange abgeschlossen";
    $("empty-note").hidden = false;
    $("empty-note").textContent = "Alle Fälle sind abgeschlossen oder ohne Zuordnung. Über die Suche können sie jederzeit wieder geöffnet werden.";
    $("queue-position").textContent = "0 offen";
  }
}

function ensureMap() {
  if (map) return true;
  if (!window.L) { message("Leaflet konnte nicht geladen werden. Für die Karte ist eine Internetverbindung erforderlich; die Zuordnung bleibt verfügbar.", true); return false; }
  $("map").replaceChildren();
  map = L.map("map", {maxZoom: 22}).setView([47.56, 7.59], DEFAULT_MAP_ZOOM);
  map.createPane("egid-points").style.zIndex = 450;
  egidRenderer = L.canvas({padding: .5, pane: "egid-points"});
  map.on("zoomend", () => ReviewEgidPoints.update(markerIndex, selectedEgid, map.getZoom()));
  const options = {maxZoom: 22, maxNativeZoom: 19, attribution: "GeoBS - Kanton Basel-Stadt"};
  const grey = L.tileLayer("https://wmts.geo.bs.ch/wmts/1.0.0/BaseMap_grau/default/3857/{z}/{y}/{x}.png", options);
  const color = L.tileLayer("https://wmts.geo.bs.ch/wmts/1.0.0/BaseMap_farbig/default/3857/{z}/{y}/{x}.png", options);
  // ResourceURL für OF_OrthofotoAktuell aus den GeoBS-WMTS-Metadaten
  // (EPSG:3857), geprüft am 16.11.2026; aktuell True Orthofoto Mai 2023.
  const aerial = L.tileLayer("https://wmtscache.fgi.cloud.bs.ch/mapcache/wmts/1.0.0/OF_TrueOrthofoto2023Mai/default/v1/3857/{z}/{y}/{x}.png", {...options, maxNativeZoom: 22});
  mapLayers = {parcels: L.layerGroup().addTo(map), buildings: L.layerGroup().addTo(map), markers: L.layerGroup().addTo(map), labels: L.layerGroup().addTo(map), mask: L.layerGroup().addTo(map)};
  grey.addTo(map);
  map.attributionControl.addAttribution("Quelle: Geodaten Kanton Basel-Stadt · Statistisches Amt Basel-Stadt, GWR (CC BY) · Nur bestehende Gebäude (GSTAT 1004)");
  L.control.layers({"Grundkarte grau": grey, "Grundkarte farbig": color, "Luftbild (Mai 2023)": aerial}, {}, {collapsed: true}).addTo(map);
  return true;
}

function clearMap() {
  if (mapLayers) for (const layer of Object.values(mapLayers)) layer.clearLayers();
  markerIndex.clear(); geometryIndex.clear();
  $("egid-details").textContent = "Keine EGID ausgewählt.";
}

function maskParcel(parcel) {
  mapLayers.mask.clearLayers();
  if (!parcel) return;
  const polygons = parcel.geometry.type === "Polygon" ? [parcel.geometry.coordinates] : parcel.geometry.coordinates;
  const outer = [[-85, -180], [-85, 180], [85, 180], [85, -180]];
  const latlng = ring => ring.map(point => [point[1], point[0]]);
  const style = {stroke: false, fillColor: "#4d565b", fillOpacity: .52, interactive: false};
  L.polygon([outer, ...polygons.map(polygon => latlng(polygon[0]))], {...style, fillRule: "evenodd"}).addTo(mapLayers.mask);
  for (const polygon of polygons) for (const hole of polygon.slice(1)) L.polygon(latlng(hole), style).addTo(mapLayers.mask);
}

function focusParcel(egrid) {
  if (!map || !current?.geo) return;
  const parcel = current.geo.parcels.find(value => (value.key || value.egrid) === egrid);
  maskParcel(parcel);
  for (const layer of mapLayers.parcels.getLayers()) layer.setStyle({color: layer.options.reviewEgrid === egrid ? "#cf6a19" : "#3c7d86", weight: layer.options.reviewEgrid === egrid ? 4 : 2});
  if (parcel) map.setView(L.geoJSON(parcel.geometry).getBounds().getCenter(), DEFAULT_MAP_ZOOM);
}

function renderGeo() {
  clearMap();
  if (!ensureMap() || !current?.geo) return;
  const geo = current.geo;
  const allBounds = L.latLngBounds();
  for (const parcel of geo.parcels) {
    const layer = L.geoJSON(parcel.geometry, {style: {color: "#3c7d86", weight: 2, fillOpacity: .05}}).addTo(mapLayers.parcels);
    layer.options.reviewEgrid = parcel.key || parcel.egrid; allBounds.extend(layer.getBounds());
  }
  const pointFeatures = [];
  const buildings = geo.buildings.filter(building => building.gstat === "1004");
  const buildingIndex = new Map(buildings.map(building => [building.egid, building]));
  for (const building of buildings) {
    if (!building.geometry) continue;
    const egid = building.egid;
    const addresses = gwrAddresses(building);
    const geometries = building.geometry.type === "GeometryCollection" ? building.geometry.geometries : [building.geometry];
    for (const geometry of geometries) {
      const isPoint = geometry.type === "Point" || geometry.type === "MultiPoint";
      if (isPoint) {
        pointFeatures.push({type: "Feature", geometry, properties: {egid, gstat: building.gstat, needs_review: building.needs_review, addresses}});
      } else if (!isPoint) {
        const layer = L.geoJSON(geometry, {style: {color: "#547d8a", weight: 2, fillColor: "#75a3ac", fillOpacity: .35}}).addTo(mapLayers.buildings);
        layer.bindTooltip(ReviewEgidPoints.tooltip(egid, addresses));
        layer.on("click", () => selectEgid(egid));
        allBounds.extend(layer.getBounds());
        if (!geometryIndex.has(egid)) geometryIndex.set(egid, []); geometryIndex.get(egid).push(layer);
        const center = layer.getBounds().getCenter();
        pointFeatures.push({type: "Feature", geometry: {type: "Point", coordinates: [center.lng, center.lat]},
          properties: {egid, gstat: building.gstat, needs_review: building.needs_review, addresses}});
      }
    }
  }
  const features = {type: "FeatureCollection", features: pointFeatures};
  for (const feature of features.features) feature.properties.needs_review = buildingIndex.get(feature.properties.egid)?.needs_review;
  ReviewEgidPoints.layer(L, features, {renderer: egidRenderer, map, index: markerIndex, selected: selectedEgid, onSelect: selectEgid,
    onPosition: (egid, position) => {
      allBounds.extend(position);
      const label = L.marker(position, {icon: L.divIcon({className: "", html: `<span class="egid-label">${egid}</span>`, iconAnchor: [-8, 8]})}).addTo(mapLayers.labels);
      label.bindTooltip(ReviewEgidPoints.tooltip(egid, gwrAddresses(buildingIndex.get(egid))));
      label.on("click", () => selectEgid(egid));
    }
  }).addTo(mapLayers.markers);
  if (geo.parcels.length === 1) focusParcel(geo.parcels[0].key || geo.parcels[0].egrid);
  else if (allBounds.isValid()) map.setView(allBounds.getCenter(), DEFAULT_MAP_ZOOM);
  if (selectedEgid) selectEgid(selectedEgid);
  map.invalidateSize();
}

function selectEgid(egid) {
  selectedEgid = egid;
  for (const element of $("matrix").querySelectorAll("[data-egid]")) element.classList.toggle("selected-egid", element.dataset.egid === egid);
  if (map) ReviewEgidPoints.update(markerIndex, egid, map.getZoom());
  for (const [id, layers] of geometryIndex) for (const layer of layers) layer.setStyle({color: id === egid ? "#b86a00" : "#547d8a", weight: id === egid ? 4 : 2});
  const buildings = (current?.geo?.buildings || []).filter(value => value.egid === egid);
  const addresses = [...new Set(buildings.flatMap(gwrAddresses))];
  const addressStatus = current?.geo?.gwr_address_status;
  const addressText = addresses.length ? `GWR: ${addresses.join("; ")}` : `GWR: ${addressStatus?.code === "unreachable" ? addressStatus.message : "Keine Adresse zur EGID im GWR gefunden."}`;
  $("egid-details").textContent = `EGID ${egid}\n${addressText}\n${[...new Set(buildings.map(value => `${value.relation} · GSTAT ${value.gstat || "unbekannt"}${value.needs_review ? " · klärungsbedürftig" : ""}${value.geometry_note ? "\n" + value.geometry_note : ""}${value.source_updated ? "\nQuellen-Exportdatum: " + value.source_updated : ""}`))].join("\n")}${buildings.some(value => !value.gstat_verified) ? "\nBestandsstatus GSTAT ungeprüft." : ""}`;
}

async function loadGeo() {
  if (!current) return;
  const selected = current.selected, stamp = generation;
  const requestId = ++geoRequestId;
  if (!ensureMap()) return;
  let geo;
  try {geo = await api("/api/geo", {selected});}
  catch (error) {if (stamp !== generation || requestId !== geoRequestId) return; throw error;}
  if (stamp !== generation || requestId !== geoRequestId || current?.selected !== selected) return;
  const refreshed = await api("/api/case?gvbsid=" + encodeURIComponent(selected));
  if (stamp !== generation || requestId !== geoRequestId || current?.selected !== selected) return;
  applyGeoCase(refreshed, geo); renderGeo();
}

function applyGeoCase(refreshed, geo = refreshed.geo) {
  const edits = new Map(current.records.filter(record => dirty.has(record.gvbsid)).map(record => [record.gvbsid, record]));
  refreshed.records = refreshed.records.map(record => edits.get(record.gvbsid) || record);
  refreshed.egids = [...new Set([...refreshed.egids, ...[...edits.values()].flatMap(record => record.assigned)])].sort((a,b) => Number(a)-Number(b));
  current = {...refreshed, geo}; renderCase();
}

$("select-db").addEventListener("click", () => action(async () => {if (!canLeave()) return; const value = await api("/api/database/select", {}); if (!value.cancelled) {applyState(value); message("Datenbank ausgewählt. Bitte Schritt 2 bestätigen.");}}));
$("new-db").addEventListener("click", () => action(async () => {if (!canLeave()) return; const value = await api("/api/database/create", {}); if (!value.cancelled) {applyState(value); message("Neue Datenbank erstellt. Jetzt Excel laden.");}}));
$("import").addEventListener("click", () => action(async () => {if (!canLeave()) return; const value = await api("/api/import", {}); if (!value.cancelled) {await activate(value); message(`${value.imported} Zeilen übernommen. Vorhandene manuelle Entscheidungen bleiben erhalten.`);}}));
$("activate").addEventListener("click", () => action(async () => {if (!canLeave()) return; await activate(await api("/api/activate", {})); message("Gespeicherter Bearbeitungsstand aktiviert.");}));
$("search-form").addEventListener("submit", event => {event.preventDefault(); action(async () => {const id = $("search").value.trim(); if (id) await openCase(id);});});
$("queue").addEventListener("change", () => action(() => openCase($("queue").value)));
$("previous").addEventListener("click", () => action(async () => {const index = queue.findIndex(record => record.gvbsid === current?.selected); if (index > 0) await openCase(queue[index - 1].gvbsid);}));
$("next").addEventListener("click", () => action(async () => {const index = queue.findIndex(record => record.gvbsid === current?.selected); if (index + 1 < queue.length) await openCase(queue[index + 1].gvbsid);}));
$("save").addEventListener("click", () => action(async () => {
  const selected = current.selected, oldIndex = queue.findIndex(record => record.gvbsid === selected);
  const decisions = current.records.filter(record => dirty.has(record.gvbsid)).map(record => ({gvbsid: record.gvbsid, version: record.version, assigned: record.assigned, status: record.status, comment: record.comment}));
  const value = await api("/api/save", {selected, decisions}); dirty.clear(); applyState(value); await refreshQueue();
  if (queue.some(record => record.gvbsid === selected)) await openCase(selected, false);
  else if (queue.length) await openCase(queue[Math.min(Math.max(oldIndex, 0), queue.length - 1)].gvbsid, false);
  else {current = null; generation++; $("case-content").hidden = true; $("empty-note").hidden = false; $("empty-note").textContent = "Alle Fälle bearbeitet. Abgeschlossene Fälle bleiben über die Suche erreichbar."; $("case-title").textContent = "Warteschlange abgeschlossen"; $("queue-position").textContent = "0 offen"; clearMap();}
  message("Entscheidung gespeichert.");
}));
$("export").addEventListener("click", () => action(async () => {if (dirty.size && !window.confirm("Es gibt ungespeicherte Änderungen. Nur den gespeicherten Datenbankstand exportieren?")) return; const value = await api("/api/export", {}); if (!value.cancelled) message("Gesamte Zuteilung exportiert: " + value.path);}));

const divider = $("divider");
function split(percent) {const value = Math.min(75, Math.max(25, percent)); document.documentElement.style.setProperty("--left", value + "%"); divider.setAttribute("aria-valuenow", String(Math.round(value))); if (map) map.invalidateSize();}
divider.addEventListener("pointerdown", event => {divider.setPointerCapture(event.pointerId);});
divider.addEventListener("pointermove", event => {if (divider.hasPointerCapture(event.pointerId)) {const bounds = $("workspace").getBoundingClientRect(); split((event.clientX - bounds.left) / bounds.width * 100);}});
divider.addEventListener("keydown", event => {if (["ArrowLeft", "ArrowRight"].includes(event.key)) {event.preventDefault(); split(Number(divider.getAttribute("aria-valuenow")) + (event.key === "ArrowLeft" ? -2 : 2));}});
window.addEventListener("beforeunload", event => {if (dirty.size) {event.preventDefault(); event.returnValue = "";}});
action(async () => {
  const initial = await api("/api/state");
  if (initial.active) await activate(initial);
  else applyState(initial);
});
