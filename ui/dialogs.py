"""
ui/dialogs.py — Fenêtres modales d'édition
"""
import customtkinter as ctk
from config import C, ASSET_TYPES, MONTHS_FR

# helper pour formatter les quantités sans zéros inutiles
def _fmt_qty(q: float) -> str:
    if q == int(q):
        return str(int(q))
    return f"{q:.6f}".rstrip("0")


class _BaseDialog(ctk.CTkToplevel):
    """Dialogue modal générique."""

    def __init__(self, parent, title: str, width: int = 480, height: int = 340):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()
        self._result = None

        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=C["sidebar"], corner_radius=0)
        hdr.pack(fill="x", side="top")
        ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").pack(anchor="w", padx=20, pady=14)

        # ── Footer — AVANT le body pour que expand=True ne l'écrase pas ──
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0,
                              border_width=1, border_color=C["border"])
        footer.pack(fill="x", side="bottom")
        ctk.CTkButton(footer, text="Annuler", width=110, height=38,
                      fg_color=C["light"], text_color=C["text"],
                      hover_color=C["border"],
                      command=self.destroy).pack(side="right", padx=8, pady=10)
        self._save_btn = ctk.CTkButton(
            footer, text="✓  Enregistrer", width=140, height=38,
            command=self._on_save,
        )
        self._save_btn.pack(side="right", padx=(0, 4), pady=10)

        # ── Body — après le footer pour ne pas le recouvrir ──
        self.body = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0)
        self.body.pack(fill="both", expand=True, side="top")
        self.body.grid_columnconfigure(0, weight=1)

        # Raccourci clavier Entrée
        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _field(self, row: int, label: str, placeholder: str = "",
               initial: str = "", col: int = 0, colspan: int = 1) -> ctk.CTkEntry:
        ctk.CTkLabel(self.body, text=label, font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=row * 2, column=col, columnspan=colspan,
            padx=20, pady=(14, 2), sticky="w")
        e = ctk.CTkEntry(self.body, placeholder_text=placeholder, height=38,
                         font=ctk.CTkFont(size=13))
        e.grid(row=row * 2 + 1, column=col, columnspan=colspan,
               padx=20, pady=(0, 0), sticky="ew")
        if initial:
            e.insert(0, initial)
        return e

    def _on_save(self):
        raise NotImplementedError


