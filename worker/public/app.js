"use strict";

const $ = (sel) => document.querySelector(sel);
const DAY_MS = 86_400_000;
const POLL_IDLE_MS = 60_000;
const POLL_BUSY_MS = 5_000;
const LISTING_ORIGIN = "https://www.wg-gesucht.de/";

const state = {
  config: null,
  listings: [],
  rejected: [],
  runs: [],
  nextRunAt: null,
  tab: null,
  sort: "newest",
};

// localStorage can be missing or throw (private mode, blocked storage): it only holds conveniences.
const saved = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* ignore */ } },
};

async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  const token = saved.get("apiToken");
  if (token && method !== "GET") headers["x-api-token"] = token;
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  return { ok: res.ok, status: res.status, data };
}

// --- formatting ----------------------------------------------------------------------------------
const todayIso = () => new Date().toLocaleDateString("en-CA");
const fmtDay = (iso) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const fmtClock = (d) => d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
const eur = (n) => `${Math.round(n)} €`;

function ago(iso) {
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

function fmtWhen(iso) {
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay ? fmtClock(d) : `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${fmtClock(d)}`;
}

const rent = (l) => l.price_warm ?? l.price_cold ?? l.price_listed;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

let toastTimer = 0;
function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 4000);
}

// --- tabs and sorting ----------------------------------------------------------------------------
const TABS = [
  { id: "new", label: "New", pick: (s) => s.listings.filter((l) => l.triage === "new") },
  { id: "interested", label: "Interested", pick: (s) => s.listings.filter((l) => l.triage === "interested") },
  { id: "matches", label: "All matches", pick: (s) => s.listings.filter((l) => l.triage !== "dismissed") },
  { id: "dismissed", label: "Dismissed", pick: (s) => s.listings.filter((l) => l.triage === "dismissed") },
  { id: "rejected", label: "Rejected", pick: (s) => s.rejected },
];
const SORTS = {
  newest: (a, b) => b.first_seen_at.localeCompare(a.first_seen_at) || b.id - a.id,
  bike: (a, b) => (a.bike_minutes ?? Infinity) - (b.bike_minutes ?? Infinity),
  price: (a, b) => (rent(a) ?? Infinity) - (rent(b) ?? Infinity),
};

const currentTab = () => TABS.find((t) => t.id === state.tab) ?? TABS[2];
const visibleListings = () => [...currentTab().pick(state)].sort(SORTS[state.sort] ?? SORTS.newest);

function renderTabs() {
  const nav = $("#tabs");
  nav.replaceChildren(
    ...TABS.map((t) => {
      const btn = el("button", {
        class: "tab", type: "button", role: "tab", "aria-selected": String(t.id === state.tab), "data-tab": t.id,
      }, t.label, el("span", { class: "count", text: String(t.pick(state).length) }));
      btn.addEventListener("click", () => {
        state.tab = t.id;
        saved.set("tab", t.id);
        render();
      });
      return btn;
    }),
  );
}

// --- cards ---------------------------------------------------------------------------------------
function bikeFact(l) {
  if (l.bike_minutes == null) return el("span", { class: "fact" }, icon("bike"), el("span", { class: "muted", text: "ride unknown" }));
  const approx = l.bike_source === "estimate" ? "~" : "";
  const parts = (l.bike_detail ?? [{ label: "", minutes: l.bike_minutes }])
    .map((a) => `${approx}${Math.round(a.minutes)} min${a.label ? ` ${a.label}` : ""}`);
  return el("span", { class: "fact", title: `${l.bike_km ?? "?"} km by e-bike (slower anchor)` }, icon("bike"), parts.join(" · "));
}

function availabilityText(l) {
  const today = todayIso();
  const from = !l.available_from || l.available_from <= today ? "available now" : `from ${fmtDay(l.available_from)}`;
  return l.available_to ? `${from} – ${fmtDay(l.available_to)}` : from;
}

