"""
ui/pages/dashboard.py — Tableau de bord

Soft-refresh : les clics sur graphiques et filtres mettent à jour uniquement
les KPIs et les graphiques — sans reconstruire toute la page.
Clic sur une tranche/barre = filtre toggle.
"""
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
matplotlib.rcParams.update({
    "path.simplify": True,
    "path.simplify_threshold": 1.0,
    "agg.path.chunksize": 10000,
})
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import customtkinter as ctk
from config import C, MONTHS_FR, PALETTE, ASSET_LABEL, FILTER_ALL_CATS, FILTER_ALL_PAYEES
from ui.components import kpi_card, make_card, filter_dropdown, month_selector
from ui.dialogs import RecurringApplyDialog, RecurringManagerDialog, MonthCloseDialog


class DashboardPage:
    def render(self, container: ctk.CTkFrame, app):
        db  = app.db
        y   = app.sel_year
        m   = app.sel_month

        scroll = ctk.CTkScrollableFrame(container, fg_color=C["bg"])
        scroll.grid(row=0, column=0, sticky="nsew", padx=24, pady=20)
        scroll.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # ── Titre + sélecteur mois ───────────────────────────
        hdr = ctk.CTkFrame(scroll, fg_color="transparent")
        hdr.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 12))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="Tableau de bord",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        def on_month_change(new_m, new_y):
            app.sel_month = new_m
            app.sel_year  = new_y
            app._go("dashboard")

        month_selector(hdr, MONTHS_FR, y, m, on_month_change).grid(
            row=0, column=2, sticky="e")

        # ── Bouton Récurrentes ────────────────────────────
        pending_rec = db.get_pending_recurring(y, m)
        n_pending   = len(pending_rec)
        rec_label   = f"📅  Récurrentes  ({n_pending})" if n_pending else "📅  Récurrentes"
        rec_color   = C["primary"] if n_pending else C["light"]
        rec_txtclr  = "white" if n_pending else C["text"]

        def _open_recurring_apply():
            month_name = f"{MONTHS_FR[m - 1]} {y}"
            RecurringApplyDialog(
                app, db, y, m, month_name,
                on_applied=lambda n: app._go("dashboard"),
            )

        btn_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=(20, 8), sticky="w")

        ctk.CTkButton(
            btn_frame, text=rec_label, height=32, width=170,
            fg_color=rec_color, text_color=rec_txtclr,
            hover_color=C.get("primary_hover", C["primary"]),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=_open_recurring_apply,
        ).grid(row=0, column=0, padx=(0, 8))

        is_closed = db.is_month_closed(y, m)

        def _open_month_close():
            if is_closed:
                return  # Mois déjà clôturé, ne rien faire
            MonthCloseDialog(
                app, db, app, y, m,
                on_close=lambda: app._go("dashboard"),
            )

        close_lbl   = "🔒  Mois clôturé" if is_closed else "🗓  Clôturer le mois"
        close_color = "#D1FAE5" if is_closed else C["light"]
        close_txt   = "#065F46" if is_closed else C["text"]

        ctk.CTkButton(
            btn_frame, text=close_lbl, height=32, width=170,
            fg_color=close_color, text_color=close_txt,
            hover_color=close_color,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=_open_month_close,
        ).grid(row=0, column=1, padx=(0, 0))

        # ── Données statiques (non filtrées) ─────────────────
        rev_data     = db.get_revenues(y, m)
        sav_data     = db.get_savings(y, m)
        pat_data     = db.get_assets(y, m)          # pour le mini-patrimoine du mois
        pat_current  = db.get_assets_current()      # pour la valeur nette (snapshot courant)
        total_rev    = sum(r["amount"] for r in rev_data)
        total_sav    = sum(r["amount"] for r in sav_data)
        total_pat    = sum(r["value"]  for r in pat_current)
        total_dettes = db.get_total_liabilities()
        valeur_nette = total_pat - total_dettes

        # ── KPI holder (row=1) ───────────────────────────────
        kpi_holder = ctk.CTkFrame(scroll, fg_color="transparent")
        kpi_holder.grid(row=1, column=0, columnspan=4, sticky="ew")
        kpi_holder.grid_columnconfigure((0, 1, 2, 3), weight=1)

        def _draw_kpis(exp_total: float):
            for w in kpi_holder.winfo_children():
                w.destroy()
            bilan = total_rev - exp_total
            kpis_data = [
                ("Revenus",  f"{total_rev:,.0f} €",  C["green"], "💶"),
                ("Dépenses", f"{exp_total:,.0f} €",  C["red"],   "💸"),
                ("Épargne",  f"{total_sav:,.0f} €",  C["blue"],  "🏦"),
                ("Bilan",    f"{bilan:+,.0f} €",
                 C["green"] if bilan >= 0 else C["red"], "⚖️"),
            ]
            for col, (t, v, clr, ico) in enumerate(kpis_data):
                kpi_card(kpi_holder, t, v, clr, ico).grid(
                    row=0, column=col, padx=6, pady=6, sticky="ew")

        # ── Bande Valeur nette (row=2) ───────────────────────
        vn_color = C["green"] if valeur_nette >= 0 else C["red"]
        vn_bg    = "#F0FDF4" if valeur_nette >= 0 else "#FEF2F2"
        vn_brd   = "#86EFAC" if valeur_nette >= 0 else "#FCA5A5"
        sign     = "+" if valeur_nette >= 0 else ""

        vn_band = ctk.CTkFrame(scroll, fg_color=vn_bg, corner_radius=10,
                                border_width=1, border_color=vn_brd)
        vn_band.grid(row=2, column=0, columnspan=4, sticky="ew",
                     padx=6, pady=(0, 8))
        vn_band.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(vn_band,
                     text=f"⚖️  Valeur nette",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=vn_color).grid(row=0, column=0, padx=16, pady=10, sticky="w")
        ctk.CTkLabel(vn_band,
                     text=f"{sign}{valeur_nette:,.2f} €",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=vn_color).grid(row=0, column=1, padx=8, pady=10, sticky="w")

        sub_txt = (f"Actifs {total_pat:,.0f} €  −  Dettes {total_dettes:,.0f} €"
                   if total_dettes > 0
                   else f"Patrimoine total : {total_pat:,.0f} €  ·  Aucune dette enregistrée")
        ctk.CTkLabel(vn_band, text=sub_txt,
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).grid(
            row=0, column=2, padx=16, pady=10, sticky="e")

        # ── Barre de filtres (row=3) ──────────────────────────
        cats   = [FILTER_ALL_CATS] + [c["name"] for c in db.get_categories()]
        payees = [FILTER_ALL_PAYEES]  + db.get_payees(y, m)

        fb = make_card(scroll, corner_radius=10)
        fb.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 4))
        fi = ctk.CTkFrame(fb, fg_color="transparent")
        fi.pack(anchor="w", padx=16, pady=8)

        ctk.CTkLabel(fi, text="🔍  Filtrer :",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["text"]).pack(side="left", padx=(0, 12))

        cat_var   = ctk.StringVar(value=app.dash_cat_filter)
        payee_var = ctk.StringVar(value=app.dash_payee_filter)

        def _apply_dropdown(*_):
            app.dash_cat_filter   = cat_var.get()
            app.dash_payee_filter = payee_var.get()
            _soft_refresh()

        filter_dropdown(fi, "Catégorie :", cats,   cat_var,   _apply_dropdown)
        filter_dropdown(fi, "Enseigne :",  payees, payee_var, _apply_dropdown)

        # Effacer button (togglable)
        effacer_holder = {"btn": None}

        def _sync_effacer():
            is_active = (
                app.dash_cat_filter   not in (FILTER_ALL_CATS,) or
                app.dash_payee_filter not in (FILTER_ALL_PAYEES,)
            )
            if is_active and effacer_holder["btn"] is None:
                def _clear():
                    app.dash_cat_filter   = FILTER_ALL_CATS
                    app.dash_payee_filter = FILTER_ALL_PAYEES
                    cat_var.set(FILTER_ALL_CATS)
                    payee_var.set(FILTER_ALL_PAYEES)
                    _soft_refresh()
                btn = ctk.CTkButton(fi, text="✕ Effacer", height=28, width=90,
                                    fg_color="#FEE2E2", text_color=C["red"],
                                    hover_color="#FECACA", command=_clear)
                btn.pack(side="left")
                effacer_holder["btn"] = btn
            elif not is_active and effacer_holder["btn"] is not None:
                effacer_holder["btn"].destroy()
                effacer_holder["btn"] = None

        # ── Zone graphiques (row=4) ───────────────────────────
        charts = ctk.CTkFrame(scroll, fg_color="transparent")
        charts.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        charts.grid_columnconfigure((0, 1), weight=1)

        pie_card = _chart_card(charts, "Dépenses par catégorie  💡 clic = filtre", 0, 0)
        bar_card = _chart_card(charts, "Top enseignes  💡 clic = filtre", 0, 1)

        pie_zone = [None]
        bar_zone = [None]

        def _redraw_charts():
            if pie_zone[0]:
                pie_zone[0].destroy()
            if bar_zone[0]:
                bar_zone[0].destroy()

            cf = app.dash_cat_filter
            pf = app.dash_payee_filter

            pz = ctk.CTkFrame(pie_card, fg_color="transparent")
            pz.pack(fill="both", expand=True)
            pie_zone[0] = pz

            bz = ctk.CTkFrame(bar_card, fg_color="transparent")
            bz.pack(fill="both", expand=True)
            bar_zone[0] = bz

            cat_data = db.get_expenses_by_category(
                y, m, pf if pf not in (FILTER_ALL_PAYEES,) else None)
            payee_data = db.get_expenses_by_payee(
                y, m, cf if cf not in (FILTER_ALL_CATS,) else None)

            _render_pie(pz, cat_data, key="name", root=app,
                        filter_attr="dash_cat_filter",
                        on_change=_soft_refresh,
                        active_filter=cf, reset_value=FILTER_ALL_CATS)
            _render_hbar(bz, payee_data, key="payee", root=app,
                         filter_attr="dash_payee_filter",
                         on_change=_soft_refresh,
                         active_filter=pf, reset_value=FILTER_ALL_PAYEES)

        # ── Soft refresh (met à jour KPIs + graphiques seulement) ──
        def _soft_refresh():
            cat_var.set(app.dash_cat_filter)
            payee_var.set(app.dash_payee_filter)
            _sync_effacer()
            new_exp = db.get_expenses(y, m, app.dash_cat_filter, app.dash_payee_filter)
            _draw_kpis(sum(r["amount"] for r in new_exp))
            _redraw_charts()

        # Enregistrer pour usage externe (ex: bouton Agrandir)
        app._dash_soft_refresh = _soft_refresh

        # Premier rendu
        exp_data = db.get_expenses(y, m, app.dash_cat_filter, app.dash_payee_filter)
        _draw_kpis(sum(r["amount"] for r in exp_data))
        _sync_effacer()
        _redraw_charts()

        # ── Épargne par compte (row=5) ────────────────────────
        if sav_data:
            by_account: dict[str, float] = {}
            for r in sav_data:
                acc = r["account"] or "Non précisé"
                by_account[acc] = by_account.get(acc, 0.0) + r["amount"]

            sc = make_card(scroll)
            sc.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(12, 0))

            sh = ctk.CTkFrame(sc, fg_color="transparent")
            sh.pack(fill="x", padx=16, pady=(14, 6))
            ctk.CTkLabel(sh, text="🏦  Épargne par compte",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=C["text"]).pack(side="left")
            ctk.CTkLabel(sh, text=f"Total : {total_sav:,.0f} €",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=C["blue"]).pack(side="right")

            sg = ctk.CTkFrame(sc, fg_color="transparent")
            sg.pack(fill="x", padx=16, pady=(0, 14))
            for i, (acc, amt) in enumerate(sorted(by_account.items(),
                                                   key=lambda kv: -kv[1])):
                sg.grid_columnconfigure(i, weight=1)
                af = ctk.CTkFrame(sg, fg_color=C["light"], corner_radius=10)
                af.grid(row=0, column=i, padx=5, pady=4, sticky="ew")
                ctk.CTkLabel(af, text=acc,
                             font=ctk.CTkFont(size=10), text_color=C["muted"]).pack(
                    anchor="w", padx=12, pady=(8, 1))
                ctk.CTkLabel(af, text=f"{amt:,.0f} €",
                             font=ctk.CTkFont(size=15, weight="bold"),
                             text_color=C["blue"]).pack(anchor="w", padx=12, pady=(0, 2))
                pct = amt / total_sav * 100 if total_sav else 0
                ctk.CTkLabel(af, text=f"{pct:.0f} %",
                             font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(
                    anchor="w", padx=12, pady=(0, 8))

        # ── Mini patrimoine (row=6) ───────────────────────────
        if pat_data:
            pc = make_card(scroll)
            pc.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(12, 0))
            ph = ctk.CTkFrame(pc, fg_color="transparent")
            ph.pack(fill="x", padx=16, pady=(14, 6))
            ctk.CTkLabel(ph, text="📊  Patrimoine ce mois",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=C["text"]).pack(side="left")
            ctk.CTkLabel(ph, text=f"Total : {total_pat:,.0f} €",
                         font=ctk.CTkFont(size=16, weight="bold"),
                         text_color=C["primary"]).pack(side="right")
            pin = ctk.CTkFrame(pc, fg_color="transparent")
            pin.pack(fill="x", padx=16, pady=(0, 14))
            for i, bt in enumerate(db.get_assets_by_type(y, m)):
                pin.grid_columnconfigure(i, weight=1)
                tf = ctk.CTkFrame(pin, fg_color=C["light"], corner_radius=10)
                tf.grid(row=0, column=i, padx=5, pady=4, sticky="ew")
                ctk.CTkLabel(tf,
                             text=ASSET_LABEL.get(bt["asset_type"], bt["asset_type"]),
                             font=ctk.CTkFont(size=10),
                             text_color=C["muted"]).pack(anchor="w", padx=12, pady=(8, 1))
                pv = bt["total_value"] if "total_value" in bt.keys() else bt["total"]
                cb = bt["total_basis"] if "total_basis" in bt.keys() else 0
                pnl = pv - cb if cb else 0
                clr = C["green"] if pnl >= 0 else C["red"]
                ctk.CTkLabel(tf, text=f"{pv:,.0f} €",
                             font=ctk.CTkFont(size=15, weight="bold"),
                             text_color=C["text"]).pack(anchor="w", padx=12, pady=(0, 2))
                if cb:
                    ctk.CTkLabel(tf, text=f"{pnl:+,.0f} €",
                                 font=ctk.CTkFont(size=11),
                                 text_color=clr).pack(anchor="w", padx=12, pady=(0, 8))
                else:
                    ctk.CTkFrame(tf, height=8, fg_color="transparent").pack()


