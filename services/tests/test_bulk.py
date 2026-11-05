"""Saisie en masse : analyse des collages (unitaire) et parcours web complet."""
import re

import pytest

from test_web import csrf, login, setup  # noqa: F401 — fixture réutilisée
from web.app import bulk

CATS = [{"id": 1, "name": "ALIMENTATION"}, {"id": 2, "name": "AUTRES"},
        {"id": 3, "name": "LOGEMENT"}, {"id": 4, "name": "RESTAURANTS"},
        {"id": 5, "name": "Santé"}]


@pytest.mark.parametrize("raw,expected", [
    ("42,50", 42.5), ("1 234,56 €", 1234.56), ("1 234,56", 1234.56), ("-12,30", 12.3),
    ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("12.5", 12.5), ("(8.90)", 8.9),
    ("1.234.567", 1234567), ("+3", 3), ("800", 800),
    ("abc", None), ("", None), ("12/03/2026", None), ("nan", None), ("1e9999", None), ("12a", None),
])
def test_parse_amount(raw, expected):
    assert bulk.parse_amount(raw) == expected


def test_paste_excel_without_header_detects_columns():
    text = "ALIMENTATION\t42,50\tCourses\tLidl\r\n800\tlogement\tLoyer\n\n05/11/2026\tSanté\t-25,00\tPharmacie\n"
    rows, warnings = bulk.parse_paste(text, "expenses", CATS)
    assert warnings == []
    assert [(r.category_id, r.amount, r.label, r.extra) for r in rows] == [
        (1, "42,50", "Courses", "Lidl"),
        (3, "800,00", "Loyer", ""),
        (5, "25,00", "Pharmacie", ""),            # date ignorée, accent et casse ignorés
    ]


def test_paste_bank_export_with_header():
    text = ("Date;Libellé;Débit;Crédit;Catégorie\n"
            "02/11/2026;CB CARREFOUR;-54,20;;Alimentation\n"
            "03/11/2026;PRLV FREE MOBILE;-19,99;;Inconnue\n")
    rows, _ = bulk.parse_paste(text, "expenses", CATS)
    assert [(r.label, r.amount, r.category_id) for r in rows] == [
        ("CB CARREFOUR", "54,20", 1), ("PRLV FREE MOBILE", "19,99", None)]
    bulk.validate(rows, "expenses", CATS)
    assert rows[1].errors == ["Catégorie à choisir."] and rows[0].errors == []


def test_paste_revenues_and_english_csv():
    rows, _ = bulk.parse_paste("Salaire\t2 500,00\tNovembre\nPrime;300", "revenues", CATS)
    assert [(r.extra, r.amount, r.label) for r in rows] == [
        ("Salaire", "2500,00", "Novembre"), ("Prime", "300,00", "")]
    rows, _ = bulk.parse_paste("category,amount,label\nRESTAURANTS,18.40,Pizza", "expenses", CATS)
    assert (rows[0].category_id, rows[0].amount, rows[0].label) == (4, "18,40", "Pizza")


def test_paste_limits_and_empty():
    rows, warnings = bulk.parse_paste("", "expenses", CATS)
    assert rows == [] and warnings
    rows, warnings = bulk.parse_paste("\n".join(f"AUTRES\t{i + 1}" for i in range(250)),
                                      "expenses", CATS)
    assert len(rows) == bulk.MAX_ROWS and "250 lignes" in warnings[0]
    rows, _ = bulk.parse_paste("AUTRES\t5\t" + "x" * 500, "expenses", CATS)
    assert len(rows[0].label) == 120


