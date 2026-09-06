"""
ui/pages/recommandations.py — Recommandations personnalisées

• Sans clé IA  → moteur de règles (1 / 3 / 6 derniers mois, choix utilisateur)
• Avec clé IA  → analyse IA via Anthropic (Claude Haiku) ou OpenAI (GPT-4o-mini)
                  La période est commune aux deux modes.
"""
import threading
import customtkinter as ctk
from config import C, MONTHS_FR, ASSET_LABEL
from logger import log
from ui.components import make_card, render_ai_text


# ─────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────
PERIOD_OPTIONS = {"1 mois": 1, "3 mois": 3, "6 mois": 6}

_ESSENTIAL_CATS = {
    "LOGEMENT", "ALIMENTATION", "TRANSPORT", "VOITURE",
    "MUTUELLE", "SANTÉ", "IMPÔT", "BANQUE",
}
_LIFESTYLE_CATS = {
    "LOISIR ET SORTIES", "RESTAURANTS", "SHOPPING", "VÊTEMENTS",
    "VOYAGE", "SPORT ET FITNESS", "ABONNEMENT", "CADEAUX", "DONS",
}

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

_AI_STYLE = {"fg": "#F5F3FF", "border": "#C4B5FD", "color": "#7C3AED"}


# ─────────────────────────────────────────────────────────────
#  Page principale
# ─────────────────────────────────────────────────────────────
class RecommandationsPage:
    def render(self, container: ctk.CTkFrame, app):
        db = app.db

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Barre supérieure ─────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top,
                     text="🧠  Recommandations & Optimisations",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        # Sélecteur de période
        period_var = ctk.StringVar(value="1 mois")
        ctk.CTkSegmentedButton(
            top,
            values=list(PERIOD_OPTIONS.keys()),
            variable=period_var,
            font=ctk.CTkFont(size=12),
            width=220,
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        # Badge IA
        from utils_ai import get_ai_config
        ai_configured, ai_provider, ai_key = get_ai_config(db)
        ai_badge_text  = f"🤖 IA : {ai_provider.title()}" if ai_configured else "🤖 IA : non configurée"
        ai_badge_color = _AI_STYLE["color"] if ai_configured else C["muted"]
        ctk.CTkLabel(top,
                     text=ai_badge_text,
                     font=ctk.CTkFont(size=11),
                     text_color=ai_badge_color).grid(row=0, column=3, sticky="e", padx=(16, 0))

        # ── Zone de contenu (rechargeable) ───────────────────
        wrap = ctk.CTkFrame(container, fg_color="transparent")
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        state = {"frame": None}

        def _reload(*_):
            nb  = PERIOD_OPTIONS[period_var.get()]
            ctx = db.get_setting("user_context", "")
            if state["frame"]:
                state["frame"].destroy()
            f = ctk.CTkFrame(wrap, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            f.grid_columnconfigure(0, weight=1)
            f.grid_rowconfigure(0, weight=1)
            state["frame"] = f
            _render_body(f, db, app, nb, ai_configured, ai_provider, ai_key, ctx)

        period_var.trace_add("write", _reload)
        _reload()


# ─────────────────────────────────────────────────────────────
#  Corps rechargeable
# ─────────────────────────────────────────────────────────────
def _render_body(container, db, app, nb_months: int,
                 ai_configured: bool, ai_provider: str, ai_key: str,
                 user_context: str = ""):
    """Construit le scroll avec score, carte IA (si dispo) et recommandations règles."""
    scroll = ctk.CTkScrollableFrame(container, fg_color=C["bg"])
    scroll.grid(row=0, column=0, sticky="nsew", padx=24, pady=(0, 16))
    scroll.grid_columnconfigure((0, 1), weight=1)

    recs       = _build_recommendations(db, nb_months)
    categories = _group_by_category(recs)

    if not recs:
        ctk.CTkLabel(scroll,
                     text="Aucune donnée pour cette période.\n"
                          "Saisissez vos revenus et dépenses du mois sélectionné.",
                     text_color=C["muted"], justify="center",
                     font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, columnspan=2, pady=60)
        return

    row_idx = [0]

    def _next_row():
        r = row_idx[0]; row_idx[0] += 1; return r

    # ── Score global ─────────────────────────────────────────
    _render_score_banner(scroll, recs, _next_row())

    # ── Carte IA ─────────────────────────────────────────────
    if ai_configured:
        _render_ai_card(scroll, db, app, nb_months,
                        ai_provider, ai_key, _next_row, user_context)

    # ── Recommandations règles par thème ─────────────────────
    for cat_key, cat_label, cat_icon, cat_recs in categories:
        if not cat_recs:
            continue

        sec_hdr = ctk.CTkFrame(scroll, fg_color="transparent")
        sec_hdr.grid(row=_next_row(), column=0, columnspan=2,
                     sticky="ew", pady=(14, 4))
        ctk.CTkLabel(sec_hdr,
                     text=f"{cat_icon}  {cat_label}",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(side="left")

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
                 font=ctk.CTkFont(size=10),
                 text_color=C["muted"],
                 justify="center").pack()


# ─────────────────────────────────────────────────────────────
#  Carte IA
# ─────────────────────────────────────────────────────────────
def _render_ai_card(scroll, db, app, nb_months: int,
                    provider: str, api_key: str, next_row_fn,
                    user_context: str = ""):
    """
    Carte IA avec cache DB.
    • Si un résultat est en cache → affiché immédiatement, 0 appel réseau.
    • Bouton "Mettre à jour" pour forcer une nouvelle analyse (1 appel).
    """
    from utils_ai import (load_cached_result, save_cached_result,
                          build_financial_summary, get_ai_recommendations,
                          PROVIDER_INFO)

    provider_label = PROVIDER_INFO.get(provider, {}).get("label", provider.title())
    provider_model = PROVIDER_INFO.get(provider, {}).get("model", provider)

    cached_text, cached_ts = load_cached_result(db, nb_months)

    card = ctk.CTkFrame(scroll,
                        fg_color=_AI_STYLE["fg"],
                        corner_radius=12,
                        border_width=1,
                        border_color=_AI_STYLE["border"])
    card.grid(row=next_row_fn(), column=0, columnspan=2,
              sticky="ew", padx=5, pady=(0, 8))

    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="x", padx=18, pady=18)

    # ── En-tête ──────────────────────────────────────────────
    hdr = ctk.CTkFrame(inner, fg_color="transparent")
    hdr.pack(fill="x")
    ctk.CTkLabel(hdr,
                 text=f"🤖  Analyse IA — {provider_label}",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=_AI_STYLE["color"]).pack(side="left")
    ctk.CTkLabel(hdr,
                 text=provider_model,
                 font=ctk.CTkFont(size=10),
                 text_color=C["muted"]).pack(side="right")

    # ── Timestamp cache ───────────────────────────────────────
    ts_lbl = ctk.CTkLabel(inner,
                          text=f"Dernière analyse : {cached_ts}" if cached_ts
                               else "Aucune analyse effectuée pour cette période.",
                          font=ctk.CTkFont(size=10),
                          text_color=C["muted"])
    ts_lbl.pack(anchor="w", pady=(6, 0))

    # ── Zone de résultat (rendu Markdown) ────────────────────
    result_frame = ctk.CTkFrame(inner, fg_color="transparent")
    result_widget = [None]   # référence mutable au tk.Text courant

    def _display_result(text: str):
        """(Re)crée le widget de rendu Markdown."""
        if result_widget[0]:
            try:
                result_widget[0].destroy()
            except Exception:
                pass
        w = render_ai_text(result_frame, text, bg_color=_AI_STYLE["fg"])
        w.pack(fill="x")
        result_widget[0] = w

    if cached_text:
        _display_result(cached_text)
        result_frame.pack(fill="x", pady=(14, 6))

    status_lbl = ctk.CTkLabel(inner, text="",
                               font=ctk.CTkFont(size=11),
                               text_color=C["muted"],
                               wraplength=760, justify="left")
    status_lbl.pack(anchor="w", pady=(2, 0))

    # ── Bouton ────────────────────────────────────────────────
    btn_label = "🔄  Mettre à jour" if cached_text else "✨  Analyser avec l'IA"
    btn_ai = ctk.CTkButton(inner,
                           text=btn_label,
                           height=34,
                           font=ctk.CTkFont(size=12, weight="bold"),
                           fg_color=_AI_STYLE["color"],
                           hover_color="#6D28D9",
                           width=200)
    btn_ai.pack(anchor="w", pady=(14, 0))

    def _do_run_ai():
        """Lance l'appel IA — appelé après acceptation du disclaimer."""
        btn_ai.configure(state="disabled", text="⏳  Analyse en cours…")
        status_lbl.configure(text="Envoi des données à l'IA…", text_color=C["muted"])

        def _worker():
            try:
                summary = build_financial_summary(db, nb_months)
                ok, text = get_ai_recommendations(
                    summary, nb_months, provider, api_key, user_context)
            except Exception as exc:
                # Erreur réelle (API, données) ou fenêtre fermée pendant l'appel —
                # dans les deux cas on relaie à _done : winfo_exists() ci-dessous
                # gère silencieusement le cas fenêtre fermée, sinon l'utilisateur
                # voit l'erreur et peut réessayer au lieu du bouton bloqué en "…".
                log.warning("Analyse IA échouée", exc_info=True)
                ok, text = False, str(exc)

            def _done():
                if ok:
                    save_cached_result(db, nb_months, text)
                    _, new_ts = load_cached_result(db, nb_months)
                    ts_lbl.configure(text=f"Dernière analyse : {new_ts}")
                    _display_result(text)
                    result_frame.pack(fill="x", pady=(10, 4))
                    status_lbl.configure(text="")
                    btn_ai.configure(state="normal", text="🔄  Mettre à jour")
                else:
                    status_lbl.configure(text=f"❌  {text}", text_color=C["red"])
                    btn_ai.configure(state="normal", text="🔄  Réessayer")

            # Ne jamais interroger Tkinter (winfo_exists, etc.) depuis ce thread
            # d'arrière-plan — seul le thread principal doit toucher Tcl.
            # `app._closing` est un simple booléen Python, sûr à lire ici.
            try:
                if not getattr(app, "_closing", False):
                    app.after(0, _done)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _run_ai():
        """Affiche le disclaimer RGPD puis lance l'analyse si accepté."""
        _show_ai_disclaimer(app, provider, _do_run_ai)

    btn_ai.configure(command=_run_ai)


# ─────────────────────────────────────────────────────────────
#  Disclaimer RGPD — affiché avant chaque appel IA
# ─────────────────────────────────────────────────────────────
def _show_ai_disclaimer(app, provider: str, on_accept):
    """
    Modal de consentement affiché AVANT chaque envoi de données à l'API IA.
    L'utilisateur doit confirmer explicitement à chaque analyse.
    on_accept() est appelé uniquement si l'utilisateur clique « Confirmer ».
    """
    from utils_ai import PROVIDER_INFO
    provider_label = PROVIDER_INFO.get(provider, {}).get("label", provider.title())

    dlg = ctk.CTkToplevel(app)
    dlg.title("Consentement — données envoyées à un service externe")
    dlg.geometry("520x320")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.focus_force()

    # ── En-tête ──────────────────────────────────────────────
    ctk.CTkLabel(dlg,
                 text=f"⚠️  Données financières envoyées à {provider_label}",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color="#B45309").pack(padx=24, pady=(20, 8))

    # ── Corps ────────────────────────────────────────────────
    msg = (
        "Pour générer cette analyse, un résumé de vos données financières\n"
        "(revenus moyens, dépenses par catégorie, épargne, patrimoine)\n"
        f"sera transmis à l'API {provider_label} — un service externe.\n\n"
        "Aucune donnée d'identité ni coordonnée bancaire n'est envoyée.\n"
        "Vos données brutes restent uniquement sur votre appareil.\n\n"
        "Confirmez-vous l'envoi de ce résumé pour obtenir l'analyse ?"
    )
    ctk.CTkLabel(dlg, text=msg,
                 font=ctk.CTkFont(size=12),
                 text_color=C["text"],
                 justify="left").pack(padx=24, pady=(0, 16))

    # ── Boutons ──────────────────────────────────────────────
    btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_row.pack(padx=24, pady=(0, 24))

    def _accept():
        dlg.destroy()
        on_accept()

    def _cancel():
        dlg.destroy()

    ctk.CTkButton(btn_row,
                  text="✅  Oui, analyser",
                  fg_color=_AI_STYLE["color"], hover_color="#6D28D9",
                  command=_accept, width=160,
                  font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 10))
    ctk.CTkButton(btn_row,
                  text="✕  Annuler",
                  fg_color=C["muted"], hover_color="#475569",
                  command=_cancel, width=120,
                  font=ctk.CTkFont(size=12)).pack(side="left")


