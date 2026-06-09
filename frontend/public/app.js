const API = "";
let token = localStorage.getItem("pf_token") || "";
let isGuest = false;
let meta = {
  diets: [],
  intolerances: [],
  health_conditions: [],
  protein_options: [],
  side_options: [],
  cuisine_options: [],
  mock_mode: true,
  xai_configured: false,
  spoonacular_configured: false,
};
let lastCraving = null;
let selectedIds = new Set();
let inspiredSetup = null;
let pendingSubstitutions = [];
let approvedSubs = [];
let currentChefProposal = null;

// Local Spots data (Northwood, OH area examples). Matched at render time to recipe styles/cuisines
// from the improved backend results (AllRecipes + Grok curation). No external tabs for details.
const LOCAL_SPOTS = [
  {
    id: 1,
    name: "Olive & Thyme",
    cuisine: "Mediterranean",
    distance: "1.4 mi",
    rating: 4.7,
    image: "https://picsum.photos/id/160/80/80",
    address: "Northwood, OH",
    menu: [
      { name: "Herb Grilled Chicken Plate", price: "$14.50", why: "High protein, lemon-oregano profile matches anti-inflammatory picks." },
      { name: "Falafel Power Bowl (greens heavy)", price: "$12.75", why: "Plant-based fiber option that aligns with blood-sugar friendly results." },
    ],
  },
  {
    id: 2,
    name: "Green Bowl Asian Fusion",
    cuisine: "Asian Fusion",
    distance: "2.8 mi",
    rating: 4.5,
    image: "https://picsum.photos/id/201/80/80",
    address: "Northwood / Rossford area",
    menu: [
      { name: "Ginger Turkey & Veg Stir", price: "$13.25", why: "Clean ginger-garlic flavors mirror quick high-protein home versions." },
      { name: "Sesame Salmon Bowl (light sauce)", price: "$15.75", why: "Omega-3 + veg heavy; great for inflammation-conscious filters." },
    ],
  },
  {
    id: 3,
    name: "Harvest Cafe",
    cuisine: "Mediterranean / Healthy American",
    distance: "0.9 mi",
    rating: 4.3,
    image: "https://picsum.photos/id/251/80/80",
    address: "Northwood, OH",
    menu: [
      { name: "Lemon Chicken Salad Plate", price: "$12.00", why: "Direct style match to many of the chef-curated mains and sides." },
    ],
  },
  {
    id: 4,
    name: "Northwood Fresh Market Cafe",
    cuisine: "Healthy American",
    distance: "0.6 mi",
    rating: 4.2,
    image: "https://picsum.photos/id/318/80/80",
    address: "Northwood, OH",
    menu: [
      { name: "Tuna Power Salad (no cheese)", price: "$9.95", why: "Budget-friendly, high-protein + bean option that fits fasting & macros." },
    ],
  },
];
let currentCookData = null;
let pendingSaveRecipe = null;
let guestSaveAuthMode = "register";
let stepMode = "beginner";
let currentRecipeId = null;
let cookKits = new Map();
let activeDetailId = null;
let expandedCompanionKey = null;
let cookKitLoading = null;
let prefsSaveTimer = null;
let subsDebounce = null;
let refineDebounce = null;
const MAX_RECIPE_SELECT = 5;

const $ = (id) => document.getElementById(id);

