"""
ui/pages/analyses.py — Analyses graphiques avec hover interactif et filtres par clic
Soft refresh : les filtres ne reconstruisent plus toute la page.
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
from config import C, MONTHS_FR, PALETTE, FILTER_ALL_CATS, FILTER_ALL_PAYEES
from ui.components import make_card, filter_dropdown, month_selector


class AnalysesPage:
    def render(self, container: ctk.CTkFrame, app):
        db   = app.db
        y, m = app.sel_year, app.sel_month

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(2, weight=1)

        # ── Titre ────────────────────────────────────────────
        ctk.CTkLabel(container, text="📊  Analyses détaillées",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 6)
        )

        # ── Sélecteur mois + filtres ─────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 6))

        def on_month_change(new_m, new_y):
            app.sel_month = new_m
            app.sel_year  = new_y
            app._go("analyses")

        month_selector(top, MONTHS_FR, y, m, on_month_change).pack(side="left")

        cats   = [FILTER_ALL_CATS] + [c["name"] for c in db.get_categories()]
        payees = [FILTER_ALL_PAYEES]  + db.get_payees(y, m)
        cat_var   = ctk.StringVar(value=app.ana_cat_filter)
        payee_var = ctk.StringVar(value=app.ana_payee_filter)

        fi = ctk.CTkFrame(top, fg_color="transparent")
        fi.pack(side="left", padx=20)

        effacer_holder = {"btn": None}

        def _sync_effacer():
            is_active = (app.ana_cat_filter not in (FILTER_ALL_CATS,) or
                         app.ana_payee_filter not in (FILTER_ALL_PAYEES,))
            if is_active and effacer_holder["btn"] is None:
                def clear_filters():
                    app.ana_cat_filter   = FILTER_ALL_CATS
                    app.ana_payee_filter = FILTER_ALL_PAYEES
                    cat_var.set(FILTER_ALL_CATS)
                    payee_var.set(FILTER_ALL_PAYEES)
                    _soft_refresh()
                btn = ctk.CTkButton(fi, text="✕ Effacer", height=28, width=90,
                                    fg_color="#FEE2E2", text_color=C["red"],
                                    hover_color="#FECACA",
                                    command=clear_filters)
                btn.pack(side="left")
                effacer_holder["btn"] = btn
            elif not is_active and effacer_holder["btn"] is not None:
                effacer_holder["btn"].destroy()
                effacer_holder["btn"] = None

        def _apply_dropdown(*_):
            app.ana_cat_filter   = cat_var.get()
            app.ana_payee_filter = payee_var.get()
            _soft_refresh()

        filter_dropdown(fi, "Catégorie :", cats,   cat_var,   _apply_dropdown)
        filter_dropdown(fi, "Enseigne :",  payees, payee_var, _apply_dropdown)

        # ── Fonctions toggle partagées ────────────────────────
        def _toggle_cat(label: str):
            current = app.ana_cat_filter
            app.ana_cat_filter = FILTER_ALL_CATS if current == label else label
            cat_var.set(app.ana_cat_filter)
            app.after(0, _soft_refresh)

        def _toggle_payee(label: str):
            current = app.ana_payee_filter
            app.ana_payee_filter = FILTER_ALL_PAYEES if current == label else label
            payee_var.set(app.ana_payee_filter)
            app.after(0, _soft_refresh)

        # ── Scroll ───────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(container, fg_color=C["bg"])
        scroll.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 16))
        scroll.grid_columnconfigure((0, 1), weight=1)

        # ── Section 1 : Évolution (statique, pas filtre-dépendante) ──
        _section_evolution(scroll, db, app)

        # ── Holders pour sections filtre-dépendantes ──────────
        stacked_holder = ctk.CTkFrame(scroll, fg_color="transparent")
        stacked_holder.grid(row=1, column=0, columnspan=2, sticky="ew")
        stacked_holder.grid_columnconfigure((0, 1), weight=1)

        detail_holder = ctk.CTkFrame(scroll, fg_color="transparent")
        detail_holder.grid(row=2, column=0, columnspan=2, sticky="ew")
        detail_holder.grid_columnconfigure((0, 1), weight=1)

        catevo_holder = ctk.CTkFrame(scroll, fg_color="transparent")
        catevo_holder.grid(row=3, column=0, columnspan=2, sticky="ew")
        catevo_holder.grid_columnconfigure((0, 1), weight=1)

        def _draw_stacked():
            for w in stacked_holder.winfo_children():
                w.destroy()
            _section_stacked_by_category(stacked_holder, db, app, _toggle_cat)

        def _draw_detail():
            for w in detail_holder.winfo_children():
                w.destroy()
            _section_month_detail(detail_holder, db, y, m, app, _toggle_cat, _toggle_payee)

        def _draw_catevo():
            for w in catevo_holder.winfo_children():
                w.destroy()
            _section_cat_evolution(catevo_holder, db, app)

        def _soft_refresh():
            _sync_effacer()
            _draw_stacked()
            _draw_detail()
            _draw_catevo()

        app._ana_soft_refresh = _soft_refresh

        # Initial draw
        _sync_effacer()
        _draw_stacked()
        _draw_detail()
        _draw_catevo()


# ── Hover helpers ─────────────────────────────────────────
def _annot(ax):
    return ax.annotate(
        "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.55", fc="white",
                  ec="#94A3B8", alpha=0.97, lw=1.2),
        fontsize=10.5, color="#1E293B",
        arrowprops=dict(arrowstyle="->", color="#94A3B8", lw=0.8),
    )


def _pie_hover(fig, ax, wedges, labels, vals):
    ann = _annot(ax)
    ann.set_visible(False)
    total = sum(vals)

    def on_move(ev):
        if ev.inaxes != ax:
            if ann.get_visible():
                ann.set_visible(False)
                fig.canvas.draw_idle()
            return
        hit = False
        for i, w in enumerate(wedges):
            if w.contains(ev)[0]:
                pct = vals[i] / total * 100 if total else 0
                ann.xy = (ev.xdata, ev.ydata)
                ann.set_text(f"{labels[i]}\n{vals[i]:,.0f} €  ({pct:.1f}%)")
                ann.set_visible(True)
                hit = True
                break
        if not hit and ann.get_visible():
            ann.set_visible(False)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)


def _bar_hover(fig, ax, bars, labels, vals, fmt="{label}\n{val:,.0f} €"):
    ann = _annot(ax)
    ann.set_visible(False)

    def on_move(ev):
        if ev.inaxes != ax:
            if ann.get_visible():
                ann.set_visible(False)
                fig.canvas.draw_idle()
            return
        hit = False
        for i, b in enumerate(bars):
            if b.contains(ev)[0]:
                ann.xy = (ev.xdata, ev.ydata)
                ann.set_text(fmt.format(label=labels[i], val=vals[i]))
                ann.set_visible(True)
                hit = True
                break
        if not hit and ann.get_visible():
            ann.set_visible(False)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)


def _line_hover(fig, ax, lines_data, x_labels):
    """lines_data = [(line_obj, cat_name, y_values), ...]"""
    ann = _annot(ax)
    ann.set_visible(False)

    def on_move(ev):
        if ev.inaxes != ax or ev.xdata is None:
            if ann.get_visible():
                ann.set_visible(False)
                fig.canvas.draw_idle()
            return
        best_dist = 0.35
        best_text = None
        best_xy   = None
        for line_obj, cname, y_vals in lines_data:
            xdata = line_obj.get_xdata()
            ydata = line_obj.get_ydata()
            for xi, yi in zip(xdata, ydata):
                dist = abs(ev.xdata - xi)
                if dist < best_dist:
                    best_dist = dist
                    xi_idx = int(round(xi))
                    mlbl   = x_labels[xi_idx] if 0 <= xi_idx < len(x_labels) else ""
                    best_text = f"{cname}\n{mlbl}\n{yi:,.0f} €"
                    best_xy   = (xi, yi)
        if best_text and best_xy:
            ann.xy = best_xy
            ann.set_text(best_text)
            ann.set_visible(True)
        else:
            ann.set_visible(False)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)


def _expand_btn(card, title, root, render_fn):
    """Bouton ⛶ Agrandir sous un graphique."""
    def expand():
        win = ctk.CTkToplevel(root)
        win.title(title)
        win.geometry("960x640")
        win.grab_set()
        win.configure(fg_color="white")
        ctk.CTkLabel(win, text=title,
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(14, 4))
        render_fn(win, figsize=(12, 8))
        ctk.CTkButton(win, text="Fermer", width=100,
                      command=win.destroy).pack(pady=10)

    ctk.CTkButton(card, text="⛶  Agrandir", height=26, width=110,
                  fg_color=C["light"], text_color=C["muted"],
                  hover_color="#E2E8F0", font=ctk.CTkFont(size=11),
                  command=expand).pack(anchor="e", padx=12, pady=(0, 10))


# ── Légende CTk cliquable helper ──────────────────────────
def _ctk_legend(parent, items, colors, toggle_fn=None,
                active_filter=None, ncols=2, height=110):
    """
    Grille de légende avec items cliquables si toggle_fn fourni.
    items = [(label, value_str), ...]
    toggle_fn(label) appelé au clic.
    """
    leg = ctk.CTkScrollableFrame(parent, fg_color=C["card"], height=height)
    leg.pack(fill="x", padx=12, pady=(0, 6))
    leg.grid_columnconfigure(tuple(range(ncols)), weight=1)

    for i, (lbl, val_str) in enumerate(items):
        is_active = (active_filter and lbl == active_filter and
                     active_filter not in (FILTER_ALL_CATS, FILTER_ALL_PAYEES, "", None))
        rf = ctk.CTkFrame(
            leg,
            fg_color="#DBEAFE" if is_active else "transparent",
            corner_radius=4,
            cursor="hand2" if toggle_fn else "",
        )
        rf.grid(row=i // ncols, column=i % ncols, sticky="ew", padx=4, pady=1)
        dot = ctk.CTkFrame(rf, width=10, height=10,
                           fg_color=colors[i % len(colors)], corner_radius=3)
        dot.pack(side="left", padx=(2, 5))
        dot.pack_propagate(False)
        ctk.CTkLabel(
            rf,
            text=f"{lbl}  {val_str}",
            font=ctk.CTkFont(size=10, weight="bold" if is_active else "normal"),
            text_color=C["primary"] if is_active else C["text"],
            anchor="w",
        ).pack(side="left")
        if toggle_fn:
            def _make_cb(label=lbl):
                return lambda e: toggle_fn(label)
            rf.bind("<Button-1>", _make_cb(lbl))
    return leg


# ── Section 1 : Évolution 6 mois ──────────────────────────
def _section_evolution(parent, db, app):
    card = make_card(parent)
    card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
    ctk.CTkLabel(card, text="Évolution revenus / dépenses / épargne (6 mois)",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(14, 4))

    summaries = list(reversed(db.monthly_summary(6)))
    if not summaries:
        ctk.CTkLabel(card, text="Pas encore de données",
                     text_color=C["muted"]).pack(pady=40)
        return

    def _draw(parent, figsize=(10, 3.6)):
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor("#FAFCFF")
        x  = range(len(summaries))
        xl = [f"{MONTHS_FR[r['month']-1][:3]}\n{r['year']}" for r in summaries]
        w  = 0.28
        rev_vals = [r["rev"] for r in summaries]
        exp_vals = [r["exp"] for r in summaries]
        sav_vals = [r["sav"] for r in summaries]
        b_rev = ax.bar([i - w for i in x], rev_vals, w, color="#22C55E", alpha=0.85, label="Revenus")
        b_exp = ax.bar([i     for i in x], exp_vals, w, color="#EF4444", alpha=0.85, label="Dépenses")
        b_sav = ax.bar([i + w for i in x], sav_vals, w, color="#3B82F6", alpha=0.85, label="Épargne")
        ax.set_xticks(list(x))
        ax.set_xticklabels(xl, fontsize=9)
        ax.legend(fontsize=10, frameon=False)
        ax.set_ylabel("€", fontsize=9)
        ax.yaxis.set_tick_params(labelsize=8)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=1.5)
        cv = FigureCanvasTkAgg(fig, parent)
        cv.draw_idle()
        cv.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=(0, 14))
        all_bars  = list(b_rev) + list(b_exp) + list(b_sav)
        bar_lbls  = (
            [f"Revenus — {xl[i]}" for i in range(len(summaries))] +
            [f"Dépenses — {xl[i]}" for i in range(len(summaries))] +
            [f"Épargne — {xl[i]}" for i in range(len(summaries))]
        )
        bar_vals  = rev_vals + exp_vals + sav_vals
        _bar_hover(fig, ax, all_bars, bar_lbls, bar_vals)
        plt.close(fig)

    _draw(card)
    _expand_btn(card, "Évolution 6 mois", app, _draw)


# ── Section 2 : Détail du mois sélectionné ────────────────
def _section_month_detail(parent, db, y, m, app, toggle_cat, toggle_payee):
    cat_f   = app.ana_cat_filter
    payee_f = app.ana_payee_filter

    cat_data   = db.get_expenses_by_category(
        y, m, payee_f if payee_f not in (FILTER_ALL_PAYEES,) else None
    )
    payee_data = db.get_expenses_by_payee(
        y, m, cat_f if cat_f not in (FILTER_ALL_CATS,) else None
    )

    # ── Camembert catégories ──
    pie_c = make_card(parent)
    pie_c.grid(row=0, column=0, padx=(0, 8), sticky="nsew", pady=(0, 12))
    ctk.CTkLabel(pie_c, text=f"Catégories — {MONTHS_FR[m-1]} {y}  💡 clic = filtre",
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(14, 4))

    if cat_data:
        labels_p = [r["name"] for r in cat_data]
        vals_p   = [r["total"] for r in cat_data]
        colors_p = [PALETTE[i % len(PALETTE)] for i in range(len(labels_p))]
        is_cat_active = (cat_f and cat_f not in (FILTER_ALL_CATS, "", None)
                         and cat_f in labels_p)

        def _draw_pie(parent, figsize=(5, 3.2)):
            explode = None
            if is_cat_active:
                idx = labels_p.index(cat_f)
                explode = [0.06 if i == idx else 0.0 for i in range(len(labels_p))]

            fig, ax = plt.subplots(figsize=figsize)
            fig.patch.set_facecolor(C["card"])
            wedges, _ = ax.pie(vals_p, colors=colors_p,
                               startangle=90, wedgeprops=dict(width=0.6),
                               explode=explode)
            plt.tight_layout(pad=0.5)
            cv = FigureCanvasTkAgg(fig, parent)
            cv.draw_idle()
            cv.get_tk_widget().pack(fill="x", padx=10, pady=(0, 4))
            _pie_hover(fig, ax, wedges, labels_p, vals_p)

            def on_click(event):
                if event.inaxes != ax:
                    return
                for i, w in enumerate(wedges):
                    if w.contains(event)[0]:
                        toggle_cat(labels_p[i])
                        break
            fig.canvas.mpl_connect("button_press_event", on_click)
            plt.close(fig)

            total_p = sum(vals_p)
            items = [(lbl, f"{val:,.0f} €  ({val/total_p*100:.0f}%)" if total_p else f"{val:,.0f} €")
                     for lbl, val in zip(labels_p, vals_p)]
            _ctk_legend(parent, items, colors_p,
                        toggle_fn=toggle_cat, active_filter=cat_f, height=110)

        _draw_pie(pie_c)
        _expand_btn(pie_c, f"Catégories — {MONTHS_FR[m-1]} {y}", app, _draw_pie)
    else:
        ctk.CTkLabel(pie_c, text="Aucune dépense ce mois",
                     text_color=C["muted"]).pack(expand=True, pady=55)

    # ── Top enseignes ──
    bar_c = make_card(parent)
    bar_c.grid(row=0, column=1, padx=(8, 0), sticky="nsew", pady=(0, 12))
    ctk.CTkLabel(bar_c, text=f"Top enseignes — {MONTHS_FR[m-1]} {y}  💡 clic = filtre",
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(14, 4))

    if payee_data:
        pnames   = [r["payee"] for r in payee_data]
        pamounts = [r["total"] for r in payee_data]
        is_payee_active = (payee_f and payee_f not in (FILTER_ALL_PAYEES, "", None)
                           and payee_f in pnames)

        def _draw_hbar(parent, figsize=(5, 4.2)):
            bar_colors = [
                "#F59E0B" if (is_payee_active and n == payee_f) else PALETTE[0]
                for n in pnames
            ]
            fig2, ax2 = plt.subplots(figsize=figsize)
            fig2.patch.set_facecolor("white")
            ax2.set_facecolor("#FAFCFF")
            yp   = range(len(pnames))
            bars = ax2.barh(list(yp), pamounts,
                            color=bar_colors, alpha=0.85)
            ax2.set_yticks(list(yp))
            ax2.set_yticklabels(pnames, fontsize=8.5 if figsize[0] < 8 else 11)
            ax2.invert_yaxis()
            ax2.set_xlabel("€", fontsize=9)
            for sp in ["top", "right"]:
                ax2.spines[sp].set_visible(False)
            plt.tight_layout(pad=1.5)
            cv2 = FigureCanvasTkAgg(fig2, parent)
            cv2.draw_idle()
            cv2.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0, 14))
            _bar_hover(fig2, ax2, bars, pnames, pamounts)

            def on_click(event):
                if event.inaxes != ax2:
                    return
                for i, b in enumerate(bars):
                    if b.contains(event)[0]:
                        toggle_payee(pnames[i])
                        break
            fig2.canvas.mpl_connect("button_press_event", on_click)
            plt.close(fig2)

        _draw_hbar(bar_c)
        _expand_btn(bar_c, f"Top enseignes — {MONTHS_FR[m-1]} {y}", app, _draw_hbar)
    else:
        ctk.CTkLabel(bar_c, text="Aucune enseigne ce mois",
                     text_color=C["muted"]).pack(expand=True, pady=55)


# ── Section 3 : Évolution par catégorie ───────────────────
def _section_cat_evolution(parent, db, app):
    cat_filter = app.ana_cat_filter
    summaries  = list(reversed(db.monthly_summary(6)))
    if not summaries:
        return

    card = make_card(parent)
    card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
    ctk.CTkLabel(card, text="Évolution des dépenses par catégorie (6 mois)",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(14, 4))

    cat_series: dict[str, list] = {}
    x_labels = []
    for r in summaries:
        y2, m2 = r["year"], r["month"]
        x_labels.append(f"{MONTHS_FR[m2-1][:3]}\n{y2}")
        cats_m = db.get_expenses_by_category(y2, m2)
        for c in cats_m:
            cname = c["name"]
            if cat_filter not in (FILTER_ALL_CATS,) and cname != cat_filter:
                continue
            cat_series.setdefault(cname, [0] * len(summaries))

    if not cat_series:
        ctk.CTkLabel(card, text="Aucune donnée de catégorie",
                     text_color=C["muted"]).pack(pady=40)
        return

    for i, r in enumerate(summaries):
        cats_m = db.get_expenses_by_category(r["year"], r["month"])
        totals = {c["name"]: c["total"] for c in cats_m}
        for cname in cat_series:
            cat_series[cname][i] = totals.get(cname, 0)

    sorted_cats = sorted(cat_series.items(), key=lambda kv: -sum(kv[1]))

    def _draw_lines(parent, figsize=(10, 3.8)):
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor("#FAFCFF")
        x = range(len(summaries))
        lines_data = []
        for i, (cname, vals) in enumerate(sorted_cats):
            line, = ax.plot(list(x), vals, marker="o", ms=5, lw=2,
                            color=PALETTE[i % len(PALETTE)], label=cname)
            lines_data.append((line, cname, vals))
        ax.set_xticks(list(x))
        ax.set_xticklabels(x_labels, fontsize=9)
        ax.set_ylabel("€", fontsize=9)
        ax.yaxis.set_tick_params(labelsize=8)
        ax.legend(fontsize=8, frameon=False, ncol=4,
                  loc="upper right", bbox_to_anchor=(1, 1.15))
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=1.5)
        cv = FigureCanvasTkAgg(fig, parent)
        cv.draw_idle()
        cv.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=(0, 14))
        _line_hover(fig, ax, lines_data, x_labels)
        plt.close(fig)

    _draw_lines(card)
    _expand_btn(card, "Évolution par catégorie", app, _draw_lines)


# ── Section : Dépenses empilées par catégorie ─────────────
def _section_stacked_by_category(parent, db, app, toggle_cat):
    """Barres empilées par catégorie sur N mois avec sélecteur de période."""

    period_var = ctk.IntVar(value=getattr(app, "stacked_period", 6))

    card = make_card(parent)
    card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))

    # ── En-tête avec sélecteur période ───────────────────
    hdr = ctk.CTkFrame(card, fg_color="transparent")
    hdr.pack(fill="x", padx=16, pady=(14, 4))
    hdr.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(hdr, text="Dépenses par catégorie — vue empilée  💡 clic = filtre",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=C["text"]).grid(row=0, column=0, sticky="w")

    period_frame = ctk.CTkFrame(hdr, fg_color="transparent")
    period_frame.grid(row=0, column=2, sticky="e")

    ctk.CTkLabel(period_frame, text="Période :",
                 font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(side="left", padx=(0, 8))

    chart_holder = ctk.CTkFrame(card, fg_color="transparent")
    chart_holder.pack(fill="both", expand=True)

    expand_holder = [None]

    def redraw(n: int):
        app.stacked_period = n
        period_var.set(n)
        for w in chart_holder.winfo_children():
            w.destroy()
        expand_holder[0] = _draw_stacked(chart_holder, db, n, app, toggle_cat)
        _update_expand_btn()

    for label, n in [("3 mois", 3), ("6 mois", 6), ("12 mois", 12)]:
        is_active = (period_var.get() == n)
        ctk.CTkButton(
            period_frame, text=label, width=72, height=28,
            fg_color=C["primary"] if is_active else C["light"],
            text_color="white" if is_active else C["muted"],
            hover_color=C["primary"],
            font=ctk.CTkFont(size=11),
            command=lambda v=n: redraw(v),
        ).pack(side="left", padx=2)

    expand_btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    expand_btn_frame.pack(anchor="e", padx=12, pady=(0, 10))

    def _update_expand_btn():
        for w in expand_btn_frame.winfo_children():
            w.destroy()
        draw_fn = expand_holder[0]
        if draw_fn is None:
            return
        def do_expand():
            win = ctk.CTkToplevel(app)
            win.title("Dépenses empilées par catégorie")
            win.geometry("1100x700")
            win.grab_set()
            win.configure(fg_color="white")
            ctk.CTkLabel(win, text="Dépenses empilées par catégorie",
                         font=ctk.CTkFont(size=16, weight="bold"),
                         text_color=C["text"]).pack(anchor="w", padx=20, pady=(14, 4))
            draw_fn(win, figsize=(14, 8))
            ctk.CTkButton(win, text="Fermer", width=100,
                          command=win.destroy).pack(pady=10)
        ctk.CTkButton(expand_btn_frame, text="⛶  Agrandir", height=26, width=110,
                      fg_color=C["light"], text_color=C["muted"],
                      hover_color="#E2E8F0", font=ctk.CTkFont(size=11),
                      command=do_expand).pack()

    expand_holder[0] = _draw_stacked(chart_holder, db, period_var.get(), app, toggle_cat)
    _update_expand_btn()


def _draw_stacked(parent, db, n_months: int, app, toggle_cat):
    """Dessine le stacked bar chart dans `parent`. Retourne _draw pour Agrandir."""
    summaries = list(reversed(db.monthly_summary(n_months)))
    if not summaries:
        ctk.CTkLabel(parent, text="Pas encore de données",
                     text_color=C["muted"]).pack(pady=40)
        return None

    x_labels = [f"{MONTHS_FR[r['month']-1][:3]} {str(r['year'])[2:]}" for r in summaries]
    all_cats: dict[str, list[float]] = {}

    for i, r in enumerate(summaries):
        cats_m = db.get_expenses_by_category(r["year"], r["month"])
        for c in cats_m:
            all_cats.setdefault(c["name"], [0.0] * len(summaries))
            all_cats[c["name"]][i] = c["total"]

    if not all_cats:
        ctk.CTkLabel(parent, text="Aucune dépense sur cette période",
                     text_color=C["muted"]).pack(pady=40)
        return None

    sorted_cats = sorted(all_cats.items(), key=lambda kv: -sum(kv[1]))
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(sorted_cats))]

    cat_filter = app.ana_cat_filter
    cat_names  = [cn for cn, _ in sorted_cats]

    def _draw(draw_parent, figsize=(10, 4.4)):
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(C["card"])
        ax.set_facecolor("#FAFCFF")

        x = list(range(len(summaries)))
        bottoms = [0.0] * len(summaries)
        bar_groups: list[tuple] = []

        for ci, (cname, vals) in enumerate(sorted_cats):
            alpha = 0.88
            if (cat_filter and cat_filter not in (FILTER_ALL_CATS, "", None)
                    and cname != cat_filter):
                alpha = 0.25
            bars = ax.bar(x, vals, bottom=bottoms, color=colors[ci],
                          alpha=alpha, width=0.65, label=cname)
            bar_groups.append((bars, cname, vals, list(bottoms)))
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        for i, total in enumerate(bottoms):
            if total > 0:
                ax.text(i, total + max(bottoms) * 0.01,
                        f"{total/1000:.1f}k €" if total >= 1000 else f"{total:.0f} €",
                        ha="center", va="bottom", fontsize=8.5, color="#475569",
                        fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(x_labels, fontsize=9)
        ax.set_ylabel("€", fontsize=9)
        ax.yaxis.set_tick_params(labelsize=8)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{v/1000:.0f}k" if v >= 1000 else f"{v:.0f}")
        )
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=1.2)

        cv = FigureCanvasTkAgg(fig, draw_parent)
        cv.draw_idle()
        cv.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0, 4))

        # ── Hover ──
        ann = ax.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.55", fc="white",
                      ec="#94A3B8", alpha=0.97, lw=1.2),
            fontsize=10.5, color="#1E293B",
            arrowprops=dict(arrowstyle="->", color="#94A3B8", lw=0.8),
        )
        ann.set_visible(False)

        def on_move(ev):
            if ev.inaxes != ax:
                if ann.get_visible():
                    ann.set_visible(False)
                    fig.canvas.draw_idle()
                return
            hit = False
            for bars, cname, vals, bots in bar_groups:
                for i, (bar, val, bot) in enumerate(zip(bars, vals, bots)):
                    if bar.contains(ev)[0] and val > 0:
                        pct = val / bottoms[i] * 100 if bottoms[i] else 0
                        ann.xy = (ev.xdata, ev.ydata)
                        ann.set_text(
                            f"{cname}\n{x_labels[i]}\n"
                            f"{val:,.0f} €  ({pct:.0f}%)"
                        )
                        ann.set_visible(True)
                        hit = True
                        break
                if hit:
                    break
            if not hit and ann.get_visible():
                ann.set_visible(False)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect("motion_notify_event", on_move)

        # ── Click filtre ──
        def on_click(ev):
            if ev.inaxes != ax:
                return
            for bars, cname, vals, bots in bar_groups:
                for bar, val in zip(bars, vals):
                    if bar.contains(ev)[0] and val > 0:
                        toggle_cat(cname)
                        return

        fig.canvas.mpl_connect("button_press_event", on_click)
        plt.close(fig)

        # ── Légende CTk cliquable ──
        items = [(cn, "") for cn in cat_names]
        _ctk_legend(draw_parent, items, colors,
                    toggle_fn=toggle_cat,
                    active_filter=cat_filter,
                    ncols=5, height=90)

    _draw(parent)
    return _draw