# ── Helpers layout ────────────────────────────────────────
def _chart_card(parent, title: str, row: int, col: int) -> ctk.CTkFrame:
    card = make_card(parent)
    card.grid(row=row, column=col,
              padx=(0, 8) if col == 0 else (8, 0),
              sticky="nsew")
    ctk.CTkLabel(card, text=title,
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(14, 4))
    return card


# ── Hover helpers ─────────────────────────────────────────
def _mk_annot(ax):
    ann = ax.annotate(
        "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.55", fc="white",
                  ec="#94A3B8", alpha=0.97, lw=1.2),
        fontsize=10.5, color="#1E293B",
        arrowprops=dict(arrowstyle="->", color="#94A3B8", lw=0.8),
    )
    ann.set_visible(False)
    return ann


def _add_pie_hover(fig, ax, wedges, labels, vals):
    ann   = _mk_annot(ax)
    total = sum(vals)

    def on_move(ev):
        if ev.inaxes != ax:
            if ann.get_visible():
                ann.set_visible(False); fig.canvas.draw_idle()
            return
        hit = False
        for i, w in enumerate(wedges):
            if w.contains(ev)[0]:
                pct = vals[i] / total * 100 if total else 0
                ann.xy = (ev.xdata, ev.ydata)
                ann.set_text(f"{labels[i]}\n{vals[i]:,.0f} €  ({pct:.1f}%)")
                ann.set_visible(True); hit = True; break
        if not hit and ann.get_visible():
            ann.set_visible(False)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)