# ──────────────────────────────────────────────────────────
#  Dialogue: Revenu
# ──────────────────────────────────────────────────────────
class RevenueDialog(_BaseDialog):
    def __init__(self, parent, initial: dict = None, on_save=None):
        super().__init__(parent,
                         "✏  Modifier le revenu" if initial else "＋  Ajouter un revenu",
                         width=480, height=360)
        self._on_save_cb = on_save
        init = initial or {}

        self._source = self._field(0, "Source *", "Ex : Salaire", init.get("source", ""))
        self._amount = self._field(1, "Montant (€) *", "0.00", str(init.get("amount", "")))
        self._label  = self._field(2, "Description", "Optionnel", init.get("label", ""))
        self._source.focus()

    def _on_save(self):
        try:
            amount = float(self._amount.get().replace(",", ".").replace(" ", ""))
        except ValueError:
            self._amount.configure(border_color=C["red"])
            return
        source = self._source.get().strip()
        if not source:
            self._source.configure(border_color=C["red"])
            return
        if self._on_save_cb:
            self._on_save_cb({
                "source": source,
                "amount": amount,
                "label":  self._label.get().strip(),
            })
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Dépense
# ──────────────────────────────────────────────────────────
class ExpenseDialog(_BaseDialog):
    def __init__(self, parent, categories: list[str], initial: dict = None, on_save=None):
        super().__init__(parent,
                         "✏  Modifier la dépense" if initial else "＋  Ajouter une dépense",
                         width=520, height=420)
        self._on_save_cb = on_save
        init = initial or {}

        # Catégorie
        ctk.CTkLabel(self.body, text="Catégorie *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(row=0, column=0, padx=20, pady=(14, 2), sticky="w")
        self._cat_var = ctk.StringVar(value=init.get("cat", categories[0] if categories else ""))
        ctk.CTkOptionMenu(self.body, values=categories, variable=self._cat_var,
                          height=38, font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=20, sticky="ew")

        self._payee  = self._field(1, "Enseigne / À qui", "Ex : Carrefour", init.get("payee", ""))
        self._amount = self._field(2, "Montant (€) *", "0.00", str(init.get("amount", "")))
        self._label  = self._field(3, "Description", "Optionnel", init.get("label", ""))
        self._payee.focus()

    def _on_save(self):
        try:
            amount = float(self._amount.get().replace(",", ".").replace(" ", ""))
        except ValueError:
            self._amount.configure(border_color=C["red"])
            return
        if self._on_save_cb:
            self._on_save_cb({
                "cat":    self._cat_var.get(),
                "payee":  self._payee.get().strip(),
                "amount": amount,
                "label":  self._label.get().strip(),
            })
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Épargne
# ──────────────────────────────────────────────────────────
class SavingDialog(_BaseDialog):
    def __init__(self, parent, initial: dict = None, on_save=None):
        super().__init__(parent,
                         "✏  Modifier l'épargne" if initial else "＋  Ajouter une épargne",
                         width=480, height=360)
        self._on_save_cb = on_save
        init = initial or {}

        self._account = self._field(0, "Compte / Destination *", "Ex : Livret A",
                                     init.get("account", ""))
        self._amount  = self._field(1, "Montant (€) *", "0.00", str(init.get("amount", "")))
        self._label   = self._field(2, "Description", "Optionnel", init.get("label", ""))
        self._account.focus()

    def _on_save(self):
        try:
            amount = float(self._amount.get().replace(",", ".").replace(" ", ""))
        except ValueError:
            self._amount.configure(border_color=C["red"])
            return
        account = self._account.get().strip()
        if not account:
            self._account.configure(border_color=C["red"])
            return
        if self._on_save_cb:
            self._on_save_cb({
                "account": account,
                "amount":  amount,
                "label":   self._label.get().strip(),
            })
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Actif / Investissement
# ──────────────────────────────────────────────────────────
class AssetDialog(_BaseDialog):
    def __init__(self, parent, initial: dict = None, on_save=None):
        super().__init__(parent,
                         "✏  Modifier l'actif" if initial else "＋  Ajouter un actif",
                         width=560, height=520)
        self._on_save_cb = on_save
        init = initial or {}

        # 2 colonnes dans le body
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)

        type_names = [t[0] for t in ASSET_TYPES]
        self._type_keys = {t[0]: t[1] for t in ASSET_TYPES}
        init_type = next(
            (t[0] for t in ASSET_TYPES if t[1] == init.get("asset_type", "")),
            type_names[0]
        )

        # Type d'actif (pleine largeur)
        ctk.CTkLabel(self.body, text="Type d'actif *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=0, column=0, columnspan=2, padx=20, pady=(14, 2), sticky="w")
        self._type_var = ctk.StringVar(value=init_type)
        ctk.CTkOptionMenu(self.body, values=type_names, variable=self._type_var,
                          height=38, font=ctk.CTkFont(size=13),
                          fg_color=C["primary"], button_color=C["primary"]).grid(
            row=1, column=0, columnspan=2, padx=20, sticky="ew")

        # Nom (pleine largeur)
        self._name = self._field(1, "Nom *", "Ex : PEA Boursorama",
                                  init.get("asset_name", ""), col=0, colspan=2)

        # Valeur actuelle | Prix d'achat (côte à côte)
        self._value = self._field(2, "Valeur actuelle (€) *", "0.00",
                                   str(init.get("value", "") or ""), col=0)
        self._cost_basis = self._field(2, "Prix d'achat / Investi (€)", "0.00",
                                        str(init.get("cost_basis", "") or ""), col=1)

        # Notes (pleine largeur)
        self._notes = self._field(3, "Notes", "Optionnel",
                                   init.get("notes", "") or "", col=0, colspan=2)

        # Astuce
        ctk.CTkLabel(self.body,
                     text="* champs obligatoires  ·  Entrée pour valider  ·  Échap pour annuler",
                     font=ctk.CTkFont(size=10), text_color=C["muted"]).grid(
            row=8, column=0, columnspan=2, padx=20, pady=(12, 8), sticky="w")

        self._name.focus()

    def _on_save(self):
        name = self._name.get().strip()
        if not name:
            self._name.configure(border_color=C["red"])
            return
        raw_value = self._value.get().replace(",", ".").replace(" ", "")
        raw_cb    = (self._cost_basis.get() or "0").replace(",", ".").replace(" ", "")
        try:
            value      = float(raw_value)
            cost_basis = float(raw_cb) if raw_cb else 0.0
        except ValueError:
            self._value.configure(border_color=C["red"])
            return
        if self._on_save_cb:
            self._on_save_cb({
                "asset_type": self._type_keys.get(self._type_var.get(), "autre"),
                "asset_name": name,
                "value":      value,
                "cost_basis": cost_basis,
                "notes":      self._notes.get().strip(),
            })
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Mise à jour rapide de la valeur
# ──────────────────────────────────────────────────────────
class QuickValueUpdateDialog(_BaseDialog):
    """Popup minimaliste pour mettre à jour la valeur actuelle d'un actif."""

    def __init__(self, parent, asset_name: str, current_value: float, on_save=None):
        label = asset_name if len(asset_name) <= 30 else asset_name[:28] + "…"
        super().__init__(parent, f"💰  Màj valeur — {label}",
                         width=400, height=250)
        self._on_save_cb = on_save

        ctk.CTkLabel(self.body,
                     text=f"Actif : {asset_name}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(
            row=0, column=0, padx=20, pady=(16, 4), sticky="w")

        self._value = self._field(1, "Nouvelle valeur actuelle (€) *", "0.00",
                                   f"{current_value:.2f}")
        self._value.select_range(0, "end")
        self._value.focus()

    def _on_save(self):
        raw = self._value.get().replace(",", ".").replace(" ", "").replace("\u202f", "")
        try:
            value = float(raw)
        except ValueError:
            self._value.configure(border_color=C["red"])
            return
        if self._on_save_cb:
            self._on_save_cb(value)
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Évolution par actif (graphique)
# ──────────────────────────────────────────────────────────
class AssetEvolutionDialog:
    """Fenêtre pop-up avec le graphique d'évolution d'un actif spécifique."""

    def __init__(self, parent, asset_name: str, history: list):
        import matplotlib
        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        win = ctk.CTkToplevel(parent)
        win.title(f"Évolution — {asset_name}")
        win.geometry("720x480")
        win.configure(fg_color="white")
        win.grab_set()

        # Header
        hdr = ctk.CTkFrame(win, fg_color=C["sidebar"], corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"📊  Évolution — {asset_name}",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").pack(anchor="w", padx=20, pady=12)

        ctk.CTkButton(win, text="Fermer", width=100,
                      command=win.destroy).pack(side="bottom", pady=10)

        if not history or len(history) < 2:
            ctk.CTkLabel(win,
                         text="Pas assez de données.\nSaisissez la valeur sur au moins 2 mois.",
                         font=ctk.CTkFont(size=13), text_color=C["muted"],
                         justify="center").pack(expand=True)
            return

        labels = [f"{MONTHS_FR[r['month']-1][:3]}\n{r['year']}" for r in history]
        vals   = [r["value"]      for r in history]
        bases  = [r["cost_basis"] for r in history]
        x      = list(range(len(history)))

        fig, ax = plt.subplots(figsize=(9, 4.0))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("#FAFCFF")

        ax.fill_between(x, vals, alpha=0.10, color=C["primary"])
        line_val, = ax.plot(x, vals, color=C["primary"], lw=2.5,
                            marker="o", ms=6, label="Valeur actuelle")

        if any(b for b in bases):
            ax.plot(x, bases, color=C["amber"], lw=1.5, ls="--",
                    marker="s", ms=4, label="Prix d'achat / Investi")

        # Étiquettes de valeur sur chaque point
        for xi, vi in zip(x, vals):
            ax.annotate(f"{vi:,.0f} €", (xi, vi),
                        textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=7.5, color=C["primary"])

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8.5)
        ax.yaxis.set_tick_params(labelsize=8)
        ax.set_ylabel("€", fontsize=9)
        ax.legend(fontsize=9, frameon=False)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        plt.tight_layout(pad=1.5)

        cv = FigureCanvasTkAgg(fig, win)
        cv.draw()
        cv.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=(8, 0))
        plt.close(fig)