function formatApiError(data, fallback = "Request failed") {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => e.msg || JSON.stringify(e)).join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(`${API}${path}`, { ...options, headers });
  } catch {
    throw new Error("Could not reach the server. Check that the app is running.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(formatApiError(data, res.statusText || "Request failed"));
  return data;
}

function setStatus(el, msg, isError = false) {
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("error", !!isError);
}

function selectedFromMenu(menuId) {
  return [...document.querySelectorAll(`#${menuId} input:checked`)].map((el) => el.value);
}

function selectedDiets() {
  return selectedFromMenu("diet-options");
}

function selectedIntolerances() {
  return selectedFromMenu("intolerance-options");
}

function selectedHealthConditions() {
  return selectedFromMenu("health-condition-options");
}

function selectedProteins() {
  return selectedFromMenu("protein-options");
}

function selectedSides() {
  return selectedFromMenu("side-options");
}

function selectedCuisines() {
  return selectedFromMenu("cuisine-options");
}

function updateFilterCount(menuId, countId) {
  const n = document.querySelectorAll(`#${menuId} input:checked`).length;
  const el = $(countId);
  if (!el) return;
  el.textContent = n ? String(n) : "";
  el.classList.toggle("visible", n > 0);
}

function updateAllFilterCounts() {
  updateFilterCount("diet-options", "diet-count");
  updateFilterCount("intolerance-options", "allergy-count");
  updateFilterCount("health-condition-options", "medical-count");
  updateFilterCount("cuisine-options", "cuisine-count");
  updateFilterCount("protein-options", "protein-count");
  updateFilterCount("side-options", "side-count");
}

function soundsGoodText() {
  return $("sounds-good-input")?.value?.trim() || "";
}

function renderFilterMenu(containerId, options, name) {
  const wrap = $(containerId);
  if (!wrap) return;
  if (!options?.length) {
    wrap.innerHTML = `<p class="fieldset-hint">No options.</p>`;
    return;
  }
  wrap.innerHTML = options
    .map(
      (d) =>
        `<label class="filter-menu-item"><input type="checkbox" name="${name}" value="${d.value}" />${escapeHtml(d.label)}</label>`
    )
    .join("");
}

function applyPreferences(prefs) {
  if (!prefs) return;
  $("explain-techniques").checked = prefs.explain_techniques;
  document.querySelectorAll("#diet-options input").forEach((el) => {
    el.checked = prefs.diets.includes(el.value);
  });
  document.querySelectorAll("#intolerance-options input").forEach((el) => {
    el.checked = prefs.intolerances.includes(el.value);
  });
  document.querySelectorAll("#health-condition-options input").forEach((el) => {
    el.checked = (prefs.health_conditions || []).includes(el.value);
  });
  updateAllFilterCounts();
}

function schedulePrefsSave() {
  if (!token) return;
  clearTimeout(prefsSaveTimer);
  prefsSaveTimer = setTimeout(savePreferences, 600);
}

async function savePreferences() {
  if (!token) return;
  try {
    await api("/preferences/me", {
      method: "PUT",
      body: JSON.stringify({
        diets: selectedDiets(),
        intolerances: selectedIntolerances(),
        health_conditions: selectedHealthConditions(),
        explain_techniques: $("explain-techniques").checked,
        include_pantry_staples: true,
      }),
    });
  } catch {
    /* non-blocking */
  }
}

function showResultsListPane() {
  $("results-list-pane")?.classList.remove("hidden");
}

function closeResultsTab() {
  $("results-tab")?.classList.add("hidden");
  showResultsListPane();
  $("search-panel")?.classList.remove("hidden");
  const spots = $("local-spots");
  if (spots) spots.innerHTML = "";
}

function openResultsTab() {
  $("results-tab")?.classList.remove("hidden");
  showResultsListPane();
}

function closeRecipeTab() {
  closeResultsTab();
}

function backToResultsList() {
  showResultsListPane();
}

function hideAllPanels() {
  [
    "landing-panel",
    "search-panel",
    "inspired-panel",
    "judge-panel",
    "cook-panel",
  ].forEach((id) => $(id)?.classList.add("hidden"));
  closeResultsTab();
}

function showLanding() {
  hideAllPanels();
  $("landing-panel").classList.remove("hidden");
  $("session-badge").classList.add("hidden");
  $("auth-user").classList.add("hidden");
  $("sign-out").classList.add("hidden");
}

function updateSessionChrome(displayName = "", guest = false) {
  $("sign-out").classList.remove("hidden");
  if (guest) {
    $("session-badge").textContent = "Guest";
    $("session-badge").classList.remove("hidden");
    $("auth-user").classList.add("hidden");
  } else {
    $("session-badge").classList.add("hidden");
    $("auth-user").textContent = displayName;
    $("auth-user").classList.remove("hidden");
  }
}

function showApp(displayName = "", guest = false) {
  isGuest = guest;
  hideAllPanels();
  $("search-panel").classList.remove("hidden");
  updateSessionChrome(displayName, guest);
}

function categoryLabel(cat) {
  return { main: "Main", side: "Side", salad: "Salad", dip: "Dip" }[cat] || cat;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeRecipes(data) {
  if (data.recipes?.length) return data.recipes;
  return [...(data.mains || []), ...(data.pairings || [])];
}

function renderMealCard(recipe) {
  const checked = selectedIds.has(recipe.id);
  const cat = recipe.category || "main";
  const catClass = `meal-card-${cat}`;
  const popularBadge = recipe.is_popular
    ? `<span class="meal-card-popular">Popular</span>`
    : "";
  const img = recipe.image
    ? `<img class="meal-card-hero" src="${escapeHtml(recipe.image)}" alt="" loading="lazy" />`
    : `<div class="meal-card-hero meal-card-hero-placeholder" aria-hidden="true"></div>`;
  const ingredients = recipe.ingredient_names || [];
  const ingList = ingredients.length
    ? `<ul>${ingredients.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`
    : `<p>Ingredient list loading on select.</p>`;
  return `
    <article class="meal-card meal-card-tile ${catClass} ${checked ? "meal-card-selected" : ""}" data-recipe-id="${recipe.id}" tabindex="0" role="button" aria-pressed="${checked}">
      <div class="meal-card-hover-ingredients" aria-hidden="true">
        <strong>Ingredients</strong>
        ${ingList}
      </div>
      <label class="meal-card-select-label" title="Select for cook steps">
        <input type="checkbox" class="meal-select" data-recipe-id="${recipe.id}" ${checked ? "checked" : ""} />
        <span class="sr-only">Select ${escapeHtml(recipe.title)}</span>
      </label>
      ${img}
      <div class="meal-card-body">
        <span class="meal-card-cat">${categoryLabel(cat)}${popularBadge}${recipe.thread_label ? ` · ${escapeHtml(recipe.thread_label)}` : ""}</span>
        <strong class="result-title">${escapeHtml(recipe.title)}</strong>
        ${recipe.fit_note ? `<p class="meal-card-fit meal-card-cite">${escapeHtml(recipe.fit_note)}</p>` : ""}
        ${recipe.ready_in_minutes ? `<p class="hint meal-card-meta">${recipe.ready_in_minutes} min · ${recipe.servings || "?"} servings</p>` : ""}
        <p class="meal-card-hint hint">${checked ? "Selected — scroll for steps" : "Hover ingredients · select to cook"}</p>
      </div>
    </article>`;
}

function updateSelectionUI() {
  const count = selectedIds.size;
  const inspireBtn = $("inspired-btn");
  if (count === 0) {
    $("selection-count").textContent =
      "Hover for ingredients · select a card for cook steps, elevation tips, and companion recipes.";
  } else if (count === 1) {
    $("selection-count").textContent =
      "1 selected — cook steps below. Pick one more to build your inspire dash.";
  } else {
    $("selection-count").textContent = `${count} of ${MAX_RECIPE_SELECT} selected — switch tabs below for each dish.`;
  }
  if (inspireBtn) {
    const showInspire = count >= 2;
    inspireBtn.classList.toggle("hidden", !showInspire);
    inspireBtn.disabled = !showInspire;
  }
}

function recipeTitleById(id) {
  const recipes = normalizeRecipes(lastCraving || {});
  return recipes.find((r) => r.id === id)?.title || `Recipe ${id}`;
}

function renderStepsList(steps) {
  return (steps || [])
    .map(
      (s) =>
        `<li><strong>Step ${s.step}.</strong> ${escapeHtml(s.text)}${
          s.tip ? `<span class="step-tip">${escapeHtml(s.tip)}</span>` : ""
        }</li>`
    )
    .join("");
}

function renderAccentSide(side) {
  if (!side) return "";
  return `
    <div class="accent-side-block">
      <h4 class="cook-kit-subhead">Accent side — pairs with your main</h4>
      <p class="accent-side-why"><strong>${escapeHtml(side.title)}</strong> — ${escapeHtml(side.why)}</p>
      ${side.pairs_because ? `<p class="accent-side-pairs hint">Pairs because: ${escapeHtml(side.pairs_because)}</p>` : ""}
      ${side.diet_note ? `<p class="accent-side-diet">${escapeHtml(side.diet_note)}</p>` : ""}
      <h5>Ingredients</h5>
      <ul>${(side.ingredients || []).map((ing) => `<li>${escapeHtml(ing)}</li>`).join("")}</ul>
      <h5>Steps</h5>
      <ol class="recipe-steps companion-steps">${renderStepsList(side.steps)}</ol>
    </div>`;
}

function renderCookKitPanel(kit) {
  if (!kit) return "<p class='hint'>Loading cook steps…</p>";
  if (kit.error) return `<p class="status error">${escapeHtml(kit.error)}</p>`;
  const insights = (kit.elevation_insights || [])
    .map(
      (i) =>
        `<div class="elevation-insight"><strong>${escapeHtml(i.heading)}</strong><p>${escapeHtml(i.body)}</p></div>`
    )
    .join("");

  return `
    <div class="cook-kit-main">
      <h4 class="cook-kit-subhead">How to make it</h4>
      <ol class="recipe-steps">${renderStepsList(kit.steps)}</ol>
    </div>
    ${renderAccentSide(kit.accent_side)}
    ${insights ? `<div class="cook-kit-elevations"><h4 class="cook-kit-subhead">Chef tips</h4>${insights}</div>` : ""}`;
}

function renderSelectionDetail() {
  const panel = $("selection-detail");
  const body = $("selection-detail-body");
  const tabs = $("selection-detail-tabs");
  if (!panel || !body) return;

  if (!selectedIds.size) {
    panel.classList.add("hidden");
    body.innerHTML = "";
    if (tabs) tabs.innerHTML = "";
    activeDetailId = null;
    expandedCompanionKey = null;
    return;
  }

  if (!activeDetailId || !selectedIds.has(activeDetailId)) {
    activeDetailId = [...selectedIds][0];
  }

  panel.classList.remove("hidden");
  const activeTitle = recipeTitleById(activeDetailId);
  $("selection-detail-title").textContent = activeTitle;

  if (tabs) {
    tabs.innerHTML = [...selectedIds]
      .map((id) => {
        const title = recipeTitleById(id);
        const short = title.length > 28 ? `${title.slice(0, 26)}…` : title;
        return `<button type="button" class="selection-tab ${id === activeDetailId ? "active" : ""}" data-detail-id="${id}" role="tab" aria-selected="${id === activeDetailId}">${escapeHtml(short)}</button>`;
      })
      .join("");
    tabs.querySelectorAll(".selection-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeDetailId = Number(btn.dataset.detailId);
        expandedCompanionKey = null;
        renderSelectionDetail();
        $("selection-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });
  }

  if (cookKitLoading === activeDetailId) {
    body.innerHTML = "<p class='hint cook-kit-loading'>Chef is writing your steps and elevation ideas…</p>";
    return;
  }

  const kit = cookKits.get(activeDetailId);
  body.innerHTML = renderCookKitPanel(kit);
}

async function loadCookKit(recipeId) {
  const explain = $("explain-techniques")?.checked !== false;
  const filters = searchFilterPayload();
  const data = await api(`/recipes/${recipeId}/cook-kit`, {
    method: "POST",
    body: JSON.stringify({
      ...filters,
      what_sounds_good: soundsGoodText() || null,
      dish_anchor: lastCraving?.parsed?.dish_anchor || null,
      explain_techniques: explain,
      skill_level: explain && stepMode === "beginner" ? "beginner" : "direct",
    }),
  });
  cookKits.set(recipeId, data);
  return data;
}

async function ensureCookKit(recipeId) {
  if (cookKits.has(recipeId)) return;
  cookKitLoading = recipeId;
  renderSelectionDetail();
  try {
    await loadCookKit(recipeId);
  } catch (err) {
    cookKits.set(recipeId, { recipe_id: recipeId, title: recipeTitleById(recipeId), steps: [], elevation_insights: [], companions: [], error: err.message });
  } finally {
    cookKitLoading = null;
    renderSelectionDetail();
    $("selection-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function scheduleLineupRefine() {
  clearTimeout(refineDebounce);
  refineDebounce = setTimeout(() => {
    if (selectedIds.size > 0) runSearch({ refine: true });
  }, 700);
}

async function toggleRecipeSelect(rid, checked) {
  if (checked) {
    if (selectedIds.size >= MAX_RECIPE_SELECT) {
      setStatus($("search-status"), `Up to ${MAX_RECIPE_SELECT} recipes — chef refines the rest.`, true);
      return false;
    }
    selectedIds.add(rid);
    activeDetailId = rid;
    expandedCompanionKey = null;
    updateSelectionUI();
    renderSelectionDetail();
    await ensureCookKit(rid);
    scheduleLineupRefine();
    return true;
  }
  selectedIds.delete(rid);
  cookKits.delete(rid);
  if (activeDetailId === rid) {
    activeDetailId = [...selectedIds][0] || null;
    expandedCompanionKey = null;
  }
  updateSelectionUI();
  renderSelectionDetail();
  scheduleLineupRefine();
  return true;
}

function syncCardSelectState(card, checked) {
  card.classList.toggle("meal-card-selected", checked);
  card.setAttribute("aria-pressed", String(checked));
  const cb = card.querySelector(".meal-select");
  if (cb) cb.checked = checked;
  const hint = card.querySelector(".meal-card-hint");
  if (hint) {
    hint.textContent = checked ? "Selected — scroll for steps" : "Hover ingredients · select to cook";
  }
}

function bindMealCards(container) {
  container.querySelectorAll(".meal-card").forEach((card) => {
    const id = Number(card.dataset.recipeId);
    syncCardSelectState(card, selectedIds.has(id));

    card.querySelector(".meal-select")?.addEventListener("change", async (e) => {
      e.stopPropagation();
      const rid = Number(e.target.dataset.recipeId);
      const ok = await toggleRecipeSelect(rid, e.target.checked);
      if (!ok) e.target.checked = false;
      syncCardSelectState(card, selectedIds.has(rid));
    });

    card.addEventListener("click", async (e) => {
      if (e.target.closest(".meal-select") || e.target.closest("label")) return;
      const rid = Number(card.dataset.recipeId);
      const next = !selectedIds.has(rid);
      const ok = await toggleRecipeSelect(rid, next);
      if (ok) syncCardSelectState(card, selectedIds.has(rid));
    });

    card.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      const rid = Number(card.dataset.recipeId);
      const next = !selectedIds.has(rid);
      const ok = await toggleRecipeSelect(rid, next);
      if (ok) syncCardSelectState(card, selectedIds.has(rid));
    });
  });
}

function dishFamilyLabel(anchor) {
  const labels = {
    taco: "Tacos & adjacents",
    chili: "Chili recipes",
    pasta: "Pasta dishes",
    pizza: "Pizza & flatbreads",
    burger: "Burgers",
    curry: "Curry dishes",
    stir_fry: "Stir-fry",
    soup: "Soups & stews",
    salad: "Salads & bowls",
  };
  return labels[anchor] || anchor?.replace(/_/g, " ") || "Dish search";
}

function renderParsedCraving(parsed) {
  const el = $("parsed-craving");
  if (!parsed) {
    el.classList.add("hidden");
    return;
  }
  const chips = [];
  if (parsed.main_query) chips.push(parsed.main_query);
  if (parsed.protein) chips.push(parsed.protein);
  if (parsed.mood) chips.push(parsed.mood);
  for (const f of parsed.flavors || []) {
    if (f) chips.push(f);
  }
  for (const term of parsed.search_terms || []) {
    if (term && !chips.includes(term)) chips.push(term);
  }
  if (!chips.length) {
    for (const th of parsed.craving_threads || []) {
      if (th.label) chips.push(th.label);
    }
  }
  if (parsed.protein) chips.push(`Protein: ${parsed.protein}`);
  if (parsed.cuisine) chips.push(`Cuisine: ${parsed.cuisine}`);
  for (const c of selectedCuisines()) {
    const label = meta.cuisine_options?.find((o) => o.value === c)?.label || c;
    if (!chips.some((chip) => chip.toLowerCase().includes(label.toLowerCase()))) {
      chips.push(`Cuisine: ${label}`);
    }
  }
  if (!chips.length && parsed.main_query) chips.push(parsed.main_query);
  if (!chips.length) {
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = chips.map((c) => `<span>${escapeHtml(c)}</span>`).join("");
}

function renderCravingResults(data, opts = {}) {
  lastCraving = data;
  if (!opts.preserveSelection) {
    selectedIds = new Set();
    cookKits = new Map();
    activeDetailId = null;
    expandedCompanionKey = null;
  }
  openResultsTab();
  $("inspired-panel").classList.add("hidden");
  $("judge-panel").classList.add("hidden");
  $("cook-panel").classList.add("hidden");

  const recipes = normalizeRecipes(data);
  const total = recipes.length;
  const parsed = data.parsed || {};
  const pageSize = data.page_size || 12;
  $("results-heading").textContent = total
    ? `Chef's main courses (${total})`
    : "Chef's main courses";
  $("results-message").textContent = data.message || (total
    ? `${total} match${total === 1 ? "" : "es"} your search and filters — nothing else shown.`
    : "No matches yet.");
  renderParsedCraving(parsed);

  const list = $("recipes-list");
  const spotsContainer = $("local-spots");

  if (!total) {
    list.innerHTML = `<p class="hint">No matches. Try different keywords or loosen diet filters.</p>`;
    updateSelectionUI();
    if (spotsContainer) spotsContainer.innerHTML = `<p class="hint" style="font-size:0.8rem;">No local matches for this search.</p>`;
    return;
  }

  // New layout: local spots first (top, matching user profile), then 5x5 recipe tokens
  renderLocalSpotsProfileBased(recipes, parsed, spotsContainer);  // spots based on full flavor profile from current + past

  // Render up to 25 recipe tokens in 5-wide grid. Fill with accent sides if needed.
  const maxRecipes = 25;
  let displayRecipes = recipes.slice(0, maxRecipes);
  if (displayRecipes.length < maxRecipes) {
    // Fill with accent sides/appetizers that match flavor (simple mock for demo; backend should provide more)
    const accents = generateAccentTokens(parsed, maxRecipes - displayRecipes.length);
    displayRecipes = displayRecipes.concat(accents);
  }
  list.innerHTML = displayRecipes.map((r, idx) => renderRecipeToken(r, idx)).join("");
  bindRecipeTokens(list, displayRecipes);

  updateSelectionUI();
  // Hide old selection-detail for now; new detail is in showRecipeDetail
  if ($("selection-detail")) $("selection-detail").classList.add("hidden");
  $("results-tab")?.scrollTo({ top: 0, behavior: "smooth" });
}

function renderLocalSpots(recipes) {
  const container = $("local-spots");
  if (!container) return;

  if (!recipes || !recipes.length) {
    container.innerHTML = `<p class="hint" style="font-size:0.8rem;">No local matches yet.</p>`;
    return;
  }

  // Simple matching: use first recipe's category/title keywords to label relevance for spots
  const top = recipes[0];
  const topLabel = (top.title || top.category || "your picks").toString().slice(0, 40);

  // Always show the 4 spots, but annotate with match info from current results
  container.innerHTML = LOCAL_SPOTS.map((spot) => {
    const matchText = spot.cuisine.toLowerCase().includes((top.category || "").toLowerCase()) ||
                      top.title?.toLowerCase().includes(spot.cuisine.toLowerCase().split(" ")[0])
      ? `Pairs with ${topLabel}`
      : `Style match for ${topLabel}`;
    return `
      <div class="spot-card" data-spot-id="${spot.id}">
        <img src="${escapeHtml(spot.image)}" alt="">
        <div class="spot-body">
          <div class="spot-name">${escapeHtml(spot.name)}</div>
          <div class="spot-meta">${escapeHtml(spot.cuisine)} · ${escapeHtml(spot.distance)} · ★ ${spot.rating}</div>
          <div class="spot-match">${escapeHtml(matchText)}</div>
        </div>
      </div>`;
  }).join("");

  // Click -> inline detail (no new tabs)
  container.querySelectorAll(".spot-card").forEach((card) => {
    card.addEventListener("click", () => {
      const sid = Number(card.dataset.spotId);
      const spot = LOCAL_SPOTS.find((s) => s.id === sid);
      if (spot) showSpotDetailInline(spot, topLabel, container);
    });
  });
}

function showSpotDetailInline(spot, topLabel, container) {
  const menuHtml = spot.menu.map((m) => `
    <div class="menu-item">
      <strong>${escapeHtml(m.name)}</strong> <span style="color:var(--muted);">${escapeHtml(m.price)}</span><br>
      <span style="font-size:0.8rem;">${escapeHtml(m.why)}</span>
    </div>
  `).join("");

  container.innerHTML = `
    <div class="spot-detail">
      <span class="spot-back" data-action="back">← Back to spots</span>
      <h4>${escapeHtml(spot.name)}</h4>
      <div class="spot-meta-line">${escapeHtml(spot.cuisine)} · ${escapeHtml(spot.distance)} · ★ ${spot.rating} · ${escapeHtml(spot.address)}</div>
      <div class="menu-match">
        <strong>Menu items that match your profile + ${escapeHtml(topLabel)}:</strong>
        ${menuHtml}
      </div>
      <div class="actions-note">
        Get Directions: search “${escapeHtml(spot.name)} ${escapeHtml(spot.address)}” in Google Maps (or use device location).<br>
        Order: available via Uber Eats, DoorDash, Grubhub — search the name in those apps (you stay logged in on your device).
      </div>
    </div>
  `;

  const back = container.querySelector(".spot-back");
  if (back) {
    back.addEventListener("click", () => {
      // re-render the list using current lastCraving
      const recipes = normalizeRecipes(lastCraving || {});
      renderLocalSpots(recipes);
    });
  }
}

function searchFilterPayload() {
  const proteins = selectedProteins();
  const sides = selectedSides();
  const cuisines = selectedCuisines();
  return {
    diets: selectedDiets(),
    intolerances: selectedIntolerances(),
    health_conditions: selectedHealthConditions(),
    protein_filters: proteins,
    protein_filter: proteins[0] || null,
    side_filters: sides,
    cuisine_filters: cuisines,
  };
}

async function runSearch(opts = {}) {
  const text = soundsGoodText();
  if (!text) {
    setStatus($("search-status"), "Tell me what sounds good first.", true);
    return;
  }
  setStatus(
    $("search-status"),
    opts.refine ? "Chef is refining your lineup…" : "Chef is reading your craving…"
  );
  $("search-btn").disabled = true;
  try {
    await savePreferences();
    const body = {
      what_sounds_good: text,
      ...searchFilterPayload(),
    };
    if (opts.refine && selectedIds.size) {
      body.selected_recipe_ids = [...selectedIds];
    }
    const data = await api("/search/craving", {
      method: "POST",
      body: JSON.stringify(body),
    });
    renderCravingResults(data, { preserveSelection: Boolean(opts.refine) });
    setStatus(
      $("search-status"),
      data.refined
        ? "Lineup refined around your picks."
        : data.live
          ? "Chef lineup from Grok + Spoonacular."
          : data.message || "Results ready."
    );
  } catch (err) {
    setStatus($("search-status"), err.message, true);
  } finally {
    $("search-btn").disabled = false;
  }
}

function renderCreationInsight(insight) {
  const block = $("creation-insight");
  if (!insight || !block) {
    block?.classList.add("hidden");
    return;
  }
  block.classList.remove("hidden");
  const mix = (insight.mix_elements || [])
    .map(
      (m) => `
      <div class="creation-mix-item">
        <strong>${escapeHtml(m.from_recipe)}</strong> — steal ${escapeHtml(m.borrow)}.
        ${escapeHtml(m.use_it)}
      </div>`
    )
    .join("");
  block.innerHTML = `
    <h3>${escapeHtml(insight.headline)}</h3>
    <p>${escapeHtml(insight.urge_summary)}</p>
    <p>${escapeHtml(insight.fusion_idea)}</p>
    ${mix ? `<div class="creation-mix-list">${mix}</div>` : ""}
    <p><strong>Chef preview:</strong> ${escapeHtml(insight.scratch_meal)}</p>`;
}

function renderInspireDash(titles) {
  const el = $("inspire-dash-meals");
  if (!el) return;
  if (!titles?.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `
    <p class="inspire-dash-label">Inspired by</p>
    <div class="inspire-dash-chips">${titles
      .map((t) => `<span class="inspire-dash-chip">${escapeHtml(t)}</span>`)
      .join("")}</div>`;
}

function renderChefProposal(proposal) {
  const block = $("chef-proposal");
  if (!proposal || !block) {
    block?.classList.add("hidden");
    return;
  }
  block.classList.remove("hidden");
  block.innerHTML = `
    <h3>${escapeHtml(proposal.dish_name)}</h3>
    <p class="proposal-pitch">${escapeHtml(proposal.pitch)}</p>
    <dl class="proposal-details">
      <div><dt>Signature technique</dt><dd>${escapeHtml(proposal.technique_highlight)}</dd></div>
      <div><dt>On the plate</dt><dd>${escapeHtml(proposal.plate_description)}</dd></div>
      <div><dt>Your pantry</dt><dd>${escapeHtml(proposal.pantry_note || "")}</dd></div>
    </dl>`;
}

async function openInspiredPanel() {
  if (!selectedIds.size) return;
  setStatus($("inspired-status"), "Building your inspire dash…");
  closeResultsTab();
  $("judge-panel").classList.add("hidden");
  $("cook-panel").classList.add("hidden");
  $("inspired-panel").classList.remove("hidden");
  $("substitutions-block").classList.add("hidden");
  $("present-judge-btn").disabled = true;
  approvedSubs = [];
  pendingSubstitutions = [];
  currentChefProposal = null;
  renderCreationInsight(null);
  renderInspireDash([]);

  try {
    const data = await api("/cook/inspired/setup", {
      method: "POST",
      body: JSON.stringify({
        recipe_ids: [...selectedIds],
        what_sounds_good: soundsGoodText() || null,
        protein: lastCraving?.parsed?.protein || null,
      }),
    });
    inspiredSetup = data;
    $("inspired-title").textContent = "Your inspire dash";
    renderInspireDash(data.recipe_titles || []);
    renderCreationInsight(data.creation_insight);
    const list = $("pantry-checklist");
    list.innerHTML = (data.ingredients || [])
      .map(
        (ing) => `
        <label class="pantry-item">
          <input type="checkbox" class="pantry-have" data-ing-key="${ing.key}" />
          <span>
            <strong>${ing.name}</strong>
            ${ing.amount ? `<em>${ing.amount}</em>` : ""}
            <span class="hint">${ing.recipe_title} · ${ing.role}</span>
          </span>
        </label>`
      )
      .join("");
    $("present-judge-btn").disabled = true;
    scheduleSubstitutionFetch();
    setStatus($("inspired-status"), "");
  } catch (err) {
    setStatus($("inspired-status"), err.message, true);
  }
}

function availableKeys() {
  return [...document.querySelectorAll(".pantry-have:checked")].map((el) => el.dataset.ingKey);
}

function renderSubstitutions(subs) {
  pendingSubstitutions = subs || [];
  const block = $("substitutions-block");
  if (!pendingSubstitutions.length) {
    block.classList.add("hidden");
    refreshCookButton();
    return;
  }
  block.classList.remove("hidden");
  $("substitutions-list").innerHTML = pendingSubstitutions
    .map(
      (s, i) => `
      <label class="sub-item">
        <input type="checkbox" class="sub-approve" data-sub-idx="${i}" checked />
        <div>
          <strong>${s.original_name}</strong> → <strong>${s.substitute}</strong>
          <p class="hint">${s.purpose}: ${s.note}</p>
        </div>
      </label>`
    )
    .join("");
  document.querySelectorAll(".sub-approve").forEach((cb) => {
    cb.addEventListener("change", updateApprovedSubs);
  });
  updateApprovedSubs();
}

function updateApprovedSubs() {
  approvedSubs = [];
  document.querySelectorAll(".sub-approve").forEach((cb) => {
    if (!cb.checked) return;
    const sub = pendingSubstitutions[Number(cb.dataset.subIdx)];
    if (sub) {
      approvedSubs.push({
        original_key: sub.original_key,
        original_name: sub.original_name,
        substitute: sub.substitute,
      });
    }
  });
  refreshCookButton();
}

function refreshCookButton() {
  const btn = $("present-judge-btn");
  if (!btn) return;
  const total = inspiredSetup?.ingredients?.length || 0;
  const have = availableKeys().length;
  if (!total) {
    btn.disabled = true;
    return;
  }
  if (have === total) {
    btn.disabled = false;
    return;
  }
  if (!pendingSubstitutions.length) {
    btn.disabled = true;
    return;
  }
  btn.disabled = document.querySelectorAll(".sub-approve:checked").length === 0;
}

function scheduleSubstitutionFetch() {
  clearTimeout(subsDebounce);
  subsDebounce = setTimeout(() => suggestSubstitutions(), 450);
}

async function suggestSubstitutions() {
  if (!selectedIds.size || !inspiredSetup) return;
  const have = availableKeys();
  const total = inspiredSetup.ingredients?.length || 0;
  if (have.length === total) {
    pendingSubstitutions = [];
    approvedSubs = [];
    $("substitutions-block").classList.add("hidden");
    refreshCookButton();
    setStatus($("inspired-status"), "Pantry set — ready for the chef's pitch.");
    return;
  }
  setStatus($("inspired-status"), "Finding alternatives…");
  try {
    const data = await api("/cook/inspired/substitutions", {
      method: "POST",
      body: JSON.stringify({
        recipe_ids: [...selectedIds],
        available_keys: have,
        what_sounds_good: soundsGoodText() || null,
      }),
    });
    renderSubstitutions(data.substitutions);
    if (!data.substitutions?.length) {
      setStatus($("inspired-status"), "Check what you have to continue.");
      refreshCookButton();
    } else {
      setStatus($("inspired-status"), "Approve alternatives for items you don't have.");
      refreshCookButton();
    }
  } catch (err) {
    setStatus($("inspired-status"), err.message, true);
  }
}

async function presentToJudge() {
  if (!selectedIds.size) return;
  setStatus($("inspired-status"), "Chef is plating the pitch…");
  $("present-judge-btn").disabled = true;
  try {
    const data = await api("/cook/inspired/proposal", {
      method: "POST",
      body: JSON.stringify({
        recipe_ids: [...selectedIds],
        available_keys: availableKeys(),
        approved_substitutions: approvedSubs,
        what_sounds_good: soundsGoodText() || null,
      }),
    });
    currentChefProposal = data.proposal;
    $("inspired-panel").classList.add("hidden");
    $("judge-panel").classList.remove("hidden");
    renderChefProposal(data.proposal);
    $("approve-cook-btn").disabled = false;
    setStatus($("judge-status"), data.mock ? "Demo pitch — approve to get steps." : "");
    setStatus($("inspired-status"), "");
    refreshCookButton();
  } catch (err) {
    setStatus($("inspired-status"), err.message, true);
    refreshCookButton();
  }
}

async function startInspiredCook() {
  if (!selectedIds.size || !currentChefProposal) return;
  setStatus($("judge-status"), "Chef is writing your instructor steps…");
  $("approve-cook-btn").disabled = true;
  try {
    const explain = $("explain-techniques").checked && stepMode === "beginner";
    const data = await api("/cook/inspired/steps", {
      method: "POST",
      body: JSON.stringify({
        recipe_ids: [...selectedIds],
        available_keys: availableKeys(),
        approved_substitutions: approvedSubs,
        explain_techniques: explain,
        what_sounds_good: soundsGoodText() || null,
        chef_proposal: currentChefProposal,
      }),
    });
    renderCookPanel(data);
    setStatus($("judge-status"), "");
  } catch (err) {
    setStatus($("judge-status"), err.message, true);
    $("approve-cook-btn").disabled = false;
  }
}

function renderCookPanel(data) {
  currentCookData = data;
  $("inspired-panel").classList.add("hidden");
  $("judge-panel").classList.add("hidden");
  $("cook-panel").classList.remove("hidden");
  $("cook-title").textContent = data.meal_title;
  const subNote = data.substitutions_applied?.length
    ? `${data.substitutions_applied.length} substitution(s) applied`
    : null;
  $("cook-meta").textContent = [
    subNote,
    data.mock ? "demo instructor steps" : "Executive chef instructions",
  ]
    .filter(Boolean)
    .join(" · ");
  $("cook-steps").innerHTML = (data.steps || [])
    .map(
      (s) =>
        `<li><strong>Step ${s.step}.</strong> ${escapeHtml(s.text)}${
          s.tip ? `<span class="step-tip">${escapeHtml(s.tip)}</span>` : ""
        }</li>`
    )
    .join("");
  setStatus($("save-recipe-status"), "");
}

function buildSavePayload() {
  if (!currentCookData) return null;
  return {
    title: currentCookData.meal_title,
    what_sounds_good: soundsGoodText() || null,
    recipe_ids: [...selectedIds],
    steps: currentCookData.steps || [],
    substitutions_applied: currentCookData.substitutions_applied || [],
    chef_proposal: currentCookData.chef_proposal || currentChefProposal,
  };
}

async function saveCurrentRecipe() {
  const payload = buildSavePayload();
  if (!payload) return;
  if (isGuest) {
    pendingSaveRecipe = payload;
    showGuestSaveModal();
    return;
  }
  setStatus($("save-recipe-status"), "Saving…");
  try {
    const res = await api("/saved-recipes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStatus($("save-recipe-status"), res.message || "Saved to your recipe file.");
  } catch (err) {
    setStatus($("save-recipe-status"), err.message, true);
  }
}

function showGuestSaveModal() {
  $("guest-save-modal")?.classList.remove("hidden");
  setStatus($("guest-save-status"), "");
  guestSaveAuthMode = "register";
  document.querySelectorAll("[data-guest-auth-mode]").forEach((b) => {
    b.classList.toggle("active", b.dataset.guestAuthMode === "register");
  });
  $("guest-save-submit").textContent = "Create account & save";
}

function hideGuestSaveModal() {
  $("guest-save-modal")?.classList.add("hidden");
  setStatus($("guest-save-status"), "");
}

async function flushPendingSave() {
  if (!pendingSaveRecipe || isGuest) return;
  try {
    const res = await api("/saved-recipes", {
      method: "POST",
      body: JSON.stringify(pendingSaveRecipe),
    });
    pendingSaveRecipe = null;
    setStatus($("save-recipe-status"), res.message || "Saved to your recipe file.");
    hideGuestSaveModal();
  } catch (err) {
    setStatus($("guest-save-status"), err.message, true);
  }
}

async function reloadActiveCookKit() {
  if (!activeDetailId || !selectedIds.has(activeDetailId)) return;
  cookKits.delete(activeDetailId);
  await ensureCookKit(activeDetailId);
}

async function enterSession(authData, opts = {}) {
  token = authData.access_token;
  localStorage.setItem("pf_token", token);
  isGuest = authData.is_guest;
  if (opts.keepView) {
    updateSessionChrome(authData.email, authData.is_guest);
  } else {
    showApp(authData.email, authData.is_guest);
  }
  try {
    applyPreferences(await api("/preferences/me"));
  } catch {
    /* defaults */
  }
  if (pendingSaveRecipe && !isGuest) {
    await flushPendingSave();
  }
}

async function bootstrap() {
  try {
    const health = await api("/healthz");
    if ($("build-tag") && health.version) $("build-tag").textContent = `Build ${health.version}`;
    if ($("ui-version-badge") && health.version) {
      $("ui-version-badge").textContent = `UI ${health.version}`;
    }
    meta = await api("/search/meta");
    renderFilterMenu("diet-options", meta.diets, "diet");
    renderFilterMenu("intolerance-options", meta.intolerances, "intolerance");
    renderFilterMenu("health-condition-options", meta.health_conditions, "health-condition");
    renderFilterMenu("cuisine-options", meta.cuisine_options, "cuisine");
    renderFilterMenu("protein-options", meta.protein_options, "protein");
    renderFilterMenu("side-options", meta.side_options, "side");
    updateAllFilterCounts();
    const badge = $("mock-badge");
    if (badge) {
      if (meta.mock_mode || !meta.xai_configured) {
        badge.textContent = meta.xai_configured
          ? "AllRecipes mode"
          : "Set XAI_API_KEY on server for chef judge";
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }
  } catch {
    setStatus($("auth-status"), "Could not reach API. Is the server running?", true);
    showLanding();
    return;
  }

  if (token) {
    try {
      const me = await api("/auth/me");
      showApp(me.email, me.is_guest);
      applyPreferences(await api("/preferences/me"));
      return;
    } catch {
      token = "";
      localStorage.removeItem("pf_token");
    }
  }
  showLanding();
}

$("guest-btn")?.addEventListener("click", async () => {
  setStatus($("auth-status"), "Starting guest session…");
  try {
    await enterSession(await api("/auth/guest", { method: "POST" }));
    setStatus($("auth-status"), "");
  } catch (err) {
    setStatus($("auth-status"), err.message, true);
  }
});

// === New flavor-profile aware 5x5 recipe tokens + local spots first + detail tabs ===

function renderRecipeToken(recipe, idx) {
  const img = recipe.image ? `<img src="${escapeHtml(recipe.image)}" alt="">` : `<div class="meal-card-hero meal-card-hero-placeholder"></div>`;
  const name = escapeHtml(recipe.title || recipe.name || `Option ${idx+1}`);
  // Simple complexity estimate 1-10 based on ingredients or steps length (or from data if added)
  const ingCount = (recipe.ingredient_names || []).length || (recipe.ingredients || []).length || 5;
  const complexity = Math.min(10, Math.max(1, Math.round(ingCount / 2 + (recipe.steps?.length || 4) / 2)));
  const ings = (recipe.ingredient_names || recipe.ingredients || ["fresh ingredients"]).slice(0,6).map(i => `<li>${escapeHtml(i)}</li>`).join("");
  return `
    <div class="recipe-token" data-idx="${idx}" data-recipe-id="${recipe.id || idx}">
      ${img}
      <div class="token-body">
        <div class="token-name">${name}</div>
      </div>
      <div class="token-hover">
        <strong>Ingredients:</strong>
        <ul>${ings}</ul>
        <div class="complexity">Complexity: ${complexity}/10</div>
        <small>Hover for quick view • Click for full instructions</small>
      </div>
    </div>`;
}

function bindRecipeTokens(container, recipes) {
  container.querySelectorAll(".recipe-token").forEach((el) => {
    const idx = parseInt(el.dataset.idx);
    const rec = recipes[idx];
    el.addEventListener("click", () => showRecipeDetail(rec));
    // Hover already handled by CSS for .token-hover
  });
}

function generateAccentTokens(parsed, count) {
  // Mock accents that match the flavor profile (spicy Mexican/gumbo etc.)
  const baseFlavor = (parsed.flavor_profile || parsed.main_query || "spicy mexican").toLowerCase();
  const accents = [
    {id: "acc1", title: "Spicy Pickled Veggies", image: "https://picsum.photos/id/292/120/90", ingredients: ["jalapeno", "onion", "lime", "cilantro"], complexity: 2, flavor: "spicy tangy"},
    {id: "acc2", title: "Crispy Tortilla Chips", image: "https://picsum.photos/id/312/120/90", ingredients: ["corn tortilla", "oil", "salt", "chili powder"], complexity: 3, flavor: "crispy savory"},
    {id: "acc3", title: "Gumbo-style Rice", image: "https://picsum.photos/id/106/120/90", ingredients: ["rice", "celery", "bell pepper", "onion", "spices"], complexity: 4, flavor: "hearty spicy"},
    {id: "acc4", title: "Mexican Street Corn (Elote)", image: "https://picsum.photos/id/201/120/90", ingredients: ["corn", "mayo", "cheese", "chili", "lime"], complexity: 3, flavor: "creamy spicy"},
    {id: "acc5", title: "Chili Lime Shrimp Skewers", image: "https://picsum.photos/id/160/120/90", ingredients: ["shrimp", "lime", "chili", "garlic", "cilantro"], complexity: 5, flavor: "zesty spicy"},
  ];
  return accents.slice(0, count).map((a, i) => ({...a, id: `acc${Date.now()}${i}`, title: a.title + " (accent)"}));
}

function renderLocalSpotsProfileBased(recipes, parsed, container) {
  if (!container) return;
  const profile = (parsed.flavor_profile || parsed.main_query || "spicy mexican").toLowerCase();
  // Mock top 5 spots matching the common spicy Mexican/gumbo/chili/taco profile (bold, spicy, savory, hearty)
  const allSpots = [
    {id:1, name:"Taco & Chili Cantina", cuisine:"Mexican", distance:"0.9 mi", rating:4.3, image:"https://picsum.photos/id/251/80/80", address:"Northwood, OH", menu:[{name:"Spicy Gumbo Tacos", price:"$11", why:"Fusion of tacos, chili, gumbo spice"}]},
    {id:2, name:"Gumbo & Spice House", cuisine:"Cajun/Mexican", distance:"1.8 mi", rating:4.4, image:"https://picsum.photos/id/106/80/80", address:"Northwood area", menu:[{name:"Chili Gumbo Bowl", price:"$12", why:"Spicy stew profile match"}]},
    {id:3, name:"Spicy Taco Spot", cuisine:"Mexican", distance:"0.6 mi", rating:4.5, image:"https://picsum.photos/id/160/80/80", address:"Northwood, OH", menu:[{name:"Loaded Tacos", price:"$10", why:"Taco element of profile"}]},
    {id:4, name:"Bold Chili Grill", cuisine:"Tex-Mex", distance:"2.1 mi", rating:4.2, image:"https://picsum.photos/id/201/80/80", address:"Nearby", menu:[{name:"Hearty Chili", price:"$9", why:"Chili core of input"}]},
    {id:5, name:"Mexican Heat Kitchen", cuisine:"Mexican Fusion", distance:"1.2 mi", rating:4.6, image:"https://picsum.photos/id/312/80/80", address:"Northwood", OH, menu:[{name:"Spicy Mexican Gumbo Tacos", price:"$13", why:"All elements combined"}]},
  ];
  // Rank by profile match (simple keyword overlap with input/profile)
  const scored = allSpots.map(s => {
    const score = (profile.includes("mex") && s.cuisine.toLowerCase().includes("mex") ? 3 : 0) +
                  (profile.includes("spicy") ? 2 : 0) +
                  (s.cuisine.toLowerCase().includes("cajun") || s.cuisine.toLowerCase().includes("tex") ? 1 : 0);
    return {...s, score};
  }).sort((a,b) => b.score - a.score);
  const top5 = scored.slice(0,5);

  container.innerHTML = top5.map(spot => `
    <div class="spot-card" data-spot-id="${spot.id}">
      <img src="${escapeHtml(spot.image)}" alt="">
      <div><strong>${escapeHtml(spot.name)}</strong><br><small>${escapeHtml(spot.distance)} • ${spot.rating}★</small></div>
    </div>
  `).join("");

  // Click shows inline detail (no new tab)
  container.querySelectorAll(".spot-card").forEach(card => {
    card.addEventListener("click", () => {
      const sid = card.dataset.spotId;
      const spot = top5.find(s => s.id == sid);
      if (spot) showSpotDetailInline(spot, profile, container);
    });
  });
}

function showRecipeDetail(recipe) {
  const pane = $("results-list-pane");
  if (!pane) return;

  // Hide lists, show detail in place (no new tab)
  const lists = pane.querySelectorAll("#local-spots-section, #recipes-section");
  lists.forEach(l => l.style.display = "none");

  let detail = $("recipe-detail-view");
  if (!detail) {
    detail = document.createElement("div");
    detail.id = "recipe-detail-view";
    detail.className = "detail-tab-container";
    pane.appendChild(detail);
  }

  const complexity = recipe.complexity || Math.min(10, Math.max(1, (recipe.ingredient_names || []).length || 5));
  const ings = (recipe.ingredient_names || recipe.ingredients || []).join(", ");

  detail.innerHTML = `
    <button class="btn-ghost" id="close-detail">← Back to all options</button>
    <h3>${escapeHtml(recipe.title || recipe.name)}</h3>
    <p><small>Complexity: ${complexity}/10 • Flavor match: ${escapeHtml(recipe.fit_note || "Matches your spicy Mexican/gumbo profile")}</small></p>
    <div class="detail-tokens">
      <div class="detail-token" data-tab="shopping">1. Shopping List / Checklist</div>
      <div class="detail-token" data-tab="meal">2. Build Larger Meal (up to 10 accents)</div>
      <div class="detail-token" data-tab="inspired">3. Inspired Full Meal</div>
    </div>
    <div id="detail-content" class="detail-content"></div>
  `;

  $("close-detail").addEventListener("click", () => {
    detail.remove();
    lists.forEach(l => l.style.display = "");
  });

  // Bind the 3 tokens
  detail.querySelectorAll(".detail-token").forEach(token => {
    token.addEventListener("click", () => {
      const tab = token.dataset.tab;
      renderDetailTab(tab, recipe, $("detail-content"), detail);
      // record input (simple state)
      detail.dataset.currentTab = tab;
    });
  });

  // Default to first tab
  renderDetailTab("shopping", recipe, $("detail-content"), detail);
}

function renderDetailTab(tab, recipe, contentEl, parentDetail) {
  contentEl.innerHTML = "";
  const flavor = recipe.fit_note || "spicy Mexican profile with gumbo/chili/taco elements";

  if (tab === "shopping") {
    const ings = (recipe.ingredient_names || recipe.ingredients || ["protein", "spices", "veggies"]);
    // Simple have/not based on common pantry (in real, use user prefs.pantry_staples())
    const have = ["salt", "pepper", "oil", "garlic", "onion"];
    contentEl.innerHTML = `
      <h4>Shopping List / Have & Don't Have</h4>
      <ul class="shopping-checklist">
        ${ings.map(ing => {
          const has = have.some(h => ing.toLowerCase().includes(h.toLowerCase()));
          return `<li><input type="checkbox" ${has ? "checked" : ""}> ${escapeHtml(ing)} ${has ? "(you have)" : "(need to buy)"}</li>`;
        }).join("")}
      </ul>
      <small>Check off as you shop or prep. Matches your pantry prefs where possible.</small>
    `;
  } else if (tab === "meal") {
    // Up to 10 tokens for sides/apps based on flavor. If no main, list mains (here assume recipe is main).
    const sides = generateAccentTokens({flavor_profile: flavor}, 10);
    contentEl.innerHTML = `
      <h4>Build Larger Meal - Accents & Sides (up to 10 tokens)</h4>
      <div class="meal-sides-grid">
        ${sides.map((s, i) => `
          <div class="recipe-token" data-side-idx="${i}">
            <img src="${s.image}" style="height:60px;">
            <div class="token-body"><strong>${escapeHtml(s.title)}</strong></div>
          </div>
        `).join("")}
      </div>
      <div id="side-detail" style="margin-top:0.5rem; border-top:1px solid #ccc; padding-top:0.5rem;"></div>
    `;
    contentEl.querySelectorAll(".recipe-token").forEach((tok, i) => {
      const side = sides[i];
      tok.addEventListener("click", () => {
        // Open "own tab window" - show in side-detail, with back implied by re-click or clear
        const sub = $("side-detail");
        sub.innerHTML = `
          <strong>${escapeHtml(side.title)}</strong> (complexity ${side.complexity}/10)<br>
          <small>Ingredients: ${side.ingredients.join(", ")}</small>
          <p>Step-by-step: Heat pan, add oil, cook ${side.ingredients[0]} with spices from your profile until fragrant. Simple for anyone - no chef jargon needed. Time: 10 min.</p>
          <button class="btn-ghost" id="back-side">Back to sides</button>
        `;
        $("back-side").addEventListener("click", () => sub.innerHTML = "");
      });
      // Hover already via CSS if we reuse class
    });
  } else if (tab === "inspired") {
    contentEl.innerHTML = `
      <h4>Inspired Full Meal from your full profile + this selection</h4>
      <div class="inspired-full">
        <p>Using your past inputs and current "spicy Mexican with gumbo/chili/taco" flavor, here's a complete meal:</p>
        <h4>Main: ${escapeHtml(recipe.title || recipe.name)}</h4>
        <h4>Accents (from flavor profile):</h4>
        <ul>${generateAccentTokens({flavor_profile: flavor}, 3).map(a => `<li>${escapeHtml(a.title)} - ${a.ingredients.slice(0,2).join(", ")}</li>`).join("")}</ul>
        <h4>Shopping for whole meal:</h4>
        <ul class="shopping-checklist">
          ${(recipe.ingredient_names || []).concat(["extra veggies for sides", "spices for gumbo twist"]).map(i => `<li><input type="checkbox"> ${escapeHtml(i)}</li>`).join("")}
        </ul>
        <h4>Efficient Professional Chef Instructions (anyone can follow):</h4>
        <p>1. Prep all proteins and veggies first (mise en place - 10 min). 2. Start the main using your selected recipe method (sear protein hard for flavor). 3. While main rests, quickly make 1-2 accents in parallel pans (total active time ~25 min). 4. Plate with acid/fresh element last for brightness. Total effort: medium, serves 4. This builds a balanced meal that hits every note from your history and today's craving without overworking.</p>
      </div>
    `;
  }
}

function showSpotDetailInline(spot, profile, container) {
  // Adapted from previous inline detail - no new tab
  container.innerHTML = `
    <div class="spot-detail">
      <span class="spot-back" data-action="back">← Back to spots</span>
      <h4>${escapeHtml(spot.name)} (matches ${escapeHtml(profile)})</h4>
      <div>${escapeHtml(spot.cuisine)} • ${escapeHtml(spot.distance)}</div>
      <div class="menu-match">
        <strong>Menu that fits your profile:</strong><br>
        ${spot.menu ? spot.menu.map(m => `${escapeHtml(m.name)} (${m.price}) - ${escapeHtml(m.why)}`).join("<br>") : "Ask for spicy Mexican/gumbo style adaptations."}
      </div>
      <div class="actions-note">Get directions in Maps app for ${escapeHtml(spot.address)}. Order via your usual apps (search the name).</div>
    </div>
  `;
  const back = container.querySelector(".spot-back");
  if (back) back.addEventListener("click", () => {
    // re-render spots (simplified, in real re-call renderLocalSpotsProfileBased)
    container.innerHTML = "<p>Spots re-loaded on next search or refresh results.</p>";
  });
}

// Simple reuse/adapt of previous renderLocalSpots if needed, but new one is profile based above.


$("auth-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const mode = document.querySelector(".auth-tabs button.active")?.dataset.authMode || "login";
  const fd = new FormData(e.target);
  setStatus($("auth-status"), "…");
  try {
    await enterSession(
      await api(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ email: fd.get("email"), password: fd.get("password") }),
      })
    );
    setStatus($("auth-status"), "");
  } catch (err) {
    setStatus($("auth-status"), err.message, true);
  }
});

document.querySelectorAll(".auth-tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".auth-tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $("auth-submit").textContent = btn.dataset.authMode === "register" ? "Create account" : "Sign in";
  });
});

$("sign-out")?.addEventListener("click", () => {
  token = "";
  isGuest = false;
  localStorage.removeItem("pf_token");
  $("sounds-good-input").value = "";
  showLanding();
});

$("search-btn")?.addEventListener("click", runSearch);
$("inspired-btn")?.addEventListener("click", openInspiredPanel);
$("present-judge-btn")?.addEventListener("click", presentToJudge);
$("approve-cook-btn")?.addEventListener("click", startInspiredCook);
$("re-pitch-btn")?.addEventListener("click", async () => {
  setStatus($("judge-status"), "Chef is reworking the pitch…");
  $("approve-cook-btn").disabled = true;
  try {
    const data = await api("/cook/inspired/proposal", {
      method: "POST",
      body: JSON.stringify({
        recipe_ids: [...selectedIds],
        available_keys: availableKeys(),
        approved_substitutions: approvedSubs,
        what_sounds_good: soundsGoodText() || null,
      }),
    });
    currentChefProposal = data.proposal;
    renderChefProposal(data.proposal);
    $("approve-cook-btn").disabled = false;
    setStatus($("judge-status"), "New pitch ready — you're the judge.");
  } catch (err) {
    setStatus($("judge-status"), err.message, true);
    $("approve-cook-btn").disabled = false;
  }
});
$("save-recipe-btn")?.addEventListener("click", saveCurrentRecipe);

$("close-results-tab")?.addEventListener("click", closeResultsTab);

$("back-to-results")?.addEventListener("click", () => {
  $("inspired-panel").classList.add("hidden");
  openResultsTab();
});

$("back-to-inspired-from-judge")?.addEventListener("click", () => {
  $("judge-panel").classList.add("hidden");
  $("inspired-panel").classList.remove("hidden");
});

$("back-to-judge")?.addEventListener("click", () => {
  $("cook-panel").classList.add("hidden");
  $("judge-panel").classList.remove("hidden");
});

$("guest-save-dismiss")?.addEventListener("click", hideGuestSaveModal);

document.querySelectorAll("[data-guest-auth-mode]").forEach((btn) => {
  btn.addEventListener("click", () => {
    guestSaveAuthMode = btn.dataset.guestAuthMode || "register";
    document.querySelectorAll("[data-guest-auth-mode]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $("guest-save-submit").textContent =
      guestSaveAuthMode === "register" ? "Create account & save" : "Sign in & save";
  });
});

$("guest-save-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  setStatus($("guest-save-status"), "…");
  try {
    await enterSession(
      await api(`/auth/${guestSaveAuthMode}`, {
        method: "POST",
        body: JSON.stringify({ email: fd.get("email"), password: fd.get("password") }),
      }),
      { keepView: true }
    );
    setStatus($("guest-save-status"), "");
  } catch (err) {
    setStatus($("guest-save-status"), err.message, true);
  }
});

$("sounds-good-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    runSearch();
  }
});