# ─────────────────────────────────────────────────────────────
#  Moteur d'analyse (règles)
# ─────────────────────────────────────────────────────────────
def _build_recommendations(db, nb_months: int) -> list[dict]:
    recs    = []
    summary = db.monthly_summary(nb_months)
    if not summary:
        return recs

    summary_asc = list(reversed(summary))
    recent      = summary_asc[-1]
    all_assets  = db.get_assets_current()

    avg_rev = sum(r["rev"] for r in summary_asc) / len(summary_asc)
    avg_exp = sum(r["exp"] for r in summary_asc) / len(summary_asc)
    avg_sav = sum(r["sav"] for r in summary_asc) / len(summary_asc)

    recs += _analyze_savings_rate(avg_rev, avg_sav, summary_asc)
    recs += _analyze_50_30_20(db, summary_asc, avg_rev)
    recs += _analyze_expense_trend(summary_asc)
    recs += _analyze_top_categories(db, summary_asc, avg_rev)
    recs += _analyze_emergency_fund(all_assets, avg_exp)
    recs += _analyze_diversification(all_assets)
    recs += _analyze_investment_ratio(all_assets)
    recs += _analyze_monthly_balance(summary_asc, recent)
    return recs


def _analyze_savings_rate(avg_rev, avg_sav, summary):
    recs = []
    if avg_rev <= 0:
        return recs
    rate     = avg_sav / avg_rev * 100
    if rate >= 20:
        recs.append({"category": "epargne", "level": _LEVEL_OK,
                     "title": f"Taux d'épargne : {rate:.1f}% ✨",
                     "body": f"Excellent ! Vous épargnez {rate:.1f}% de vos revenus "
                             f"({avg_sav:,.0f} €/mois). L'objectif recommandé est 20%.",
                     "actions": ["Maintenez cette discipline.",
                                 "Envisagez d'investir l'excédent en bourse ou PEA."]})
    elif rate >= 10:
        recs.append({"category": "epargne", "level": _LEVEL_WARNING,
                     "title": f"Taux d'épargne : {rate:.1f}%",
                     "body": f"Votre taux est de {rate:.1f}% ({avg_sav:,.0f} €/mois). "
                             f"Bon début, mais l'objectif est 20%.",
                     "actions": [f"Visez {avg_rev * 0.20:,.0f} €/mois (20% des revenus).",
                                 "Automatisez un virement épargne le jour de paie."]})
    else:
        recs.append({"category": "epargne", "level": _LEVEL_ALERT,
                     "title": f"Taux d'épargne faible : {rate:.1f}%",
                     "body": f"Vous n'épargnez que {rate:.1f}% ({avg_sav:,.0f} €/mois). "
                             f"Insuffisant pour construire un patrimoine solide.",
                     "actions": [f"Objectif minimum : {avg_rev * 0.10:,.0f} €/mois (10%).",
                                 "Identifiez les dépenses non-essentielles à réduire.",
                                 "Virement automatique dès réception du salaire."]})
    return recs