function priceBlock(l) {
  if (l.price_warm != null) {
    return [eur(l.price_warm), l.price_cold != null ? `warm · ${eur(l.price_cold)} cold` : "warm"];
  }
  if (l.price_listed != null) {
    const sub = l.stage === "pending_detail" ? "listed · checking" : l.detail_status === "failed" ? "listed, unconfirmed" : "listed";
    return [eur(l.price_listed), sub];
  }
  return ["–", "price unknown"];
}

function flags(l) {
  const out = [];
  if (l.stage === "pending_detail") out.push(el("span", { class: "badge info", text: "checking price…" }));
  if (l.bike_source === "estimate") out.push(el("span", { class: "badge warn", text: "ride estimated" }));
  if (l.available_to) out.push(el("span", { class: "badge gold", text: "temporary" }));
  if (Date.now() - Date.parse(l.last_seen_at) > 1.1 * DAY_MS) {
    out.push(el("span", { class: "badge", text: `not seen since ${fmtDay(l.last_seen_at.slice(0, 10))}` }));
  }
  return out;
}

function actionButton(name, label, onClick, extra = {}) {
  const b = el("button", { class: `act ${extra.class ?? ""}`, type: "button", "aria-label": label, title: label, ...extra.attrs }, icon(name));
  b.addEventListener("click", onClick);
  return b;
}

function renderCard(l) {
  const node = $("#card-tpl").content.firstElementChild.cloneNode(true);
  node.dataset.id = l.id;
  node.dataset.triage = l.triage;
  node.dataset.stage = l.stage;

  node.querySelector(".badge.new").hidden = !(l.triage === "new" && l.stage !== "rejected");
  const link = node.querySelector(".card-title");
  link.textContent = l.title || "Untitled listing";
  if (l.url?.startsWith(LISTING_ORIGIN)) link.href = l.url;
  link.addEventListener("click", () => {
    if (l.triage === "new" && l.stage !== "rejected" && saved.get("apiToken")) setTriage(l, "seen", { quiet: true });
  });

  node.querySelector(".card-where").textContent = [l.kind_label, l.place, l.street].filter(Boolean).join(" · ");
  const facts = node.querySelector(".card-facts");
  facts.append(bikeFact(l));
  if (l.size_sqm != null) facts.append(el("span", { class: "fact", text: `${l.size_sqm} m²` }));
  facts.append(el("span", { class: "fact", text: availabilityText(l) }));
  node.querySelector(".card-flags").append(...flags(l));
  if (l.stage === "rejected") node.querySelector(".card-reasons").textContent = l.reasons.join(" · ");

  const [main, sub] = priceBlock(l);
  node.querySelector(".price-main").textContent = main;
  node.querySelector(".price-sub").textContent = sub;

  const actions = node.querySelector(".card-actions");
  if (l.stage === "rejected") {
    actions.remove();
  } else if (l.triage === "dismissed") {
    actions.append(actionButton("undo", "Restore", () => setTriage(l, "seen")));
  } else {
    const starred = l.triage === "interested";
    actions.append(actionButton("star", starred ? "Remove from interested" : "Mark interested",
      () => setTriage(l, starred ? "seen" : "interested"), { class: "star", attrs: { "aria-pressed": String(starred) } }));
    if (l.triage === "new") actions.append(actionButton("check", "Mark seen", () => setTriage(l, "seen")));
    actions.append(actionButton("x", "Dismiss", () => setTriage(l, "dismissed")));
  }

  node.addEventListener("mouseenter", () => highlightMarker(l.id, true));
  node.addEventListener("mouseleave", () => highlightMarker(l.id, false));
  return node;
}

