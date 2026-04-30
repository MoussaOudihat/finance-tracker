"""
ui/pages/recommandations.py — Recommandations personnalisées

Analyse automatique des données financières pour proposer des conseils
concrets sur les dépenses, l'épargne et le patrimoine.
"""
import customtkinter as ctk
from config import C, MONTHS_FR, ASSET_LABEL
from ui.components import make_card


# ─────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────
_NB_MONTHS_ANALYSIS = 6   # nb de mois récents à analyser

# Catégories considérées comme "besoins essentiels" (règle 50/30/20)
_ESSENTIAL_CATS = {
    "LOGEMENT", "ALIMENTATION", "TRANSPORT", "VOITURE",
    "MUTUELLE", "SANTÉ", "IMPÔT", "BANQUE",
}
# Catégories "envies / lifestyle"
_LIFESTYLE_CATS = {
    "LOISIR ET SORTIES", "RESTAURANTS", "SHOPPING", "VÊTEMENTS",
    "VOYAGE", "SPORT ET FITNESS", "ABONNEMENT", "CADEAUX", "DONS",
}

# Niveau d'alerte
_LEVEL_OK      = "ok"
_LEVEL_WARNING = "warning"
_LEVEL_ALERT   = "alert"
_LEVEL_INFO    = "info"

_LEVEL_STYLE = {
    _LEVEL_OK:      {"icon": "✅", "fg": "#F0FDF4", "border": "#86EFAC", "color": "#15803D"},
    _LEVEL_WARNING: {"icon": "⚠️", "fg": "#FFFBEB", "border": "#FDE68A", "color": "#B45309"},
    _LEVEL_ALERT:   {"icon": "🔴", "fg": "#FEF2F2", "border": "#FCA5A5", "color": "#DC2626"},
    _LEVEL_INFO:    {"icon": "💡", "fg": "#EFF6FF", "border": "#BFDBFE", "color": "#1D4ED8"},
}