def _analyze_50_30_20(db, summary, avg_rev):
    recs = []
    if avg_rev <= 0 or not summary:
        return recs
    essential_totals, lifestyle_totals = [], []
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
        recs.append({"category": "depenses", "level": _LEVEL_ALERT,
                     "title": f"Charges fixes élevées ({ess_pct:.0f}% des revenus)",
                     "body": f"Vos dépenses essentielles ({avg_ess:,.0f} €/mois) dépassent "
                             f"50% de vos revenus. Règle 50/30/20 non respectée.",
                     "actions": ["Renégociez loyer, assurances, télécom.",
                                 "Comparez les offres énergie et mutuelle."]})
    elif ess_pct <= 50:
        recs.append({"category": "depenses", "level": _LEVEL_OK,
                     "title": f"Charges fixes maîtrisées ({ess_pct:.0f}%)",
                     "body": f"Vos dépenses essentielles ({avg_ess:,.0f} €/mois) "
                             f"respectent la règle 50/30/20.",
                     "actions": ["Continuez à surveiller l'évolution de vos charges."]})

    if lif_pct > 30:
        recs.append({"category": "depenses", "level": _LEVEL_WARNING,
                     "title": f"Style de vie : {lif_pct:.0f}% des revenus",
                     "body": f"Loisirs, restaurants, shopping : {avg_lif:,.0f} €/mois "
                             f"({lif_pct:.0f}%). Max recommandé : 30%.",
                     "actions": ["Fixez un budget mensuel loisirs.",
                                 "Règle des 24h avant tout achat impulsif.",
                                 f"Objectif : {avg_rev * 0.30:,.0f} €/mois."]})
    return recs


