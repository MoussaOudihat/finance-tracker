// Saisie en masse : lignes ajoutées sur place, retour visuel pendant l'envoi,
// anti double-envoi, compteur en direct et contrôle des catégories avant envoi.
// Servi depuis /static (CSP script-src 'self'). La page reste utilisable sans JS.
(function () {
  "use strict";
  var form = document.getElementById("bulk-form");
  if (!form) return;
  var table = form.querySelector("table.grid");
  var tbody = table.tBodies[0];
  var maxRows = parseInt(table.dataset.maxRows, 10) || 200;
  var summary = document.getElementById("bulk-summary");
  var saveBtn = document.getElementById("bulk-save");
  var addBtn = document.getElementById("bulk-add");
  var hasCat = !!form.querySelector("select[name=cat]");
  var ADD_STEP = 10;

  function rows() { return Array.prototype.slice.call(tbody.querySelectorAll("tr[data-row]")); }
  function field(tr, name) { return tr.querySelector("[name=" + name + "]"); }
  function val(tr, name) { var f = field(tr, name); return f ? f.value.trim() : ""; }
  function parseAmount(s) {
    s = s.replace(/[\s €]/g, "");
    if (s.indexOf(",") >= 0 && s.indexOf(".") >= 0) {
      s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".")
                                                  : s.replace(/,/g, "");
    } else { s = s.replace(",", "."); }
    var v = Math.abs(parseFloat(s));
    return isFinite(v) ? v : NaN;
  }
  function isBlank(tr) { return !(val(tr, "amount") || val(tr, "label") || val(tr, "extra")); }
  function isKept(tr) { var k = field(tr, "keep"); return k && k.checked; }
  function plural(n, word) { return n + " " + word + (n > 1 ? "s" : ""); }
  var euro = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

  // ── Ajout de lignes ──────────────────────────────────────
  function addRows(count) {
    var all = rows();
    var model = all[all.length - 1];
    if (!model) return;
    var room = maxRows - all.length;
    for (var k = 0; k < Math.min(count, room); k++) {
      var i = all.length + k;
      var tr = model.cloneNode(true);
      tr.className = "row-blank";
      tr.querySelectorAll(".badge-ai").forEach(function (b) { b.remove(); });
      tr.querySelectorAll("input, select").forEach(function (f) {
        if (f.type === "checkbox") { f.checked = true; f.value = String(i); }
        else if (f.tagName === "SELECT") { f.selectedIndex = 0; f.classList.remove("field-error"); }
        else if (f.type !== "hidden") { f.value = ""; }
        var lbl = f.getAttribute("aria-label");
        if (lbl) f.setAttribute("aria-label", lbl.replace(/\d+$/, String(i + 1)));
      });
      tbody.appendChild(tr);
    }
    refresh();
  }

  if (addBtn) {
    addBtn.addEventListener("click", function (e) {
      e.preventDefault();                       // sans JS : aller-retour serveur
      var before = rows().length;
      addRows(ADD_STEP);
      var first = rows()[before];
      if (first) (field(first, "cat") || field(first, "amount")).focus();
    });
  }

  // ── Compteur ─────────────────────────────────────────────
  function refresh() {
    var all = rows(), n = 0, total = 0;
    all.forEach(function (tr) {
      var blank = isBlank(tr), kept = isKept(tr);
      tr.classList.toggle("row-blank", blank);
      tr.classList.toggle("row-skipped", !blank && !kept);
      if (!blank && kept) {
        n += 1;
        var v = parseAmount(val(tr, "amount"));
        if (!isNaN(v)) total += v;
      }
    });
    if (summary && !summary.classList.contains("neg")) {
      summary.textContent = n ? plural(n, "ligne") + " à enregistrer · total " + euro.format(total)
                              : "Aucune ligne à enregistrer pour l'instant.";
    }
    if (saveBtn) saveBtn.textContent = n ? "Enregistrer " + plural(n, "ligne") : "Enregistrer les lignes";
    if (addBtn) addBtn.disabled = all.length >= maxRows;
  }

  function markMissing(tr, on) {
    var sel = field(tr, "cat");
    if (!sel) return;
    sel.classList.toggle("field-error", on);
    sel.setAttribute("aria-invalid", on ? "true" : "false");
  }

  form.addEventListener("input", function (e) {
    var all = rows();
    // La dernière ligne commence à être remplie : on en prépare une autre.
    if (e.target.closest("tr") === all[all.length - 1]) addRows(1);
    if (summary) summary.classList.remove("neg");
    refresh();
  });
  form.addEventListener("change", function (e) {
    if (e.target.name === "cat" && e.target.value) markMissing(e.target.closest("tr"), false);
    refresh();
  });

  // ── Envoi ────────────────────────────────────────────────
  form.addEventListener("submit", function (e) {
    if (form.dataset.busy === "1") { e.preventDefault(); return; }   // double clic
    var btn = e.submitter || saveBtn;
    var saving = !btn || !btn.getAttribute("formaction");
    if (saving && hasCat) {
      var missing = rows().filter(function (tr) { return isKept(tr) && !isBlank(tr) && !val(tr, "cat"); });
      rows().forEach(function (tr) { markMissing(tr, missing.indexOf(tr) >= 0); });
      if (missing.length) {
        e.preventDefault();
        summary.textContent = plural(missing.length, "ligne") + " sans catégorie : choisissez-la, " +
          "ou décochez la ligne. Rien n'a été envoyé.";
        summary.classList.add("neg");
        field(missing[0], "cat").focus();
        return;
      }
    }
    if (summary) summary.classList.remove("neg");
    form.dataset.busy = "1";
    form.setAttribute("aria-busy", "true");
    if (btn) {
      btn.classList.add("is-busy");
      btn.textContent = saving ? "Enregistrement…" : "Analyse en cours…";
    }
    // Désactivation différée : l'envoi en cours (et son formaction) est déjà parti.
    setTimeout(function () {
      form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = true; });
    }, 0);
  });

  // Retour arrière (cache navigateur) : la page doit redevenir utilisable.
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    form.dataset.busy = "";
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button[type=submit]").forEach(function (b) {
      b.disabled = false; b.classList.remove("is-busy");
    });
    var ai = form.querySelector("button[formaction$='/suggestion']");
    if (ai) ai.textContent = "✨ Suggérer les catégories manquantes";
    refresh();
  });

  refresh();
})();
