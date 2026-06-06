const API = "";
let token = localStorage.getItem("pf_token") || "";
let isGuest = false;
let meta = {
  diets: [],
  intolerances: [],
  health_conditions: [],
  mock_mode: true,
  xai_configured: false,
  spoonacular_configured: false,
};
let lastCraving = null;
let selectedIds = new Set();
let inspiredSetup = null;
let pendingSubstitutions = [];
let approvedSubs = [];
let stepMode = "beginner";
let currentRecipeId = null;
let prefsSaveTimer = null;
let subsDebounce = null;

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

function selectedDiets() {
  return [...document.querySelectorAll("#diet-options input:checked")].map((el) => el.value);
}

function selectedIntolerances() {
  return [...document.querySelectorAll("#intolerance-options input:checked")].map((el) => el.value);
}

function selectedHealthConditions() {
  return [...document.querySelectorAll("#health-condition-options input:checked")].map((el) => el.value);
}

function soundsGoodText() {
  return $("sounds-good-input")?.value?.trim() || "";
}

function renderChipOptions(containerId, options, name, extraClass = "") {
  const wrap = $(containerId);
  if (!wrap) return;
  if (!options?.length) {
    wrap.innerHTML = `<p class="fieldset-hint">No options available.</p>`;
    return;
  }
  wrap.innerHTML = options
    .map(
      (d) =>
        `<label class="chip chip-token ${extraClass}"><input type="checkbox" name="${name}" value="${d.value}" />${d.label}</label>`
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

function hideAllPanels() {
  ["landing-panel", "search-panel", "results-panel", "inspired-panel", "cook-panel", "recipe-panel"].forEach(
    (id) => $(id)?.classList.add("hidden")
  );
}

function showLanding() {
  hideAllPanels();
  $("landing-panel").classList.remove("hidden");
  $("session-badge").classList.add("hidden");
  $("auth-user").classList.add("hidden");
  $("sign-out").classList.add("hidden");
}

function showApp(displayName = "", guest = false) {
  hideAllPanels();
  $("search-panel").classList.remove("hidden");
  $("sign-out").classList.remove("hidden");
  isGuest = guest;
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
  const img = recipe.image
    ? `<img class="result-thumb" src="${escapeHtml(recipe.image)}" alt="" loading="lazy" />`
    : `<div class="result-thumb result-thumb-placeholder" aria-hidden="true"></div>`;
  return `
    <label class="meal-card ${catClass} ${checked ? "meal-card-selected" : ""}">
      <input type="checkbox" class="meal-select" data-recipe-id="${recipe.id}" ${checked ? "checked" : ""} />
      <div class="meal-card-inner">
        ${img}
        <div class="meal-card-body">
          <span class="meal-card-cat">${categoryLabel(cat)}</span>
          <strong class="result-title">${escapeHtml(recipe.title)}</strong>
          ${recipe.fit_note ? `<p class="meal-card-fit">${escapeHtml(recipe.fit_note)}</p>` : ""}
          ${recipe.summary ? `<p class="meal-card-summary">${escapeHtml(recipe.summary)}</p>` : ""}
          ${recipe.ready_in_minutes ? `<p class="hint">${recipe.ready_in_minutes} min · ${recipe.servings || "?"} servings</p>` : ""}
          <button type="button" class="btn-ghost btn-small view-recipe-btn" data-view-recipe="${recipe.id}">View recipe</button>
        </div>
      </div>
    </label>`;
}

function updateSelectionUI() {
  const count = selectedIds.size;
  $("selection-count").textContent = count
    ? `${count} recipe${count === 1 ? "" : "s"} selected`
    : "Select the recipes you want to make.";
  $("inspired-btn").disabled = count === 0;
}

function bindMealCards(container) {
  container.querySelectorAll(".meal-select").forEach((cb) => {
    cb.addEventListener("change", (e) => {
      const id = Number(e.target.dataset.recipeId);
      if (e.target.checked) selectedIds.add(id);
      else selectedIds.delete(id);
      e.target.closest(".meal-card")?.classList.toggle("meal-card-selected", e.target.checked);
      updateSelectionUI();
    });
  });
  container.querySelectorAll(".view-recipe-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openRecipe(Number(btn.dataset.viewRecipe));
    });
  });
}

