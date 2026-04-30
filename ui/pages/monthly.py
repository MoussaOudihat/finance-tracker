"""
ui/pages/monthly.py — Saisie mensuelle en tableau inline (sans popup pour l'ajout)

FIX: tous les enfants directs de `wrap` utilisent .pack() uniquement
     pour éviter le conflit pack/grid de CTkTabview.
"""
import customtkinter as ctk
from config import C, MONTHS_FR
from ui.components import make_card, table_header, table_row, total_bar, month_selector
from ui.dialogs   import RevenueDialog, ExpenseDialog, SavingDialog


class MonthlyPage:
    def render(self, container: ctk.CTkFrame, app):
        # ── Header ──────────────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="📝  Saisir le mois",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        def on_month_change(new_m, new_y):
            app.sel_month = new_m
            app.sel_year  = new_y
            app._go("monthly")

        month_selector(top, MONTHS_FR, app.sel_year, app.sel_month,
                        on_month_change).grid(row=0, column=2, sticky="e")

        # ── Tabs ────────────────────────────────────────────
        tabs = ctk.CTkTabview(
            container, fg_color=C["card"], corner_radius=12,
            segmented_button_fg_color=C["light"],
            segmented_button_selected_color=C["primary"],
            segmented_button_selected_hover_color=C["primary"],
        )
        tabs.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        container.grid_rowconfigure(1, weight=1)

        for name in ("💶  Revenus", "💸  Dépenses", "🏦  Épargne"):
            tabs.add(name)

        _render_revenues_tab(tabs.tab("💶  Revenus"),  app)
        _render_expenses_tab(tabs.tab("💸  Dépenses"), app)
        _render_savings_tab(tabs.tab("🏦  Épargne"),   app)


# ══════════════════════════════════════════════════════════
#  TAB REVENUS
# ══════════════════════════════════════════════════════════
def _render_revenues_tab(tab, app):
    db   = app.db
    y, m = app.sel_year, app.sel_month
    data = db.get_revenues(y, m)

    # wrap utilise UNIQUEMENT pack pour ses enfants directs (règle CTkTabview)
    wrap = ctk.CTkFrame(tab, fg_color="transparent")
    wrap.pack(fill="both", expand=True)

    def _refresh():
        app._go("monthly")

    # ── Liste scrollable ─────────────────────────────────
    list_f = ctk.CTkScrollableFrame(wrap, fg_color=C["card"])
    list_f.pack(fill="both", expand=True, padx=4, pady=4)
    list_f.grid_columnconfigure((0, 1, 2), weight=1)

    table_header(list_f, [(2, "Source"), (1, "Montant"), (2, "Description")])

    for idx, r in enumerate(data):
        def make_edit(row=r):
            def _edit():
                RevenueDialog(app, initial=dict(row), on_save=lambda d: (
                    db.update_revenue(row["id"], d["source"], d["amount"], d["label"]),
                    _refresh(),
                ))
            return _edit
        table_row(list_f, idx,
                  [(2, r["source"], C["text"]),
                   (1, f"{r['amount']:,.2f} €", C["green"]),
                   (2, r["label"] or "—", C["muted"], True)],
                  on_edit=make_edit(),
                  on_delete=lambda rid=r["id"]: (db.delete_revenue(rid), _refresh()))

    # ── Bande d'ajout inline ─────────────────────────────
    _inline_revenue_row(wrap, db=db, y=y, m=m, on_save=_refresh)

    # ── Total ────────────────────────────────────────────
    total = sum(r["amount"] for r in data)
    total_bar(wrap, f"Total revenus : {total:,.2f} €",
              C["green"], "#F0FDF4", "#86EFAC")


def _inline_revenue_row(parent, db, y, m, on_save):
    band = ctk.CTkFrame(parent, fg_color="#F0FDF4", corner_radius=10)
    band.pack(fill="x", padx=4, pady=(2, 6))

    ctk.CTkLabel(band, text="＋  Nouvelle ligne :",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["green"]).pack(anchor="w", padx=12, pady=(8, 4))

    fields = ctk.CTkFrame(band, fg_color="transparent")
    fields.pack(fill="x", padx=12)
    fields.grid_columnconfigure((0, 1, 2), weight=1)

    e_source = ctk.CTkEntry(fields, placeholder_text="Source (ex: Salaire)", height=34)
    e_source.grid(row=0, column=0, padx=(0, 4), pady=(0, 8), sticky="ew")

    e_amount = ctk.CTkEntry(fields, placeholder_text="Montant (€)", height=34)
    e_amount.grid(row=0, column=1, padx=4, pady=(0, 8), sticky="ew")

    e_label = ctk.CTkEntry(fields, placeholder_text="Description (optionnel)", height=34)
    e_label.grid(row=0, column=2, padx=(4, 0), pady=(0, 8), sticky="ew")

    def save_and_clear(event=None):
        source = e_source.get().strip()
        raw = e_amount.get().replace(",", ".").replace(" ", "").replace("\u202f", "")
        try:
            amount = float(raw)
        except ValueError:
            e_amount.configure(border_color=C["red"])
            return
        if not source:
            e_source.configure(border_color=C["red"])
            return
        db.add_revenue(y, m, source, amount, e_label.get().strip())
        on_save()

    btn_row = ctk.CTkFrame(band, fg_color="transparent")
    btn_row.pack(anchor="w", padx=12, pady=(0, 8))

    ctk.CTkButton(btn_row, text="✓  Ajouter", height=34, width=120,
                  fg_color=C["green"], hover_color="#16A34A",
                  command=save_and_clear).pack(side="left", padx=(0, 12))
    ctk.CTkLabel(btn_row, text="↵ Entrée dans n'importe quel champ pour valider",
                 font=ctk.CTkFont(size=10), text_color=C["muted"]).pack(side="left")

    for e in (e_source, e_amount, e_label):
        e.bind("<Return>", save_and_clear)
    e_source.focus()