def _analyze_expense_trend(summary):
    recs = []
    if len(summary) < 3:
        return recs
    recent_3 = [m["exp"] for m in summary[-3:]]
    older_3  = [m["exp"] for m in summary[:3]]
    avg_rec  = sum(recent_3) / 3
    avg_old  = sum(older_3)  / 3
    if avg_old > 0:
        change = (avg_rec - avg_old) / avg_old * 100
        if change > 15:
            recs.append({"category": "depenses", "level": _LEVEL_ALERT,
                         "title": f"Dépenses en hausse de {change:.0f}%",
                         "body": f"Vos dépenses sont passées de {avg_old:,.0f} € à "
                                 f"{avg_rec:,.0f} €/mois en moyenne.",
                         "actions": ["Identifiez la catégorie responsable.",
                                     "Vérifiez les nouveaux abonnements.",
                                     "Fixez un plafond mensuel."]})
        elif change < -10:
            recs.append({"category": "depenses", "level": _LEVEL_OK,
                         "title": f"Dépenses en baisse de {abs(change):.0f}% 🎉",
                         "body": f"Vos dépenses ont diminué de {avg_old:,.0f} € à "
                                 f"{avg_rec:,.0f} €/mois. Continuez !",
                         "actions": ["Redirigez l'économie vers l'épargne ou l'investissement."]})
    return recs


