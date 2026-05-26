/* ================================================================
   Bee Ausschreibungen — Bee digital growth
   ================================================================ */

"use strict";

// ── State ──────────────────────────────────────────────────────────
const state = {
  allTenders: [],
  filtered: [],
  filters: {
    search: "",
    source: "all",
    country: "all",
    status: "all",
    categories: new Set(),
  },
  sort: "status",
};

// All categories encountered in data
const allCategories = new Set();

// ── DOM refs ───────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const grid = $("tender-grid");
const emptyState = $("empty-state");
const visibleCount = $("visible-count");
const totalEl = $("count-total");
const simapEl = $("count-simap");
const dtvpEl = $("count-dtvp");
const updateLabel = $("update-label");
const catPillsEl = $("cat-pills");
const activeFiltersEl = $("active-filters");
const resetBtn = $("reset-btn");

// ── Utility ────────────────────────────────────────────────────────
function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDate(str) {
  if (!str) return "—";
  try {
    // Handle DD.MM.YYYY
    if (str.includes(".")) {
      const [d, m, y] = str.split(".");
      return new Date(`${y}-${m}-${d}`).toLocaleDateString("de-CH", {
        day: "2-digit", month: "short", year: "numeric"
      });
    }
    return new Date(str).toLocaleDateString("de-CH", {
      day: "2-digit", month: "short", year: "numeric"
    });
  } catch {
    return str;
  }
}

function parseDeadline(deadlineStr) {
  if (!deadlineStr) return null;
  try {
    if (deadlineStr.includes(".")) {
      const [day, month, year] = deadlineStr.split(".");
      const d = new Date(`${year}-${month}-${day}`);
      return isNaN(d) ? null : d;
    }
    const d = new Date(deadlineStr);
    return isNaN(d) ? null : d;
  } catch {
    return null;
  }
}

function getDaysLeft(deadlineStr) {
  const d = parseDeadline(deadlineStr);
  if (!d) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return Math.floor((d - today) / 86400000);
}

/** Compute live status from the actual deadline date — ignores JSON status field */
function liveStatus(tender) {
  const days = getDaysLeft(tender.deadline);
  if (days === null) return "open";     // no deadline = assume open
  if (days < 0)  return "closed";
  if (days <= 7) return "closing";
  return "open";
}

function formatTimestamp(isoStr) {
  try {
    return new Date(isoStr).toLocaleDateString("de-CH", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit"
    });
  } catch {
    return isoStr;
  }
}

// ── Render category pills ──────────────────────────────────────────
function renderCategoryPills() {
  const cats = [...allCategories].sort();
  catPillsEl.innerHTML = cats.map(cat => `
    <button class="cat-pill${state.filters.categories.has(cat) ? " active" : ""}"
            data-cat="${esc(cat)}">${esc(cat)}</button>
  `).join("");

  catPillsEl.querySelectorAll(".cat-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      const cat = btn.dataset.cat;
      if (state.filters.categories.has(cat)) {
        state.filters.categories.delete(cat);
        btn.classList.remove("active");
      } else {
        state.filters.categories.add(cat);
        btn.classList.add("active");
      }
      applyAndRender();
    });
  });
}

// ── Card rendering ─────────────────────────────────────────────────
function statusText(status, daysLeft) {
  if (status === "closed") return "Abgelaufen";
  if (daysLeft === null) return "Offen";
  if (daysLeft === 0) return "Heute";
  if (daysLeft === 1) return "Morgen";
  if (daysLeft <= 7) return `${daysLeft}d`;
  return "Offen";
}

