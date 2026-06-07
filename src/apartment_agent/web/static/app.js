"use strict";

// --- tiny fetch helpers ----------------------------------------------------
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : null,
  });
  return r;
}

// --- formatting ------------------------------------------------------------
function eur(v) { return v == null ? null : `${Math.round(v)} €`; }
function fmtPrice(c) {
  const warm = c.price_warm != null ? `${Math.round(c.price_warm)} € warm` : null;
  const cold = c.price_cold != null ? `${Math.round(c.price_cold)} € kalt` : null;
  const listed = c.price_listed != null ? `${Math.round(c.price_listed)} €` : null;
  return warm || cold || listed || "? €";
}
function fmtWhen(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}
function fmtClock(secs) {
  if (secs < 0) secs = 0;
  const m = Math.floor(secs / 60), s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

// --- rendering -------------------------------------------------------------
const grid = document.getElementById("grid");
const tpl = document.getElementById("card-tpl");

function renderCards(listings) {
  grid.innerHTML = "";
  document.getElementById("empty").classList.toggle("hidden", listings.length > 0);
  for (const c of listings) {
    const node = tpl.content.cloneNode(true);
    const card = node.querySelector(".card");
    card.classList.toggle("is-new", c.is_new);
    card.classList.add(`status-${c.status}`);

    const title = node.querySelector(".title");
    title.textContent = c.title;
    title.href = c.url || "#";

    node.querySelector(".fit").innerHTML =
      c.fit_score != null ? `fit <b>${c.fit_score}</b>/100` : "";

    const where = [c.district, c.city].filter(Boolean).join(" · ");
    const bits = [fmtPrice(c)];
    if (c.size_sqm != null) bits.push(`${Math.round(c.size_sqm)} m²`);
    if (c.listing_type) bits.push(c.listing_type);
    const avail = c.available_from ? ` · ab ${c.available_from}` : "";
    node.querySelector(".meta").innerHTML =
      `<span class="price">${bits.join(" · ")}</span>` +
      (where ? `<br>📍 ${where}${avail}` : avail);

    node.querySelector(".summary").textContent = c.summary || "";

    node.querySelectorAll(".actions button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.status === c.status);
      btn.onclick = () => setStatus(c.key, btn.dataset.status);
    });
    grid.appendChild(node);
  }
}

async function setStatus(key, status) {
  const r = await postJSON("/api/listings/status", { key, status });
  if (r.ok) loadListings();
}

async function loadListings() {
  try {
    const { listings } = await getJSON("/api/listings");
    renderCards(listings);
  } catch (e) { console.error(e); }
}

// --- status banner + auto-search timer -------------------------------------
let wasRunning = false;
let autoMinutes = 0;
let nextSearchAt = null; // epoch ms

function setReport(text, run) {
  const badge = document.getElementById("report-badge");
  badge.textContent = text;
  badge.className = "badge " + ((run && (run.new || 0) > 0) ? "fresh" : "none");
}

async function loadStatus() {
  let s;
  try { s = await getJSON("/api/status"); } catch (e) { console.error(e); return; }

  setReport(s.report, s.last_run);
  document.getElementById("last-activity").textContent =
    "last activity: " + fmtWhen(s.last_activity);

  const running = s.agent && s.agent.running;
  const stateEl = document.getElementById("agent-state");
  stateEl.innerHTML = running ? '<span class="spin"></span> searching…'
                    : (s.agent && s.agent.last_error ? "last run errored" : "idle");
  document.getElementById("search-btn").disabled = running;

  if (autoMinutes === 0 && s.auto_search_minutes > 0) {
    autoMinutes = s.auto_search_minutes;
    if (!nextSearchAt) nextSearchAt = Date.now() + autoMinutes * 60000;
  }

  // a run just finished -> refresh listings + reset the auto timer
  if (wasRunning && !running) {
    loadListings();
    if (autoMinutes > 0) nextSearchAt = Date.now() + autoMinutes * 60000;
  }
  wasRunning = running;
}

async function triggerSearch(manual) {
  const r = await postJSON("/api/search");
  if (r.status === 409) return; // already running
  if (autoMinutes > 0) nextSearchAt = Date.now() + autoMinutes * 60000;
  if (manual) loadStatus();
}

function tickCountdown() {
  const el = document.getElementById("countdown");
  if (!nextSearchAt || autoMinutes === 0) { el.textContent = ""; return; }
  const secs = Math.round((nextSearchAt - Date.now()) / 1000);
  if (secs <= 0 && !wasRunning) { triggerSearch(false); el.textContent = "next search: 0:00"; return; }
  el.textContent = "next search: " + fmtClock(secs);
}

document.getElementById("search-btn").onclick = () => triggerSearch(true);

// initial load + polling loops
loadListings();
loadStatus();
setInterval(loadStatus, 4000);
setInterval(tickCountdown, 1000);