function renderEmpty(count) {
  const empty = $("#empty");
  empty.hidden = count > 0;
  if (count > 0) return;
  const messages = {
    new: ["Nothing new right now", "New matches show up here after each hourly check."],
    interested: ["No favourites yet", "Star a listing to keep it here."],
    matches: ["No matches yet", "The agent checks WG-Gesucht every hour from 6:00 to 23:00."],
    dismissed: ["Nothing dismissed", "Listings you dismiss move here."],
    rejected: ["Nothing rejected in the last 14 days", "Listings that miss a criterion show up here with the reason."],
  };
  const [title, text] = messages[state.tab] ?? messages.matches;
  empty.replaceChildren(el("strong", { text: title }), text);
}

// --- header: criteria, run status, banner ------------------------------------------------------
function renderCriteria() {
  const c = state.config?.criteria;
  if (!c) return;
  const anchors = c.anchors.map((a) => a.label).join(" & ");
  $("#criteria").replaceChildren(
    "≤ ", el("b", { text: `${c.maxWarmRentEur} €` }), " warm · ≤ ", el("b", { text: `${c.maxBikeMinutes} min` }),
    ` e-bike to ${anchors} · move in by `, el("b", { text: fmtDay(c.availableBy) }),
  );
}

function renderStatus() {
  const pill = $("#run-status");
  const text = $("#run-status-text");
  const last = state.runs[0];
  const next = state.nextRunAt ? `next ${fmtClock(new Date(state.nextRunAt))}` : "";
  pill.dataset.state = last?.status ?? "none";
  if (!last) text.textContent = ["No runs yet", next].filter(Boolean).join(" · ");
  else if (last.status === "queued" || last.status === "running") text.textContent = "Searching…";
  else if (last.status === "failed") text.textContent = `Last run failed · ${ago(last.created_at)}`;
  else if (last.status === "stalled") text.textContent = `Last run stalled · ${ago(last.created_at)}`;
  else text.textContent = [`Checked ${ago(last.created_at)}`, next].filter(Boolean).join(" · ");

  const banner = $("#banner");
  const failed = last?.status === "failed" ? last : null;
  banner.hidden = !failed;
  if (failed) banner.textContent = `The last run failed (${failed.errors ?? "unknown error"}). Listings may be out of date.`;
}

function renderRunsTable() {
  const body = $("#runs-body");
  body.replaceChildren();
  for (const r of state.runs) {
    body.append(el("tr", {},
      el("td", { text: fmtWhen(r.created_at) }),
      el("td", { text: r.trigger }),
      el("td", {}, el("span", { class: `state ${r.status}`, text: r.status })),
      el("td", { class: "num", text: String(r.scraped) }),
      el("td", { class: "num", text: String(r.new) }),
      el("td", { class: "num", text: String(r.matched) }),
    ));
    if (r.errors) body.append(el("tr", { class: "err" }, el("td", { colspan: "6", text: r.errors })));
  }
  if (!state.runs.length) body.append(el("tr", {}, el("td", { colspan: "6", class: "muted", text: "No runs yet." })));
  $("#runs-next").textContent = state.nextRunAt ? `Next scheduled run: ${fmtWhen(state.nextRunAt)}.` : "";
}

// --- map -----------------------------------------------------------------------------------------
const mapState = { map: null, tiles: null, markers: new Map(), layer: null, fitted: false };
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

// OSM's own tiles need no key; dark mode inverts them in CSS (see .map-pane .leaflet-tile-pane).
function tileLayer() {
  return L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  });
}

