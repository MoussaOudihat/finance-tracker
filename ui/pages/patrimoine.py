"""
ui/pages/patrimoine.py — Suivi du patrimoine et des investissements

Vue globale (pas de filtre mensuel) :
- Affiche toujours la valeur LA PLUS RÉCENTE de chaque actif
- La mise à jour d'une valeur crée un enregistrement pour le mois courant
  → l'historique mensuel est préservé pour les graphiques d'évolution

Structure : un seul item de menu "Patrimoine", découpé en 5 sous-onglets
internes (barre de segments) pour éviter de tout empiler sur un seul écran :
  Vue d'ensemble | Actifs | Passifs | Clôturées | Graphiques
Un bandeau permanent (Patrimoine total / Valeur nette / Cash en attente)
reste visible sur tous les sous-onglets comme point de repère.
"""
import datetime
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import customtkinter as ctk
from config import C, MONTHS_FR, ASSET_LABEL, ASSET_TYPES, PALETTE, FILTER_ALL_TYPES, LIABILITY_LABEL
from ui.components import make_card, Tooltip, table_header, table_row
from ui.dialogs import (AssetDialog, QuickValueUpdateDialog,
                        AssetEvolutionDialog, AssetTransactionsDialog,
                        LiabilityDialog)

# Types d'actifs pour lesquels le bouton transactions est particulièrement utile
_TRANSACTION_TYPES = {"bourse", "crypto", "or_metaux"}

# Périodes disponibles (label affiché → nb de mois, None = tout)
_PERIODS = [("3M", 3), ("6M", 6), ("1A", 12), ("2A", 24), ("Tout", None)]

# Couleurs par type d'actif (accent sidebar gauche)
_TYPE_ACCENT = {
    "bourse":     "#3B6FE8",
    "immobilier": "#22C55E",
    "crypto":     "#F59E0B",
    "or_metaux":  "#EAB308",
    "compte":     "#06B6D4",
    "autre":      "#94A3B8",
}

# Sous-onglets internes de la page
_SUBVIEWS = [
    ("Vue d'ensemble", "overview"),
    ("Actifs",          "actifs"),
    ("Passifs",         "passifs"),
    ("Clôturées",       "closes"),
    ("Graphiques",      "graphs"),
]


class PatrimoinePage:
    def render(self, container: ctk.CTkFrame, app):
        db       = app.db
        type_f   = getattr(app, "pat_type_filter",   FILTER_ALL_TYPES)
        period_f = getattr(app, "pat_period_filter",  "Tout")
        subview  = getattr(app, "pat_subview",        "overview")

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(2, weight=1)

        # ── Données communes (utilisées par le bandeau + plusieurs onglets) ──
        type_lbl_to_key = {lbl: key for lbl, key in ASSET_TYPES}

        all_assets_raw = db.get_assets_current()
        all_assets = []
        for a in all_assets_raw:
            a_dict = dict(a)
            if a["asset_type"] in _TRANSACTION_TYPES:
                st = db.get_position_status(a["asset_name"])
                if st["status"] == "vendu":
                    if st["all_reinvested"]:
                        continue
                    a_dict["value"] = st["sale_proceeds"]
            all_assets.append(a_dict)

        if type_f != FILTER_ALL_TYPES:
            type_key = type_lbl_to_key.get(type_f)
            assets   = [a for a in all_assets if a["asset_type"] == type_key]
        else:
            assets = all_assets

        total_all    = sum(a["value"] for a in all_assets)
        total        = sum(a["value"] for a in assets)
        total_cb_all = sum((a["cost_basis"] or 0.0) for a in all_assets)
        total_cb     = sum((a["cost_basis"] or 0.0) for a in assets)
        pnl_total    = total_all - total_cb_all if total_cb_all else None
        pnl_pct_all  = (pnl_total / total_cb_all * 100) if total_cb_all else None

        liquidites   = sum(a["value"] for a in all_assets if a["asset_type"] == "compte")
        cash_pending = db.get_cash_pending_total()

        passifs      = db.get_liabilities_current()
        total_p      = sum(p["remaining_capital"] for p in passifs)
        valeur_nette = total_all - total_p

        # ── Ligne 0 : titre + barre de sous-onglets ─────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="📈  Patrimoine & Investissements",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        subview_label_to_key = dict(_SUBVIEWS)
        subview_key_to_label = {k: lbl for lbl, k in _SUBVIEWS}
        subview_var = ctk.StringVar(value=subview_key_to_label.get(subview, "Vue d'ensemble"))

        def on_subview_change(choice):
            app.pat_subview = subview_label_to_key[choice]
            app._go("patrimoine")

        ctk.CTkSegmentedButton(
            top, values=[lbl for lbl, _ in _SUBVIEWS], variable=subview_var,
            command=on_subview_change,
            font=ctk.CTkFont(size=12),
            fg_color=C["light"], selected_color=C["primary"],
            selected_hover_color=C["primary"], unselected_color=C["light"],
        ).grid(row=0, column=2, sticky="e")

        # ── Ligne 1 : bandeau permanent (3 KPIs) ────────────────
        strip = ctk.CTkFrame(container, fg_color="transparent")
        strip.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        strip.grid_columnconfigure((0, 1, 2), weight=1)

        _kpi_pat(strip, 0, "💰  Patrimoine total",
                 f"{total_all:,.0f} €", C["primary"], "#EFF6FF", "#DBEAFE")

        vn_color = C["green"] if valeur_nette >= 0 else C["red"]
        vn_bg    = "#F0FDF4" if valeur_nette >= 0 else "#FEF2F2"
        vn_brd   = "#86EFAC" if valeur_nette >= 0 else "#FCA5A5"
        vn_sign  = "+" if valeur_nette >= 0 else ""
        _kpi_pat(strip, 1, "⚖️  Valeur nette (actifs − dettes)",
                 f"{vn_sign}{valeur_nette:,.0f} €", vn_color, vn_bg, vn_brd)

        cash_color = "#047857" if cash_pending > 0 else C["muted"]
        cash_bg    = "#ECFDF5" if cash_pending > 0 else "#F8FAFC"
        cash_brd   = "#A7F3D0" if cash_pending > 0 else "#E2E8F0"
        _kpi_pat(strip, 2, "💵  Cash en attente",
                 f"{cash_pending:,.0f} €" if cash_pending > 0 else "—",
                 cash_color, cash_bg, cash_brd)

        # ── Ligne 2 : corps scrollable, délégué au sous-onglet actif ──
        scroll = ctk.CTkScrollableFrame(container, fg_color=C["bg"])
        scroll.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 16))
        scroll.grid_columnconfigure(0, weight=1)

        if subview == "actifs":
            _render_actifs(scroll, db, app, type_f, type_lbl_to_key,
                           all_assets, assets, total_all, total, total_cb)
        elif subview == "passifs":
            _render_passifs(scroll, db, app, passifs, total_p)
        elif subview == "closes":
            _render_closes(scroll, db, app, type_f, type_lbl_to_key)
        elif subview == "graphs":
            _render_graphs_subview(scroll, db, app, type_f, type_lbl_to_key, period_f)
        else:
            _render_overview(scroll, db, app, all_assets, total_all,
                             total_cb_all, pnl_total, pnl_pct_all,
                             liquidites, cash_pending)