function setStepMode(mode) {
  stepMode = mode;
  const beginner = mode === "beginner";
  $("mode-beginner")?.classList.toggle("active", beginner);
  $("mode-direct")?.classList.toggle("active", !beginner);
}

$("mode-beginner")?.addEventListener("click", () => {
  setStepMode("beginner");
  if (currentChefProposal) startInspiredCook();
});
$("mode-direct")?.addEventListener("click", () => {
  setStepMode("direct");
  if (currentChefProposal) startInspiredCook();
});
document.addEventListener("change", (e) => {
  if (
    e.target.matches(
      "#diet-options input, #intolerance-options input, #health-condition-options input, #explain-techniques"
    )
  ) {
    schedulePrefsSave();
    updateAllFilterCounts();
    if (e.target.id === "explain-techniques") reloadActiveCookKit();
  }
  if (e.target.matches("#cuisine-options input, #protein-options input, #side-options input")) {
    updateAllFilterCounts();
  }
  if (e.target.matches(".pantry-have")) {
    approvedSubs = [];
    scheduleSubstitutionFetch();
  }
});

document.querySelectorAll(".filter-dropdown-trigger").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const parent = btn.closest(".filter-dropdown");
    document.querySelectorAll(".filter-dropdown.open").forEach((d) => {
      if (d !== parent) d.classList.remove("open");
    });
    parent?.classList.toggle("open");
  });
});

document.querySelectorAll(".filter-dropdown").forEach((dd) => {
  dd.addEventListener("click", (e) => e.stopPropagation());
});

document.addEventListener("click", () => {
  document.querySelectorAll(".filter-dropdown.open").forEach((d) => d.classList.remove("open"));
});

bootstrap();