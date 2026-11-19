"use strict";

const reviewConfig = JSON.parse(document.getElementById("review-config").textContent);
const token = reviewConfig.token;
const categoryColors = reviewConfig.category_colors || {};
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

function recordCategory(record) {
  const name = String(record?.raw?.["Matching-Kategorie"] || "").trim();
  const hex = categoryColors[name];
  const color = typeof hex === "string" && /^[a-f\d]{6}$/i.test(hex) ? "#" + hex : null;
  const labels = {
    review_address_suffix: "Adress-Suffix · Allgemeine Prüfung",
    address_suffix_pair_lt4: "Adress-Suffix-Paar · Manuell prüfen",
    address_suffix_pair_ge4: "Adress-Suffix-Paar · Automatisch zugeordnet",
    review_suffix_single_building: "Ein Gebäude mit Adress-Suffix",
  };
  return {name, color, label: Object.hasOwn(labels, name) ? labels[name] : name || "Kategorie unbekannt"};
}

function isBlockedEgid(egid) {
  return Boolean(current?.blocked_egids?.includes(String(egid)));
}

function canAssignEgid(egid) {
  return Boolean(current?.automatic_assignments_loaded && current.assignable_egids?.includes(String(egid)));
}

function paintCategory(element, category) {
  element.classList.toggle("has-category", Boolean(category.color));
  element.style.setProperty("--category-color", category.color || "#d9e2e6");
  const rgb = category.color?.slice(1).match(/../g).map(part => parseInt(part, 16));
  element.style.setProperty("--category-tint", rgb ? `rgba(${rgb.join(",")},0.15)` : "#fafcfd");
}

