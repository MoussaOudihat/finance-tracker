// Suggestion de catégorie par IA sur le formulaire de dépense.
// Servi depuis /static (CSP script-src 'self'), jeton CSRF en en-tête.
(function () {
  "use strict";
  var btn = document.getElementById("suggest-category");
  var form = document.getElementById("entry-form");
  var status = document.getElementById("suggest-status");
  if (!btn || !form) return;

  btn.addEventListener("click", function () {
    var label = form.elements.label.value.trim();
    var payee = form.elements.payee ? form.elements.payee.value.trim() : "";
    if (!label && !payee) {
      status.textContent = "Saisissez d'abord un libellé ou une enseigne.";
      return;
    }
    btn.disabled = true;
    status.textContent = "Analyse en cours…";
    fetch("/api/categorize", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": form.dataset.csrf },
      body: JSON.stringify({ label: label, payee: payee })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.d.detail || "Suggestion impossible.");
        form.elements.category_id.value = String(res.d.category_id);
        status.textContent = "Catégorie suggérée : " + res.d.category + " (vérifiez avant d'ajouter).";
      })
      .catch(function (e) { status.textContent = e.message; })
      .finally(function () { btn.disabled = false; });
  });
})();