# ══════════════════════════════════════════════════════════
#  TAB DÉPENSES
# ══════════════════════════════════════════════════════════
def _render_expenses_tab(tab, app):
    db        = app.db
    y, m      = app.sel_year, app.sel_month
    cats      = db.get_categories()
    cat_names = [c["name"] for c in cats]
    cat_map   = {c["name"]: c["id"] for c in cats}
    data      = db.get_expenses(y, m)

    wrap = ctk.CTkFrame(tab, fg_color="transparent")
    wrap.pack(fill="both", expand=True)

    def _refresh():
        app._go("monthly")

    list_f = ctk.CTkScrollableFrame(wrap, fg_color=C["card"])
    list_f.pack(fill="both", expand=True, padx=4, pady=4)
    list_f.grid_columnconfigure((0, 1, 2, 3), weight=1)

    table_header(list_f, [(2,"Catégorie"),(2,"Enseigne"),(1,"Montant"),(2,"Description")])

    for idx, r in enumerate(data):
        def make_edit(row=r):
            def _edit():
                ExpenseDialog(app, cat_names, initial=dict(row),
                              on_save=lambda d: (
                                  db.update_expense(row["id"],
                                                    cat_map[d["cat"]],
                                                    d["amount"], d["label"], d["payee"]),
                                  _refresh(),
                              ))
            return _edit
        table_row(list_f, idx,
                  [(2, r["cat"],              C["text"]),
                   (2, r["payee"] or "—",     C["muted"]),
                   (1, f"{r['amount']:,.2f} €", C["red"]),
                   (2, r["label"] or "—",      C["muted"], True)],
                  on_edit=make_edit(),
                  on_delete=lambda rid=r["id"]: (db.delete_expense(rid), _refresh()))

    _inline_expense_row(wrap, db=db, y=y, m=m,
                        cat_names=cat_names, cat_map=cat_map, on_save=_refresh)

    total = sum(r["amount"] for r in data)
    total_bar(wrap, f"Total dépenses : {total:,.2f} €",
              C["red"], "#FEF2F2", "#FCA5A5")


def _inline_expense_row(parent, db, y, m, cat_names, cat_map, on_save):
    band = ctk.CTkFrame(parent, fg_color="#FEF2F2", corner_radius=10)
    band.pack(fill="x", padx=4, pady=(2, 6))

    ctk.CTkLabel(band, text="＋  Nouvelle dépense :",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["red"]).pack(anchor="w", padx=12, pady=(8, 4))

    fields = ctk.CTkFrame(band, fg_color="transparent")
    fields.pack(fill="x", padx=12)
    fields.grid_columnconfigure((0, 1, 2, 3), weight=1)

    cat_var = ctk.StringVar(value=cat_names[0] if cat_names else "")
    cat_opt = ctk.CTkOptionMenu(fields, values=cat_names, variable=cat_var,
                                 height=34, fg_color=C["primary"],
                                 button_color=C["primary"])
    cat_opt.grid(row=0, column=0, padx=(0, 4), pady=(0, 8), sticky="ew")

    e_payee  = ctk.CTkEntry(fields, placeholder_text="Enseigne (ex: Carrefour)", height=34)
    e_payee.grid(row=0, column=1, padx=4, pady=(0, 8), sticky="ew")

    e_amount = ctk.CTkEntry(fields, placeholder_text="Montant (€)", height=34)
    e_amount.grid(row=0, column=2, padx=4, pady=(0, 8), sticky="ew")

    e_label  = ctk.CTkEntry(fields, placeholder_text="Description (optionnel)", height=34)
    e_label.grid(row=0, column=3, padx=(4, 0), pady=(0, 8), sticky="ew")

    def save_and_clear(event=None):
        raw = e_amount.get().replace(",", ".").replace(" ", "").replace("\u202f", "")
        try:
            amount = float(raw)
        except ValueError:
            e_amount.configure(border_color=C["red"])
            return
        cat_id = cat_map.get(cat_var.get())
        if not cat_id:
            return
        db.add_expense(y, m, cat_id, amount, e_label.get().strip(), e_payee.get().strip())
        on_save()

    btn_row = ctk.CTkFrame(band, fg_color="transparent")
    btn_row.pack(anchor="w", padx=12, pady=(0, 8))

    ctk.CTkButton(btn_row, text="✓  Ajouter", height=34, width=120,
                  fg_color=C["red"], hover_color="#B91C1C",
                  command=save_and_clear).pack(side="left", padx=(0, 12))
    ctk.CTkLabel(btn_row, text="↵ Entrée dans n'importe quel champ pour valider",
                 font=ctk.CTkFont(size=10), text_color=C["muted"]).pack(side="left")

    for e in (e_payee, e_amount, e_label):
        e.bind("<Return>", save_and_clear)
    e_amount.focus()