function renderCard(t) {
  const days = getDaysLeft(t.deadline);
  const isUrgent = days !== null && days >= 0 && days <= 7;
  const status = liveStatus(t);   // always computed live

  const statusLabel = {
    open: "Offen",
    closing: "Läuft ab",
  }[status] || "Offen";

  const metaItems = [
    t.authority && `
      <span class="meta-item">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M2 14V6l6-4 6 4v8"/>
          <rect x="5" y="9" width="2.5" height="5"/>
          <rect x="8.5" y="9" width="2.5" height="5"/>
        </svg>
        ${esc(t.authority)}
      </span>`,
    t.location && `
      <span class="meta-item">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8" cy="6.5" r="3"/>
          <path d="M8 15s5-4.5 5-8.5a5 5 0 0 0-10 0c0 4 5 8.5 5 8.5z"/>
        </svg>
        ${esc(t.location)}, ${esc(t.country)}
      </span>`,
    t.value && `<span class="meta-item meta-value">${esc(t.value)}</span>`,
  ].filter(Boolean).join("");

  const categories = (t.categories || [])
    .map(c => `<span class="cat-tag">${esc(c)}</span>`)
    .join("");

  const deadlineFmt = formatDate(t.deadline);
  const deadlineDays = days !== null && days >= 0
    ? `<span class="deadline-days${isUrgent ? " urgent" : ""}">noch ${days} Tag${days !== 1 ? "e" : ""}</span>`
    : days !== null && days < 0
    ? `<span class="deadline-days" style="color:var(--closed)">abgelaufen</span>`
    : "";

  return `
    <article class="tender-card source-${t.source}" data-id="${esc(t.id)}">
      <div class="card-top">
        <span class="source-badge ${t.source}">${t.source === "simap" ? "SIMAP.ch" : "DTVP.de"}</span>
        <span class="status-badge ${status}">
          <span class="status-dot"></span>${statusLabel}
        </span>
      </div>

      <h3 class="card-title">${esc(t.title)}</h3>

      <div class="card-meta">${metaItems}</div>

      <p class="card-desc">${esc(t.description)}</p>

      <div class="card-cats">${categories}</div>

      <div class="card-footer">
        <div class="deadline-block">
          <span class="deadline-label">Einreichungsfrist</span>
          <span class="deadline-date${isUrgent ? " urgent" : ""}">${deadlineFmt}</span>
          ${deadlineDays}
        </div>
        <a href="${esc(t.url)}" target="_blank" rel="noopener noreferrer" class="card-link"
           aria-label="Zur Ausschreibung: ${esc(t.title)}">
          Öffnen
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M2 10L10 2M10 2H5M10 2v5"/>
          </svg>
        </a>
      </div>
    </article>
  `;
}

// ── Filter + Sort ──────────────────────────────────────────────────
function applyFilters() {
  const { search, source, country, status, categories } = state.filters;
  const q = search.toLowerCase();

  state.filtered = state.allTenders.filter(t => {
    // Compute real-time status from deadline — never trust JSON status field
    const currentStatus = liveStatus(t);

    // Always exclude expired tenders regardless of what the JSON says
    if (currentStatus === "closed") return false;

    if (q && ![t.title, t.description, t.authority, ...(t.categories || [])]
              .some(s => (s || "").toLowerCase().includes(q))) return false;
    if (source !== "all" && t.source !== source) return false;
    if (country !== "all" && t.country !== country) return false;
    if (status !== "all" && currentStatus !== status) return false;
    if (categories.size > 0 && !t.categories?.some(c => categories.has(c))) return false;
    return true;
  });
}

function sortTenders() {
  const s = state.sort;
  state.filtered.sort((a, b) => {
    if (s === "status") {
      const order = { open: 0, closing: 1, closed: 2 };
      const so = (order[liveStatus(a)] ?? 3) - (order[liveStatus(b)] ?? 3);
      if (so !== 0) return so;
      return (a.deadline || "9999").localeCompare(b.deadline || "9999");
    }
    if (s === "deadline") {
      return (a.deadline || "9999").localeCompare(b.deadline || "9999");
    }
    if (s === "published") {
      return (b.published || "").localeCompare(a.published || "");
    }
    if (s === "value") {
      const parse = v => parseFloat((v || "0").replace(/[^\d.]/g, "")) || 0;
      return parse(b.value) - parse(a.value);
    }
    return 0;
  });
}

function applyAndRender() {
  applyFilters();
  sortTenders();
  renderGrid();
  renderActiveFilters();
  updateResetBtn();
}

// ── Grid ───────────────────────────────────────────────────────────
function renderGrid() {
  visibleCount.textContent = state.filtered.length;

  if (state.filtered.length === 0) {
    grid.innerHTML = "";
    emptyState.style.display = "block";
    return;
  }
  emptyState.style.display = "none";

  grid.innerHTML = state.filtered.map(renderCard).join("");

  // Staggered animation
  grid.querySelectorAll(".tender-card").forEach((card, i) => {
    card.style.animationDelay = `${Math.min(i * 35, 400)}ms`;
  });
}

// ── Active filters display ─────────────────────────────────────────
function renderActiveFilters() {
  const tags = [];
  if (state.filters.search) {
    tags.push(`<span class="active-filter-tag">
      „${esc(state.filters.search)}"
      <button onclick="clearSearch()" title="Entfernen">×</button>
    </span>`);
  }
  if (state.filters.source !== "all") {
    tags.push(`<span class="active-filter-tag">
      ${esc(state.filters.source.toUpperCase())}
      <button onclick="clearFilter('source')" title="Entfernen">×</button>
    </span>`);
  }
  if (state.filters.country !== "all") {
    tags.push(`<span class="active-filter-tag">
      ${state.filters.country === "CH" ? "🇨🇭" : "🇩🇪"} ${esc(state.filters.country)}
      <button onclick="clearFilter('country')" title="Entfernen">×</button>
    </span>`);
  }
  if (state.filters.status !== "all") {
    tags.push(`<span class="active-filter-tag">
      ${esc({ open: "Offen", closing: "Läuft ab", closed: "Abgelaufen" }[state.filters.status] || state.filters.status)}
      <button onclick="clearFilter('status')" title="Entfernen">×</button>
    </span>`);
  }
  state.filters.categories.forEach(cat => {
    tags.push(`<span class="active-filter-tag">
      ${esc(cat)}
      <button onclick="clearCategory('${esc(cat)}')" title="Entfernen">×</button>
    </span>`);
  });
  activeFiltersEl.innerHTML = tags.join("");
}

