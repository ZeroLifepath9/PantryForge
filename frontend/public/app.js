const API = "";
let token = localStorage.getItem("pf_token") || "";
let isGuest = false;
let meta = { diets: [], intolerances: [], health_conditions: [], mock_mode: true };
let lastResults = [];
let currentRecipeId = null;
let stepMode = "beginner";
let prefsSaveTimer = null;

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
  el.textContent = msg || "";
  el.classList.toggle("error", !!isError);
}

function tierClass(tier) {
  return `tier tier-${tier}`;
}

function selectedDiets() {
  return [...document.querySelectorAll("#diet-options input:checked")].map((el) => el.value);
}

function selectedIntolerances() {
  return [...document.querySelectorAll("#intolerance-options input:checked")].map((el) => el.value);
}

function selectedHealthConditions() {
  return [...document.querySelectorAll("#health-condition-options input:checked")].map(
    (el) => el.value
  );
}

function renderChipOptions(containerId, options, name, extraClass = "") {
  const wrap = $(containerId);
  if (!wrap) return;
  const chips = options || [];
  if (!chips.length) {
    wrap.innerHTML = `<p class="fieldset-hint">No options available.</p>`;
    return;
  }
  wrap.innerHTML = chips
    .map(
      (d) =>
        `<label class="chip chip-token ${extraClass}"><input type="checkbox" name="${name}" value="${d.value}" />${d.label}</label>`
    )
    .join("");
}

function renderDietOptions() {
  renderChipOptions("diet-options", meta.diets, "diet", "chip-diet");
}

function renderIntoleranceOptions() {
  renderChipOptions("intolerance-options", meta.intolerances, "intolerance", "chip-allergy");
}

function renderHealthConditionOptions() {
  renderChipOptions(
    "health-condition-options",
    meta.health_conditions,
    "health-condition",
    "chip-medical"
  );
}

function applyPreferences(prefs) {
  if (!prefs) return;
  $("explain-techniques").checked = prefs.explain_techniques;
  $("include-pantry").checked = prefs.include_pantry_staples;
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
        include_pantry_staples: $("include-pantry").checked,
      }),
    });
  } catch {
    /* non-blocking */
  }
}

function showLanding() {
  $("landing-panel").classList.remove("hidden");
  $("search-panel").classList.add("hidden");
  $("results-panel").classList.add("hidden");
  $("recipe-panel").classList.add("hidden");
  $("session-badge").classList.add("hidden");
  $("auth-user").classList.add("hidden");
  $("sign-out").classList.add("hidden");
}