function renderCategoryTheme() {
  const record = current?.records.find(item => item.gvbsid === current.selected);
  const category = recordCategory(record), badge = $("case-category");
  paintCategory($("left-pane"), category);
  badge.textContent = category.label;
  badge.title = category.name;
  badge.hidden = !record;
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

function packageNavigation() {
  const packages = [], seen = new Set();
  for (const record of queue) {
    const id = record.package_id || record.gvbsid;
    if (seen.has(id)) continue;
    seen.add(id); packages.push({id, index: record.package_index, gvbsid: record.gvbsid});
  }
  const selected = current?.package_id || queue.find(record => record.gvbsid === current?.selected)?.package_id || current?.selected;
  const position = packages.findIndex(item => item.id === selected);
  let previous = null, next = null;
  if (current && position >= 0) {
    previous = packages[position - 1]?.gvbsid || null;
    next = packages[position + 1]?.gvbsid || null;
  } else if (current && Number.isInteger(current.package_index)) {
    previous = packages.filter(item => item.index < current.package_index).at(-1)?.gvbsid || null;
    next = packages.find(item => item.index > current.package_index)?.gvbsid || null;
  }
  return {packages, position, previous, next};
}

function gates() {
  const database = Boolean(state?.database), active = Boolean(state?.active);
  for (const id of ["select-db", "new-db"]) $(id).disabled = busy;
  $("import").disabled = busy || !database;
  $("activate").disabled = busy || !database || !state?.progress.total;
  for (const id of ["search", "search-button", "export", "queue"]) $(id).disabled = busy || !active;
  const selectedRecord = current?.records.find(record => record.gvbsid === current.selected);
  const openDecision = selectedRecord && !["Abgeschlossen", "Keine Zuordnung möglich"].includes(selectedRecord.status);
  $("save").disabled = busy || !active || !current?.automatic_assignments_loaded || (!dirty.size && !openDecision);
  const navigation = packageNavigation();
  $("previous").disabled = busy || !active || !navigation.previous;
  $("next").disabled = busy || !active || !navigation.next;
  for (const input of $("case-content").querySelectorAll("input,select,textarea,button[data-remove-blocked]")) {
    input.disabled = busy || !active || !current?.automatic_assignments_loaded || (input.type === "checkbox" && !canAssignEgid(input.dataset.egid));
  }
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
    renderCategoryTheme();
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

async function refreshQueue(stamp = null) {
  const value = await api("/api/queue");
  if (stamp !== null && stamp !== generation) return;
  queue = value.records;
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

function gwrVolume(egid) {
  return current?.geo?.volumes?.[egid] ?? current?.geo?.buildings?.find(building => building.egid === egid)?.volume;
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
  renderCategoryTheme();
  $("case-content").hidden = false; $("empty-note").hidden = true;
  $("case-title").textContent = `${current.selected} (GVBSID)`;
  $("egrids").textContent = current.egrids.join(", ") || "Keine verlässliche EGRID vorhanden";
  const position = queue.findIndex(record => record.gvbsid === current.selected);
  const navigation = packageNavigation();
  $("queue-position").textContent = navigation.position < 0 ? "Über Suche geöffnet"
    : `Paket ${navigation.position + 1} / ${navigation.packages.length}`;
  $("queue-position").title = `${current.records.length} GVBSID im angezeigten Paket`;
  if (position >= 0) $("queue").value = current.selected;
  const lockNote = $("assignment-lock-note");
  lockNote.hidden = Boolean(current.automatic_assignments_loaded && !current.blocked_egids?.length);
  lockNote.textContent = !current.automatic_assignments_loaded
    ? "Bitte die vollständige Matching-Datei importieren. Ohne die Liste automatischer Zuordnungen bleibt die Vergabe gesperrt."
    : "Graue EGID sind bereits automatisch zugeteilt und können nicht erneut vergeben werden.";
  const table = node("table"), head = node("thead"), headings = node("tr");
  headings.append(node("th", "GVBS"));
  for (const egid of current.egids) {
    const volumeText = ReviewEgidPoints.volumeText(gwrVolume(egid));
    const th = node("th", undefined, "gwr-column"), button = node("button", `${egid} (GWR)${volumeText ? " · " + volumeText : ""}`, "egid-button");
    th.classList.toggle("egid-locked", isBlockedEgid(egid));
    button.type = "button"; button.dataset.egid = egid;
    button.addEventListener("click", () => selectEgid(egid));
    const addresses = [...new Set((current.geo?.buildings || []).filter(building => building.egid === egid).flatMap(gwrAddresses))];
    const addressText = addresses.join("; ") || (current.geo ? "GWR-Adresse nicht verfügbar" : "GWR-Adresse wird geladen …");
    th.append(button, node("span", addressText, "gwr-table-address")); headings.append(th);
    if (isBlockedEgid(egid)) th.append(node("span", "Automatisch zugeteilt · gesperrt", "egid-lock-label"));
  }
  head.append(headings); table.append(head);
  const body = node("tbody");
  for (const record of current.records) {
    const tr = node("tr"); if (["Abgeschlossen", "Keine Zuordnung möglich"].includes(record.status)) tr.className = "row-finished";
    const category = recordCategory(record);
    paintCategory(tr, category);
    const identity = node("td"), trigger = node("button", `${record.gvbsid} (GVBSID)`, "gvbsid-info");
    trigger.type = "button"; recordInfo.attach(trigger, record);
    const info = node("ul", undefined, "gvbs-info-list");
    const volume = String(record.raw?.Kubatur ?? "").replace(/\s+/g, " ").trim();
    info.append(node("li", `Adresse: ${String(record.address || "–").replace(/\s+/g, " ").trim()}`),
      node("li", `Zweckbestimmung: ${String(record.purpose || "Zweckbestimmung fehlt").replace(/\s+/g, " ").trim()}`),
      node("li", `Gebäudevolumen: ${volume ? volume + " m³" : "Nicht angegeben"}`));
    identity.append(trigger, node("strong", "GVBS-Info:", "gvbs-info-title"), info);
    const categoryLabel = node("span", category.label, "row-category-label");
    categoryLabel.title = category.name;
    identity.append(categoryLabel);
    const conflicts = record.assigned.filter(isBlockedEgid);
    if (conflicts.length) {
      const note = node("div", undefined, "assignment-conflict");
      note.append(node("p", `Gespeicherte Zuordnung steht im Konflikt mit automatischer Zuteilung: ${conflicts.join(", ")}.`));
      const remove = node("button", "Gesperrte Zuordnung entfernen", "secondary");
      remove.type = "button"; remove.dataset.removeBlocked = "true";
      remove.addEventListener("click", () => {
        if (busy || !state?.active || !current?.automatic_assignments_loaded) return;
        record.assigned = record.assigned.filter(egid => !isBlockedEgid(egid));
        changed(record); renderCase();
      });
      note.append(remove); identity.append(note);
    }
    tr.append(identity);
    for (const egid of current.egids) {
      const td = node("td"), checkbox = document.createElement("input");
      td.classList.toggle("egid-locked", isBlockedEgid(egid));
      td.dataset.egid = egid; checkbox.type = "checkbox"; checkbox.checked = record.assigned.includes(egid);
      checkbox.dataset.egid = egid;
      checkbox.setAttribute("aria-label", `${record.gvbsid} der EGID ${egid} zuordnen`);
      checkbox.addEventListener("change", () => {
        if (!canAssignEgid(egid)) {checkbox.checked = record.assigned.includes(egid); return;}
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
  renderCategoryTheme();
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
  map.createPane("parcel-mask").style.zIndex = 350;
  map.getPane("parcel-mask").style.pointerEvents = "none";
  map.createPane("parcel-boundaries").style.zIndex = 440;
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

function maskParcels(parcels) {
  mapLayers.mask.clearLayers();
  if (!parcels.length) return;
  const polygons = parcels.flatMap(parcel => parcel.geometry.type === "Polygon" ? [parcel.geometry.coordinates] : parcel.geometry.coordinates);
  const outer = [[-85, -180], [-85, 180], [85, 180], [85, -180]];
  const latlng = ring => ring.map(point => [point[1], point[0]]);
  const style = {pane: "parcel-mask", stroke: false, fillColor: "#4d565b", fillOpacity: .52, interactive: false};
  L.polygon([outer, ...polygons.flatMap(polygon => polygon.map(latlng))], {...style, fillRule: "evenodd"}).addTo(mapLayers.mask);
}

function focusParcel(egrid) {
  if (!map || !current?.geo) return;
  const parcel = current.geo.parcels.find(value => (value.key || value.egrid) === egrid);
  maskParcels(parcel ? [parcel] : []);
  for (const layer of mapLayers.parcels.getLayers()) layer.setStyle({color: layer.options.reviewEgrid === egrid ? "#cf6a19" : "#3c7d86", weight: layer.options.reviewEgrid === egrid ? 4 : 2});
  if (parcel) map.fitBounds(L.geoJSON(parcel.geometry).getBounds(), {maxZoom: DEFAULT_MAP_ZOOM, padding: [28, 28]});
}

function renderGeo() {
  clearMap();
  if (!ensureMap() || !current?.geo) return;
  map.invalidateSize({pan: false});
  const geo = current.geo;
  const allBounds = L.latLngBounds();
  for (const parcel of geo.parcels) {
    const layer = L.geoJSON(parcel.geometry, {pane: "parcel-boundaries", style: {color: "#cf6a19", weight: 3, opacity: 1, fill: false}}).addTo(mapLayers.parcels);
    layer.options.reviewEgrid = parcel.key || parcel.egrid; allBounds.extend(layer.getBounds());
  }
  // Grundstück und Kartenausschnitt unabhängig von EGID-Beschriftungen zeichnen.
  if (geo.parcels.length === 1) focusParcel(geo.parcels[0].key || geo.parcels[0].egrid);
  else if (geo.parcels.length > 1) {
    maskParcels(geo.parcels);
    map.fitBounds(allBounds, {maxZoom: DEFAULT_MAP_ZOOM, padding: [28, 28]});
  } else {
    const reason = geo.sources?.parcels?.message;
    $("egid-details").textContent = `Keine Parzellengrenze verfügbar.${reason ? " " + reason : ""}`;
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
        const layer = L.geoJSON(geometry, {style: {color: isBlockedEgid(egid) ? "#7b858d" : "#547d8a", weight: 2,
          fillColor: isBlockedEgid(egid) ? "#a0a9b0" : "#75a3ac", fillOpacity: .35}}).addTo(mapLayers.buildings);
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
  for (const feature of features.features) {
    feature.properties.needs_review = buildingIndex.get(feature.properties.egid)?.needs_review;
    feature.properties.automatically_assigned = isBlockedEgid(feature.properties.egid);
  }
  ReviewEgidPoints.layer(L, features, {renderer: egidRenderer, map, index: markerIndex, selected: selectedEgid, onSelect: selectEgid,
    onPosition: (egid, position) => {
      allBounds.extend(position);
      const content = ReviewEgidPoints.label(egid, gwrAddresses(buildingIndex.get(egid)), isBlockedEgid(egid), gwrVolume(egid));
      const label = L.marker(position, {icon: L.divIcon({className: "", html: content, iconAnchor: [-8, 8]})}).addTo(mapLayers.labels);
      label.on("click", () => selectEgid(egid));
    }
  }).addTo(mapLayers.markers);
  if (!geo.parcels.length && allBounds.isValid()) map.setView(allBounds.getCenter(), DEFAULT_MAP_ZOOM);
  if (selectedEgid) selectEgid(selectedEgid);
}

function selectEgid(egid) {
  selectedEgid = egid;
  for (const element of $("matrix").querySelectorAll("[data-egid]")) element.classList.toggle("selected-egid", element.dataset.egid === egid);
  if (map) ReviewEgidPoints.update(markerIndex, egid, map.getZoom());
  for (const [id, layers] of geometryIndex) for (const layer of layers) layer.setStyle({color: isBlockedEgid(id) ? "#7b858d" : id === egid ? "#b86a00" : "#547d8a", weight: id === egid ? 4 : 2});
  const buildings = (current?.geo?.buildings || []).filter(value => value.egid === egid);
  const addresses = [...new Set(buildings.flatMap(gwrAddresses))];
  const addressStatus = current?.geo?.gwr_address_status;
  const addressText = addresses.length ? `GWR: ${addresses.join("; ")}` : `GWR: ${addressStatus?.code === "unreachable" ? addressStatus.message : "Keine Adresse zur EGID im GWR gefunden."}`;
  const statuses = [...new Set(buildings.map(value => value.gstat).filter(Boolean))];
  const volumeText = ReviewEgidPoints.volumeText(gwrVolume(egid));
  $("egid-details").textContent = `EGID ${egid}${volumeText ? " · " + volumeText : ""}\n${addressText}\nGSTAT ${statuses.join(", ") || "unbekannt"}${isBlockedEgid(egid) ? "\nAutomatisch zugeteilt · Für manuelle Vergabe gesperrt" : ""}`;
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
  await refreshQueue(stamp);
  if (stamp === generation && current?.selected === selected) renderCase();
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
$("previous").addEventListener("click", () => action(async () => {const target = packageNavigation().previous; if (target) await openCase(target);}));
$("next").addEventListener("click", () => action(async () => {const target = packageNavigation().next; if (target) await openCase(target);}));
$("save").addEventListener("click", () => action(async () => {
  const selected = current.selected, oldIndex = queue.findIndex(record => record.gvbsid === selected);
  const edited = current.records.filter(record => dirty.has(record.gvbsid));
  const recordsToSave = edited.length ? edited : current.records.filter(record => record.gvbsid === selected);
  const decisions = recordsToSave.map(record => ({gvbsid: record.gvbsid, version: record.version, assigned: record.assigned, comment: record.comment}));
  const value = await api("/api/save", {selected, decisions}); dirty.clear(); applyState(value); await refreshQueue();
  if (queue.some(record => record.gvbsid === selected)) await openCase(selected, false);
  else if (queue.length) await openCase(queue[Math.min(Math.max(oldIndex, 0), queue.length - 1)].gvbsid, false);
  else {current = null; generation++; renderCategoryTheme(); $("case-content").hidden = true; $("empty-note").hidden = false; $("empty-note").textContent = "Alle Fälle bearbeitet. Abgeschlossene Fälle bleiben über die Suche erreichbar."; $("case-title").textContent = "Warteschlange abgeschlossen"; $("queue-position").textContent = "0 offen"; clearMap();}
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