def _analyze_top_categories(db, summary, avg_rev):
    recs = []
    if avg_rev <= 0:
        return recs
    cat_totals: dict = {}
    for m in summary:
        for r in db.get_expenses_by_category(m["year"], m["month"]):
            cat_totals[r["name"]] = cat_totals.get(r["name"], 0.0) + r["total"]
    if not cat_totals:
        return recs
    nb = len(summary)
    cat_monthly = {k: v / nb for k, v in cat_totals.items()}
    top3 = sorted(cat_monthly.items(), key=lambda x: -x[1])[:3]
    body_lines = [f"• {n.title()} : {a:,.0f} €/mois ({a/avg_rev*100:.1f}%)"
                  for n, a in top3]
    recs.append({"category": "depenses", "level": _LEVEL_INFO,
                 "title": "Top 3 des dépenses",
                 "body": "Vos postes les plus importants :\n" + "\n".join(body_lines),
                 "actions": ["Concentrez vos efforts sur ces catégories.",
                              "Comparez mois par mois."]})
    for name, avg in cat_monthly.items():
        pct = avg / avg_rev * 100
        if pct > 25 and name not in ("LOGEMENT", "IMPÔT"):
            recs.append({"category": "depenses", "level": _LEVEL_WARNING,
                         "title": f"{name.title()} : {pct:.0f}% des revenus",
                         "body": f"« {name.title()} » représente {pct:.0f}% de vos revenus "
                                 f"({avg:,.0f} €/mois).",
                         "actions": ["Cherchez à réduire ce poste de 10-15%.",
                                     "Comparez les offres et négociez."]})
            break
    return recs


