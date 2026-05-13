const API_BASE = "https://blindtaste.onrender.com";

const _wakeupTimer = setTimeout(() => {
  document.getElementById('server-status').style.display = 'block';
}, 4000);

async function loadWineTypes() {
  try {
    const res  = await fetch(`${API_BASE}/api/wine-types`);
    clearTimeout(_wakeupTimer);
    document.getElementById('server-status').style.display = 'none';
    const data = await res.json();
    const sel  = document.getElementById("wine_type");
    data.wine_types.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      sel.appendChild(opt);
    });
  } catch {
    clearTimeout(_wakeupTimer);
    document.getElementById('server-status').style.display = 'none';
  }
}

async function loadFoodPairings(wineType) {
  const sel = document.getElementById("food_pairing");
  const currentValue = sel.value;
  sel.innerHTML = '<option value="">— Any pairing —</option>';
  try {
    const url  = wineType
      ? `${API_BASE}/api/food-pairings?wine_type=${encodeURIComponent(wineType)}`
      : `${API_BASE}/api/food-pairings`;
    const res  = await fetch(url);
    const data = await res.json();
    data.food_pairings.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      sel.appendChild(opt);
    });
    // Restore previous selection if it still exists in the new list
    if ([...sel.options].some(o => o.value === currentValue)) {
      sel.value = currentValue;
    }
  } catch { /* keep default "Any pairing" option */ }
}

document.getElementById("wine_type").addEventListener("change", function () {
  loadFoodPairings(this.value);
});

document.getElementById("flavor-form").addEventListener("submit", async e => {
  e.preventDefault();
  const errorEl     = document.getElementById("form-error");
  const wine_type    = document.getElementById("wine_type").value;
  const body         = document.getElementById("body").value;
  const acidity      = document.getElementById("acidity").value;
  const alcohol      = document.getElementById("alcohol").value;
  const food_pairing = document.getElementById("food_pairing").value;

  errorEl.style.display = "none";

  if (!wine_type && !body && !acidity && !alcohol && !food_pairing) {
    errorEl.textContent = "Please fill in at least one field.";
    errorEl.style.display = "block";
    return;
  }

  const payload = {};
  if (wine_type)    payload.wine_type    = wine_type;
  if (body)         payload.body         = parseFloat(body);
  if (acidity)      payload.acidity      = parseFloat(acidity);
  if (alcohol)      payload.alcohol      = parseFloat(alcohol);
  if (food_pairing) payload.food_pairing = food_pairing;

  try {
    const res  = await fetch(`${API_BASE}/api/recommend/flavor`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      errorEl.textContent = `Error: ${data.error}`;
      errorEl.style.display = "block";
      return;
    }
    localStorage.setItem("bt_results",    JSON.stringify(data.results));
    localStorage.setItem("bt_input_mode", "flavor_profile");
    localStorage.setItem("bt_input",      JSON.stringify(payload));
    window.location.href = "results.html";
  } catch {
    errorEl.textContent = "Could not reach the server. Make sure the API is running on port 5000.";
    errorEl.style.display = "block";
  }
});

loadWineTypes();
loadFoodPairings("");