function showApp(displayName = "", guest = false) {
  $("landing-panel").classList.add("hidden");
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

function renderResults(data) {
  lastResults = data.results || [];
  $("results-panel").classList.remove("hidden");
  $("recipe-panel").classList.add("hidden");
  const count = lastResults.length;
  $("results-heading").textContent = count ? `Your options (${count})` : "Your options";
  $("results-message").textContent = data.message || "";
  const parsed = $("parsed-ingredients");
  if (data.effective_ingredients?.length) {
    parsed.classList.remove("hidden");
    parsed.innerHTML = data.effective_ingredients
      .map((i) => `<span>${i}</span>`)
      .join("");
  } else {
    parsed.classList.add("hidden");
  }

  const list = $("results-list");
  if (!lastResults.length) {
    list.innerHTML = `<p class="hint">No matches. Try adding pasta, oil, or cheese — or loosen diet filters.</p>`;
    return;
  }

  list.innerHTML = lastResults
    .map((r) => {
      const missed = (r.missed_ingredients || [])
        .map((m) => `<span class="missed">${m.name}</span>`)
        .join("");
      const used = (r.used_ingredients || [])
        .map((m) => `<span>${m.name}</span>`)
        .join("");
      return `
        <details class="result-card">
          <summary>
            <img class="result-thumb" src="${r.image || ""}" alt="" loading="lazy" />
            <div>
              <div class="result-title">${r.title}</div>
              <div class="${tierClass(r.match_tier)}">${r.match_label}</div>
            </div>
          </summary>
          <div class="result-body">
            <p>${r.summary || ""}</p>
            ${r.ready_in_minutes ? `<p class="hint">${r.ready_in_minutes} min · ${r.servings || "?"} servings</p>` : ""}
            ${used ? `<div class="ingredient-row">${used}</div>` : ""}
            ${missed ? `<p class="hint">Still need:</p><div class="ingredient-row">${missed}</div>` : ""}
            <div class="card-actions">
              <button type="button" class="btn-primary" data-open-recipe="${r.id}">Cook this</button>
              ${r.source_url ? `<a href="${r.source_url}" target="_blank" rel="noopener">Original recipe</a>` : ""}
              ${r.video_url ? `<a href="${r.video_url}" target="_blank" rel="noopener">Watch video</a>` : ""}
            </div>
          </div>
        </details>`;
    })
    .join("");

  list.querySelectorAll("[data-open-recipe]").forEach((btn) => {
    btn.addEventListener("click", () => openRecipe(Number(btn.dataset.openRecipe)));
  });

  $("results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function openRecipe(id) {
  currentRecipeId = id;
  $("results-panel").classList.add("hidden");
  $("recipe-panel").classList.remove("hidden");
  $("recipe-title").textContent = "Loading…";
  $("recipe-steps").innerHTML = "";
  try {
    const detail = await api(`/recipes/${id}`);
    $("recipe-title").textContent = detail.title;
    $("recipe-meta").textContent = [
      detail.ready_in_minutes ? `${detail.ready_in_minutes} min` : null,
      detail.servings ? `${detail.servings} servings` : null,
      detail.mock ? "mock recipe" : null,
    ]
      .filter(Boolean)
      .join(" · ");
    $("recipe-links").innerHTML = [
      detail.source_url
        ? `<a href="${detail.source_url}" target="_blank" rel="noopener">Original recipe</a>`
        : "",
      detail.video_url
        ? `<a href="${detail.video_url}" target="_blank" rel="noopener">Watch video</a>`
        : "",
    ].join("");
    await loadSimplifiedSteps();
  } catch (err) {
    $("recipe-title").textContent = "Could not load recipe";
    setStatus($("search-status"), err.message, true);
  }
}

async function loadSimplifiedSteps() {
  if (!currentRecipeId) return;
  const explain = stepMode === "beginner";
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

async function runSearch() {
  const text = $("ingredient-input").value.trim();
  if (!text) {
    setStatus($("search-status"), "Add at least one ingredient.", true);
    return;
  }
  setStatus($("search-status"), "Searching…");
  $("search-btn").disabled = true;
  try {
    await savePreferences();
    let parsed;
    try {
      parsed = await api("/search/parse-ingredients", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
    } catch (err) {
      throw new Error(`Ingredient parse failed: ${err.message}`);
    }
    let data;
    try {
      data = await api("/search/recipes", {
        method: "POST",
        body: JSON.stringify({
          ingredients: parsed.ingredients,
          diets: selectedDiets(),
          intolerances: selectedIntolerances(),
          health_conditions: selectedHealthConditions(),
          include_pantry_staples: $("include-pantry").checked,
        }),
      });
    } catch (err) {
      throw new Error(`Recipe search failed: ${err.message}`);
    }
    renderResults(data);
    setStatus(
      $("search-status"),
      data.mock ? "Showing mock recipes (no API key used)." : "Results ready."
    );
  } catch (err) {
    setStatus($("search-status"), err.message, true);
  } finally {
    $("search-btn").disabled = false;
  }
}

async function enterSession(authData) {
  token = authData.access_token;
  localStorage.setItem("pf_token", token);
  isGuest = authData.is_guest;
  showApp(authData.email, authData.is_guest);
  try {
    const prefs = await api("/preferences/me");
    applyPreferences(prefs);
  } catch {
    /* defaults are fine */
  }
}

async function bootstrap() {
  try {
    const health = await api("/healthz");
    const tag = $("build-tag");
    if (tag && health.version) tag.textContent = `Build ${health.version}`;
    meta = await api("/search/meta");
    renderDietOptions();
    renderIntoleranceOptions();
    renderHealthConditionOptions();
    if (meta.mock_mode) $("mock-badge").classList.remove("hidden");
  } catch {
    setStatus($("auth-status"), "Could not reach API. Is the server running?", true);
    showLanding();
    return;
  }

  if (token) {
    try {
      const me = await api("/auth/me");
      showApp(me.email, me.is_guest);
      const prefs = await api("/preferences/me");
      applyPreferences(prefs);
      return;
    } catch {
      token = "";
      localStorage.removeItem("pf_token");
    }
  }
  showLanding();
}

$("guest-btn").addEventListener("click", async () => {
  setStatus($("auth-status"), "Starting guest session…");
  try {
    const data = await api("/auth/guest", { method: "POST" });
    setStatus($("auth-status"), "");
    await enterSession(data);
  } catch (err) {
    setStatus($("auth-status"), err.message, true);
  }
});

$("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const mode = document.querySelector(".auth-tabs button.active")?.dataset.authMode || "login";
  const fd = new FormData(e.target);
  const body = { email: fd.get("email"), password: fd.get("password") };
  setStatus($("auth-status"), "…");
  try {
    const data = await api(`/auth/${mode}`, { method: "POST", body: JSON.stringify(body) });
    setStatus($("auth-status"), "");
    await enterSession(data);
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

$("sign-out").addEventListener("click", () => {
  token = "";
  isGuest = false;
  localStorage.removeItem("pf_token");
  $("ingredient-input").value = "";
  $("results-panel").classList.add("hidden");
  $("recipe-panel").classList.add("hidden");
  showLanding();
});

$("search-btn").addEventListener("click", runSearch);

$("back-to-results").addEventListener("click", () => {
  $("recipe-panel").classList.add("hidden");
  $("results-panel").classList.remove("hidden");
});

$("mode-beginner").addEventListener("click", async () => {
  stepMode = "beginner";
  $("mode-beginner").classList.add("active");
  $("mode-direct").classList.remove("active");
  await loadSimplifiedSteps();
});

$("mode-direct").addEventListener("click", async () => {
  stepMode = "direct";
  $("mode-direct").classList.add("active");
  $("mode-beginner").classList.remove("active");
  await loadSimplifiedSteps();
});

document.addEventListener("change", (e) => {
  const t = e.target;
  if (
    t.matches(
      "#diet-options input, #intolerance-options input, #health-condition-options input, #include-pantry, #explain-techniques"
    )
  ) {
    schedulePrefsSave();
  }
});

bootstrap();