def _add_hbar_hover(fig, ax, bars, labels, vals):
    ann = _mk_annot(ax)

    def on_move(ev):
        if ev.inaxes != ax:
            if ann.get_visible():
                ann.set_visible(False); fig.canvas.draw_idle()
            return
        hit = False
        for i, b in enumerate(bars):
            if b.contains(ev)[0]:
                ann.xy = (ev.xdata, ev.ydata)
                ann.set_text(f"{labels[i]}\n{vals[i]:,.0f} €")
                ann.set_visible(True); hit = True; break
        if not hit and ann.get_visible():
            ann.set_visible(False)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)


# ── Expand window ─────────────────────────────────────────
def _open_expand(root, title: str, render_fn):
    win = ctk.CTkToplevel(root)
    win.title(title); win.geometry("920x620")
    win.grab_set(); win.configure(fg_color="white")
    ctk.CTkLabel(win, text=title,
                 font=ctk.CTkFont(size=16, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))
    render_fn(win, figsize=(11, 7.5))
    ctk.CTkButton(win, text="Fermer", width=100,
                  command=win.destroy).pack(pady=12)


# ── CTk legend helper ─────────────────────────────────────
def _ctk_legend(parent, labels, vals, colors, total,
                toggle_fn=None, active_filter=None):
    leg = ctk.CTkScrollableFrame(parent, fg_color=C["card"], height=120)
    leg.pack(fill="x", padx=12, pady=(0, 6))
    leg.grid_columnconfigure((0, 1), weight=1)
    for i, (lbl, val) in enumerate(zip(labels, vals)):
        is_active = (active_filter and lbl == active_filter and
                     active_filter not in (FILTER_ALL_CATS, FILTER_ALL_PAYEES, None, ""))
        rf = ctk.CTkFrame(leg,
                          fg_color="#DBEAFE" if is_active else "transparent",
                          corner_radius=4,
                          cursor="hand2" if toggle_fn else "")
        rf.grid(row=i // 2, column=i % 2, sticky="ew", padx=4, pady=1)
        dot = ctk.CTkFrame(rf, width=10, height=10,
                           fg_color=colors[i], corner_radius=5)
        dot.pack(side="left", padx=(2, 5)); dot.pack_propagate(False)
        pct = val / total * 100 if total else 0
        ctk.CTkLabel(rf,
                     text=f"{lbl}  {val:,.0f} €  ({pct:.0f}%)",
                     font=ctk.CTkFont(size=10,
                                      weight="bold" if is_active else "normal"),
                     text_color=C["primary"] if is_active else C["text"],
                     anchor="w").pack(side="left")
        if toggle_fn:
            def _cb(label=lbl): return lambda e: toggle_fn(label)
            rf.bind("<Button-1>", _cb(lbl))


# ── Renderers graphiques ──────────────────────────────────
def _render_pie(card, data, key: str, root=None,
                filter_attr=None, on_change=None,
                active_filter=None, reset_value=FILTER_ALL_CATS):
    if not data:
        ctk.CTkLabel(card, text="Aucune donnée",
                     text_color=C["muted"]).pack(expand=True, pady=55)
        return

    labels = [r[key] for r in data]
    vals   = [r["total"] for r in data]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
    total  = sum(vals)
    is_active = (active_filter and
                 active_filter not in (reset_value, None, "") and
                 active_filter in labels)

    def _toggle(label: str):
        if root is None or filter_attr is None: return
        current = getattr(root, filter_attr, reset_value)
        setattr(root, filter_attr,
                reset_value if current == label else label)
        if on_change:
            root.after(0, on_change)

    def _draw(parent, figsize=(5, 3.2)):
        explode = None
        if is_active:
            idx = labels.index(active_filter)
            explode = [0.06 if i == idx else 0.0 for i in range(len(labels))]

        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(C["card"])
        wedges, _ = ax.pie(vals, colors=colors, startangle=90,
                           wedgeprops=dict(width=0.6), explode=explode)
        plt.tight_layout(pad=0.5)
        cv = FigureCanvasTkAgg(fig, parent)
        cv.draw_idle()
        cv.get_tk_widget().pack(fill="x", padx=10, pady=(0, 4))
        _add_pie_hover(fig, ax, wedges, labels, vals)

        if filter_attr and on_change:
            def on_click(ev):
                if ev.inaxes != ax: return
                for i, w in enumerate(wedges):
                    if w.contains(ev)[0]:
                        _toggle(labels[i]); break
            fig.canvas.mpl_connect("button_press_event", on_click)
        plt.close(fig)

        _ctk_legend(parent, labels, vals, colors, total,
                    toggle_fn=_toggle if on_change else None,
                    active_filter=active_filter)

    _draw(card)

    if root is not None:
        ctk.CTkButton(card, text="⛶  Agrandir", height=26, width=110,
                      fg_color=C["light"], text_color=C["muted"],
                      hover_color="#E2E8F0", font=ctk.CTkFont(size=11),
                      command=lambda: _open_expand(
                          root, "Dépenses par catégorie",
                          lambda p, fs: _draw(p, figsize=fs))
                      ).pack(anchor="e", padx=12, pady=(0, 10))


def _render_hbar(card, data, key: str, root=None,
                 filter_attr=None, on_change=None,
                 active_filter=None, reset_value=FILTER_ALL_PAYEES):
    if not data:
        ctk.CTkLabel(card, text="Aucune enseigne enregistrée",
                     text_color=C["muted"]).pack(expand=True, pady=55)
        return

    names   = [r[key] for r in data]
    amounts = [r["total"] for r in data]
    is_active = (active_filter and
                 active_filter not in (reset_value, None, "") and
                 active_filter in names)

    def _toggle(name: str):
        if root is None or filter_attr is None: return
        current = getattr(root, filter_attr, reset_value)
        setattr(root, filter_attr,
                reset_value if current == name else name)
        if on_change:
            root.after(0, on_change)

    def _draw(parent, figsize=(5, 3.8)):
        bar_colors = [
            "#F59E0B" if (is_active and n == active_filter) else PALETTE[0]
            for n in names
        ]
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor("#FAFCFF")
        yp   = range(len(names))
        bars = ax.barh(list(yp), amounts, color=bar_colors, alpha=0.85)
        ax.set_yticks(list(yp))
        ax.set_yticklabels(names, fontsize=9 if figsize[0] < 8 else 11)
        ax.invert_yaxis()
        ax.set_xlabel("€", fontsize=9)
        mx = max(amounts) if amounts else 1
        for bar, val in zip(bars, amounts):
            ax.text(bar.get_width() + mx * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:,.0f} €", va="center",
                    fontsize=8 if figsize[0] < 8 else 10)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=1.5)
        cv = FigureCanvasTkAgg(fig, parent)
        cv.draw_idle()
        cv.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0, 14))
        _add_hbar_hover(fig, ax, bars, names, amounts)

        if filter_attr and on_change:
            def on_click(ev):
                if ev.inaxes != ax: return
                for i, b in enumerate(bars):
                    if b.contains(ev)[0]:
                        _toggle(names[i]); break
            fig.canvas.mpl_connect("button_press_event", on_click)
        plt.close(fig)

    _draw(card)

    if root is not None:
        ctk.CTkButton(card, text="⛶  Agrandir", height=26, width=110,
                      fg_color=C["light"], text_color=C["muted"],
                      hover_color="#E2E8F0", font=ctk.CTkFont(size=11),
                      command=lambda: _open_expand(
                          root, "Top enseignes",
                          lambda p, fs: _draw(p, figsize=fs))
                      ).pack(anchor="e", padx=12, pady=(0, 10))