# ─────────────────────────────────────────────────────────────
#  Sous-onglet : Vue d'ensemble
# ─────────────────────────────────────────────────────────────
def _render_overview(scroll, db, app, all_assets, total_all, total_cb_all,
                     pnl_total, pnl_pct_all, liquidites, cash_pending):
    kpi_row = ctk.CTkFrame(scroll, fg_color="transparent")
    kpi_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
    kpi_row.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

    _kpi_pat(kpi_row, 0, "💰  Patrimoine total",
             f"{total_all:,.0f} €", C["primary"], "#EFF6FF", "#DBEAFE")
    if pnl_total is not None:
        pnl_color = C["green"] if pnl_total >= 0 else C["red"]
        pnl_bg    = "#F0FDF4" if pnl_total >= 0 else "#FEF2F2"
        pnl_brd   = "#86EFAC" if pnl_total >= 0 else "#FCA5A5"
        sign      = "+" if pnl_total >= 0 else ""
        _kpi_pat(kpi_row, 1, "📊  Plus-value latente",
                 f"{sign}{pnl_total:,.0f} €  ({sign}{pnl_pct_all:.1f}%)",
                 pnl_color, pnl_bg, pnl_brd)
    else:
        _kpi_pat(kpi_row, 1, "📊  Investi total",
                 f"{total_cb_all:,.0f} €" if total_cb_all else "—",
                 C["amber"], "#FFFBEB", "#FDE68A")

    _kpi_pat(kpi_row, 2, "🏦  Liquidités",
             f"{liquidites:,.0f} €", C["blue"], "#EFF6FF", "#BFDBFE")

    cash_color = "#047857" if cash_pending > 0 else C["muted"]
    cash_bg    = "#ECFDF5" if cash_pending > 0 else "#F8FAFC"
    cash_brd   = "#A7F3D0" if cash_pending > 0 else "#E2E8F0"
    _kpi_pat(kpi_row, 3, "💵  Cash en attente",
             f"{cash_pending:,.0f} €" if cash_pending > 0 else "—",
             cash_color, cash_bg, cash_brd)

    nb_types  = len({a["asset_type"] for a in all_assets})
    nb_actifs = len(all_assets)
    _kpi_pat(kpi_row, 4, "🗂️  Actifs suivis",
             f"{nb_actifs} actif{'s' if nb_actifs > 1 else ''}  ·  {nb_types} type{'s' if nb_types > 1 else ''}",
             "#8B5CF6", "#F5F3FF", "#DDD6FE")

    def open_add():
        today = datetime.date.today()
        AssetDialog(app, on_save=lambda d: (
            db.upsert_asset(today.year, today.month,
                            d["asset_type"], d["asset_name"],
                            d["value"], d["cost_basis"], d["notes"]),
            app._go("patrimoine"),
        ))

    add_f = ctk.CTkFrame(scroll, fg_color="transparent")
    add_f.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    ctk.CTkButton(add_f, text="＋  Ajouter / Mettre à jour un actif",
                  height=36, command=open_add,
                  font=ctk.CTkFont(size=13)).pack(side="left")

    ev_card = make_card(scroll)
    ev_card.grid(row=2, column=0, sticky="nsew")
    hdr = ctk.CTkFrame(ev_card, fg_color="transparent")
    hdr.pack(fill="x", padx=16, pady=(14, 0))
    ctk.CTkLabel(hdr, text="Évolution du patrimoine",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=C["text"]).pack(anchor="w")

    history = db.get_patrimoine_history()
    if len(history) >= 2:
        _render_single_evolution_chart(ev_card, app, history)
    elif len(history) == 1:
        p = history[0]
        ctk.CTkLabel(ev_card,
                     text=(f"📌  1 enregistrement — {MONTHS_FR[p['month']-1]} {p['year']} : "
                           f"{p['total_value']:,.0f} €\n\n"
                           f"Mettez à jour vos actifs sur plusieurs mois pour voir l'évolution."),
                     text_color=C["muted"], justify="center",
                     font=ctk.CTkFont(size=12)).pack(expand=True, pady=40)
    else:
        ctk.CTkLabel(ev_card, text="Aucune donnée pour le moment.\nAjoutez un actif pour commencer.",
                     text_color=C["muted"], justify="center",
                     font=ctk.CTkFont(size=12)).pack(expand=True, pady=55)