function renderParsedCraving(parsed) {
  const el = $("parsed-craving");
  if (!parsed) {
    el.classList.add("hidden");
    return;
  }
  const chips = [];
  if (parsed.protein) chips.push(`Protein: ${parsed.protein}`);
  if (parsed.starches?.length) chips.push(`Starches: ${parsed.starches.join(", ")}`);
  if (parsed.mood) chips.push(`Mood: ${parsed.mood}`);
  if (parsed.main_query) chips.push(`Searching: ${parsed.main_query}`);
  if (!chips.length) {
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = chips.map((c) => `<span>${c}</span>`).join("");
}

function renderCravingResults(data) {
  lastCraving = data;
  selectedIds = new Set();
  $("results-panel").classList.remove("hidden");
  $("inspired-panel").classList.add("hidden");
  $("cook-panel").classList.add("hidden");

  const recipes = normalizeRecipes(data);
  const total = recipes.length;
  $("results-heading").textContent = total ? `Recipes for you (${total})` : "Recipes for you";
  $("results-message").textContent = total
    ? `Grok picked ${total} recipe${total === 1 ? "" : "s"} that fit what sounds good.`
    : data.message || "No matches yet.";
  renderParsedCraving(data.parsed);

  let list = $("recipes-list");
  if (!list) {
    const panel = $("results-panel");
    list = document.createElement("div");
    list.id = "recipes-list";
    list.className = "meal-card-grid results-scroll";
    panel?.appendChild(list);
  }

  if (!total) {
    list.innerHTML = `<p class="hint">No matches. Try describing a protein, starch, or mood — or loosen diet filters.</p>`;
    updateSelectionUI();
    return;
  }

  list.innerHTML = recipes.map((r) => renderMealCard(r)).join("");
  bindMealCards(list);
  updateSelectionUI();
  $("results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runSearch() {
  const text = soundsGoodText();
  if (!text) {
    setStatus($("search-status"), "Tell me what sounds good first.", true);
    return;
  }
  setStatus($("search-status"), "Understanding your craving…");
  $("search-btn").disabled = true;
  try {
    await savePreferences();
    const data = await api("/search/craving", {
      method: "POST",
      body: JSON.stringify({
        what_sounds_good: text,
        diets: selectedDiets(),
        intolerances: selectedIntolerances(),
        health_conditions: selectedHealthConditions(),
      }),
    });
    renderCravingResults(data);
    setStatus(
      $("search-status"),
      data.live ? "Live recipes from Spoonacular." : data.message || "Results ready."
    );
  } catch (err) {
    setStatus($("search-status"), err.message, true);
  } finally {
    $("search-btn").disabled = false;
  }
}

async function openInspiredPanel() {
  if (!selectedIds.size) return;
  setStatus($("inspired-status"), "Loading ingredients…");
  $("results-panel").classList.add("hidden");
  $("inspired-panel").classList.remove("hidden");
  $("substitutions-block").classList.add("hidden");
  $("start-cook-btn").disabled = true;
  approvedSubs = [];
  pendingSubstitutions = [];

  try {
    const data = await api("/cook/inspired/setup", {
      method: "POST",
      body: JSON.stringify({
        recipe_ids: [...selectedIds],
        what_sounds_good: soundsGoodText() || null,
      }),
    });
    inspiredSetup = data;
    $("inspired-title").textContent = data.meal_title;
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
    $("start-cook-btn").disabled = true;
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
  const total = inspiredSetup?.ingredients?.length || 0;
  const have = availableKeys().length;
  if (!total) {
    $("start-cook-btn").disabled = true;
    return;
  }
  if (have === total) {
    $("start-cook-btn").disabled = false;
    return;
  }
  if (!pendingSubstitutions.length) {
    $("start-cook-btn").disabled = true;
    return;
  }
  $("start-cook-btn").disabled = document.querySelectorAll(".sub-approve:checked").length === 0;
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
    setStatus($("inspired-status"), "You have everything — ready to cook.");
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

async function startInspiredCook() {
  if (!selectedIds.size) return;
  setStatus($("inspired-status"), "Building your cooking plan…");
  $("start-cook-btn").disabled = true;
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
      }),
    });
    renderCookPanel(data);
    setStatus($("inspired-status"), "");
  } catch (err) {
    setStatus($("inspired-status"), err.message, true);
    $("start-cook-btn").disabled = false;
  }
}

function renderCookPanel(data) {
  $("inspired-panel").classList.add("hidden");
  $("cook-panel").classList.remove("hidden");
  $("cook-title").textContent = data.meal_title;
  const subNote = data.substitutions_applied?.length
    ? `${data.substitutions_applied.length} substitution(s) applied`
    : null;
  $("cook-meta").textContent = [subNote, data.mock ? "guidance mode" : "AI-adjusted steps"]
    .filter(Boolean)
    .join(" · ");
  $("cook-steps").innerHTML = (data.steps || [])
    .map(
      (s) =>
        `<li><strong>Step ${s.step}.</strong> ${s.text}${
          s.tip ? `<span class="step-tip">${s.tip}</span>` : ""
        }</li>`
    )
    .join("");
}