# ══════════════════════════════════════════════════════════
#  TAB ÉPARGNE
# ══════════════════════════════════════════════════════════
def _render_savings_tab(tab, app):
    db   = app.db
    y, m = app.sel_year, app.sel_month
    data = db.get_savings(y, m)

    wrap = ctk.CTkFrame(tab, fg_color="transparent")
    wrap.pack(fill="both", expand=True)

    def _refresh():
        app._go("monthly")

    list_f = ctk.CTkScrollableFrame(wrap, fg_color=C["card"])
    list_f.pack(fill="both", expand=True, padx=4, pady=4)
    list_f.grid_columnconfigure((0, 1, 2), weight=1)

    table_header(list_f, [(2,"Compte"),(1,"Montant"),(2,"Description")])

    for idx, r in enumerate(data):
        def make_edit(row=r):
            def _edit():
                SavingDialog(app, initial=dict(row), on_save=lambda d: (
                    db.update_saving(row["id"], d["account"], d["amount"], d["label"]),
                    _refresh(),
                ))
            return _edit
        table_row(list_f, idx,
                  [(2, r["account"] or "—",   C["text"]),
                   (1, f"{r['amount']:,.2f} €", C["blue"]),
                   (2, r["label"] or "—",      C["muted"], True)],
                  on_edit=make_edit(),
                  on_delete=lambda rid=r["id"]: (db.delete_saving(rid), _refresh()))

    _inline_saving_row(wrap, db=db, y=y, m=m, on_save=_refresh)

    total = sum(r["amount"] for r in data)
    total_bar(wrap, f"Total épargne : {total:,.2f} €",
              C["blue"], "#EFF6FF", "#93C5FD")


def _inline_saving_row(parent, db, y, m, on_save):
    band = ctk.CTkFrame(parent, fg_color="#EFF6FF", corner_radius=10)
    band.pack(fill="x", padx=4, pady=(2, 6))

    ctk.CTkLabel(band, text="＋  Nouvelle épargne :",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 text_color=C["blue"]).pack(anchor="w", padx=12, pady=(8, 4))

    fields = ctk.CTkFrame(band, fg_color="transparent")
    fields.pack(fill="x", padx=12)
    fields.grid_columnconfigure((0, 1, 2), weight=1)

    e_account = ctk.CTkEntry(fields, placeholder_text="Compte (ex: Livret A)", height=34)
    e_account.grid(row=0, column=0, padx=(0, 4), pady=(0, 8), sticky="ew")

    e_amount = ctk.CTkEntry(fields, placeholder_text="Montant (€)", height=34)
    e_amount.grid(row=0, column=1, padx=4, pady=(0, 8), sticky="ew")

    e_label = ctk.CTkEntry(fields, placeholder_text="Description (optionnel)", height=34)
    e_label.grid(row=0, column=2, padx=(4, 0), pady=(0, 8), sticky="ew")

    def save_and_clear(event=None):
        raw = e_amount.get().replace(",", ".").replace(" ", "").replace("\u202f", "")
        try:
            amount = float(raw)
        except ValueError:
            e_amount.configure(border_color=C["red"])
            return
        db.add_saving(y, m, e_account.get().strip(), amount, e_label.get().strip())
        on_save()

    btn_row = ctk.CTkFrame(band, fg_color="transparent")
    btn_row.pack(anchor="w", padx=12, pady=(0, 8))

    ctk.CTkButton(btn_row, text="✓  Ajouter", height=34, width=120,
                  fg_color=C["blue"], hover_color="#1D4ED8",
                  command=save_and_clear).pack(side="left", padx=(0, 12))
    ctk.CTkLabel(btn_row, text="↵ Entrée dans n'importe quel champ pour valider",
                 font=ctk.CTkFont(size=10), text_color=C["muted"]).pack(side="left")

    for e in (e_account, e_amount, e_label):
        e.bind("<Return>", save_and_clear)
    e_account.focus()
