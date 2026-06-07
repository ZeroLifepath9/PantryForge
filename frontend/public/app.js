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
let selectedProteinFilter = null;
let proteinFilterExplicit = false;
let selectedIds = new Set();
let inspiredSetup = null;
let pendingSubstitutions = [];
let approvedSubs = [];
let currentChefProposal = null;
let currentCookData = null;
let pendingSaveRecipe = null;
let guestSaveAuthMode = "register";
let stepMode = "beginner";
let currentRecipeId = null;
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
  [
    "landing-panel",
    "search-panel",
    "results-panel",
    "inspired-panel",
    "judge-panel",
    "cook-panel",
    "recipe-panel",
  ].forEach((id) => $(id)?.classList.add("hidden"));
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
    ? `<img class="result-thumb" src="${escapeHtml(recipe.image)}" alt="" loading="lazy" />`
    : `<div class="result-thumb result-thumb-placeholder" aria-hidden="true"></div>`;
  return `
    <label class="meal-card ${catClass} ${checked ? "meal-card-selected" : ""}">
      <input type="checkbox" class="meal-select" data-recipe-id="${recipe.id}" ${checked ? "checked" : ""} />
      <div class="meal-card-inner">
        ${img}
        <div class="meal-card-body">
          <span class="meal-card-cat">${categoryLabel(cat)}${popularBadge}${recipe.thread_label ? ` · ${escapeHtml(recipe.thread_label)}` : ""}</span>
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
    ? `${count} of ${MAX_RECIPE_SELECT} selected — lineup refines as you pick`
    : `Select up to ${MAX_RECIPE_SELECT} — the chef refines pairings around your picks.`;
  $("inspired-btn").disabled = count === 0;
}

function scheduleLineupRefine() {
  clearTimeout(refineDebounce);
  refineDebounce = setTimeout(() => {
    if (selectedIds.size > 0) runSearch({ refine: true });
  }, 700);
}

function bindMealCards(container) {
  container.querySelectorAll(".meal-select").forEach((cb) => {
    const id = Number(cb.dataset.recipeId);
    cb.checked = selectedIds.has(id);
    cb.closest(".meal-card")?.classList.toggle("meal-card-selected", cb.checked);
    cb.addEventListener("change", (e) => {
      const rid = Number(e.target.dataset.recipeId);
      if (e.target.checked) {
        if (selectedIds.size >= MAX_RECIPE_SELECT) {
          e.target.checked = false;
          setStatus($("search-status"), `Up to ${MAX_RECIPE_SELECT} recipes — chef refines the rest.`, true);
          return;
        }
        selectedIds.add(rid);
      } else {
        selectedIds.delete(rid);
      }
      e.target.closest(".meal-card")?.classList.toggle("meal-card-selected", e.target.checked);
      updateSelectionUI();
      scheduleLineupRefine();
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
  for (const th of parsed.craving_threads || []) {
    if (th.label) chips.push(th.label);
  }
  if (parsed.shared_bridge?.label) chips.push(`+ ${parsed.shared_bridge.label}`);
  if (parsed.protein) chips.push(`Protein: ${parsed.protein}`);
  if (!chips.length && parsed.main_query) chips.push(parsed.main_query);
  if (!chips.length) {
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = chips.map((c) => `<span>${escapeHtml(c)}</span>`).join("");
}

function renderChefInsight(data) {
  const block = $("chef-insight");
  if (!block) return;
  const threads = data.craving_threads || data.parsed?.craving_threads || [];
  const bridge = data.shared_bridge || data.parsed?.shared_bridge;
  if (!data.chef_headline && !data.chef_intro && !threads.length) {
    block.classList.add("hidden");
    block.innerHTML = "";
    return;
  }
  block.classList.remove("hidden");
  const threadHtml = threads
    .map(
      (t) => `
      <div class="chef-thread">
        <strong>${escapeHtml(t.label)}</strong>
        ${t.chef_note ? `<p>${escapeHtml(t.chef_note)}</p>` : ""}
      </div>`
    )
    .join("");
  const bridgeHtml = bridge?.label
    ? `<div class="chef-bridge">
        <strong>Chef's bridge: ${escapeHtml(bridge.label)}</strong>
        ${bridge.chef_note ? `<p>${escapeHtml(bridge.chef_note)}</p>` : ""}
      </div>`
    : "";
  block.innerHTML = `
    ${data.chef_headline ? `<h3>${escapeHtml(data.chef_headline)}</h3>` : ""}
    ${data.chef_intro ? `<p class="chef-intro-lead">${escapeHtml(data.chef_intro)}</p>` : ""}
    ${threadHtml}
    ${bridgeHtml}`;
}

function renderProteinPrompt(parsed) {
  const block = $("protein-prompt");
  const options = $("protein-options");
  if (!block || !options) return;

  const choices = parsed?.protein_options || [];
  if (!choices.length) {
    block.classList.add("hidden");
    options.innerHTML = "";
    return;
  }

  block.classList.remove("hidden");
  const active = proteinFilterExplicit
    ? (selectedProteinFilter || "")
    : (parsed.protein || "");

  options.innerHTML = [
    `<button type="button" class="protein-chip${active === "" ? " active" : ""}" data-protein="">All proteins</button>`,
    ...choices.map(
      (p) =>
        `<button type="button" class="protein-chip${active === p ? " active" : ""}" data-protein="${escapeHtml(p)}">${escapeHtml(p)}</button>`
    ),
  ].join("");

  options.querySelectorAll(".protein-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const protein = btn.dataset.protein || null;
      if (protein === selectedProteinFilter) return;
      selectedProteinFilter = protein;
      runSearch({ proteinFilter: protein });
    });
  });
}

function renderCravingResults(data, opts = {}) {
  lastCraving = data;
  if (!opts.preserveSelection) selectedIds = new Set();
  $("results-panel").classList.remove("hidden");
  $("inspired-panel").classList.add("hidden");
  $("judge-panel").classList.add("hidden");
  $("cook-panel").classList.add("hidden");

  const recipes = normalizeRecipes(data);
  const total = recipes.length;
  const parsed = data.parsed || {};
  const pageSize = data.page_size || 25;
  const popularTop = data.popular_top || 5;
  $("results-heading").textContent = total
    ? `Chef's lineup (${total})`
    : "Chef's lineup";
  $("results-message").textContent = data.message || (total
    ? `${total} mains & pairings — select up to ${MAX_RECIPE_SELECT} to refine.`
    : "No matches yet.");
  renderChefInsight(data);
  renderParsedCraving(parsed);
  renderProteinPrompt(parsed);

  let list = $("recipes-list");
  if (!list) {
    const panel = $("results-panel");
    list = document.createElement("div");
    list.id = "recipes-list";
    list.className = "meal-card-grid results-scroll";
    panel?.appendChild(list);
  }

  if (!total) {
    list.innerHTML = `<p class="hint">No matches. Try tacos, pasta, chicken, or loosen diet filters.</p>`;
    updateSelectionUI();
    return;
  }

  list.innerHTML = recipes.map((r) => renderMealCard(r)).join("");
  bindMealCards(list);
  updateSelectionUI();
  $("results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runSearch(opts = {}) {
  const text = soundsGoodText();
  if (!text) {
    setStatus($("search-status"), "Tell me what sounds good first.", true);
    return;
  }
  if (!opts.refine) {
    if (!("proteinFilter" in opts)) {
      selectedProteinFilter = null;
      proteinFilterExplicit = false;
    } else {
      selectedProteinFilter = opts.proteinFilter;
      proteinFilterExplicit = true;
    }
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
      diets: selectedDiets(),
      intolerances: selectedIntolerances(),
      health_conditions: selectedHealthConditions(),
    };
    if (proteinFilterExplicit) body.protein_filter = selectedProteinFilter || null;
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
  $("results-panel").classList.add("hidden");
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
    meta = await api("/search/meta");
    renderChipOptions("diet-options", meta.diets, "diet", "chip-diet");
    renderChipOptions("intolerance-options", meta.intolerances, "intolerance", "chip-allergy");
    renderChipOptions("health-condition-options", meta.health_conditions, "health-condition", "chip-medical");
    const badge = $("mock-badge");
    if (badge) {
      if (meta.mock_mode || !meta.spoonacular_configured) {
        badge.textContent = meta.spoonacular_configured
          ? "Demo mode"
          : "API keys not detected on server";
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

$("back-to-results")?.addEventListener("click", () => {
  $("inspired-panel").classList.add("hidden");
  $("results-panel").classList.remove("hidden");
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
  if (currentChefProposal) startInspiredCook();
});
$("mode-direct")?.addEventListener("click", () => {
  setStepMode("direct");
  if (currentChefProposal) startInspiredCook();
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