async function openRecipe(id) {
  currentRecipeId = id;
  hideAllPanels();
  $("recipe-panel").classList.remove("hidden");
  $("recipe-title").textContent = "Loading…";
  $("recipe-steps").innerHTML = "";
  try {
    const detail = await api(`/recipes/${id}`);
    $("recipe-title").textContent = detail.title;
    $("recipe-meta").textContent = [
      detail.ready_in_minutes ? `${detail.ready_in_minutes} min` : null,
      detail.servings ? `${detail.servings} servings` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    $("recipe-links").innerHTML = detail.source_url
      ? `<a href="${detail.source_url}" target="_blank" rel="noopener">Original recipe</a>`
      : "";
    await loadRecipeSteps();
  } catch (err) {
    $("recipe-title").textContent = "Could not load recipe";
    setStatus($("search-status"), err.message, true);
  }
}

async function loadRecipeSteps() {
  if (!currentRecipeId) return;
  const explain = stepMode === "beginner" && $("explain-techniques").checked;
  const data = await api(`/recipes/${currentRecipeId}/simplify`, {
    method: "POST",
    body: JSON.stringify({
      explain_techniques: explain,
      skill_level: explain ? "beginner" : "direct",
    }),
  });
  $("recipe-steps").innerHTML = data.steps
    .map(
      (s) =>
        `<li><strong>Step ${s.step}.</strong> ${s.text}${
          s.tip ? `<span class="step-tip">${s.tip}</span>` : ""
        }</li>`
    )
    .join("");
}

async function enterSession(authData) {
  token = authData.access_token;
  localStorage.setItem("pf_token", token);
  isGuest = authData.is_guest;
  showApp(authData.email, authData.is_guest);
  try {
    applyPreferences(await api("/preferences/me"));
  } catch {
    /* defaults */
  }
}

async function bootstrap() {
  try {
    const health = await api("/healthz");
    if ($("build-tag") && health.version) $("build-tag").textContent = `Build ${health.version}`;
    meta = await api("/search/meta");
    renderChipOptions("diet-options", meta.diets, "diet", "chip-diet");
    renderChipOptions("intolerance-options", meta.intolerances, "intolerance", "chip-allergy");
    renderChipOptions("health-condition-options", meta.health_conditions, "health-condition", "chip-medical");
    const badge = $("mock-badge");
    if (badge) {
      if (meta.mock_mode) {
        badge.textContent = meta.spoonacular_configured
          ? "Partial demo mode"
          : "Demo recipes — API keys not active";
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
$("start-cook-btn")?.addEventListener("click", startInspiredCook);

$("back-to-results")?.addEventListener("click", () => {
  $("inspired-panel").classList.add("hidden");
  $("results-panel").classList.remove("hidden");
});

$("back-to-inspired")?.addEventListener("click", () => {
  $("cook-panel").classList.add("hidden");
  $("inspired-panel").classList.remove("hidden");
});

$("back-from-recipe")?.addEventListener("click", () => {
  $("recipe-panel").classList.add("hidden");
  if (inspiredSetup) $("inspired-panel").classList.remove("hidden");
  else $("results-panel").classList.remove("hidden");
});

function setStepMode(mode) {
  stepMode = mode;
  const beginner = mode === "beginner";
  ["mode-beginner", "recipe-mode-beginner"].forEach((id) => $(id)?.classList.toggle("active", beginner));
  ["mode-direct", "recipe-mode-direct"].forEach((id) => $(id)?.classList.toggle("active", !beginner));
}

$("mode-beginner")?.addEventListener("click", () => {
  setStepMode("beginner");
  startInspiredCook();
});
$("mode-direct")?.addEventListener("click", () => {
  setStepMode("direct");
  startInspiredCook();
});
$("recipe-mode-beginner")?.addEventListener("click", async () => {
  setStepMode("beginner");
  await loadRecipeSteps();
});
$("recipe-mode-direct")?.addEventListener("click", async () => {
  setStepMode("direct");
  await loadRecipeSteps();
});

document.addEventListener("change", (e) => {
  if (
    e.target.matches(
      "#diet-options input, #intolerance-options input, #health-condition-options input, #explain-techniques"
    )
  ) {
    schedulePrefsSave();
  }
  if (e.target.matches(".pantry-have")) {
    approvedSubs = [];
    scheduleSubstitutionFetch();
  }
});

bootstrap();