def test_validate_rejects_bad_rows_and_skips_blank_or_unchecked():
    rows = bulk.rows_from_form(keep=["0", "1", "3"], amounts=["10", "0", "99", ""],
                               cats=["1", "1", "", ""], labels=["a", "b", "c", ""],
                               extras=["", "", "", ""])
    assert bulk.validate(rows, "expenses", CATS) == []          # ligne 1 : montant 0
    assert rows[1].errors == ["Montant invalide."] and rows[2].errors == [] and rows[3].errors == []
    rows[1].amount = "12,5"
    assert bulk.validate(rows, "expenses", CATS) == [
        {"category_id": 1, "amount": 10.0, "label": "a", "payee": ""},
        {"category_id": 1, "amount": 12.5, "label": "b", "payee": ""}]
    with pytest.raises(ValueError):
        bulk.rows_from_form([], ["1"], [], [], [])


# ── Parcours web ─────────────────────────────────────────────

def _grid(page):
    return {name: re.findall(rf'name="{name}" value="([^"]*)"', page)
            for name in ("amount", "label", "extra")}


def test_bulk_expenses_end_to_end(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    page = c.get("/depenses/saisie?y=2026&m=11")
    assert page.status_code == 200 and page.text.count('name="amount"') == bulk.GRID_BLANK_ROWS
    tok = csrf(page.text)
    pasted = "ALIMENTATION\t42,50\tCourses\tlidl\nRESTAURANTS\t18\tPizza\nInconnu\t5\tMystère"
    prev = c.post("/depenses/saisie/apercu", data={"y": 2026, "m": 11, "paste": pasted, "csrf": tok})
    assert prev.status_code == 200 and "Catégorie à choisir." in prev.text
    g = _grid(prev.text)
    assert g["amount"][:3] == ["42,50", "18,00", "5,00"]
    n = len(g["amount"])
    cats = ["1", "4", ""] + [""] * (n - 3)

    # 1) ligne sans catégorie cochée : rien n'est écrit, la grille est conservée
    form = {"y": 2026, "m": 11, "keep": [str(i) for i in range(n)], "amount": g["amount"],
            "cat": cats, "label": g["label"], "extra": g["extra"], "csrf": tok}
    r = c.post("/depenses/saisie", data=form)
    assert r.status_code == 422 and "Corrigez les lignes signalées" in r.text and "Pizza" in r.text
    assert "Rien de saisi" in c.get("/depenses?y=2026&m=11").text

    # 2) ligne décochée : les deux autres sont enregistrées d'un coup
    form["keep"] = ["0", "1"]
    r = c.post("/depenses/saisie", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/depenses?y=2026&m=11"
    page = c.get("/depenses?y=2026&m=11").text
    assert "2 dépense(s) enregistré(e)s" in page and "LIDL" in page and "Mystère" not in page


def test_bulk_revenues_and_api_error_keeps_grid(setup, seeded, user_id):  # noqa: F811
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/revenus/saisie?y=2026&m=11").text)
    form = {"y": 2026, "m": 11, "keep": ["0", "1"], "amount": ["2 500", "300"], "cat": ["", ""],
            "label": ["Nov", ""], "extra": ["Salaire", "Prime"], "csrf": tok}
    r = c.post("/revenus/saisie", data=form, follow_redirects=False)
    assert r.status_code == 303
    assert "2 500,00" in c.get("/revenus?y=2026&m=11").text
    # mois clôturé côté base : refus de l'API, la saisie reste à l'écran
    seeded.seed("months", [{"id": 50, "user_id": user_id, "year": 2026, "month": 2, "closed": 1}])
    r = c.post("/revenus/saisie", data={**form, "m": 2})
    assert r.status_code == 409 and "a été enregistré" in r.text and 'value="Prime"' in r.text


def test_bulk_guards(setup):  # noqa: F811
    c, *_ = setup
    login(c)
    tok = csrf(c.get("/depenses/saisie?y=2026&m=11").text)
    assert c.get("/epargne/saisie?y=2026&m=11").status_code == 404
    assert c.post("/depenses/saisie", data={"y": 2026, "m": 11, "amount": ["1"], "cat": [],
                                            "label": [], "extra": [], "csrf": "forged"},
                  follow_redirects=False).status_code == 303          # CSRF : refus + retour
    r = c.post("/depenses/saisie", data={"y": 2026, "m": 11, "csrf": tok})
    assert r.status_code == 422 and "Aucune ligne" in r.text
    r = c.post("/depenses/saisie/apercu", data={"y": 2026, "m": 11, "csrf": tok,
                                               "paste": "x" * (bulk.MAX_PASTE_CHARS + 1)})
    assert r.status_code == 413
    r = c.post("/depenses/saisie/apercu", data={"y": 2026, "m": 11, "csrf": tok,
                                               "paste": "<script>alert(1)</script>\t5"})
    assert "<script>alert" not in r.text


# ── Suggestion IA des catégories ─────────────────────────────

def _with_ai(c, sessions, *, consent=True, fail=False):
    """Branche un faux ai-service et (dés)active le consentement IA."""
    import json as _json

    import httpx

    from fintrack_common.http import service_client
    calls = []

    def ai(request):
        body = _json.loads(request.content)
        calls.append(body)
        if fail:
            return httpx.Response(429, json={"detail": "Limite quotidienne de 40 requêtes IA atteinte."})
        res = [{"category_id": 4, "category": "RESTAURANTS"} if "pizz" in it["label"].lower()
               else None for it in body["items"]]
        return httpx.Response(200, json={"provider": "claude", "results": res})

    c.app.state.backends.clients["ai"] = service_client("http://ai", transport=httpx.MockTransport(ai))
    sessions.update(c.cookies["fintrack_sid"], ai_consent=consent, ai_provider="gemini")
    return calls


def test_paste_with_ai_suggestion(setup):  # noqa: F811
    c, _, sessions = setup
    login(c)
    calls = _with_ai(c, sessions)
    page = c.get("/depenses/saisie?y=2026&m=11").text
    assert 'name="ai" value="1" checked' in page
    r = c.post("/depenses/saisie/apercu", data={
        "y": 2026, "m": 11, "ai": "1", "csrf": csrf(page),
        "paste": "ALIMENTATION\t10\tCourses\n12\tPizzeria du coin\n7\tTruc bizarre"})
    assert r.status_code == 200
    assert len(calls) == 1 and calls[0]["provider"] == "gemini"
    assert [it["label"] for it in calls[0]["items"]] == ["Pizzeria du coin", "Truc bizarre"]
    assert "1 catégorie(s) suggérée(s)" in r.text and "✨ IA" in r.text
    assert "1 ligne(s) sans suggestion" in r.text
    assert re.search(r'<option value="4" selected>RESTAURANTS', r.text)
    # sans la case : aucun appel à l'IA
    c.post("/depenses/saisie/apercu", data={"y": 2026, "m": 11, "csrf": csrf(page),
                                           "paste": "12\tPizza"})
    assert len(calls) == 1


def test_grid_suggest_button_and_failures(setup):  # noqa: F811
    c, _, sessions = setup
    login(c)
    calls = _with_ai(c, sessions)
    tok = csrf(c.get("/depenses/saisie?y=2026&m=11").text)
    form = {"y": 2026, "m": 11, "keep": ["0", "1"], "amount": ["9", ""], "cat": ["", ""],
            "label": ["Pizza", ""], "extra": ["", ""], "csrf": tok}
    r = c.post("/depenses/saisie/suggestion", data=form)
    assert r.status_code == 200 and "✨ IA" in r.text and len(calls) == 1
    assert "Rien de saisi" in c.get("/depenses?y=2026&m=11").text      # rien enregistré
    # quota atteint : avertissement, la grille reste intacte
    _with_ai(c, sessions, fail=True)
    r = c.post("/depenses/saisie/suggestion", data=form)
    assert r.status_code == 200 and "Suggestion IA indisponible" in r.text and 'value="Pizza"' in r.text
    # sans consentement : pas d'appel, une explication
    calls = _with_ai(c, sessions, consent=False)
    r = c.post("/depenses/saisie/suggestion", data=form)
    assert calls == [] and "Activez d" in r.text
    assert "formaction" not in c.get("/depenses/saisie?y=2026&m=11").text