def _analyze_emergency_fund(all_assets, avg_exp):
    recs = []
    if avg_exp <= 0:
        return recs
    liquidites   = sum(a["value"] for a in all_assets if a["asset_type"] == "compte")
    mois_couverts = liquidites / avg_exp
    if mois_couverts >= 6:
        recs.append({"category": "epargne", "level": _LEVEL_OK,
                     "title": f"Fonds d'urgence : {mois_couverts:.1f} mois ✅",
                     "body": f"{liquidites:,.0f} € de liquidités — {mois_couverts:.1f} mois couverts. "
                             f"Objectif atteint !",
                     "actions": ["L'excédent peut être investi pour générer un rendement."]})
    elif mois_couverts >= 3:
        recs.append({"category": "epargne", "level": _LEVEL_WARNING,
                     "title": f"Fonds d'urgence : {mois_couverts:.1f} mois",
                     "body": f"{liquidites:,.0f} € ({mois_couverts:.1f} mois). "
                             f"Objectif : 6 mois ({avg_exp * 6:,.0f} €).",
                     "actions": [f"Complétez de {avg_exp*6-liquidites:,.0f} € pour atteindre 6 mois.",
                                 "Livret A ou LDDS pour ces liquidités."]})
    else:
        recs.append({"category": "epargne", "level": _LEVEL_ALERT,
                     "title": "Fonds d'urgence insuffisant",
                     "body": f"Seulement {liquidites:,.0f} € ({mois_couverts:.1f} mois). "
                             f"Objectif minimum : {avg_exp*3:,.0f} € (3 mois).",
                     "actions": ["Constituez ce fonds avant tout investissement.",
                                 f"Visez {avg_exp*3:,.0f} € min, puis {avg_exp*6:,.0f} €.",
                                 "Livret A (accessible immédiatement)."]})
    return recs