# ─────────────────────────────────────────────────────────────
#  Page principale
# ─────────────────────────────────────────────────────────────
class RecommandationsPage:
    def render(self, container: ctk.CTkFrame, app):
        db = app.db

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))

        ctk.CTkLabel(top, text="🧠  Recommandations & Optimisations",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C["text"]).pack(side="left")

        ctk.CTkLabel(top,
                     text=f"Analyse des {_NB_MONTHS_ANALYSIS} derniers mois",
                     font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(
            side="right", padx=8)

        # ── Scroll ──────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(container, fg_color=C["bg"])
        scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        scroll.grid_columnconfigure((0, 1), weight=1)

        # ── Analyse des données ──────────────────────────────────
        recs       = _build_recommendations(db)
        categories = _group_by_category(recs)

        if not recs:
            ctk.CTkLabel(scroll,
                         text="Pas assez de données pour générer des recommandations.\n"
                              "Saisissez au moins 2 mois de revenus et dépenses.",
                         text_color=C["muted"], justify="center",
                         font=ctk.CTkFont(size=13)).pack(expand=True, pady=60)
            return

        # ── Score global ─────────────────────────────────────────
        _render_score_banner(scroll, recs)

        # ── Sections par thème ────────────────────────────────────
        row_idx = [1]

        def _next_row():
            r = row_idx[0]
            row_idx[0] += 1
            return r

        for cat_key, cat_label, cat_icon, cat_recs in categories:
            if not cat_recs:
                continue

            # Titre de section
            sec_hdr = ctk.CTkFrame(scroll, fg_color="transparent")
            sec_hdr.grid(row=_next_row(), column=0, columnspan=2,
                         sticky="ew", pady=(14, 4))
            ctk.CTkLabel(sec_hdr,
                         text=f"{cat_icon}  {cat_label}",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=C["text"]).pack(side="left")

            # Cards de recommandations (2 par ligne)
            col_idx = 0
            cur_row = _next_row()
            for rec in cat_recs:
                _rec_card(scroll, rec, cur_row, col_idx)
                col_idx += 1
                if col_idx >= 2:
                    col_idx = 0
                    cur_row = _next_row()

        # ── Pied de page ─────────────────────────────────────────
        footer = ctk.CTkFrame(scroll, fg_color="transparent")
        footer.grid(row=_next_row(), column=0, columnspan=2,
                    sticky="ew", pady=(20, 4))
        ctk.CTkLabel(footer,
                     text="Ces recommandations sont générées automatiquement à partir de vos données.\n"
                          "Elles ne constituent pas un conseil financier professionnel.",
                     font=ctk.CTkFont(size=10), text_color=C["muted"],
                     justify="center").pack()


# ─────────────────────────────────────────────────────────────
#  Moteur d'analyse
# ─────────────────────────────────────────────────────────────
def _build_recommendations(db) -> list[dict]:
    """Génère la liste de recommandations à partir des données."""
    recs = []

    # ── Récupération des données ─────────────────────────────
    summary = db.monthly_summary(_NB_MONTHS_ANALYSIS)
    if len(summary) < 2:
        return recs

    # Du plus ancien au plus récent
    summary_asc = list(reversed(summary))
    recent      = summary_asc[-1]   # dernier mois
    all_assets  = db.get_assets_current()

    avg_rev = sum(r["rev"] for r in summary_asc) / len(summary_asc)
    avg_exp = sum(r["exp"] for r in summary_asc) / len(summary_asc)
    avg_sav = sum(r["sav"] for r in summary_asc) / len(summary_asc)

    # ── 1. TAUX D'ÉPARGNE ────────────────────────────────────
    recs += _analyze_savings_rate(avg_rev, avg_sav, summary_asc)

    # ── 2. RÈGLE 50/30/20 ───────────────────────────────────
    recs += _analyze_50_30_20(db, summary_asc, avg_rev)

    # ── 3. DÉPENSES EN HAUSSE ────────────────────────────────
    recs += _analyze_expense_trend(summary_asc)

    # ── 4. TOP CATÉGORIES ────────────────────────────────────
    recs += _analyze_top_categories(db, summary_asc, avg_rev)

    # ── 5. FOND D'URGENCE ────────────────────────────────────
    recs += _analyze_emergency_fund(all_assets, avg_exp)

    # ── 6. DIVERSIFICATION PATRIMOINE ───────────────────────
    recs += _analyze_diversification(all_assets)

    # ── 7. ÉPARGNE INVESTIE vs LIQUIDITÉS ───────────────────
    recs += _analyze_investment_ratio(all_assets)

    # ── 8. BILAN MENSUEL ─────────────────────────────────────
    recs += _analyze_monthly_balance(summary_asc, recent)

    return recs


def _analyze_savings_rate(avg_rev, avg_sav, summary):
    recs = []
    if avg_rev <= 0:
        return recs

    rate = avg_sav / avg_rev * 100
    trend_up = len(summary) >= 3 and summary[-1]["sav"] > summary[-2]["sav"]

    if rate >= 20:
        recs.append({
            "category": "epargne",
            "level":    _LEVEL_OK,
            "title":    f"Taux d'épargne : {rate:.1f}% ✨",
            "body":     f"Excellent ! Vous épargnez {rate:.1f}% de vos revenus en moyenne, "
                        f"soit {avg_sav:,.0f} €/mois. L'objectif recommandé est 20%.",
            "actions":  ["Maintenez cette discipline sur la durée.",
                         "Envisagez d'investir une partie de l'excédent en bourse ou PEA."],
        })
    elif rate >= 10:
        recs.append({
            "category": "epargne",
            "level":    _LEVEL_WARNING,
            "title":    f"Taux d'épargne : {rate:.1f}%",
            "body":     f"Votre taux d'épargne est de {rate:.1f}% ({avg_sav:,.0f} €/mois). "
                        f"C'est un bon début, mais l'objectif est d'atteindre 20%.",
            "actions":  [f"Cherchez à épargner {avg_rev * 0.20:,.0f} €/mois (20% de vos revenus).",
                         "Automatisez un virement épargne le jour de paie."],
        })
    else:
        recs.append({
            "category": "epargne",
            "level":    _LEVEL_ALERT,
            "title":    f"Taux d'épargne faible : {rate:.1f}%",
            "body":     f"Vous n'épargnez que {rate:.1f}% de vos revenus ({avg_sav:,.0f} €/mois). "
                        f"C'est insuffisant pour construire un patrimoine solide.",
            "actions":  [f"Objectif minimum : {avg_rev * 0.10:,.0f} €/mois (10%).",
                         "Identifiez les dépenses non-essentielles à réduire.",
                         "Mettez en place un virement automatique dès réception du salaire."],
        })

    return recs


def _analyze_50_30_20(db, summary, avg_rev):
    recs = []
    if avg_rev <= 0 or not summary:
        return recs

    # Calculer la moyenne des ratios sur les mois disponibles
    essential_totals = []
    lifestyle_totals = []

    for m in summary:
        cats = db.get_expenses_by_category(m["year"], m["month"])
        ess = sum(r["total"] for r in cats if r["name"] in _ESSENTIAL_CATS)
        lif = sum(r["total"] for r in cats if r["name"] in _LIFESTYLE_CATS)
        essential_totals.append(ess)
        lifestyle_totals.append(lif)

    avg_ess = sum(essential_totals) / len(essential_totals) if essential_totals else 0
    avg_lif = sum(lifestyle_totals) / len(lifestyle_totals) if lifestyle_totals else 0

    ess_pct = avg_ess / avg_rev * 100
    lif_pct = avg_lif / avg_rev * 100

    if ess_pct > 60:
        recs.append({
            "category": "depenses",
            "level":    _LEVEL_ALERT,
            "title":    f"Charges fixes élevées ({ess_pct:.0f}% des revenus)",
            "body":     f"Vos dépenses essentielles représentent {ess_pct:.0f}% de vos revenus "
                        f"({avg_ess:,.0f} €/mois). La règle 50/30/20 recommande max 50%.",
            "actions":  ["Renégociez votre loyer ou cherchez un logement moins cher.",
                         "Comparez les offres d'assurance et mutuelle.",
                         "Optimisez vos abonnements télécom/énergie."],
        })
    elif ess_pct <= 50:
        recs.append({
            "category": "depenses",
            "level":    _LEVEL_OK,
            "title":    f"Charges fixes maîtrisées ({ess_pct:.0f}%)",
            "body":     f"Vos dépenses essentielles sont dans la norme : {ess_pct:.0f}% des revenus "
                        f"({avg_ess:,.0f} €/mois). Règle 50/30/20 respectée !",
            "actions":  ["Continuez à surveiller l'évolution de vos charges fixes."],
        })

    if lif_pct > 30:
        recs.append({
            "category": "depenses",
            "level":    _LEVEL_WARNING,
            "title":    f"Style de vie : {lif_pct:.0f}% des revenus",
            "body":     f"Loisirs, restaurants, shopping représentent {lif_pct:.0f}% "
                        f"de vos revenus ({avg_lif:,.0f} €/mois). "
                        f"La règle 50/30/20 recommande max 30%.",
            "actions":  ["Fixez un budget mensuel pour les loisirs.",
                         "Utilisez la règle des 24h avant tout achat impulsif.",
                         f"Objectif : réduire à {avg_rev * 0.30:,.0f} €/mois."],
        })

    return recs


def _analyze_expense_trend(summary):
    recs = []
    if len(summary) < 3:
        return recs

    recent_3  = [m["exp"] for m in summary[-3:]]
    older_3   = [m["exp"] for m in summary[:3]]
    avg_rec   = sum(recent_3) / 3
    avg_old   = sum(older_3)  / 3

    if avg_old > 0:
        change = (avg_rec - avg_old) / avg_old * 100
        if change > 15:
            recs.append({
                "category": "depenses",
                "level":    _LEVEL_ALERT,
                "title":    f"Dépenses en hausse de {change:.0f}%",
                "body":     f"Vos dépenses ont augmenté de {change:.0f}% sur les derniers mois "
                            f"(de {avg_old:,.0f} € à {avg_rec:,.0f} €/mois en moyenne).",
                "actions":  ["Identifiez la catégorie responsable de la hausse.",
                             "Vérifiez si des abonnements ont été ajoutés.",
                             "Fixez-vous un budget mensuel maximum."],
            })
        elif change < -10:
            recs.append({
                "category": "depenses",
                "level":    _LEVEL_OK,
                "title":    f"Dépenses en baisse de {abs(change):.0f}% 🎉",
                "body":     f"Bravo ! Vos dépenses ont diminué de {abs(change):.0f}% "
                            f"(de {avg_old:,.0f} € à {avg_rec:,.0f} €/mois). "
                            f"Continuez sur cette lancée.",
                "actions":  ["Maintenez cet effort et redirigez l'économie vers l'épargne."],
            })

    return recs


def _analyze_top_categories(db, summary, avg_rev):
    recs = []
    if avg_rev <= 0:
        return recs

    # Agréger toutes les catégories sur la période
    cat_totals: dict = {}
    for m in summary:
        cats = db.get_expenses_by_category(m["year"], m["month"])
        for r in cats:
            name = r["name"]
            cat_totals[name] = cat_totals.get(name, 0.0) + r["total"]

    if not cat_totals:
        return recs

    total_months = len(summary)
    # Moyenne mensuelle par catégorie
    cat_monthly = {k: v / total_months for k, v in cat_totals.items()}
    top3 = sorted(cat_monthly.items(), key=lambda x: -x[1])[:3]

    body_lines = []
    for name, avg in top3:
        pct = avg / avg_rev * 100
        body_lines.append(f"• {name.title()} : {avg:,.0f} €/mois ({pct:.1f}% des revenus)")

    recs.append({
        "category": "depenses",
        "level":    _LEVEL_INFO,
        "title":    "Top 3 des dépenses",
        "body":     "Vos postes de dépenses les plus importants sur la période :\n" + "\n".join(body_lines),
        "actions":  ["Concentrez vos efforts d'optimisation sur ces catégories.",
                     "Comparez vos dépenses d'une catégorie à l'autre d'un mois sur l'autre."],
    })

    # Alerte si une seule catégorie > 25% des revenus (hors logement)
    for name, avg in cat_monthly.items():
        pct = avg / avg_rev * 100
        if pct > 25 and name not in ("LOGEMENT", "IMPÔT"):
            recs.append({
                "category": "depenses",
                "level":    _LEVEL_WARNING,
                "title":    f"{name.title()} : {pct:.0f}% des revenus",
                "body":     f"Le poste « {name.title()} » représente {pct:.0f}% de vos revenus "
                            f"({avg:,.0f} €/mois). C'est un niveau élevé.",
                "actions":  [f"Cherchez à réduire ce poste de 10–15%.",
                             "Comparez les offres et négociez si possible."],
            })
            break

    return recs


def _analyze_emergency_fund(all_assets, avg_exp):
    recs = []
    if avg_exp <= 0:
        return recs

    liquidites = sum(a["value"] for a in all_assets if a["asset_type"] == "compte")
    mois_couverts = liquidites / avg_exp if avg_exp > 0 else 0

    if mois_couverts >= 6:
        recs.append({
            "category": "epargne",
            "level":    _LEVEL_OK,
            "title":    f"Fonds d'urgence : {mois_couverts:.1f} mois ✅",
            "body":     f"Vous avez {liquidites:,.0f} € de liquidités, soit {mois_couverts:.1f} mois "
                        f"de dépenses couvertes. L'objectif (3–6 mois) est atteint !",
            "actions":  ["L'excédent de liquidités peut être investi pour générer un rendement."],
        })
    elif mois_couverts >= 3:
        recs.append({
            "category": "epargne",
            "level":    _LEVEL_WARNING,
            "title":    f"Fonds d'urgence : {mois_couverts:.1f} mois",
            "body":     f"Vous avez {liquidites:,.0f} € de liquidités ({mois_couverts:.1f} mois). "
                        f"L'objectif est 6 mois de dépenses ({avg_exp * 6:,.0f} €).",
            "actions":  [f"Complétez de {(avg_exp * 6 - liquidites):,.0f} € pour atteindre 6 mois.",
                         "Privilégiez un Livret A ou LDDS pour ces liquidités."],
        })
    else:
        recs.append({
            "category": "epargne",
            "level":    _LEVEL_ALERT,
            "title":    "Fonds d'urgence insuffisant",
            "body":     f"Vous n'avez que {liquidites:,.0f} € de liquidités ({mois_couverts:.1f} mois). "
                        f"En cas d'imprévu, ce serait insuffisant. Objectif : {avg_exp * 3:,.0f} € (3 mois).",
            "actions":  ["Constituez un fonds d'urgence avant tout investissement.",
                         f"Visez {avg_exp * 3:,.0f} € minimum, puis {avg_exp * 6:,.0f} € idéalement.",
                         "Utilisez un Livret A (accessible immédiatement)."],
        })

    return recs


def _analyze_diversification(all_assets):
    recs = []
    if not all_assets:
        return recs

    total = sum(a["value"] for a in all_assets)
    if total <= 0:
        return recs

    by_type = {}
    for a in all_assets:
        t = a["asset_type"]
        by_type[t] = by_type.get(t, 0.0) + a["value"]

    n_types = len(by_type)
    if n_types == 1:
        t_name = ASSET_LABEL.get(list(by_type.keys())[0], "")
        recs.append({
            "category": "patrimoine",
            "level":    _LEVEL_ALERT,
            "title":    "Patrimoine non diversifié",
            "body":     f"100% de votre patrimoine est en « {t_name} ». "
                        f"Un seul type d'actif représente un risque élevé.",
            "actions":  ["Diversifiez sur au moins 2–3 classes d'actifs différentes.",
                         "Considérez : bourse/ETF, immobilier, liquidités, or."],
        })
    else:
        # Vérifier si un seul actif domine (> 80%)
        for t, v in by_type.items():
            pct = v / total * 100
            if pct > 80:
                t_name = ASSET_LABEL.get(t, t)
                recs.append({
                    "category": "patrimoine",
                    "level":    _LEVEL_WARNING,
                    "title":    f"Concentration sur {t_name} ({pct:.0f}%)",
                    "body":     f"Plus de {pct:.0f}% de votre patrimoine est en « {t_name} » "
                                f"({v:,.0f} €). Une diversification plus équilibrée est recommandée.",
                    "actions":  ["Réduisez progressivement la concentration.",
                                 "Ciblez max 60% sur un seul type d'actif."],
                })
                break

    # Vérifier si investissements bourse présents
    has_bourse = "bourse" in by_type
    has_crypto = "crypto" in by_type
    crypto_pct = by_type.get("crypto", 0) / total * 100 if total else 0

    if not has_bourse and total > 10_000:
        recs.append({
            "category": "patrimoine",
            "level":    _LEVEL_INFO,
            "title":    "Aucun investissement en bourse",
            "body":     "Vous n'avez pas d'ETF/actions en portefeuille. "
                        "Sur le long terme, la bourse est l'un des meilleurs outils "
                        "de création de patrimoine.",
            "actions":  ["Ouvrez un PEA pour un avantage fiscal maximal (après 5 ans).",
                         "Commencez par des ETF World (ex. MSCI World) pour la diversification.",
                         "Investissez régulièrement (DCA) plutôt qu'en une seule fois."],
        })

    if has_crypto and crypto_pct > 10:
        recs.append({
            "category": "patrimoine",
            "level":    _LEVEL_WARNING,
            "title":    f"Crypto-monnaies : {crypto_pct:.0f}% du patrimoine",
            "body":     f"Les crypto représentent {crypto_pct:.0f}% de votre patrimoine "
                        f"({by_type.get('crypto', 0):,.0f} €). "
                        f"Ce niveau de risque est élevé.",
            "actions":  ["Limitez les crypto à 5–10% du patrimoine maximum.",
                         "Les gains crypto sont fiscalisés à 30% en France (flat tax)."],
        })

    return recs


def _analyze_investment_ratio(all_assets):
    recs = []
    if not all_assets:
        return recs

    total      = sum(a["value"] for a in all_assets)
    liquidites = sum(a["value"] for a in all_assets if a["asset_type"] == "compte")
    investis   = total - liquidites

    if total <= 0:
        return recs

    liq_pct = liquidites / total * 100
    inv_pct = investis  / total * 100

    if liq_pct > 70 and total > 20_000:
        recs.append({
            "category": "patrimoine",
            "level":    _LEVEL_WARNING,
            "title":    f"Trop de liquidités ({liq_pct:.0f}%)",
            "body":     f"{liq_pct:.0f}% de votre patrimoine ({liquidites:,.0f} €) reste en "
                        f"liquidités. Ces sommes perdent de la valeur face à l'inflation.",
            "actions":  ["Gardez 3–6 mois de dépenses en liquidités (fonds d'urgence).",
                         "Investissez l'excédent : assurance-vie, PEA, SCPI...",
                         "Même un Livret A (3%) protège partiellement de l'inflation."],
        })
    elif inv_pct >= 60:
        recs.append({
            "category": "patrimoine",
            "level":    _LEVEL_OK,
            "title":    f"Bonne allocation liquidités/investissements",
            "body":     f"{inv_pct:.0f}% de votre patrimoine est investi ({investis:,.0f} €) "
                        f"et {liq_pct:.0f}% en liquidités ({liquidites:,.0f} €). "
                        f"C'est un bon équilibre.",
            "actions":  ["Continuez à faire travailler votre épargne."],
        })

    return recs


def _analyze_monthly_balance(summary, recent):
    recs = []
    if not summary:
        return recs

    neg_months = [m for m in summary if m["rev"] - m["exp"] < 0]
    if len(neg_months) >= 2:
        recs.append({
            "category": "budget",
            "level":    _LEVEL_ALERT,
            "title":    f"{len(neg_months)} mois en déficit sur {len(summary)}",
            "body":     f"Attention : sur les {len(summary)} derniers mois, "
                        f"{len(neg_months)} présentaient un bilan négatif "
                        f"(dépenses > revenus). C'est un signal d'alarme.",
            "actions":  ["Établissez un budget mensuel strict.",
                         "Identifiez les mois problématiques et leurs causes.",
                         "Supprimez les dépenses récurrentes non essentielles."],
        })
    elif recent["rev"] > 0:
        balance   = recent["rev"] - recent["exp"]
        bal_pct   = balance / recent["rev"] * 100
        m_name    = f"{MONTHS_FR[recent['month']-1]} {recent['year']}"
        if balance > 0:
            recs.append({
                "category": "budget",
                "level":    _LEVEL_OK,
                "title":    f"Bilan {m_name} : +{balance:,.0f} €",
                "body":     f"Votre dernier mois est positif : vous avez dépensé "
                            f"{100 - bal_pct:.0f}% de vos revenus et conservé "
                            f"{bal_pct:.0f}% ({balance:,.0f} €).",
                "actions":  ["Vérifiez que ce solde positif est bien alloué à l'épargne ou à l'investissement."],
            })

    return recs


# ─────────────────────────────────────────────────────────────
#  Regroupement par catégorie
# ─────────────────────────────────────────────────────────────
def _group_by_category(recs):
    categories = [
        ("budget",     "Budget mensuel",            "📅"),
        ("epargne",    "Épargne",                   "🏦"),
        ("depenses",   "Optimisation des dépenses", "💸"),
        ("patrimoine", "Patrimoine & Investissements", "📈"),
    ]
    result = []
    for key, label, icon in categories:
        cat_recs = [r for r in recs if r["category"] == key]
        result.append((key, label, icon, cat_recs))
    return result


# ─────────────────────────────────────────────────────────────
#  Bannière score global
# ─────────────────────────────────────────────────────────────
def _render_score_banner(parent, recs):
    n_ok      = sum(1 for r in recs if r["level"] == _LEVEL_OK)
    n_warn    = sum(1 for r in recs if r["level"] == _LEVEL_WARNING)
    n_alert   = sum(1 for r in recs if r["level"] == _LEVEL_ALERT)
    total_eval = n_ok + n_warn + n_alert

    if total_eval > 0:
        score = int((n_ok * 100 + n_warn * 50) / total_eval)
    else:
        score = 50

    if score >= 70:
        score_label = "Bonne santé financière"
        score_color = C["green"]
        score_bg    = "#F0FDF4"
        score_brd   = "#86EFAC"
    elif score >= 40:
        score_label = "Santé financière correcte"
        score_color = C["amber"]
        score_bg    = "#FFFBEB"
        score_brd   = "#FDE68A"
    else:
        score_label = "Attention requise"
        score_color = C["red"]
        score_bg    = "#FEF2F2"
        score_brd   = "#FCA5A5"

    banner = ctk.CTkFrame(parent, fg_color=score_bg, corner_radius=12,
                           border_width=1, border_color=score_brd)
    banner.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

    inner = ctk.CTkFrame(banner, fg_color="transparent")
    inner.pack(fill="x", padx=20, pady=14)

    left = ctk.CTkFrame(inner, fg_color="transparent")
    left.pack(side="left")
    ctk.CTkLabel(left, text=f"Score financier global : {score}/100",
                 font=ctk.CTkFont(size=16, weight="bold"),
                 text_color=score_color).pack(anchor="w")
    ctk.CTkLabel(left, text=score_label,
                 font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(anchor="w")

    # Barre de score
    bar_f = ctk.CTkFrame(left, fg_color="#E2E8F0", corner_radius=6, height=10)
    bar_f.pack(fill="x", pady=(6, 0))
    bar_f.pack_propagate(False)
    ctk.CTkFrame(bar_f, fg_color=score_color, corner_radius=6,
                 height=10).place(relx=0, rely=0, relwidth=score/100, relheight=1)

    # Compteurs OK/Warning/Alert
    right = ctk.CTkFrame(inner, fg_color="transparent")
    right.pack(side="right")
    for count, label, color in [
        (n_ok,    "✅ Positifs",  C["green"]),
        (n_warn,  "⚠️ À surveiller", C["amber"]),
        (n_alert, "🔴 Alertes",  C["red"]),
    ]:
        f = ctk.CTkFrame(right, fg_color="transparent")
        f.pack(side="left", padx=12)
        ctk.CTkLabel(f, text=str(count),
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=color).pack()
        ctk.CTkLabel(f, text=label,
                     font=ctk.CTkFont(size=10), text_color=C["muted"]).pack()


# ─────────────────────────────────────────────────────────────
#  Card de recommandation
# ─────────────────────────────────────────────────────────────
def _rec_card(parent, rec, row, col):
    style = _LEVEL_STYLE[rec["level"]]
    card  = ctk.CTkFrame(parent, fg_color=style["fg"], corner_radius=12,
                          border_width=1, border_color=style["border"])
    card.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
    parent.grid_columnconfigure(col, weight=1)

    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=16, pady=14)

    # Titre
    title_f = ctk.CTkFrame(inner, fg_color="transparent")
    title_f.pack(fill="x", anchor="w")
    ctk.CTkLabel(title_f, text=style["icon"],
                 font=ctk.CTkFont(size=16)).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(title_f, text=rec["title"],
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color=style["color"],
                 wraplength=300, justify="left").pack(side="left", fill="x")

    # Corps
    ctk.CTkLabel(inner, text=rec["body"],
                 font=ctk.CTkFont(size=11), text_color=C["text"],
                 wraplength=320, justify="left").pack(anchor="w", pady=(8, 4))

    # Actions
    if rec.get("actions"):
        sep = ctk.CTkFrame(inner, fg_color=style["border"], height=1)
        sep.pack(fill="x", pady=(4, 6))

        ctk.CTkLabel(inner, text="Actions recommandées :",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["muted"]).pack(anchor="w")

        for action in rec["actions"]:
            af = ctk.CTkFrame(inner, fg_color="transparent")
            af.pack(fill="x", anchor="w", pady=1)
            ctk.CTkLabel(af, text="→",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=style["color"]).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(af, text=action,
                         font=ctk.CTkFont(size=11), text_color=C["text"],
                         wraplength=290, justify="left").pack(side="left", fill="x")