# ──────────────────────────────────────────────────────────
#  Dialogue: Transactions par actif (CMUP)
# ──────────────────────────────────────────────────────────
class AssetTransactionsDialog(ctk.CTkToplevel):
    """
    Fenêtre de suivi des transactions d'un actif financier.
    Calcule la position en CMUP (coût moyen pondéré).
    """

    def __init__(self, parent, asset: dict, db, app, year: int, month: int):
        super().__init__(parent)
        self._db        = db
        self._app       = app
        self._asset     = dict(asset)   # snapshot — on relit depuis DB si besoin
        self._cur_year  = year
        self._cur_month = month

        name = asset["asset_name"]
        self.title(f"Transactions — {name}")
        self.geometry("820x700")
        self.resizable(True, True)
        self.grab_set()
        self.focus_force()
        self.minsize(700, 520)

        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=C["sidebar"], corner_radius=0)
        hdr.pack(fill="x", side="top")
        ctk.CTkLabel(
            hdr, text=f"📋  Transactions — {name}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="white",
        ).pack(anchor="w", padx=20, pady=14)

        # ── Footer ── (avant le body)
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0,
                              border_width=1, border_color=C["border"])
        footer.pack(fill="x", side="bottom")
        ctk.CTkButton(
            footer, text="Fermer", width=110, height=38,
            fg_color=C["light"], text_color=C["text"],
            hover_color=C["border"],
            command=self.destroy,
        ).pack(side="right", padx=8, pady=10)

        # ── Body scrollable ──
        self._body = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0)
        self._body.pack(fill="both", expand=True, side="top")
        self._body.grid_columnconfigure(0, weight=1)

        self._render_all()
        self.bind("<Escape>", lambda e: self.destroy())

    # ── Rendu complet ──────────────────────────────────────
    def _render_all(self):
        for w in self._body.winfo_children():
            w.destroy()
        self._render_position_summary(row=0)
        # Aide à la migration : actif saisi sans transactions
        transactions = self._db.get_asset_transactions(self._asset["asset_name"])
        has_basis    = (self._asset.get("cost_basis") or 0) > 0
        has_value    = (self._asset.get("value") or 0) > 0
        if not transactions and (has_basis or has_value):
            self._render_initial_position_banner(row=1)
            self._render_add_form(row=2)
            self._render_transactions_list(row=3)
        else:
            self._render_add_form(row=1)
            self._render_transactions_list(row=2)

    # ── Bandeau "créer position initiale" ──────────────────
    def _render_initial_position_banner(self, row: int):
        """
        Affiché quand l'actif a une valeur ou un coût d'achat saisi globalement
        mais aucune transaction enregistrée. Permet de créer une position
        rétroactive en un clic.
        """
        cost  = float(self._asset.get("cost_basis") or 0)
        value = float(self._asset.get("value") or 0)

        card = ctk.CTkFrame(
            self._body, fg_color="#FFFBEB", corner_radius=10,
            border_width=1, border_color="#FDE68A",
        )
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=(10, 0))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="ℹ️  Aucune transaction enregistrée pour cet actif",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#92400E",
        ).grid(row=0, column=0, padx=14, pady=(12, 2), sticky="w")

        msg = ("Cet actif a été ajouté avec une valeur globale, mais sans "
               "détail des achats. Pour suivre les ventes et calculer la "
               "plus-value réelle, créez une position initiale en saisissant "
               "la quantité que vous détenez aujourd'hui.")
        ctk.CTkLabel(
            card, text=msg, justify="left", wraplength=720,
            font=ctk.CTkFont(size=11), text_color="#78350F",
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="w")

        # Form inline : qté + prix (auto-calculé si cost_basis présent)
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="ew")
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(form, text="Quantité détenue *",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#92400E").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ctk.CTkLabel(form, text="Prix d'achat moyen (€) *",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#92400E").grid(row=0, column=1, sticky="w", padx=6)
        ctk.CTkLabel(form, text="Mois / Année",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#92400E").grid(row=0, column=2, sticky="w", padx=6)

        init_qty = ctk.CTkEntry(form, placeholder_text="Ex : 10",
                                 height=32, font=ctk.CTkFont(size=12))
        init_qty.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(2, 0))

        # Pré-remplit le prix unitaire avec cost_basis si on a une qty estimée,
        # sinon laisse vide (utilisateur le tapera).
        init_price = ctk.CTkEntry(form, placeholder_text="Ex : 156.50",
                                   height=32, font=ctk.CTkFont(size=12))
        init_price.grid(row=1, column=1, sticky="ew", padx=6, pady=(2, 0))

        # Auto-calcul du prix dès que la qté est tapée (basé sur cost_basis)
        def _autofill_price(*_):
            try:
                q = float(init_qty.get().replace(",", ".").replace(" ", ""))
                if q > 0 and cost > 0 and not init_price.get().strip():
                    init_price.delete(0, "end")
                    init_price.insert(0, f"{cost / q:.2f}")
            except Exception:
                pass
        init_qty.bind("<FocusOut>", _autofill_price)
        init_qty.bind("<KeyRelease>", _autofill_price)

        ym = ctk.CTkFrame(form, fg_color="transparent")
        ym.grid(row=1, column=2, sticky="ew", padx=6, pady=(2, 0))
        init_month = ctk.StringVar(value=MONTHS_FR[self._cur_month - 1])
        init_year  = ctk.StringVar(value=str(self._cur_year))
        ctk.CTkOptionMenu(ym, values=MONTHS_FR, variable=init_month,
                          height=32, width=100,
                          font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ym, values=[str(yr) for yr in range(2010, 2036)],
                          variable=init_year,
                          height=32, width=72,
                          font=ctk.CTkFont(size=11)).pack(side="left")

        def _create_initial():
            try:
                q = float(init_qty.get().replace(",", ".").replace(" ", ""))
                if q <= 0:
                    raise ValueError
                init_qty.configure(border_color=C["border"])
            except ValueError:
                init_qty.configure(border_color=C["red"])
                return
            try:
                p = float(init_price.get().replace(",", ".").replace(" ", ""))
                if p <= 0:
                    raise ValueError
                init_price.configure(border_color=C["border"])
            except ValueError:
                init_price.configure(border_color=C["red"])
                return

            ty = int(init_year.get())
            tm = MONTHS_FR.index(init_month.get()) + 1

            # Crée une transaction d'achat unique reflétant la position détenue.
            self._db.add_asset_transaction(
                self._asset["asset_name"], self._asset["asset_type"],
                ty, tm, "achat", q, p, 0.0,
                "Position initiale (créée rétroactivement)",
            )
            self._sync_cost_basis()
            self._render_all()

        ctk.CTkButton(
            form, text="✓  Créer position initiale", height=32,
            fg_color="#D97706", hover_color="#B45309", text_color="white",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=_create_initial,
        ).grid(row=1, column=3, sticky="ew", padx=(6, 0), pady=(2, 0))

        # Hint sur les valeurs déjà saisies
        info_parts = []
        if cost > 0:
            info_parts.append(f"Coût d'achat saisi : {cost:,.2f} €")
        if value > 0:
            info_parts.append(f"Valeur actuelle : {value:,.2f} €")
        if info_parts:
            ctk.CTkLabel(
                card, text="  •  ".join(info_parts),
                font=ctk.CTkFont(size=10), text_color="#92400E",
            ).grid(row=3, column=0, padx=14, pady=(0, 12), sticky="w")

    # ── Résumé de position ─────────────────────────────────
    def _render_position_summary(self, row: int):
        pos     = self._db.compute_asset_position(self._asset["asset_name"])
        cur_val = self._asset["value"]

        card = ctk.CTkFrame(self._body, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=(10, 0))
        card.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkLabel(
            card, text="Position actuelle (CMUP — coût moyen pondéré)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C["muted"],
        ).grid(row=0, column=0, columnspan=5, padx=16, pady=(12, 6), sticky="w")

        kpis = [
            ("Qté détenue",  _fmt_qty(pos["qty"]) if pos["qty"] else "0"),
            ("Prix de revient", f"{pos['avg_price']:,.2f} €" if pos["avg_price"] else "—"),
            ("Investi",      f"{pos['total_cost']:,.2f} €"),
            ("P&L réalisé",  f"{pos['realized_pnl']:+,.2f} €" if pos["realized_pnl"] != 0 else "—"),
            ("Frais totaux", f"{pos['total_fees']:,.2f} €" if pos["total_fees"] else "—"),
        ]

        for i, (label, val) in enumerate(kpis):
            clr = C["text"]
            if label == "P&L réalisé" and pos["realized_pnl"] != 0:
                clr = C["green"] if pos["realized_pnl"] > 0 else C["red"]
            f = ctk.CTkFrame(card, fg_color="transparent")
            f.grid(row=1, column=i, padx=12, pady=(0, 12), sticky="ew")
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10),
                         text_color=C["muted"]).pack(anchor="w")
            ctk.CTkLabel(f, text=val,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=clr).pack(anchor="w")

        # P&L latent si on a une position ouverte
        if pos["qty"] > 1e-9 and pos["total_cost"] > 0:
            latent     = cur_val - pos["total_cost"]
            latent_pct = latent / pos["total_cost"] * 100
            clr        = C["green"] if latent >= 0 else C["red"]
            sign       = "+" if latent >= 0 else ""
            ctk.CTkLabel(
                card,
                text=(f"P&L latent  (valeur actuelle = {cur_val:,.2f} €) :  "
                      f"{sign}{latent:,.2f} €  ({sign}{latent_pct:.1f} %)"),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=clr,
            ).grid(row=2, column=0, columnspan=5, padx=16, pady=(0, 14), sticky="w")

    # ── Formulaire d'ajout ─────────────────────────────────
    def _render_add_form(self, row: int):
        card = ctk.CTkFrame(self._body, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=(10, 0))
        card.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkLabel(
            card, text="＋  Nouvelle transaction",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"],
        ).grid(row=0, column=0, columnspan=5, padx=16, pady=(12, 6), sticky="w")

        # ── Ligne 1 : type | qté | prix unit. | frais | mois/année ──
        labels1 = ["Type *", "Quantité *", "Prix unitaire (€) *", "Frais (€)", "Mois / Année"]
        for i, lbl in enumerate(labels1):
            ctk.CTkLabel(card, text=lbl, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C["muted"]).grid(
                row=1, column=i, padx=12, pady=(0, 2), sticky="w")

        # Type
        self._type_var = ctk.StringVar(value="Achat")
        ctk.CTkOptionMenu(
            card, values=["Achat", "Vente"], variable=self._type_var,
            height=34, font=ctk.CTkFont(size=12),
            fg_color=C["primary"], button_color=C["primary"],
        ).grid(row=2, column=0, padx=12, pady=(0, 8), sticky="ew")

        # Quantité
        self._qty_entry = ctk.CTkEntry(card, placeholder_text="Ex : 10",
                                        height=34, font=ctk.CTkFont(size=12))
        self._qty_entry.grid(row=2, column=1, padx=12, pady=(0, 8), sticky="ew")

        # Prix unitaire
        self._price_entry = ctk.CTkEntry(card, placeholder_text="Ex : 156.50",
                                          height=34, font=ctk.CTkFont(size=12))
        self._price_entry.grid(row=2, column=2, padx=12, pady=(0, 8), sticky="ew")

        # Frais
        self._fees_entry = ctk.CTkEntry(card, placeholder_text="0.00",
                                         height=34, font=ctk.CTkFont(size=12))
        self._fees_entry.grid(row=2, column=3, padx=12, pady=(0, 8), sticky="ew")

        # Mois / Année
        ym_f = ctk.CTkFrame(card, fg_color="transparent")
        ym_f.grid(row=2, column=4, padx=12, pady=(0, 8), sticky="ew")
        self._t_month_var = ctk.StringVar(value=MONTHS_FR[self._cur_month - 1])
        self._t_year_var  = ctk.StringVar(value=str(self._cur_year))
        ctk.CTkOptionMenu(ym_f, values=MONTHS_FR, variable=self._t_month_var,
                          height=34, width=105,
                          font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(ym_f, values=[str(yr) for yr in range(2015, 2036)],
                          variable=self._t_year_var,
                          height=34, width=72,
                          font=ctk.CTkFont(size=11)).pack(side="left")

        # ── Ligne 2 : notes + bouton ──
        ctk.CTkLabel(card, text="Notes", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=C["muted"]).grid(
            row=3, column=0, columnspan=4, padx=12, pady=(4, 2), sticky="w")

        self._notes_entry = ctk.CTkEntry(card, placeholder_text="Optionnel",
                                          height=34, font=ctk.CTkFont(size=12))
        self._notes_entry.grid(row=4, column=0, columnspan=4,
                                padx=12, pady=(0, 14), sticky="ew")

        ctk.CTkButton(
            card, text="✓  Ajouter", height=34, command=self._on_add,
        ).grid(row=4, column=4, padx=12, pady=(0, 14), sticky="ew")

        self._qty_entry.focus()

    # ── Liste des transactions ─────────────────────────────
    def _render_transactions_list(self, row: int):
        transactions = self._db.get_asset_transactions(self._asset["asset_name"])

        card = ctk.CTkFrame(self._body, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=(10, 12))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=f"Historique — {len(transactions)} transaction(s)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"],
        ).pack(anchor="w", padx=16, pady=(12, 6))

        if not transactions:
            ctk.CTkLabel(
                card,
                text="Aucune transaction enregistrée.\nAjoutez vos premiers achats ci-dessus.",
                text_color=C["muted"], justify="center",
            ).pack(pady=24)
            return

        # En-tête
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=(0, 8))
        inner.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)
        inner.grid_columnconfigure(6, weight=0)

        hdr_f = ctk.CTkFrame(inner, fg_color=C["light"], corner_radius=6)
        hdr_f.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 4))
        hdr_f.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)
        hdr_f.grid_columnconfigure(6, weight=0, minsize=38)
        for i, h in enumerate(["Date", "Type", "Quantité", "Prix unit.", "Frais", "Montant brut", ""]):
            ctk.CTkLabel(hdr_f, text=h, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C["muted"]).grid(
                row=0, column=i, padx=10, pady=6, sticky="w")

        # Lignes (du plus récent au plus ancien)
        for idx, t in enumerate(reversed(transactions)):
            bg      = C["light"] if idx % 2 == 0 else C["card"]
            is_buy  = t["trans_type"] == "achat"
            type_lbl = "🟢 Achat" if is_buy else "🔴 Vente"
            type_clr = C["green"] if is_buy else C["red"]
            date_str = f"{MONTHS_FR[t['month'] - 1][:3]} {t['year']}"
            montant  = float(t["quantity"]) * float(t["unit_price"])

            row_f = ctk.CTkFrame(inner, fg_color=bg, corner_radius=4)
            row_f.grid(row=idx + 1, column=0, columnspan=7, sticky="ew", pady=1)
            row_f.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)
            row_f.grid_columnconfigure(6, weight=0)

            cells = [
                (date_str,                             C["muted"]),
                (type_lbl,                             type_clr),
                (_fmt_qty(float(t["quantity"])),       C["text"]),
                (f"{float(t['unit_price']):,.2f} €",   C["text"]),
                (f"{float(t['fees']):,.2f} €" if t["fees"] else "—", C["muted"]),
                (f"{montant:,.2f} €",                  C["primary"]),
            ]
            for col, (txt, clr) in enumerate(cells):
                ctk.CTkLabel(row_f, text=txt,
                             font=ctk.CTkFont(size=11), text_color=clr).grid(
                    row=0, column=col, padx=10, pady=6, sticky="w")

            # Bouton supprimer
            tid = t["id"]
            ctk.CTkButton(
                row_f, text="✕", width=28, height=24,
                fg_color="#FEE2E2", text_color=C["red"], hover_color="#FECACA",
                command=lambda _tid=tid: self._delete_transaction(_tid),
            ).grid(row=0, column=6, padx=8, pady=4)

            # Notes si présentes
            if t["notes"]:
                ctk.CTkLabel(row_f, text=f"  {t['notes']}",
                             font=ctk.CTkFont(size=10), text_color=C["muted"]).grid(
                    row=1, column=0, columnspan=7, padx=10, pady=(0, 4), sticky="w")

    # ── Callbacks ─────────────────────────────────────────
    def _on_add(self):
        # Validation quantité
        try:
            qty = float(self._qty_entry.get().replace(",", ".").replace(" ", ""))
            if qty <= 0:
                raise ValueError
            self._qty_entry.configure(border_color=C["border"])
        except ValueError:
            self._qty_entry.configure(border_color=C["red"])
            return

        # Validation prix
        try:
            price = float(self._price_entry.get().replace(",", ".").replace(" ", ""))
            if price <= 0:
                raise ValueError
            self._price_entry.configure(border_color=C["border"])
        except ValueError:
            self._price_entry.configure(border_color=C["red"])
            return

        # Frais (optionnel)
        fees_raw = self._fees_entry.get().strip()
        try:
            fees = float(fees_raw.replace(",", ".")) if fees_raw else 0.0
        except ValueError:
            fees = 0.0

        trans_type = "achat" if self._type_var.get() == "Achat" else "vente"
        t_month    = MONTHS_FR.index(self._t_month_var.get()) + 1
        t_year     = int(self._t_year_var.get())
        notes      = self._notes_entry.get().strip()

        # Enregistrement de la transaction
        self._db.add_asset_transaction(
            self._asset["asset_name"], self._asset["asset_type"],
            t_year, t_month, trans_type, qty, price, fees, notes,
        )

        # Mise à jour du cost_basis ET de la valeur dans la table assets.
        # Sur une vente, on réduit la valeur stockée au prorata de la qté
        # vendue (sinon le patrimoine continue d'afficher la valeur d'avant
        # la vente, en doublon avec le cash en attente).
        self._sync_after_transaction(trans_type=trans_type, transacted_qty=qty)
        self._render_all()

    def _delete_transaction(self, trans_id: int):
        # Pour rester safe, on ne réajuste pas la valeur en sens inverse :
        # si l'utilisateur supprime une transaction, qu'il mette la valeur
        # à jour manuellement via le bouton 💰. On recalcule juste le CMUP.
        self._db.delete_asset_transaction(trans_id)
        self._sync_after_transaction(trans_type=None, transacted_qty=0.0)
        self._render_all()

    def _sync_cost_basis(self):
        """Conservé pour compat : ne touche que le cost_basis."""
        self._sync_after_transaction(trans_type=None, transacted_qty=0.0)

    def _sync_after_transaction(self, trans_type: str | None, transacted_qty: float):
        """
        Recalcule le CMUP (cost_basis) après chaque opération.
        Sur une VENTE, ajuste aussi la valeur stockée au prorata de la
        quantité vendue : new_value = old_value × (qty_après / qty_avant).
        Sinon, la valeur reste inchangée (l'utilisateur la met à jour
        manuellement via 💰).
        """
        pos        = self._db.compute_asset_position(self._asset["asset_name"])
        new_cost   = pos["total_cost"]
        old_value  = float(self._asset.get("value") or 0.0)
        new_value  = old_value

        if trans_type == "vente" and transacted_qty > 0:
            qty_after  = pos["qty"]
            qty_before = qty_after + transacted_qty
            if qty_before > 1e-9:
                ratio     = max(qty_after, 0.0) / qty_before
                new_value = old_value * ratio
            else:
                new_value = 0.0

        self._db.update_asset(
            self._asset["id"],
            self._asset["asset_type"],
            self._asset["asset_name"],
            new_value,
            new_cost,
            self._asset.get("notes", ""),
        )
        # Met à jour le snapshot local pour les prochains rendus
        self._asset             = dict(self._asset)
        self._asset["cost_basis"] = new_cost
        self._asset["value"]      = new_value
