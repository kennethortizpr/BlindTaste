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
    sel.innerHTML = '<option value="">— Select type —</option>';
    data.wine_types.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      sel.appendChild(opt);
    });
  } catch {
    clearTimeout(_wakeupTimer);
    document.getElementById('server-status').style.display = 'none';
    document.getElementById("wine_type").innerHTML =
      '<option value="">Could not load — is the API running?</option>';
  }
}

async function loadGrapes(wineType) {
  const sel = document.getElementById("main_grape");
  if (!wineType) {
    sel.innerHTML = '<option value="">Select a wine type first</option>';
    return;
  }
  sel.innerHTML = '<option value="">Loading…</option>';
  try {
    const res  = await fetch(`${API_BASE}/api/grapes?wine_type=${encodeURIComponent(wineType)}`);
    const data = await res.json();
    sel.innerHTML = '<option value="">— Select grape —</option>';
    data.grapes.forEach(g => {
      const opt = document.createElement("option");
      opt.value = g;
      opt.textContent = g;
      sel.appendChild(opt);
    });
  } catch {
    sel.innerHTML = '<option value="">Could not load grapes</option>';
  }
}

document.getElementById("wine_type").addEventListener("change", e => {
  loadGrapes(e.target.value);
});

document.getElementById("label-form").addEventListener("submit", async e => {
  e.preventDefault();
  const errorEl    = document.getElementById("form-error");
  const wine_type  = document.getElementById("wine_type").value;
  const main_grape = document.getElementById("main_grape").value;
  const alcohol    = document.getElementById("alcohol").value;
  const acidity    = document.getElementById("acidity").value;
  const body       = document.getElementById("body").value;

  errorEl.style.display = "none";

  if (!wine_type || !main_grape || !alcohol) {
    errorEl.textContent = "Please fill in all required fields (Wine Type, Main Grape, Alcohol %).";
    errorEl.style.display = "block";
    return;
  }

  const payload = { wine_type, main_grape, alcohol: parseFloat(alcohol) };
  if (acidity) payload.acidity = parseFloat(acidity);
  if (body)    payload.body    = parseFloat(body);

  try {
    const res  = await fetch(`${API_BASE}/api/recommend/label`, {
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
    localStorage.setItem("bt_input_mode", "label");
    localStorage.setItem("bt_input",      JSON.stringify(payload));
    window.location.href = "results.html";
  } catch {
    errorEl.textContent = "Could not reach the server. Make sure the API is running on port 5000.";
    errorEl.style.display = "block";
  }
});

loadWineTypes();