def _analyze_diversification(all_assets):
    recs = []
    if not all_assets:
        return recs
    total = sum(a["value"] for a in all_assets)
    if total <= 0:
        return recs
    by_type: dict = {}
    for a in all_assets:
        by_type[a["asset_type"]] = by_type.get(a["asset_type"], 0.0) + a["value"]
    if len(by_type) == 1:
        t_name = ASSET_LABEL.get(list(by_type.keys())[0], "")
        recs.append({"category": "patrimoine", "level": _LEVEL_ALERT,
                     "title": "Patrimoine non diversifié",
                     "body": f"100% en « {t_name} ». Un seul type d'actif = risque élevé.",
                     "actions": ["Diversifiez sur 2-3 classes d'actifs.",
                                 "Envisagez : bourse/ETF, immobilier, liquidités, or."]})
    else:
        for t, v in by_type.items():
            pct = v / total * 100
            if pct > 80:
                t_name = ASSET_LABEL.get(t, t)
                recs.append({"category": "patrimoine", "level": _LEVEL_WARNING,
                             "title": f"Concentration sur {t_name} ({pct:.0f}%)",
                             "body": f"{pct:.0f}% du patrimoine en « {t_name} » ({v:,.0f} €).",
                             "actions": ["Réduisez progressivement la concentration.",
                                         "Ciblez max 60% sur un seul type d'actif."]})
                break
    has_bourse = "bourse" in by_type
    crypto_pct = by_type.get("crypto", 0) / total * 100 if total else 0
    if not has_bourse and total > 10_000:
        recs.append({"category": "patrimoine", "level": _LEVEL_INFO,
                     "title": "Aucun investissement en bourse",
                     "body": "Pas d'ETF/actions dans votre portefeuille. "
                             "Sur le long terme, la bourse est l'un des meilleurs outils de création de richesse.",
                     "actions": ["Ouvrez un PEA pour l'avantage fiscal (après 5 ans).",
                                 "Commencez par un ETF World (MSCI World).",
                                 "Investissez régulièrement (DCA)."]})
    if crypto_pct > 10:
        recs.append({"category": "patrimoine", "level": _LEVEL_WARNING,
                     "title": f"Crypto : {crypto_pct:.0f}% du patrimoine",
                     "body": f"Les crypto représentent {crypto_pct:.0f}% du patrimoine. "
                             f"Niveau de risque élevé.",
                     "actions": ["Limitez les crypto à 5-10% max.",
                                 "Gains crypto fiscalisés à 30% en France (flat tax)."]})
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
    inv_pct = investis   / total * 100
    if liq_pct > 70 and total > 20_000:
        recs.append({"category": "patrimoine", "level": _LEVEL_WARNING,
                     "title": f"Trop de liquidités ({liq_pct:.0f}%)",
                     "body": f"{liq_pct:.0f}% en liquidités ({liquidites:,.0f} €). "
                             f"Ces sommes perdent de la valeur face à l'inflation.",
                     "actions": ["Gardez 3-6 mois de dépenses en liquidités.",
                                 "Investissez l'excédent : assurance-vie, PEA, SCPI…",
                                 "Même un Livret A (3%) protège partiellement de l'inflation."]})
    elif inv_pct >= 60:
        recs.append({"category": "patrimoine", "level": _LEVEL_OK,
                     "title": "Bonne allocation liquidités / investissements",
                     "body": f"{inv_pct:.0f}% investi ({investis:,.0f} €) et "
                             f"{liq_pct:.0f}% en liquidités ({liquidites:,.0f} €). "
                             f"Bon équilibre.",
                     "actions": ["Continuez à faire travailler votre épargne."]})
    return recs


def _analyze_monthly_balance(summary, recent):
    recs = []
    if not summary:
        return recs
    neg_months = [m for m in summary if m["rev"] - m["exp"] < 0]
    if len(neg_months) >= 2:
        recs.append({"category": "budget", "level": _LEVEL_ALERT,
                     "title": f"{len(neg_months)} mois en déficit sur {len(summary)}",
                     "body": f"Sur {len(summary)} mois, {len(neg_months)} présentaient "
                             f"un bilan négatif. Signal d'alarme.",
                     "actions": ["Établissez un budget mensuel strict.",
                                 "Identifiez les mois problématiques.",
                                 "Supprimez les dépenses récurrentes non essentielles."]})
    elif recent["rev"] > 0:
        balance = recent["rev"] - recent["exp"]
        bal_pct = balance / recent["rev"] * 100
        m_name  = f"{MONTHS_FR[recent['month']-1]} {recent['year']}"
        if balance > 0:
            recs.append({"category": "budget", "level": _LEVEL_OK,
                         "title": f"Bilan {m_name} : +{balance:,.0f} €",
                         "body": f"Dernier mois positif : vous avez conservé {bal_pct:.0f}% "
                                 f"de vos revenus ({balance:,.0f} €).",
                         "actions": ["Vérifiez que ce solde est bien alloué à l'épargne ou l'investissement."]})
    return recs