function updateResetBtn() {
  const hasFilter =
    state.filters.search ||
    state.filters.source !== "all" ||
    state.filters.country !== "all" ||
    state.filters.status !== "all" ||
    state.filters.categories.size > 0;
  resetBtn.style.display = hasFilter ? "inline-flex" : "none";
}

// Global reset helpers
window.clearSearch = () => {
  state.filters.search = "";
  $("search-input").value = "";
  applyAndRender();
};
window.clearFilter = (key) => {
  state.filters[key] = "all";
  // Deactivate pill
  const group = $(`filter-${key}`);
  if (group) {
    group.querySelectorAll(".pill").forEach(p => {
      p.classList.toggle("active", p.dataset.value === "all");
    });
  }
  applyAndRender();
};
window.clearCategory = (cat) => {
  state.filters.categories.delete(cat);
  catPillsEl.querySelectorAll(".cat-pill").forEach(p => {
    if (p.dataset.cat === cat) p.classList.remove("active");
  });
  applyAndRender();
};
window.resetAll = () => {
  state.filters.search = "";
  state.filters.source = "all";
  state.filters.country = "all";
  state.filters.status = "all";
  state.filters.categories.clear();
  $("search-input").value = "";
  document.querySelectorAll(".pill").forEach(p =>
    p.classList.toggle("active", p.dataset.value === "all")
  );
  catPillsEl.querySelectorAll(".cat-pill").forEach(p => p.classList.remove("active"));
  applyAndRender();
};

// ── Pill filter setup ──────────────────────────────────────────────
function setupPills(groupId, filterKey) {
  const group = $(groupId);
  if (!group) return;
  group.querySelectorAll(".pill").forEach(btn => {
    btn.addEventListener("click", () => {
      group.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      state.filters[filterKey] = btn.dataset.value;
      applyAndRender();
    });
  });
}

// ── Header counters ────────────────────────────────────────────────
function animateCounter(el, target) {
  let cur = 0;
  const step = Math.ceil(target / 20);
  const interval = setInterval(() => {
    cur = Math.min(cur + step, target);
    el.textContent = cur;
    if (cur >= target) clearInterval(interval);
  }, 30);
}

// ── Load data ──────────────────────────────────────────────────────
async function loadData() {
  try {
    const res = await fetch("./data/tenders.json?v=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Update header stats
    animateCounter(totalEl, data.total || 0);
    animateCounter(simapEl, data.sources?.simap || 0);
    animateCounter(dtvpEl, data.sources?.dtvp || 0);
    updateLabel.textContent = "Aktualisiert: " + formatTimestamp(data.updated);

    // Collect categories
    (data.tenders || []).forEach(t => {
      (t.categories || []).forEach(c => allCategories.add(c));
    });
    allCategories.forEach(c => allCategories.add(c)); // noop — just ensuring Set is stable

    state.allTenders = data.tenders || [];
    renderCategoryPills();
    applyAndRender();

  } catch (err) {
    console.error("Failed to load tenders:", err);
    grid.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:60px 20px;">
        <p style="font-size:15px;font-weight:600;color:var(--text-1);margin-bottom:8px">Daten konnten nicht geladen werden.</p>
        <p style="font-family:var(--mono);font-size:11px;color:var(--text-3);margin-bottom:20px">${esc(err.message)}</p>
        <button onclick="loadData()" class="reset-btn" style="margin:0 auto">Erneut versuchen</button>
      </div>`;
  }
}

// ── Init ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadData();

  // Search
  const searchInput = $("search-input");
  let searchTimer;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.search = searchInput.value.trim();
      applyAndRender();
    }, 250);
  });

  // Keyboard shortcut ⌘K / Ctrl+K
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
    if (e.key === "Escape" && document.activeElement === searchInput) {
      searchInput.blur();
    }
  });

  // Pill filters
  setupPills("filter-source", "source");
  setupPills("filter-country", "country");
  setupPills("filter-status", "status");

  // Sort
  $("sort-select").addEventListener("change", e => {
    state.sort = e.target.value;
    applyAndRender();
  });

  // Reset
  resetBtn.addEventListener("click", window.resetAll);
});
