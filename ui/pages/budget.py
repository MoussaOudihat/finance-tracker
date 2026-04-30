"""
ui/pages/budget.py — Page de gestion des budgets par catégorie
Affiche uniquement les catégories que l'utilisateur a ajoutées au budget du mois.
"""
import customtkinter as ctk
from config import C, MONTHS_FR
from ui.components import make_card, month_selector, show_toast


class BudgetPage:
    def render(self, container: ctk.CTkFrame, app):
        self._app = app
        self._db = app.db
        self._y = app.sel_year
        self._m = app.sel_month

        db = self._db
        y, m = self._y, self._m

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="💰 Budget mensuel",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        def on_month_change(new_m, new_y):
            app.sel_month = new_m
            app.sel_year = new_y
            app._go("budget")

        month_selector(top, MONTHS_FR, y, m, on_month_change).grid(
            row=0, column=2, sticky="e")

        # ── Boutons d'action ──────────────────────────────────
        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=(0, 16))

        ctk.CTkButton(
            actions, text="➕ Ajouter une catégorie",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=C["green"], text_color="white", height=32,
            command=self._on_add_category
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            actions, text="📋 Copier mois précédent",
            font=ctk.CTkFont(size=12),
            fg_color=C["blue"], text_color="white", height=32,
            command=self._on_copy_from_previous
        ).pack(side="left")

        # ── Card principale ────────────────────────────────────
        card = make_card(container)
        card.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        # ── Scrollable ─────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(card, fg_color=C["card"])
        scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        scroll.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        # ── Données du mois ────────────────────────────────────
        # Catégories avec budget défini OU dépenses réelles ce mois-ci
        data = db.get_budget_vs_actual(y, m)
        self._budget_fields = {}
        self._active_categories = [item["category"] for item in data]

        if not data:
            self._render_empty_state(scroll)
        else:
            self._create_table_header(scroll)
            row_idx = 1
            total_budget = 0.0
            total_actual = 0.0
            for item in data:
                cat = item["category"]
                budget = item["budget"]
                actual = item["actual"]
                total_budget += budget
                total_actual += actual
                self._create_budget_row(scroll, row_idx, cat, budget, actual, y, m, db)
                row_idx += 1
            self._create_total_row(scroll, row_idx, total_budget, total_actual)

        # ── Bouton Enregistrer ─────────────────────────────────
        if data:
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 6))
            ctk.CTkButton(
                btn_frame, text="✓ Enregistrer tous les budgets",
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color=C["green"], text_color="white",
                command=self._on_save_all
            ).pack(side="right", padx=4, pady=4)

    # ── État vide ──────────────────────────────────────────────
    def _render_empty_state(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=0, columnspan=6, pady=60)

        ctk.CTkLabel(
            frame, text="Aucun budget pour ce mois",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C["muted"],
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            frame, text="Ajoutez des catégories pour définir vos budgets",
            font=ctk.CTkFont(size=12),
            text_color=C["muted"],
        ).pack(pady=(0, 20))

        ctk.CTkButton(
            frame, text="➕ Ajouter une catégorie",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C["green"], text_color="white", height=40, width=220,
            command=self._on_add_category
        ).pack()

    # ── En-tête du tableau ─────────────────────────────────────
    def _create_table_header(self, parent):
        header_bg = ctk.CTkFrame(parent, fg_color=C["light"], corner_radius=6)
        header_bg.grid(row=0, column=0, columnspan=7, sticky="nsew", padx=2, pady=(0, 4))

        cols = [
            ("Catégorie", 0), ("Budget prévu", 1), ("Réalisé", 2),
            ("Différence", 3), ("% utilisé", 4), ("Progression", 5), ("", 6),
        ]
        for label, col in cols:
            ctk.CTkLabel(
                parent, text=label,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C["muted"], fg_color=C["light"],
            ).grid(row=0, column=col, padx=10, pady=6, sticky="w")

        header_bg.lower()

    # ── Ligne de budget ────────────────────────────────────────
    def _create_budget_row(self, parent, row_idx, category, budget, actual,
                           year, month, db):
        bg = C["light"] if row_idx % 2 == 0 else C["card"]

        row_bg = ctk.CTkFrame(parent, fg_color=bg, corner_radius=6)
        row_bg.grid(row=row_idx, column=0, columnspan=7, sticky="nsew", padx=2, pady=1)

        # Catégorie
        ctk.CTkLabel(
            parent, text=category,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["text"], fg_color=bg,
        ).grid(row=row_idx, column=0, padx=10, pady=7, sticky="w")

        # Budget prévu (éditable)
        budget_var = ctk.StringVar(value=f"{budget:.2f}")
        self._budget_fields[category] = budget_var

        def make_handler(var, cat):
            def on_change(*_):
                try:
                    amount = float(var.get().replace(",", "."))
                    amount = max(0.0, amount)
                    db.set_budget(year, month, cat, amount)
                    var.set(f"{amount:.2f}")
                except ValueError:
                    pass
            return on_change

        on_change = make_handler(budget_var, category)

        entry = ctk.CTkEntry(
            parent, textvariable=budget_var,
            font=ctk.CTkFont(size=12), width=90, height=32,
            fg_color=C["card"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        entry.grid(row=row_idx, column=1, padx=10, pady=7)
        entry.bind("<Return>", on_change)
        entry.bind("<FocusOut>", on_change)

        # Réalisé
        ctk.CTkLabel(
            parent, text=f"{actual:.2f} €",
            font=ctk.CTkFont(size=12), text_color=C["text"], fg_color=bg,
        ).grid(row=row_idx, column=2, padx=10, pady=7, sticky="w")

        # Différence
        diff = budget - actual
        ctk.CTkLabel(
            parent, text=f"{diff:+.2f} €",
            font=ctk.CTkFont(size=12),
            text_color=C["green"] if diff >= 0 else C["red"],
            fg_color=bg,
        ).grid(row=row_idx, column=3, padx=10, pady=7, sticky="w")

        # % utilisé
        pct = (actual / budget * 100) if budget > 0 else 0
        pct_color = C["green"] if pct <= 80 else (C["amber"] if pct <= 100 else C["red"])
        ctk.CTkLabel(
            parent,
            text=f"{pct:.1f} %" if budget > 0 else "—",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=pct_color if budget > 0 else C["muted"],
            fg_color=bg,
        ).grid(row=row_idx, column=4, padx=10, pady=7, sticky="w")

        # Barre de progression
        bar_cont = ctk.CTkFrame(parent, fg_color=bg, height=20)
        bar_cont.grid(row=row_idx, column=5, padx=10, pady=7, sticky="ew")
        bar_cont.pack_propagate(False)
        bar_bg = ctk.CTkFrame(bar_cont, fg_color="#E2E8F0", corner_radius=4, height=10)
        bar_bg.pack(fill="x", expand=True)
        bar_bg.pack_propagate(False)
        if budget > 0:
            ctk.CTkFrame(
                bar_bg, fg_color=pct_color, corner_radius=4, height=10
            ).place(relx=0, rely=0, relwidth=min(pct / 100, 1.0), relheight=1)

        # Bouton supprimer (seulement si pas de dépenses réelles)
        def make_remove(cat):
            def remove():
                self._db.set_budget(self._y, self._m, cat, 0)
                self._app._go("budget")
            return remove

        if actual == 0:
            ctk.CTkButton(
                parent, text="✕",
                font=ctk.CTkFont(size=11),
                fg_color="transparent", text_color=C["muted"],
                hover_color=C["border"], width=28, height=28,
                command=make_remove(category)
            ).grid(row=row_idx, column=6, padx=(0, 6), pady=7)
        else:
            ctk.CTkLabel(
                parent, text="", fg_color=bg, width=28,
            ).grid(row=row_idx, column=6, padx=(0, 6), pady=7)

        row_bg.lower()

    # ── Ligne total ────────────────────────────────────────────
    def _create_total_row(self, parent, row_idx, total_budget, total_actual):
        bg = "#F0F7FF"
        row_bg = ctk.CTkFrame(parent, fg_color=bg, corner_radius=8,
                              border_width=2, border_color=C["blue"])
        row_bg.grid(row=row_idx, column=0, columnspan=7, sticky="nsew", padx=2, pady=(6, 0))

        for col, (txt, color) in enumerate([
            ("TOTAL", C["blue"]),
            (f"{total_budget:.2f} €", C["blue"]),
            (f"{total_actual:.2f} €", C["blue"]),
            (f"{total_budget - total_actual:+.2f} €",
             C["green"] if total_budget >= total_actual else C["red"]),
        ]):
            ctk.CTkLabel(
                parent, text=txt,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=color, fg_color=bg,
            ).grid(row=row_idx, column=col, padx=10, pady=7, sticky="w")

        row_bg.lower()

    # ── Dialog : ajouter une catégorie ────────────────────────
    def _on_add_category(self):
        all_cats = [r["name"] for r in self._db.get_categories()]
        available = [c for c in sorted(all_cats)
                     if c not in self._active_categories]

        if not available:
            show_toast(self._app, "Toutes les catégories sont déjà dans le budget !")
            return

        dlg = ctk.CTkToplevel(self._app)
        dlg.title("Ajouter une catégorie au budget")
        dlg.geometry("400x480")
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text="Sélectionnez les catégories à ajouter",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(16, 8), padx=16)

        # Zone scrollable avec cases à cocher
        scroll = ctk.CTkScrollableFrame(dlg, height=320)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        check_vars = {}
        for cat in available:
            var = ctk.BooleanVar(value=False)
            check_vars[cat] = var
            ctk.CTkCheckBox(
                scroll, text=cat,
                variable=var,
                font=ctk.CTkFont(size=12),
                checkbox_width=18, checkbox_height=18,
            ).pack(anchor="w", pady=3, padx=4)

        def confirm():
            selected = [cat for cat, var in check_vars.items() if var.get()]
            if not selected:
                show_toast(self._app, "Aucune catégorie sélectionnée")
                return
            for cat in selected:
                # Initialiser le budget à 0 pour que la catégorie apparaisse
                self._db.set_budget(self._y, self._m, cat, 0.0)
            dlg.destroy()
            self._app._go("budget")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(
            btns, text="✓ Ajouter",
            fg_color=C["green"], text_color="white",
            command=confirm
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            btns, text="Annuler",
            fg_color=C["muted"], text_color="white",
            command=dlg.destroy
        ).pack(side="right", padx=4)

    # ── Copier du mois précédent ───────────────────────────────
    def _on_copy_from_previous(self):
        y, m = self._y, self._m
        prev_m, prev_y = (m - 1, y) if m > 1 else (12, y - 1)
        self._db.copy_budgets_from_month(prev_y, prev_m, y, m)
        show_toast(self._app, "Budgets copiés du mois précédent !")
        self._app._go("budget")

    # ── Enregistrer tout ───────────────────────────────────────
    def _on_save_all(self):
        saved = 0
        for cat, var in self._budget_fields.items():
            try:
                amount = max(0.0, float(var.get().replace(",", ".")))
                self._db.set_budget(self._y, self._m, cat, amount)
                saved += 1
            except ValueError:
                pass
        show_toast(self._app, f"✓ {saved} budget(s) enregistré(s) !")