def _render_single_evolution_chart(card, app, history):
    """Graphique d'évolution simple (sans filtre type/période) pour la Vue d'ensemble."""
    def _build_fig(fw, fh):
        pts    = list(history)
        labels = [f"{MONTHS_FR[p['month']-1][:3]} {str(p['year'])[2:]}" for p in pts]
        x      = list(range(len(pts)))
        vals   = [p["total_value"] for p in pts]
        bases  = [p["total_basis"]  for p in pts]

        fig, ax = plt.subplots(figsize=(fw, fh))
        fig.patch.set_facecolor(C["card"])
        _style_ax(ax)
        ax.fill_between(x, vals, alpha=0.13, color=C["primary"])
        ax.plot(x, vals, color=C["primary"], lw=2.8, marker="o", ms=6, label="Valeur", zorder=3)
        if any(b for b in bases):
            ax.plot(x, bases, color=C["amber"], lw=2, ls="--", marker="s", ms=4, label="Investi", zorder=3)
        ax.set_title("Évolution du patrimoine", fontsize=10, color="#475569", pad=8, loc="left")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_euros))
        _smart_xticks(ax, labels, x)
        ax.legend(fontsize=8.5, frameon=False, loc="upper left")
        fig.tight_layout(pad=1.6)
        return fig, None

    fig, _ = _build_fig(11.0, 4.2)
    cv = FigureCanvasTkAgg(fig, card)
    cv.draw_idle()
    cv.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(4, 12))
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
#  Sous-onglet : Actifs
# ─────────────────────────────────────────────────────────────
def _render_actifs(scroll, db, app, type_f, type_lbl_to_key,
                   all_assets, assets, total_all, total, total_cb):
    # ── Filtre type + bouton ajout ───────────────────────────
    top = ctk.CTkFrame(scroll, fg_color="transparent")
    top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    top.grid_columnconfigure(1, weight=1)

    type_labels = [FILTER_ALL_TYPES] + [lbl for lbl, _ in ASSET_TYPES]
    type_var    = ctk.StringVar(value=type_f)

    def on_type_change(choice):
        app.pat_type_filter = choice
        app._go("patrimoine")

    tf = ctk.CTkFrame(top, fg_color="transparent")
    tf.grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(tf, text="Type :",
                 font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left", padx=(0, 5))
    ctk.CTkOptionMenu(tf, values=type_labels, variable=type_var,
                      height=28, width=180,
                      fg_color=C["primary"], button_color=C["primary"],
                      command=on_type_change).pack(side="left")
    if type_f != FILTER_ALL_TYPES:
        ctk.CTkButton(tf, text="✕", height=28, width=30,
                      fg_color="#FEE2E2", text_color=C["red"],
                      hover_color="#FECACA",
                      command=lambda: (setattr(app, "pat_type_filter", FILTER_ALL_TYPES),
                                       app._go("patrimoine"))
                      ).pack(side="left", padx=(4, 0))

    def open_add():
        today = datetime.date.today()
        AssetDialog(app, on_save=lambda d: (
            db.upsert_asset(today.year, today.month,
                            d["asset_type"], d["asset_name"],
                            d["value"], d["cost_basis"], d["notes"]),
            app._go("patrimoine"),
        ))

    ctk.CTkButton(top, text="＋  Ajouter / Mettre à jour un actif",
                  height=32, command=open_add,
                  font=ctk.CTkFont(size=12)).grid(row=0, column=2, sticky="e")

    # ── Liste actifs ─────────────────────────────────────────
    lc = make_card(scroll)
    lc.grid(row=1, column=0, sticky="nsew")

    lc_title = "Portefeuille — valeurs actuelles"
    if type_f != FILTER_ALL_TYPES:
        lc_title += f"  ·  {type_f}"
    ctk.CTkLabel(lc, text=lc_title,
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(14, 6))

    if assets:
        hdr = ctk.CTkFrame(lc, fg_color=C["light"], corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(0, 4))
        hdr.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        only_comptes = (type_f != FILTER_ALL_TYPES and
                        type_lbl_to_key.get(type_f) == "compte")
        col_labels = ["Nom", "Solde actuel" if only_comptes else "Valeur act.",
                      "Total versé" if only_comptes else "Prix achat",
                      "Intérêts gagnés" if only_comptes else "Plus-value",
                      "Var. précéd."]
        for i, h in enumerate(col_labels):
            ctk.CTkLabel(hdr, text=h, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C["muted"]).grid(
                row=0, column=i, padx=10, pady=6, sticky="w")

        cur_type = None
        for asset in assets:
            if asset["asset_type"] != cur_type:
                cur_type = asset["asset_type"]
                accent = _TYPE_ACCENT.get(cur_type, C["primary"])
                type_hdr = ctk.CTkFrame(lc, fg_color="#F8FAFC", corner_radius=6)
                type_hdr.pack(fill="x", padx=12, pady=(8, 2))
                # height=1 : évite la taille par défaut 200px de CTkFrame qui
                # gonflerait tout le bandeau type_hdr (fill="y" l'étirera ensuite).
                ctk.CTkFrame(type_hdr, width=4, height=1, fg_color=accent,
                             corner_radius=4).pack(side="left", fill="y", padx=(0, 8), pady=4)
                ctk.CTkLabel(type_hdr,
                             text=f"{ASSET_LABEL.get(cur_type, cur_type)}",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=accent).pack(side="left", padx=4, pady=5)
                type_total = sum(a["value"] for a in assets if a["asset_type"] == cur_type)
                ctk.CTkLabel(type_hdr,
                             text=f"{type_total:,.0f} €",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=accent).pack(side="right", padx=12, pady=5)
            _asset_row(lc, asset, db, app)

        tf2 = ctk.CTkFrame(lc, fg_color="#EFF6FF", corner_radius=8,
                           border_width=1, border_color="#93C5FD")
        tf2.pack(fill="x", padx=12, pady=(10, 4))
        total_txt = f"Total sélection : {total:,.2f} €"
        if type_f != FILTER_ALL_TYPES and total_all > 0:
            pct = total / total_all * 100
            total_txt += f"  ({pct:.0f}% du patrimoine total)"
        ctk.CTkLabel(tf2, text=total_txt,
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["primary"]).pack(side="right", padx=16, pady=9)

        if type_f != FILTER_ALL_TYPES:
            ctk.CTkLabel(lc,
                         text=f"Patrimoine total (tous types) : {total_all:,.2f} €",
                         font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(
                anchor="e", padx=16, pady=(0, 6))

        if total_cb:
            pnl     = total - total_cb
            pnl_pct = pnl / total_cb * 100
            clr     = C["green"] if pnl >= 0 else C["red"]
            pf2 = ctk.CTkFrame(lc, fg_color="transparent")
            pf2.pack(anchor="e", padx=12, pady=(0, 10))
            pnl_label = ("Intérêts gagnés totaux" if only_comptes
                         else "Plus-value totale")
            ctk.CTkLabel(pf2,
                         text=f"{pnl_label} : {pnl:+,.2f} €  ({pnl_pct:+.1f} %)",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=clr).pack()
    else:
        msg = (f"Aucun actif de type « {type_f} »."
               if type_f != FILTER_ALL_TYPES
               else "Aucun actif enregistré.\nCliquez sur ＋ pour commencer.")
        ctk.CTkLabel(lc, text=msg, text_color=C["muted"],
                     justify="center").pack(expand=True, pady=40)


# ─────────────────────────────────────────────────────────────
#  Sous-onglet : Passifs
# ─────────────────────────────────────────────────────────────
def _render_passifs(scroll, db, app, passifs, total_p):
    today = datetime.date.today()

    card = make_card(scroll)
    card.grid(row=0, column=0, sticky="nsew")

    hdr = ctk.CTkFrame(card, fg_color="transparent")
    hdr.pack(fill="x", padx=16, pady=(14, 4))
    hdr.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(hdr, text="💳  Passifs (dettes)",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=C["text"]).grid(row=0, column=0, sticky="w")

    def open_add():
        LiabilityDialog(app, on_save=lambda d: (
            db.add_or_update_liability(
                today.year, today.month,
                d["liability_type"], d["liability_name"],
                d["remaining_capital"], d["monthly_payment"],
                d["end_date"], d["notes"],
            ),
            app._go("patrimoine"),
        ))

    ctk.CTkButton(hdr, text="＋  Ajouter une dette", height=30, width=160,
                  font=ctk.CTkFont(size=12),
                  command=open_add).grid(row=0, column=2, sticky="e")

    if not passifs:
        ctk.CTkLabel(card, text="Aucune dette enregistrée.",
                     text_color=C["muted"]).pack(pady=(10, 20))
        return

    table_f = ctk.CTkFrame(card, fg_color="transparent")
    table_f.pack(fill="x", padx=12, pady=(4, 4))
    table_header(table_f, [(2, "Nom"), (1, "Type"), (1, "Capital restant"),
                          (1, "Mensualité"), (1, "Fin")], extra_button_cols=1)

    for idx, p in enumerate(passifs):
        type_lbl = LIABILITY_LABEL.get(p["liability_type"], p["liability_type"].capitalize())
        monthly_txt = f"{p['monthly_payment']:,.0f} €/mois" if p["monthly_payment"] else "—"

        def _update_capital(liability=p):
            QuickValueUpdateDialog(
                app, liability["liability_name"], liability["remaining_capital"],
                on_save=lambda v: (
                    db.update_liability_capital(
                        liability["liability_name"], today.year, today.month, v
                    ),
                    app._go("patrimoine"),
                ),
                label="capital restant",
            )

        def _edit(liability=p):
            LiabilityDialog(app, initial=dict(liability), on_save=lambda d: (
                db.add_or_update_liability(
                    today.year, today.month,
                    d["liability_type"], d["liability_name"],
                    d["remaining_capital"], d["monthly_payment"],
                    d["end_date"], d["notes"],
                ),
                app._go("patrimoine"),
            ))

        def _delete(name=p["liability_name"]):
            db.delete_liability(name)
            app._go("patrimoine")

        table_row(
            table_f, idx,
            [(2, p["liability_name"], C["text"]),
             (1, type_lbl,            C["muted"]),
             (1, f"{p['remaining_capital']:,.2f} €", C["red"]),
             (1, monthly_txt,         C["muted"]),
             (1, p["end_date"] or "—", C["muted"])],
            on_edit=_edit, on_delete=_delete,
            extra_buttons=[("💰", "Mettre à jour le capital restant", _update_capital)],
            delete_label=f"« {p['liability_name']} »",
        )

    foot = ctk.CTkFrame(card, fg_color="transparent")
    foot.pack(anchor="e", padx=16, pady=(10, 14))
    ctk.CTkLabel(foot, text=f"Total dettes : {total_p:,.2f} €",
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color=C["red"]).pack()


# ─────────────────────────────────────────────────────────────
#  Sous-onglet : Positions clôturées
# ─────────────────────────────────────────────────────────────
def _render_closes(scroll, db, app, type_f, type_lbl_to_key):
    closed = db.get_closed_positions()
    if type_f != FILTER_ALL_TYPES:
        type_key = type_lbl_to_key.get(type_f)
        closed = [c for c in closed if c["asset_type"] == type_key]

    card = make_card(scroll)
    card.grid(row=0, column=0, sticky="nsew")

    hdr = ctk.CTkFrame(card, fg_color="transparent")
    hdr.pack(fill="x", padx=16, pady=(14, 4))

    if not closed:
        ctk.CTkLabel(hdr, text="💼  Positions clôturées",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(card, text="Aucune position clôturée pour le moment.",
                     text_color=C["muted"]).pack(pady=(10, 20))
        return

    nb_pending = sum(1 for c in closed if not c["all_reinvested"])
    total_pnl  = sum(c["realized_pnl"] for c in closed)
    pnl_clr    = C["green"] if total_pnl >= 0 else C["red"]
    pnl_sign   = "+" if total_pnl >= 0 else ""

    ctk.CTkLabel(
        hdr,
        text=f"💼  Positions clôturées  ·  {len(closed)} position{'s' if len(closed) > 1 else ''}",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=C["text"],
    ).pack(side="left")
    if nb_pending:
        _badge(hdr, f"{nb_pending} cash en attente", "#ECFDF5", "#047857")
    ctk.CTkLabel(hdr,
                 text=f"P&L total réalisé : {pnl_sign}{total_pnl:,.0f} €",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=pnl_clr).pack(side="right")

    table_f = ctk.CTkFrame(card, fg_color="transparent")
    table_f.pack(fill="x", padx=12, pady=(4, 4))
    table_header(table_f,
                 [(2, "Nom"), (1, "Qté vendue"), (1, "Prix vente moy."),
                  (1, "P&L réalisé"), (1, "Dernière vente"), (2, "Statut")],
                 extra_button_cols=2)

    for idx, c in enumerate(closed):
        rp   = c["realized_pnl"]
        sign = "+" if rp >= 0 else ""
        last_y, last_m = c["last_sale_ym"] or (0, 0)
        date_lbl = f"{MONTHS_FR[last_m - 1][:3]} {last_y}" if last_m else "—"
        name_cell = f"{c['asset_name']}  ·  {ASSET_LABEL.get(c['asset_type'], c['asset_type'])}"

        if c["all_reinvested"]:
            statut_txt, statut_clr = "♻ Réinvesti", C["muted"]
        else:
            statut_txt = f"💵 Cash : {c['cash_pending']:,.0f} €"
            statut_clr = "#047857"

        if not c["all_reinvested"]:
            def _reinvest(name=c["asset_name"]):
                db.mark_sales_reinvested(name, reinvested=True)
                app._go("patrimoine")
            toggle_btn = ("♻", "Marquer comme réinvesti", _reinvest)
        else:
            def _undo(name=c["asset_name"]):
                db.mark_sales_reinvested(name, reinvested=False)
                app._go("patrimoine")
            toggle_btn = ("↩", "Annuler réinvestissement", _undo)

        def _show_tx(name=c["asset_name"], typ=c["asset_type"]):
            today = datetime.date.today()
            asset_min = {
                "asset_name": name, "asset_type": typ,
                "value": 0.0, "cost_basis": 0.0,
                "id": -1, "year": today.year, "month": today.month,
                "notes": "",
            }
            AssetTransactionsDialog(app, asset_min, db, app, today.year, today.month)

        table_row(
            table_f, idx,
            [(2, name_cell,                        C["text"]),
             (1, f"{c['sale_qty']:g}",              C["text"]),
             (1, f"{c['avg_sale_price']:,.2f} €",   C["text"]),
             (1, f"{sign}{rp:,.0f} €",              C["green"] if rp >= 0 else C["red"]),
             (1, date_lbl,                          C["muted"]),
             (2, statut_txt,                        statut_clr)],
            extra_buttons=[toggle_btn, ("📋", "Voir les transactions", _show_tx)],
        )

    foot = ctk.CTkFrame(card, fg_color="transparent")
    foot.pack(fill="x", padx=12, pady=(8, 14))

    def _export_closed_csv():
        import tkinter.filedialog as fd
        import csv as _csv
        path = fd.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="positions_cloturees.csv",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.writer(f, delimiter=";")
            w.writerow(["Nom", "Type", "Qté vendue", "Prix vente moy. (€)",
                        "Investi (€)", "P&L réalisé (€)", "Frais (€)",
                        "Dernière vente", "Cash réinvesti"])
            for c in closed:
                ly, lm = c["last_sale_ym"] or (0, 0)
                w.writerow([
                    c["asset_name"],
                    ASSET_LABEL.get(c["asset_type"], c["asset_type"]),
                    f"{c['sale_qty']:g}",
                    f"{c['avg_sale_price']:.2f}",
                    f"{c['sale_proceeds'] - c['realized_pnl']:.2f}",
                    f"{c['realized_pnl']:.2f}",
                    f"{c['total_fees']:.2f}",
                    f"{MONTHS_FR[lm-1]} {ly}" if lm else "",
                    "Oui" if c["all_reinvested"] else "Non",
                ])

    ctk.CTkButton(foot, text="📄  Exporter CSV", height=32,
                  fg_color=C["muted"], hover_color="#475569",
                  command=_export_closed_csv).pack(side="right")


# ─────────────────────────────────────────────────────────────
#  Sous-onglet : Graphiques
# ─────────────────────────────────────────────────────────────
def _render_graphs_subview(scroll, db, app, type_f, type_lbl_to_key, period_f):
    top = ctk.CTkFrame(scroll, fg_color="transparent")
    top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    top.grid_columnconfigure(0, weight=1)

    type_labels = [FILTER_ALL_TYPES] + [lbl for lbl, _ in ASSET_TYPES]
    type_var    = ctk.StringVar(value=type_f)

    def on_type_change(choice):
        app.pat_type_filter = choice
        app._go("patrimoine")

    tf = ctk.CTkFrame(top, fg_color="transparent")
    tf.grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(tf, text="Type :",
                 font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left", padx=(0, 5))
    ctk.CTkOptionMenu(tf, values=type_labels, variable=type_var,
                      height=28, width=180,
                      fg_color=C["primary"], button_color=C["primary"],
                      command=on_type_change).pack(side="left")

    pf = ctk.CTkFrame(top, fg_color="transparent")
    pf.grid(row=0, column=1, sticky="e")
    ctk.CTkLabel(pf, text="Période :",
                 font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="left", padx=(0, 6))
    for lbl, _ in _PERIODS:
        is_active = (lbl == period_f)
        ctk.CTkButton(
            pf, text=lbl, height=26, width=42,
            font=ctk.CTkFont(size=11, weight="bold" if is_active else "normal"),
            fg_color=C["primary"] if is_active else C["light"],
            text_color="white" if is_active else C["muted"],
            hover_color="#2A5BD9" if is_active else "#E2E8F0",
            corner_radius=6,
            command=lambda l=lbl: (setattr(app, "pat_period_filter", l),
                                   app._go("patrimoine")),
        ).pack(side="left", padx=2)

    card = make_card(scroll)
    card.grid(row=1, column=0, sticky="nsew")
    _render_patrimoine_charts(card, db, app, type_f, type_lbl_to_key, period_f)


# ─────────────────────────────────────────────────────────────
#  KPI Card helper (spécifique patrimoine)
# ─────────────────────────────────────────────────────────────
def _kpi_pat(parent, col, title, value, color, bg, border_color):
    card = ctk.CTkFrame(parent, fg_color=bg, corner_radius=12,
                        border_width=1, border_color=border_color)
    card.grid(row=0, column=col, sticky="nsew", padx=5, pady=2)
    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=14, pady=12)
    ctk.CTkLabel(inner, text=title, font=ctk.CTkFont(size=11),
                 text_color=C["muted"]).pack(anchor="w")
    ctk.CTkLabel(inner, text=value,
                 font=ctk.CTkFont(size=15, weight="bold"),
                 text_color=color, wraplength=280, justify="left").pack(anchor="w", pady=(4, 0))


# ─────────────────────────────────────────────────────────────
#  Petit badge coloré à coller à côté d'un libellé
# ─────────────────────────────────────────────────────────────
def _badge(parent, text: str, bg: str, fg: str):
    """Crée un petit badge coloré (état d'une position)."""
    f = ctk.CTkFrame(parent, fg_color=bg, corner_radius=4)
    f.pack(side="left", padx=(8, 0))
    ctk.CTkLabel(f, text=text,
                 font=ctk.CTkFont(size=9, weight="bold"),
                 text_color=fg).pack(padx=6, pady=1)
    return f


# ─────────────────────────────────────────────────────────────
#  Ligne d'actif
# ─────────────────────────────────────────────────────────────
def _fmt_pnl(val, pct):
    """Formatage sur une seule ligne — cohérent avec les autres cellules de la ligne."""
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:,.0f} € ({sign}{pct:.1f}%)"


def _asset_row(parent, asset, db, app):
    """Ligne détaillée d'un actif avec métriques et boutons.

    Colonnes (aucune réutilisée) : 0=accent, 1=nom, 2=valeur, 3=coût,
    4=P&L/intérêts, 5=variation, 6=boutons.
    """
    value      = asset["value"]
    cost_basis = asset["cost_basis"] or 0.0
    prev_value = db.get_asset_previous_value(
        asset["year"], asset["month"],
        asset["asset_type"], asset["asset_name"]
    )

    pos_status = None
    if asset["asset_type"] in _TRANSACTION_TYPES:
        pos_status = db.get_position_status(asset["asset_name"])

    is_partial = pos_status and pos_status["status"] == "partiel"
    is_sold    = pos_status and pos_status["status"] == "vendu"

    if is_sold and not pos_status["all_reinvested"]:
        value = pos_status["sale_proceeds"]

    pnl          = value - cost_basis if cost_basis else None
    pnl_pct      = pnl / cost_basis * 100 if cost_basis and pnl is not None else None
    var_prev     = (value - prev_value) if prev_value is not None else None
    var_prev_pct = (var_prev / prev_value * 100) if prev_value else None

    accent = _TYPE_ACCENT.get(asset["asset_type"], C["primary"])
    row_bg = "#FAFBFC" if is_sold else C["card"]

    row_f = ctk.CTkFrame(parent, fg_color=row_bg, corner_radius=8,
                          border_width=1, border_color=C["border"])
    row_f.pack(fill="x", padx=12, pady=2)
    row_f.grid_columnconfigure(0, weight=0, minsize=8)
    row_f.grid_columnconfigure(1, weight=2)
    row_f.grid_columnconfigure((2, 3, 4, 5), weight=1)
    row_f.grid_columnconfigure(6, weight=0)

    # Colonne 0 : barre d'accent (dédiée, plus jamais réutilisée)
    # height=1 : évite la taille par défaut 200px de CTkFrame (sticky="ns"
    # l'étirera ensuite à la hauteur réelle de la ligne).
    ctk.CTkFrame(row_f, width=3, height=1, fg_color=accent,
                 corner_radius=2).grid(row=0, column=0, sticky="ns", padx=(4, 0), pady=6)

    # Colonne 1 : nom + badge + sous-ligne
    name_cell = ctk.CTkFrame(row_f, fg_color="transparent")
    name_cell.grid(row=0, column=1, padx=(10, 10), pady=8, sticky="w")

    name_line = ctk.CTkFrame(name_cell, fg_color="transparent")
    name_line.pack(anchor="w")
    ctk.CTkLabel(name_line, text=asset["asset_name"],
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["text"]).pack(side="left")
    if is_partial:
        _badge(name_line, "🟡 PARTIEL", "#FEF3C7", "#92400E")
    elif is_sold:
        _badge(name_line, "🔴 VENDU", "#FEE2E2", "#991B1B")

    update_lbl = f"{MONTHS_FR[asset['month']-1][:3]}. {asset['year']}"
    ctk.CTkLabel(name_cell, text=update_lbl,
                 font=ctk.CTkFont(size=9),
                 text_color=C["muted"]).pack(anchor="w")

    if pos_status and pos_status["has_sales"]:
        rp     = pos_status["realized_pnl"]
        rp_clr = C["green"] if rp >= 0 else C["red"]
        sign   = "+" if rp >= 0 else ""
        sale_qty = pos_status["sale_qty"]
        sale_avg = pos_status["avg_sale_price"]
        if is_partial:
            txt = (f"↳ {sale_qty:g} vendu(s) à {sale_avg:,.2f} € moy. "
                   f"·  P&L réalisé : {sign}{rp:,.0f} €")
        else:
            txt = (f"↳ Total vendu : {sale_qty:g} à {sale_avg:,.2f} € moy. "
                   f"·  P&L réalisé : {sign}{rp:,.0f} €")
        ctk.CTkLabel(name_cell, text=txt,
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=rp_clr).pack(anchor="w", pady=(2, 0))

    # Colonne 2 : valeur
    ctk.CTkLabel(row_f, text=f"{value:,.2f} €",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["primary"]).grid(row=0, column=2, padx=10, pady=8, sticky="w")

    is_compte_type = (asset["asset_type"] == "compte")

    # Colonne 3 : prix d'achat / total versé
    col3_text = f"{cost_basis:,.2f} €" if cost_basis else "—"
    ctk.CTkLabel(row_f, text=col3_text,
                 font=ctk.CTkFont(size=11), text_color=C["muted"]).grid(
        row=0, column=3, padx=10, pady=8, sticky="w")

    # Colonne 4 : intérêts gagnés (compte) ou plus-value (invest.)
    if is_compte_type:
        if cost_basis and cost_basis > 0:
            interets  = value - cost_basis
            sign      = "+" if interets >= 0 else ""
            pnl_text  = f"{sign}{interets:,.0f} €"
            pnl_color = C["green"] if interets >= 0 else C["red"]
        else:
            pnl_text, pnl_color = "—", C["muted"]
    else:
        pnl_text  = _fmt_pnl(pnl, pnl_pct)
        pnl_color = C["green"] if (pnl or 0) >= 0 else C["red"]
    ctk.CTkLabel(row_f, text=pnl_text,
                 font=ctk.CTkFont(size=11), text_color=pnl_color).grid(
        row=0, column=4, padx=10, pady=8, sticky="w")

    # Colonne 5 : variation vs mois précédent
    var_text  = _fmt_pnl(var_prev, var_prev_pct)
    var_color = C["green"] if (var_prev or 0) >= 0 else C["red"]
    ctk.CTkLabel(row_f, text=var_text,
                 font=ctk.CTkFont(size=11), text_color=var_color).grid(
        row=0, column=5, padx=10, pady=8, sticky="w")

    # Colonne 6 : boutons d'action
    btns = ctk.CTkFrame(row_f, fg_color="transparent")
    btns.grid(row=0, column=6, padx=6, pady=4)
    today = datetime.date.today()

    def edit_asset():
        AssetDialog(app, initial=dict(asset), on_save=lambda d: (
            db.update_asset(asset["id"],
                            d["asset_type"], d["asset_name"],
                            d["value"], d["cost_basis"], d["notes"]),
            app._go("patrimoine"),
        ))

    def quick_update():
        QuickValueUpdateDialog(
            app, asset["asset_name"], asset["value"],
            on_save=lambda v: (
                db.update_asset_value(asset["id"], v),
                app._go("patrimoine"),
            ),
            label="solde" if is_compte_type else "valeur",
        )

    def show_evolution():
        history = db.get_asset_history_by_name(asset["asset_name"])
        AssetEvolutionDialog(app, asset["asset_name"], history)

    def show_transactions():
        AssetTransactionsDialog(app, asset, db, app, today.year, today.month)

    btn_edit = ctk.CTkButton(btns, text="✏", width=30, height=26,
                             fg_color="#EFF6FF", text_color=C["primary"],
                             hover_color="#DBEAFE",
                             command=edit_asset)
    btn_edit.pack(side="left", padx=(0, 2))
    Tooltip(btn_edit, "Modifier l'actif")

    btn_update = ctk.CTkButton(btns, text="💰", width=30, height=26,
                               fg_color="#F0FDF4", text_color=C["green"],
                               hover_color="#DCFCE7",
                               command=quick_update)
    btn_update.pack(side="left", padx=(0, 2))
    Tooltip(btn_update, "Mettre à jour le solde" if is_compte_type else "Mettre à jour la valeur")

    has_trans = asset["asset_type"] in _TRANSACTION_TYPES
    btn_trans = ctk.CTkButton(btns, text="📋", width=30, height=26,
                              fg_color="#FFF7ED" if has_trans else "#F8FAFC",
                              text_color="#F97316" if has_trans else C["muted"],
                              hover_color="#FFEDD5",
                              state="normal" if has_trans else "disabled",
                              command=show_transactions)
    btn_trans.pack(side="left", padx=(0, 2))
    Tooltip(btn_trans, "Transactions" if has_trans else "Non applicable (compte / épargne)")

    btn_evol = ctk.CTkButton(btns, text="📊", width=30, height=26,
                             fg_color="#F5F3FF", text_color="#8B5CF6",
                             hover_color="#EDE9FE",
                             command=show_evolution)
    btn_evol.pack(side="left", padx=(0, 2))
    Tooltip(btn_evol, "Évolution historique")

    if is_sold and not pos_status["all_reinvested"]:
        def mark_reinvested():
            db.mark_sales_reinvested(asset["asset_name"], reinvested=True)
            app._go("patrimoine")
        btn_reinvest = ctk.CTkButton(btns, text="♻", width=30, height=26,
                                     fg_color="#ECFDF5", text_color="#047857",
                                     hover_color="#D1FAE5",
                                     command=mark_reinvested)
        btn_reinvest.pack(side="left", padx=(0, 2))
        Tooltip(btn_reinvest, "Marquer comme réinvesti")

    def _del_asset():
        from ui.components import confirm_delete
        confirm_delete(app, lambda: (db.delete_asset(asset["id"]), app._go("patrimoine")),
                       label=f"« {asset.get('asset_name', 'cet actif')} »")

    btn_del = ctk.CTkButton(btns, text="✕", width=30, height=26,
                            fg_color="#FEE2E2", text_color=C["red"],
                            hover_color="#FECACA",
                            command=_del_asset)
    btn_del.pack(side="left")
    Tooltip(btn_del, "Supprimer l'actif")


# ─────────────────────────────────────────────────────────────
#  Fenêtre plein-écran pour un graphique
# ─────────────────────────────────────────────────────────────
def _open_fullscreen(app, title, build_fig_fn):
    win = ctk.CTkToplevel(app)
    win.title(title)
    win.geometry("1100x680")
    win.lift()
    win.focus_force()

    bar = ctk.CTkFrame(win, fg_color=C["sidebar"], height=44, corner_radius=0)
    bar.pack(fill="x", side="top")
    ctk.CTkLabel(bar, text=f"  ⛶  {title}",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color="white").pack(side="left", padx=12, pady=8)
    ctk.CTkButton(bar, text="✕  Fermer", height=28, width=90,
                  fg_color="#EF4444", hover_color="#DC2626",
                  text_color="white", font=ctk.CTkFont(size=12),
                  command=win.destroy).pack(side="right", padx=12, pady=8)

    frame = ctk.CTkFrame(win, fg_color="white", corner_radius=0)
    frame.pack(fill="both", expand=True, padx=16, pady=16)

    fig, _ = build_fig_fn(13.0, 7.2)
    cv = FigureCanvasTkAgg(fig, frame)
    cv.draw_idle()
    cv.get_tk_widget().pack(fill="both", expand=True)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
#  Helpers graphiques
# ─────────────────────────────────────────────────────────────
def _fmt_euros(x, _pos):
    """Formateur axe Y : 1 500 €, 12 k€, 1,5 M€"""
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:.1f} M€"
    if abs(x) >= 1_000:
        return f"{x/1_000:.0f} k€"
    return f"{x:.0f} €"


def _apply_period_filter(history, period_label):
    nb = dict(_PERIODS).get(period_label)
    if nb is None or len(history) <= nb:
        return history
    return history[-nb:]


def _smart_xticks(ax, labels, x):
    n = len(labels)
    if n == 0:
        return
    step = max(1, n // 12)
    ticks_shown = list(range(0, n, step))
    if (n - 1) not in ticks_shown:
        ticks_shown.append(n - 1)
    ax.set_xticks([x[i] for i in ticks_shown])
    ax.set_xticklabels([labels[i] for i in ticks_shown],
                       rotation=35, ha="right", fontsize=8)


def _style_ax(ax):
    """Applique un style moderne commun à tous les axes."""
    ax.set_facecolor("#F8FBFF")
    ax.grid(axis="y", color="#E8EEF8", lw=0.8, zorder=0)
    ax.grid(axis="x", color="#F1F5F9", lw=0.5, zorder=0)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#DDE3EF")
    ax.spines["bottom"].set_color("#DDE3EF")
    ax.tick_params(colors="#64748B", labelsize=8.5)


# ─────────────────────────────────────────────────────────────
#  Graphiques patrimoine
# ─────────────────────────────────────────────────────────────
def _render_patrimoine_charts(card, db, app, type_filter=FILTER_ALL_TYPES,
                               type_lbl_to_key=None, period_filter="Tout"):

    tabs = ctk.CTkTabview(card, fg_color="transparent",
                          segmented_button_fg_color=C["light"],
                          segmented_button_selected_color=C["primary"],
                          segmented_button_selected_hover_color=C["primary"])
    tabs.pack(fill="both", expand=True, padx=6, pady=(10, 10))
    tabs.add("📈  Évolution")
    tabs.add("🥧  Répartition")
    tabs.add("📊  Par actif")
    tabs.add("🎯  Diversification")

    def _filter_title(base):
        parts = [base]
        if type_filter != FILTER_ALL_TYPES:
            parts.append(type_filter)
        if period_filter != "Tout":
            parts.append(period_filter)
        return "  ·  ".join(parts)

    # ╔══════════════════════════════════════════════════════════╗
    # ║  Onglet 1 : Évolution                                    ║
    # ╚══════════════════════════════════════════════════════════╝
    ev_tab = tabs.tab("📈  Évolution")

    if type_filter != FILTER_ALL_TYPES and type_lbl_to_key:
        type_key        = type_lbl_to_key[type_filter]
        history_raw     = db.get_patrimoine_history_by_type(type_key)
        history_raw     = [h for h in history_raw if h["total_value"] > 0]
        per_asset_mode  = True
    else:
        history_raw    = db.get_patrimoine_history()
        per_asset_mode = False

    history = _apply_period_filter(history_raw, period_filter)

    def _build_ev_fig(fw, fh):
        pts    = list(history)
        labels = [f"{MONTHS_FR[p['month']-1][:3]} {str(p['year'])[2:]}"
                  for p in pts]
        x      = list(range(len(pts)))

        fig, ax = plt.subplots(figsize=(fw, fh))
        fig.patch.set_facecolor(C["card"])
        _style_ax(ax)

        lines_data = []

        if per_asset_mode:
            all_names = list(pts[0]["per_asset"].keys()) if pts else []
            for i, name in enumerate(all_names):
                ydata = [p["per_asset"].get(name, 0.0) for p in pts]
                color = PALETTE[i % len(PALETTE)]
                ax.plot(x, ydata, color=color, lw=2.2, marker="o", ms=5,
                        label=name, zorder=3)
                ax.fill_between(x, ydata, alpha=0.07, color=color)
                lines_data.append((name, x, ydata, color))
            total_y = [p["total_value"] for p in pts]
            ax.plot(x, total_y, color="#1E293B", lw=2.5, marker="D",
                    ms=4, ls="--", label="Total", zorder=4)
            lines_data.append(("Total", x, total_y, "#1E293B"))
        else:
            vals  = [p["total_value"] for p in pts]
            bases = [p["total_basis"]  for p in pts]
            ax.fill_between(x, vals, alpha=0.13, color=C["primary"])
            ax.plot(x, vals, color=C["primary"], lw=2.8, marker="o",
                    ms=6, label="Valeur", zorder=3)
            lines_data.append(("Valeur", x, vals, C["primary"]))
            if any(b for b in bases):
                ax.plot(x, bases, color=C["amber"], lw=2, ls="--",
                        marker="s", ms=4, label="Investi", zorder=3)
                lines_data.append(("Investi", x, bases, C["amber"]))
                ax.fill_between(x, vals, bases,
                                where=[v >= b for v, b in zip(vals, bases)],
                                alpha=0.12, color=C["green"], label="_nolegend_")
                ax.fill_between(x, vals, bases,
                                where=[v < b for v, b in zip(vals, bases)],
                                alpha=0.12, color=C["red"], label="_nolegend_")

        ax.set_title(_filter_title("Évolution du patrimoine"),
                     fontsize=10, color="#475569", pad=8, loc="left")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_euros))
        _smart_xticks(ax, labels, x)
        ax.legend(fontsize=8.5, frameon=False, loc="upper left")
        fig.tight_layout(pad=1.6)
        return fig, (ax, pts, lines_data, per_asset_mode)

    if len(history) >= 2:
        fig_ev, (ax_ev, pts_ev, lines_ev, pam_ev) = _build_ev_fig(11.0, 5.0)
        cv_ev = FigureCanvasTkAgg(fig_ev, ev_tab)
        cv_ev.draw_idle()
        cv_ev.get_tk_widget().pack(fill="both", expand=True)

        ctk.CTkButton(ev_tab,
                      text="⛶  Agrandir", height=26, width=110,
                      font=ctk.CTkFont(size=11),
                      fg_color=C["light"], text_color=C["primary"],
                      hover_color="#DBEAFE",
                      command=lambda: _open_fullscreen(
                          app, _filter_title("Évolution du patrimoine"),
                          lambda fw, fh: _build_ev_fig(fw, fh)
                      )).place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=4)

        annot_ev = ax_ev.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.55", fc="white",
                      ec=C["primary"], lw=1.3, alpha=0.97),
            arrowprops=dict(arrowstyle="->", color=C["primary"], lw=1),
            fontsize=9, color=C["text"], zorder=12,
        )
        annot_ev.set_visible(False)
        vline_ev = ax_ev.axvline(x=0, color=C["primary"],
                                  lw=1, ls=":", alpha=0, zorder=5)

        def _ev_move(event):
            if event.inaxes != ax_ev:
                annot_ev.set_visible(False)
                vline_ev.set_alpha(0)
                cv_ev.draw_idle()
                return
            xf = event.xdata
            if xf is None:
                return
            xi = int(round(xf))
            if xi < 0 or xi >= len(pts_ev):
                return
            p     = pts_ev[xi]
            lbl_m = f"{MONTHS_FR[p['month']-1]} {p['year']}"
            lines_tooltip = [f"[{lbl_m}]"]
            for name_l, _, ydata_l, _ in lines_ev:
                val = ydata_l[xi]
                prefix = "━" if name_l == "Total" else "•"
                lines_tooltip.append(f"{prefix} {name_l} : {val:,.0f} €")
            if not pam_ev and xi > 0:
                delta = lines_ev[0][2][xi] - lines_ev[0][2][xi - 1]
                sign  = "▲" if delta >= 0 else "▼"
                lines_tooltip.append(f"{sign}  {abs(delta):,.0f} € vs mois préc.")
            annot_ev.set_text("\n".join(lines_tooltip))
            y_ref = lines_ev[0][2][xi]
            annot_ev.xy = (xi, y_ref)
            annot_ev.set_visible(True)
            vline_ev.set_xdata([xi, xi])
            vline_ev.set_alpha(0.35)
            cv_ev.draw_idle()

        fig_ev.canvas.mpl_connect("motion_notify_event", _ev_move)
        plt.close(fig_ev)

    elif len(history) == 1:
        p = history[0]
        v = p["total_value"]
        ctk.CTkLabel(ev_tab,
                     text=(f"📌  1 enregistrement\n"
                           f"{MONTHS_FR[p['month']-1]} {p['year']} : {v:,.0f} €\n\n"
                           f"Mettez à jour vos actifs sur\n"
                           f"plusieurs mois pour voir l'évolution."),
                     text_color=C["muted"], justify="center",
                     font=ctk.CTkFont(size=12)).pack(expand=True, pady=40)
    else:
        ctk.CTkLabel(ev_tab,
                     text="Aucune donnée pour cette période.\nModifiez le filtre période.",
                     text_color=C["muted"], justify="center",
                     font=ctk.CTkFont(size=12)).pack(expand=True, pady=55)

    # ╔══════════════════════════════════════════════════════════╗
    # ║  Onglet 2 : Répartition (donut)                          ║
    # ╚══════════════════════════════════════════════════════════╝
    pie_tab = tabs.tab("🥧  Répartition")
    by_type = db.get_assets_by_type_current()

    if type_filter != FILTER_ALL_TYPES and type_lbl_to_key:
        type_key  = type_lbl_to_key.get(type_filter)
        all_a     = db.get_assets_current()
        pie_rows  = [{"label": a["asset_name"], "value": a["value"]}
                     for a in all_a if a["asset_type"] == type_key]
        pie_title = _filter_title("Répartition par actif")
    else:
        pie_rows  = [{"label": ASSET_LABEL.get(r["asset_type"], r["asset_type"]),
                      "value": r["total"]}
                     for r in by_type]
        pie_title = "Répartition par type d'actif"

    def _build_pie_fig(fw, fh):
        pie_labels = [r["label"] for r in pie_rows]
        pie_vals   = [r["value"] for r in pie_rows]
        colors2    = PALETTE[:len(pie_labels)]
        total_pie  = sum(pie_vals)

        fig2, ax2 = plt.subplots(figsize=(fw, fh))
        fig2.patch.set_facecolor(C["card"])
        wedges, texts, autotexts = ax2.pie(
            pie_vals, autopct="%1.1f%%", colors=colors2,
            startangle=90, pctdistance=0.76,
            wedgeprops=dict(width=0.60, edgecolor="white", linewidth=2.5),
        )
        for at in autotexts:
            at.set_fontsize(9)
            at.set_fontweight("bold")
        ax2.text(0, 0, f"{total_pie:,.0f} €",
                 ha="center", va="center",
                 fontsize=9, fontweight="bold", color=C["text"])
        ax2.set_title(pie_title, fontsize=10, color="#475569", pad=6, loc="left")
        ax2.legend(wedges,
                   [f"{l}  —  {v:,.0f} €  ({v/total_pie*100:.1f}%)"
                    for l, v in zip(pie_labels, pie_vals)],
                   loc="lower left", bbox_to_anchor=(-0.08, -0.44),
                   fontsize=8, frameon=False)
        fig2.tight_layout(pad=1.4)
        return fig2, (ax2, wedges, pie_labels, pie_vals, colors2, total_pie)

    if pie_rows:
        fig2, (ax2, wedges2, plabels, pvals, pcolors, ptotal) = _build_pie_fig(9.5, 5.0)
        cv2 = FigureCanvasTkAgg(fig2, pie_tab)
        cv2.draw_idle()
        cv2.get_tk_widget().pack(fill="both", expand=True)

        ctk.CTkButton(pie_tab,
                      text="⛶  Agrandir", height=26, width=110,
                      font=ctk.CTkFont(size=11),
                      fg_color=C["light"], text_color=C["primary"],
                      hover_color="#DBEAFE",
                      command=lambda: _open_fullscreen(
                          app, pie_title,
                          lambda fw, fh: _build_pie_fig(fw, fh)
                      )).place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=4)

        annot2    = ax2.annotate(
            "", xy=(0, 0), xytext=(0, 0), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.55", fc="white",
                      ec="#94A3B8", lw=1.2, alpha=0.97),
            fontsize=9, color=C["text"], zorder=12,
        )
        annot2.set_visible(False)
        _prev_w = [None]

        def _pie_move(event):
            if event.inaxes != ax2:
                if _prev_w[0]:
                    _prev_w[0].set_linewidth(2.5)
                    _prev_w[0] = None
                    annot2.set_visible(False)
                    cv2.draw_idle()
                return
            found = False
            for i, wedge in enumerate(wedges2):
                cont, _ = wedge.contains(event)
                if cont:
                    if _prev_w[0] and _prev_w[0] != wedge:
                        _prev_w[0].set_linewidth(2.5)
                    wedge.set_linewidth(5)
                    _prev_w[0] = wedge
                    pct = pvals[i] / ptotal * 100
                    annot2.get_bbox_patch().set_edgecolor(pcolors[i])
                    annot2.set_text(
                        f"{'🏷' if type_filter == 'Tous types' else '📌'}  {plabels[i]}\n"
                        f"💶  {pvals[i]:,.0f} €\n"
                        f"📊  {pct:.1f}% du total"
                    )
                    annot2.xy     = (event.xdata, event.ydata)
                    annot2.xytext = (20, 20)
                    annot2.set_visible(True)
                    found = True
                    break
            if not found:
                if _prev_w[0]:
                    _prev_w[0].set_linewidth(2.5)
                    _prev_w[0] = None
                annot2.set_visible(False)
            cv2.draw_idle()

        fig2.canvas.mpl_connect("motion_notify_event", _pie_move)
        plt.close(fig2)
    else:
        ctk.CTkLabel(pie_tab, text="Aucune donnée",
                     text_color=C["muted"]).pack(expand=True, pady=55)

    # ╔══════════════════════════════════════════════════════════╗
    # ║  Onglet 3 : Par actif (barres horizontales)              ║
    # ╚══════════════════════════════════════════════════════════╝
    bar_tab = tabs.tab("📊  Par actif")
    all_assets_cur = db.get_assets_current()

    if type_filter != FILTER_ALL_TYPES and type_lbl_to_key:
        type_key_b = type_lbl_to_key[type_filter]
        bar_assets = [a for a in all_assets_cur if a["asset_type"] == type_key_b]
    else:
        bar_assets = list(all_assets_cur)

    def _build_bar_fig(fw, fh):
        b_sorted  = sorted(bar_assets, key=lambda a: a["value"], reverse=True)
        b_names   = [a["asset_name"] for a in b_sorted]
        b_vals    = [a["value"]      for a in b_sorted]
        b_types   = [a["asset_type"] for a in b_sorted]
        uniq_types = list(dict.fromkeys(b_types))
        b_colors  = [_TYPE_ACCENT.get(t, PALETTE[uniq_types.index(t) % len(PALETTE)])
                     for t in b_types]

        n      = len(b_sorted)
        fig3_h = max(fh * 0.5, 0.52 * n + 1.0) if fh < 6 else fh
        fig3, ax3 = plt.subplots(figsize=(fw, fig3_h))
        fig3.patch.set_facecolor(C["card"])
        _style_ax(ax3)

        y_pos = list(range(n))
        bars3 = ax3.barh(y_pos, b_vals, color=b_colors,
                         height=0.62, edgecolor="white", linewidth=1.5)

        max_v = max(b_vals) if b_vals else 1
        for bar, val in zip(bars3, b_vals):
            ax3.text(bar.get_width() + max_v * 0.015,
                     bar.get_y() + bar.get_height() / 2,
                     f"{val:,.0f} €", va="center", ha="left",
                     fontsize=8, color=C["text"])

        ax3.set_yticks(y_pos)
        ax3.set_yticklabels(b_names, fontsize=8.5)
        ax3.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt_euros))
        ax3.xaxis.set_tick_params(labelsize=8)
        ax3.set_title(_filter_title("Valeurs actuelles par actif"),
                      fontsize=10, color="#475569", pad=8, loc="left")
        ax3.invert_yaxis()
        ax3.set_xlim(0, max_v * 1.18)
        fig3.tight_layout(pad=1.5)
        return fig3, (ax3, bars3, b_sorted, b_vals, uniq_types, b_colors)

    if bar_assets:
        fig3, (ax3, bars3, bsorted, bvals, utypes, bcolors) = _build_bar_fig(9.8, 5.0)
        cv3 = FigureCanvasTkAgg(fig3, bar_tab)
        cv3.draw_idle()
        cv3.get_tk_widget().pack(fill="both", expand=True)

        ctk.CTkButton(bar_tab,
                      text="⛶  Agrandir", height=26, width=110,
                      font=ctk.CTkFont(size=11),
                      fg_color=C["light"], text_color=C["primary"],
                      hover_color="#DBEAFE",
                      command=lambda: _open_fullscreen(
                          app, _filter_title("Valeurs par actif"),
                          lambda fw, fh: _build_bar_fig(fw, fh)
                      )).place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=4)

        annot3  = ax3.annotate(
            "", xy=(0, 0), xytext=(-120, 0), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.55", fc="white",
                      ec=C["primary"], lw=1.3, alpha=0.97),
            fontsize=9, color=C["text"], zorder=12,
        )
        annot3.set_visible(False)
        _prev_b = [None]

        def _bar_move(event):
            if event.inaxes != ax3:
                if _prev_b[0]:
                    _prev_b[0].set_edgecolor("white")
                    _prev_b[0].set_linewidth(1.5)
                    _prev_b[0] = None
                annot3.set_visible(False)
                cv3.draw_idle()
                return
            found = False
            for i, bar in enumerate(bars3):
                cont, _ = bar.contains(event)
                if cont:
                    if _prev_b[0] and _prev_b[0] != bar:
                        _prev_b[0].set_edgecolor("white")
                        _prev_b[0].set_linewidth(1.5)
                    bar.set_edgecolor(C["primary"])
                    bar.set_linewidth(2.5)
                    _prev_b[0] = bar
                    a_info  = bsorted[i]
                    val     = bvals[i]
                    cb      = a_info["cost_basis"] or 0.0
                    type_lb = ASSET_LABEL.get(a_info["asset_type"],
                                              a_info["asset_type"])
                    pnl_txt = ""
                    if cb:
                        pnl     = val - cb
                        pnl_pct = pnl / cb * 100
                        sign    = "▲" if pnl >= 0 else "▼"
                        pnl_txt = f"\n{sign}  PV : {pnl:+,.0f} € ({pnl_pct:+.1f}%)"
                    annot3.set_text(
                        f"📌  {a_info['asset_name']}\n"
                        f"🏷  {type_lb}\n"
                        f"💶  {val:,.0f} €{pnl_txt}"
                    )
                    annot3.xy = (bar.get_width(),
                                  bar.get_y() + bar.get_height() / 2)
                    annot3.set_visible(True)
                    found = True
                    break
            if not found:
                if _prev_b[0]:
                    _prev_b[0].set_edgecolor("white")
                    _prev_b[0].set_linewidth(1.5)
                    _prev_b[0] = None
                annot3.set_visible(False)
            cv3.draw_idle()

        fig3.canvas.mpl_connect("motion_notify_event", _bar_move)
        plt.close(fig3)
    else:
        ctk.CTkLabel(bar_tab, text="Aucun actif à afficher.",
                     text_color=C["muted"]).pack(expand=True, pady=55)

    # ╔══════════════════════════════════════════════════════════╗
    # ║  Onglet 4 : Diversification                              ║
    # ╚══════════════════════════════════════════════════════════╝
    div_tab = tabs.tab("🎯  Diversification")
    _render_diversification_tab(div_tab, db, type_filter, type_lbl_to_key)


