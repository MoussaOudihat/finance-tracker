"""Tests de non-régression des corrections de l'audit v2.0.0 (database.py)."""
import zipfile

import pytest

from database import Database


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "t.db"))
    yield d
    d.close()


def _notion_zip(tmp_path, csv_text: str) -> str:
    path = tmp_path / "notion.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Depenses_all.csv", csv_text)
    return str(path)


def test_notion_import_new_and_mixed_case_categories(db, tmp_path):
    # Le cache "cats" est chaud avant l'import (comme au démarrage de l'app).
    db.get_categories()
    csv_text = (
        "Nom,Category,à qui,Mois,Montant\n"
        "Billets,Voyages Lointains,AIR,Janvier 26,\"300,00 €\"\n"
        "Courses,Alimentation,lidl,Janvier 26,\"45,50 €\"\n"
        "Divers,,,Janvier 26,\"10 €\"\n"
    )
    rev, exp, sav = db.import_notion_zip(_notion_zip(tmp_path, csv_text))
    assert (rev, exp, sav) == (0, 3, 0)
    by_cat = {r["name"]: r["total"] for r in db.get_expenses_by_category(2026, 1)}
    # Nouvelle catégorie bien utilisée (et non rabattue sur AUTRES)
    assert by_cat["VOYAGES LOINTAINS"] == pytest.approx(300.0)
    # Casse différente de la catégorie stockée : retrouvée
    assert by_cat["ALIMENTATION"] == pytest.approx(45.5)
    # Catégorie vide -> AUTRES (et non ligne ignorée)
    assert by_cat["AUTRES"] == pytest.approx(10.0)
    # Le cache a bien été invalidé en sortie de batch_mode()
    assert "VOYAGES LOINTAINS" in {c["name"] for c in db.get_categories()}


def test_ui_setting_does_not_clear_query_cache(db):
    db.get_categories()
    assert "cats" in db._cache
    db.set_setting("ui_section_rapports", "0")
    assert "cats" in db._cache
    db.set_setting("currency", "EUR")
    assert "cats" not in db._cache


def test_top_labels_grouped_over_period(db):
    cat = db.get_categories()[0]["id"]
    for m in (1, 2, 3):
        db.add_expense(2026, m, cat, 900, "Loyer")
        db.add_revenue(2026, m, "Salaire", 2500)
    db.add_expense(2026, 2, cat, 120, "", "LIDL")
    db.add_expense(2026, 3, cat, 80, "", "lidl")
    periods = [(2026, 1), (2026, 2), (2026, 3)]

    top = db.get_top_expense_labels_range(periods, limit=5)
    assert [r["name"] for r in top] == ["Loyer", "LIDL"]
    assert top[0]["total"] == pytest.approx(2700)
    assert top[1]["total"] == pytest.approx(200)

    rev = db.get_top_revenue_sources_range(periods, limit=3)
    assert len(rev) == 1 and rev[0]["total"] == pytest.approx(7500)


def test_update_rejects_non_positive_amounts(db):
    cat = db.get_categories()[0]["id"]
    db.add_expense(2026, 1, cat, 10, "x")
    exp_id = db.get_expenses(2026, 1)[0]["id"]
    with pytest.raises(ValueError):
        db.update_expense(exp_id, cat, 0, "x", "")
    db.add_revenue(2026, 1, "Salaire", 10)
    rev_id = db.get_revenues(2026, 1)[0]["id"]
    with pytest.raises(ValueError):
        db.update_revenue(rev_id, "Salaire", -5, "")
