"""
utils_taxes.py — Export des données fiscalement pertinentes
"""
import csv


def export_tax_summary(db, year: int, output_path: str) -> dict:
    """
    Extrait les données fiscales pour l'année donnée.
    Génère un fichier CSV à output_path.

    Args:
        db: Instance de Database
        year: Année fiscale
        output_path: Chemin du fichier CSV de sortie

    Returns:
        dict avec les montants par catégorie fiscale
    """

    # Initialiser le dictionnaire de résultats
    tax_data = {
        "plus_values_boursieres": 0.0,
        "plus_values_crypto": 0.0,
        "revenus_fonciers": 0.0,
        "dons_deductibles": 0.0,
        "frais_formation": 0.0,
        "total_revenus": 0.0,
        "cotisations_retraite": 0.0,
    }

    # ──────────────────────────────────────────
    # 1. PLUS-VALUES BOURSIÈRES ET CRYPTO
    # ──────────────────────────────────────────
    assets_current = db.get_assets_current()

    for asset in assets_current:
        asset_type = asset["asset_type"]
        value = asset["value"] if asset["value"] is not None else 0.0
        cost_basis = asset["cost_basis"] if asset["cost_basis"] is not None else 0.0
        plus_value = value - cost_basis

        if asset_type == "bourse" and plus_value > 0:
            tax_data["plus_values_boursieres"] += plus_value

        elif asset_type == "crypto" and plus_value > 0:
            tax_data["plus_values_crypto"] += plus_value

    # ──────────────────────────────────────────
    # 2. REVENUS FONCIERS (immobilier)
    # Estimation : à partir des notes sur les actifs immobiliers
    # ──────────────────────────────────────────
    for asset in assets_current:
        if asset["asset_type"] == "immobilier":
            # On pourrait extraire un taux locatif depuis asset["notes"]
            # Pour simplifier : on met 0, ou on estime une valeur locative standard
            # (p. ex. 3% de la valeur annuelle)
            annual_rental_estimate = (asset["value"] if asset["value"] is not None else 0.0) * 0.03
            tax_data["revenus_fonciers"] += annual_rental_estimate

    # ──────────────────────────────────────────
    # 3-4-6. DONS / FORMATION / RETRAITE
    # Récupérer TOUTES les dépenses de l'année en 1 seule requête SQL
    # (au lieu de 12 appels get_expenses séparés par section = N+1)
    # ──────────────────────────────────────────
    all_expenses_year = db.get_expenses_by_year(year)
    for exp in all_expenses_year:
        cat_name = exp["cat"].upper() if exp["cat"] else ""
        amount   = exp["amount"] or 0.0
        if cat_name == "DONS":
            tax_data["dons_deductibles"] += amount
        elif cat_name == "FORMATION":
            tax_data["frais_formation"] += amount
        elif cat_name == "RETRAITE":
            tax_data["cotisations_retraite"] += amount

    # ──────────────────────────────────────────
    # 5. TOTAL REVENUS (de l'année)
    # ──────────────────────────────────────────
    summary_data = db.monthly_summary(limit=24)
    for row in summary_data:
        if row["year"] == year:
            tax_data["total_revenus"] += row["rev"]

    # ──────────────────────────────────────────
    # Générer le fichier CSV
    # ──────────────────────────────────────────
    csv_rows = [
        ["Type fiscal", "Montant (€)", "Notes"],
        ["Plus-values boursières latentes", f"{tax_data['plus_values_boursieres']:.2f}",
         "Gains non réalisés (Bourse / ETF / PEA)"],
        ["Plus-values crypto latentes", f"{tax_data['plus_values_crypto']:.2f}",
         "Gains non réalisés (Crypto)"],
        ["Revenus fonciers estimés", f"{tax_data['revenus_fonciers']:.2f}",
         "Estimation basée sur 3% de valeur (immobilier)"],
        ["Dons déductibles", f"{tax_data['dons_deductibles']:.2f}",
         "Somme des dépenses catégorie DONS"],
        ["Frais de formation", f"{tax_data['frais_formation']:.2f}",
         "Somme des dépenses catégorie FORMATION"],
        ["Total revenus annuels", f"{tax_data['total_revenus']:.2f}",
         "Revenus déclarés (brut)"],
        ["Cotisations épargne retraite", f"{tax_data['cotisations_retraite']:.2f}",
         "Montants de catégorie RETRAITE"],
        ["", "", ""],
        ["RÉSUMÉ FISCAL", "", ""],
        ["Plus-values totales latentes", f"{tax_data['plus_values_boursieres'] + tax_data['plus_values_crypto']:.2f}",
         "Bourse + Crypto"],
        ["Revenus nets estimés", f"{tax_data['total_revenus'] + tax_data['revenus_fonciers'] - tax_data['cotisations_retraite']:.2f}",
         "Total revenus + fonciers - retraite"],
        ["Déductions possibles", f"{tax_data['dons_deductibles'] + tax_data['frais_formation']:.2f}",
         "Dons + Formation"],
    ]

    # Écrire le CSV
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=",")
        writer.writerows(csv_rows)

    return tax_data