# ─────────────────────────────────────────────────────────────
#  Onglet Diversification
# ─────────────────────────────────────────────────────────────
def _render_diversification_tab(parent, db, type_filter, type_lbl_to_key):
    """Analyse de la diversification du portefeuille."""
    all_assets = db.get_assets_current()
    if not all_assets:
        ctk.CTkLabel(parent, text="Aucun actif enregistré.",
                     text_color=C["muted"]).pack(expand=True, pady=55)
        return

    total_val  = sum(a["value"] for a in all_assets)
    by_type    = {}
    for a in all_assets:
        t = a["asset_type"]
        by_type[t] = by_type.get(t, 0.0) + a["value"]

    scroll = ctk.CTkScrollableFrame(parent, fg_color=C["card"])
    scroll.pack(fill="both", expand=True)

    weights = [v / total_val for v in by_type.values()] if total_val > 0 else []
    hhi     = sum(w ** 2 for w in weights)
    n_types = len(by_type)
    score   = int(max(0, min(100, (1 - hhi) / max(1 - 1/max(n_types,1), 0.001) * 100))) if n_types > 1 else 0

    score_color = C["green"] if score >= 70 else (C["amber"] if score >= 40 else C["red"])
    score_label = "Bien diversifié" if score >= 70 else ("Diversification modérée" if score >= 40 else "Peu diversifié")

    sc = ctk.CTkFrame(scroll, fg_color="#F8FAFC", corner_radius=10,
                      border_width=1, border_color=C["border"])
    sc.pack(fill="x", padx=8, pady=(8, 4))
    sc_inner = ctk.CTkFrame(sc, fg_color="transparent")
    sc_inner.pack(fill="x", padx=16, pady=12)

    ctk.CTkLabel(sc_inner, text="Score de diversification",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["text"]).pack(anchor="w")

    bar_frame = ctk.CTkFrame(sc_inner, fg_color="#E2E8F0",
                              corner_radius=6, height=14)
    bar_frame.pack(fill="x", pady=(6, 4))
    bar_frame.pack_propagate(False)
    bar_inner = ctk.CTkFrame(bar_frame, fg_color=score_color,
                              corner_radius=6, height=14)
    bar_inner.place(relx=0, rely=0, relwidth=score/100, relheight=1)

    row_sc = ctk.CTkFrame(sc_inner, fg_color="transparent")
    row_sc.pack(fill="x")
    ctk.CTkLabel(row_sc, text=f"{score}/100  —  {score_label}",
                 font=ctk.CTkFont(size=11, weight="bold"),
                 text_color=score_color).pack(side="left")
    ctk.CTkLabel(row_sc, text=f"{n_types} type{'s' if n_types > 1 else ''} d'actifs",
                 font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(side="right")

    ctk.CTkLabel(scroll, text="Répartition par type d'actif",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=8, pady=(10, 4))

    sorted_types = sorted(by_type.items(), key=lambda x: -x[1])
    ideal = {
        "bourse":     (30, 60),
        "immobilier": (20, 50),
        "compte":     (5, 20),
        "crypto":     (0, 10),
        "or_metaux":  (0, 10),
        "autre":      (0, 15),
    }

    for asset_type, val in sorted_types:
        pct    = val / total_val * 100 if total_val else 0
        accent = _TYPE_ACCENT.get(asset_type, C["primary"])
        label  = ASSET_LABEL.get(asset_type, asset_type)
        lo, hi = ideal.get(asset_type, (0, 100))
        in_range = lo <= pct <= hi

        row = ctk.CTkFrame(scroll, fg_color="white", corner_radius=8,
                           border_width=1, border_color=C["border"])
        row.pack(fill="x", padx=8, pady=3)

        ctk.CTkFrame(row, width=4, height=1, fg_color=accent,
                     corner_radius=3).pack(side="left", fill="y", padx=(0, 10), pady=6)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, pady=8)

        top_row = ctk.CTkFrame(info, fg_color="transparent")
        top_row.pack(fill="x")
        ctk.CTkLabel(top_row, text=label,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(top_row, text=f"{val:,.0f} €",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=accent).pack(side="right", padx=12)

        bar_bg = ctk.CTkFrame(info, fg_color="#F1F5F9", corner_radius=4, height=8)
        bar_bg.pack(fill="x", pady=(3, 2))
        bar_bg.pack_propagate(False)
        ctk.CTkFrame(bar_bg, fg_color=accent, corner_radius=4,
                     height=8).place(relx=0, rely=0, relwidth=min(pct/100, 1.0), relheight=1)

        bottom_row = ctk.CTkFrame(info, fg_color="transparent")
        bottom_row.pack(fill="x")
        ctk.CTkLabel(bottom_row, text=f"{pct:.1f}% du patrimoine",
                     font=ctk.CTkFont(size=10), text_color=C["muted"]).pack(side="left")
        if lo > 0 or hi < 100:
            range_txt = f"Conseillé : {lo}–{hi}%"
            range_col = C["green"] if in_range else C["amber"]
            ctk.CTkLabel(bottom_row, text=range_txt,
                         font=ctk.CTkFont(size=10), text_color=range_col).pack(side="right", padx=12)

    if n_types == 1:
        tip = "⚠️  Concentration totale sur un seul type d'actif. Envisagez de diversifier."
        tip_color = C["red"]
    elif score < 40:
        tip = "⚡  Diversification insuffisante. Rééquilibrez vers plusieurs classes d'actifs."
        tip_color = C["amber"]
    elif score < 70:
        tip = "🔄  Diversification correcte. Vous pouvez encore l'améliorer."
        tip_color = C["amber"]
    else:
        tip = "✅  Excellent niveau de diversification !"
        tip_color = C["green"]

    tip_f = ctk.CTkFrame(scroll, fg_color="#F8FAFC", corner_radius=8,
                          border_width=1, border_color=C["border"])
    tip_f.pack(fill="x", padx=8, pady=(10, 8))
    ctk.CTkLabel(tip_f, text=tip, font=ctk.CTkFont(size=11),
                 text_color=tip_color, wraplength=350,
                 justify="left").pack(anchor="w", padx=14, pady=10)