# ─────────────────────────────────────────────────────────────
#  Regroupement par catégorie
# ─────────────────────────────────────────────────────────────
def _group_by_category(recs):
    categories = [
        ("budget",     "Budget mensuel",               "📅"),
        ("epargne",    "Épargne",                      "🏦"),
        ("depenses",   "Optimisation des dépenses",    "💸"),
        ("patrimoine", "Patrimoine & Investissements",  "📈"),
    ]
    return [(k, l, i, [r for r in recs if r["category"] == k])
            for k, l, i in categories]


# ─────────────────────────────────────────────────────────────
#  Bannière score global
# ─────────────────────────────────────────────────────────────
def _render_score_banner(parent, recs, row):
    n_ok    = sum(1 for r in recs if r["level"] == _LEVEL_OK)
    n_warn  = sum(1 for r in recs if r["level"] == _LEVEL_WARNING)
    n_alert = sum(1 for r in recs if r["level"] == _LEVEL_ALERT)
    total_eval = n_ok + n_warn + n_alert
    score = int((n_ok * 100 + n_warn * 50) / total_eval) if total_eval else 50

    if score >= 70:
        s_label, s_color, s_bg, s_brd = "Bonne santé financière", C["green"], "#F0FDF4", "#86EFAC"
    elif score >= 40:
        s_label, s_color, s_bg, s_brd = "Santé financière correcte", C["amber"], "#FFFBEB", "#FDE68A"
    else:
        s_label, s_color, s_bg, s_brd = "Attention requise", C["red"], "#FEF2F2", "#FCA5A5"

    banner = ctk.CTkFrame(parent, fg_color=s_bg, corner_radius=12,
                           border_width=1, border_color=s_brd)
    banner.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    inner = ctk.CTkFrame(banner, fg_color="transparent")
    inner.pack(fill="x", padx=20, pady=14)

    left = ctk.CTkFrame(inner, fg_color="transparent")
    left.pack(side="left")
    ctk.CTkLabel(left, text=f"Score financier global : {score}/100",
                 font=ctk.CTkFont(size=16, weight="bold"),
                 text_color=s_color).pack(anchor="w")
    ctk.CTkLabel(left, text=s_label,
                 font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(anchor="w")
    bar_f = ctk.CTkFrame(left, fg_color="#E2E8F0", corner_radius=6, height=10)
    bar_f.pack(fill="x", pady=(6, 0))
    bar_f.pack_propagate(False)
    ctk.CTkFrame(bar_f, fg_color=s_color, corner_radius=6,
                 height=10).place(relx=0, rely=0, relwidth=score / 100, relheight=1)

    right = ctk.CTkFrame(inner, fg_color="transparent")
    right.pack(side="right")
    for count, label, color in [
        (n_ok,    "✅ Positifs",     C["green"]),
        (n_warn,  "⚠️ À surveiller", C["amber"]),
        (n_alert, "🔴 Alertes",      C["red"]),
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

    title_f = ctk.CTkFrame(inner, fg_color="transparent")
    title_f.pack(fill="x", anchor="w")
    ctk.CTkLabel(title_f, text=style["icon"],
                 font=ctk.CTkFont(size=16)).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(title_f, text=rec["title"],
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color=style["color"],
                 wraplength=300, justify="left").pack(side="left", fill="x")

    ctk.CTkLabel(inner, text=rec["body"],
                 font=ctk.CTkFont(size=11), text_color=C["text"],
                 wraplength=320, justify="left").pack(anchor="w", pady=(8, 4))

    if rec.get("actions"):
        ctk.CTkFrame(inner, fg_color=style["border"], height=1).pack(fill="x", pady=(4, 6))
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