async function initMap() {
  if (typeof L === "undefined" || !state.config) return;
  const { searchArea, criteria } = state.config;
  const map = L.map("map", { zoomControl: true, attributionControl: true });
  mapState.map = map;
  mapState.tiles = tileLayer().addTo(map);
  map.setView([searchArea.lat, searchArea.lng], 11);
  fitSearchArea();
  darkQuery.addEventListener("change", renderMarkers);

  // Labels sit on the side facing away from the other anchors, so close anchors never overlap.
  const meanLng = criteria.anchors.reduce((sum, a) => sum + a.lng, 0) / criteria.anchors.length;
  for (const a of criteria.anchors) {
    const side = a.lng < meanLng ? "left" : "right";
    const label = el("span", { class: `anchor ${side}` }, el("i", { class: "anchor-dot" }), el("span", { class: "anchor-label", text: a.label }));
    L.marker([a.lat, a.lng], {
      icon: L.divIcon({ className: "", html: label.outerHTML, iconSize: [0, 0] }),
      keyboard: false, zIndexOffset: 1000,
    }).bindTooltip(a.name, { direction: "top", offset: [0, -8] }).addTo(map);
  }

  const legend = [];
  try {
    const res = await fetch("/isochrone.geojson");
    if (res.ok) {
      const geo = await res.json();
      // One soft shape per anchor; where they overlap (both commutes fit) the shading deepens.
      L.geoJSON(geo, {
        interactive: false,
        style: { color: cssVar("--accent"), weight: 1.5, opacity: 0.7, fillColor: cssVar("--accent"), fillOpacity: 0.08 },
      }).addTo(map);
      const p = geo.features[0]?.properties;
      const anchors = geo.features.map((f) => f.properties.anchor).join(" & ");
      if (p) legend.push(el("span", {}, el("i", { class: "swatch" }), `≤ ${p.minutes} min by e-bike to ${anchors}`));
    }
  } catch { /* the overlay is optional */ }
  legend.push(el("span", {}, el("i", { class: "pin", style: `background:${cssVar("--accent")}` }), "new"));
  legend.push(el("span", {}, el("i", { class: "pin", style: `background:${cssVar("--gold")}` }), "interested"));
  legend.push(el("span", {}, el("i", { class: "pin", style: `background:${cssVar("--danger")}` }), "rejected"));
  $("#legend").replaceChildren(...legend);
  renderMarkers();
}

// A map created inside a hidden pane (phone layout) has no size yet; fit once it is visible.
function fitSearchArea() {
  const { map } = mapState;
  if (!map || mapState.fitted || map.getContainer().clientWidth === 0) return;
  const { searchArea } = state.config;
  map.fitBounds(L.latLng(searchArea.lat, searchArea.lng).toBounds(searchArea.radiusM * 1.5));
  mapState.fitted = true;
}

function markerColor(l) {
  if (l.stage === "rejected") return cssVar("--danger");
  if (l.triage === "interested") return cssVar("--gold");
  if (l.triage === "new") return cssVar("--accent");
  return cssVar("--muted");
}

function renderMarkers() {
  const { map } = mapState;
  if (!map) return;
  mapState.layer?.remove();
  mapState.markers.clear();
  const layer = L.layerGroup();
  for (const l of visibleListings()) {
    if (l.lat == null || l.lng == null) continue;
    const m = L.circleMarker([l.lat, l.lng], {
      radius: 7, weight: 2, color: cssVar("--surface"), fillColor: markerColor(l), fillOpacity: 1,
    });
    const price = rent(l);
    m.bindTooltip(`${price != null ? `${Math.round(price)} € · ` : ""}${l.bike_minutes != null ? `${Math.round(l.bike_minutes)} min` : ""}`, { direction: "top", offset: [0, -6] });
    m.on("click", () => focusCard(l.id));
    m.addTo(layer);
    mapState.markers.set(l.id, m);
  }
  mapState.layer = layer.addTo(map);
}

function highlightMarker(id, on) {
  const m = mapState.markers.get(id);
  if (!m) return;
  m.setStyle({ radius: on ? 11 : 7 });
  if (on) m.bringToFront();
}

function focusCard(id) {
  const layout = $("#layout");
  if (layout.dataset.pane === "map") setPane("list");
  const card = document.querySelector(`.card[data-id="${id}"]`);
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.remove("is-flash");
  void card.offsetWidth;
  card.classList.add("is-flash");
}

function setPane(pane) {
  const layout = $("#layout");
  layout.dataset.pane = pane;
  const toggle = $("#pane-toggle");
  toggle.setAttribute("aria-label", pane === "map" ? "Show list" : "Show map");
  toggle.replaceChildren(icon(pane === "map" ? "list" : "map"));
  if (pane === "map") {
    setTimeout(() => {
      mapState.map?.invalidateSize();
      fitSearchArea();
    }, 0);
  }
}

// --- actions -------------------------------------------------------------------------------------
function openSettings(message) {
  $("#token").value = saved.get("apiToken") ?? "";
  const writesDisabled = state.config?.writesEnabled === false;
  $("#writes-disabled").hidden = !writesDisabled;
  // A toast would sit under the modal backdrop, so the reason is shown inside the dialog.
  const msg = $("#settings-msg");
  msg.textContent = message ?? "";
  msg.hidden = !message || writesDisabled;
  $("#settings").showModal();
}

async function setTriage(l, triage, { quiet = false } = {}) {
  const previous = l.triage;
  l.triage = triage;
  render();
  const res = await api(`/api/listings/${l.id}/triage`, { method: "POST", body: { triage } });
  if (res.ok) return;
  l.triage = previous;
  render();
  if (quiet) return;
  if (res.status === 401 || res.status === 503) openSettings(res.data?.error);
  else toast(res.data?.error ?? "Could not save that change.");
}

async function searchNow() {
  const btn = $("#search-btn");
  btn.disabled = true;
  try {
    const res = await api("/api/run", { method: "POST" });
    if (res.ok) {
      toast("Search started. New matches appear here in a minute or two.");
      await refresh();
    } else if (res.status === 401 || res.status === 503) openSettings(res.data?.error);
    else toast(res.data?.error ?? "Could not start a search.");
  } finally {
    btn.disabled = false;
  }
}

// --- data loop -----------------------------------------------------------------------------------
function render() {
  if (!state.tab) state.tab = saved.get("tab") ?? (state.listings.some((l) => l.triage === "new") ? "new" : "matches");
  renderTabs();
  const items = visibleListings();
  $("#cards").replaceChildren(...items.map(renderCard));
  renderEmpty(items.length);
  renderMarkers();
}

let pollTimer = 0;
async function refresh() {
  clearTimeout(pollTimer);
  try {
    const [listings, runs] = await Promise.all([api("/api/listings"), api("/api/runs")]);
    if (listings.ok) Object.assign(state, { listings: listings.data.listings, rejected: listings.data.rejected });
    if (runs.ok) Object.assign(state, { runs: runs.data.runs, nextRunAt: runs.data.nextRunAt });
    render();
    renderStatus();
    if ($("#runs").open) renderRunsTable();
  } catch {
    toast("Can't reach the agent right now; retrying.");
  }
  const busy = ["queued", "running"].includes(state.runs[0]?.status);
  pollTimer = setTimeout(refresh, busy ? POLL_BUSY_MS : POLL_IDLE_MS);
}

async function boot() {
  const sort = saved.get("sort");
  if (sort && SORTS[sort]) state.sort = sort;
  $("#sort").value = state.sort;
  $("#sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    saved.set("sort", state.sort);
    render();
  });
  $("#search-btn").addEventListener("click", searchNow);
  $("#settings-btn").addEventListener("click", () => openSettings());
  $("#settings").addEventListener("close", () => {
    if ($("#settings").returnValue === "save") {
      saved.set("apiToken", $("#token").value.trim());
      toast("Token saved in this browser.");
    }
  });
  $("#run-status").addEventListener("click", () => {
    renderRunsTable();
    $("#runs").showModal();
  });
  $("#pane-toggle").addEventListener("click", () => setPane($("#layout").dataset.pane === "map" ? "list" : "map"));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });

  const config = await api("/api/config");
  if (config.ok) {
    state.config = config.data;
    renderCriteria();
  }
  await refresh();
  await initMap();
}

boot();
