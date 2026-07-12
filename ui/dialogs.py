"""
ui/dialogs.py — Fenêtres modales d'édition
"""
import os
import threading
import tkinter as tk
import customtkinter as ctk
from config import C, ASSET_TYPES, MONTHS_FR

# helper pour formatter les quantités sans zéros inutiles
def _fmt_qty(q: float) -> str:
    if q == int(q):
        return str(int(q))
    return f"{q:.6f}".rstrip("0")


def _parse_amount(entry: "ctk.CTkEntry", allow_zero: bool = False,
                  max_val: float = 1_000_000) -> "float | None":
    """
    Parse et valide un montant depuis un CTkEntry.
    Retourne le float si valide, None + bordure rouge sinon.
    Règles : doit être un nombre, > 0 (sauf allow_zero), <= max_val.
    """
    raw = entry.get().replace(",", ".").replace(" ", "").replace(" ", "")
    try:
        value = float(raw)
    except ValueError:
        entry.configure(border_color=C["red"])
        return None
    if not allow_zero and value <= 0:
        entry.configure(border_color=C["red"])
        return None
    if value < 0:
        entry.configure(border_color=C["red"])
        return None
    if value > max_val:
        entry.configure(border_color=C["red"])
        return None
    entry.configure(border_color=C["border"])
    return value


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
        amount = _parse_amount(self._amount)
        if amount is None:
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
        amount = _parse_amount(self._amount)
        if amount is None:
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
        amount = _parse_amount(self._amount)
        if amount is None:
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
    """
    Dialogue d'ajout/modification d'un actif.
    Deux modes selon le type :
      • compte  → Nom + Solde actuel + Notes  (pas de coût d'achat)
      • autres  → Nom + Valeur actuelle + Prix d'achat/Investi + Notes
    """

    _COMPTE_KEYS = {"compte"}   # types traités comme dépôt monétaire

    def __init__(self, parent, initial: dict = None, on_save=None):
        super().__init__(parent,
                         "✏  Modifier l'actif" if initial else "＋  Ajouter un actif",
                         width=560, height=480)
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

        # ── Type d'actif (pleine largeur) ──────────────────
        ctk.CTkLabel(self.body, text="Type d'actif *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=0, column=0, columnspan=2, padx=20, pady=(14, 2), sticky="w")
        self._type_var = ctk.StringVar(value=init_type)
        ctk.CTkOptionMenu(self.body, values=type_names, variable=self._type_var,
                          height=38, font=ctk.CTkFont(size=13),
                          fg_color=C["primary"], button_color=C["primary"],
                          command=self._on_type_change).grid(
            row=1, column=0, columnspan=2, padx=20, sticky="ew")

        # ── Nom (pleine largeur) ────────────────────────────
        self._name = self._field(1, "Nom *", "Ex : Livret A, Bourso+, PEA…",
                                  init.get("asset_name", ""), col=0, colspan=2)

        # ── Valeur / Solde — label dynamique, col=0 ────────
        self._value_lbl = ctk.CTkLabel(
            self.body, text="Solde actuel (€) *",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=C["muted"])
        self._value_lbl.grid(row=4, column=0, padx=20, pady=(14, 2), sticky="w")
        self._value = ctk.CTkEntry(self.body, placeholder_text="0.00",
                                    height=38, font=ctk.CTkFont(size=13))
        self._value.grid(row=5, column=0, padx=20, sticky="ew")
        val_init = str(init.get("value", "") or "")
        if val_init:
            self._value.insert(0, val_init)

        # ── Prix d'achat / Investi — col=1, masqué pour compte ──
        self._cost_lbl = ctk.CTkLabel(
            self.body, text="Prix d'achat / Investi (€)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=C["muted"])
        self._cost_lbl.grid(row=4, column=1, padx=20, pady=(14, 2), sticky="w")
        self._cost_basis = ctk.CTkEntry(self.body, placeholder_text="0.00",
                                         height=38, font=ctk.CTkFont(size=13))
        self._cost_basis.grid(row=5, column=1, padx=20, sticky="ew")
        cost_init = str(init.get("cost_basis", "") or "")
        if cost_init:
            self._cost_basis.insert(0, cost_init)

        # ── Notes (pleine largeur) ──────────────────────────
        self._notes = self._field(3, "Notes", "Optionnel",
                                   init.get("notes", "") or "", col=0, colspan=2)

        # ── Astuce ──────────────────────────────────────────
        ctk.CTkLabel(self.body,
                     text="* champs obligatoires  ·  Entrée pour valider  ·  Échap pour annuler",
                     font=ctk.CTkFont(size=10), text_color=C["muted"]).grid(
            row=8, column=0, columnspan=2, padx=20, pady=(12, 8), sticky="w")

        self._name.focus()
        # Applique l'état initial selon le type sélectionné
        self._on_type_change(init_type)

    # ── Adaptation du formulaire selon le type ─────────────
    def _on_type_change(self, selected_name: str):
        is_compte = self._type_keys.get(selected_name, "") in self._COMPTE_KEYS
        if is_compte:
            # Compte / Épargne : Solde actuel | Total versé (côte à côte)
            # Le "Total versé" permet de calculer les intérêts gagnés = solde - versé
            self._value_lbl.configure(text="Solde actuel (€) *")
            self._value_lbl.grid(row=4, column=0, columnspan=1,
                                  padx=20, pady=(14, 2), sticky="w")
            self._value.grid(row=5, column=0, columnspan=1, padx=20, sticky="ew")
            self._cost_lbl.configure(text="Total versé (€)  — facultatif")
            self._cost_lbl.grid(row=4, column=1, padx=20, pady=(14, 2), sticky="w")
            self._cost_basis.grid(row=5, column=1, padx=20, sticky="ew")
            self._cost_basis.configure(placeholder_text="Ex : 3 000")
        else:
            # Investissement : valeur + coût d'achat côte à côte
            self._value_lbl.configure(text="Valeur actuelle (€) *")
            self._value_lbl.grid(row=4, column=0, columnspan=1,
                                  padx=20, pady=(14, 2), sticky="w")
            self._value.grid(row=5, column=0, columnspan=1, padx=20, sticky="ew")
            self._cost_lbl.configure(text="Prix d'achat / Investi (€)")
            self._cost_lbl.grid(row=4, column=1, padx=20, pady=(14, 2), sticky="w")
            self._cost_basis.grid(row=5, column=1, padx=20, sticky="ew")
            self._cost_basis.configure(placeholder_text="0.00")

    def _on_save(self):
        name = self._name.get().strip()
        if not name:
            self._name.configure(border_color=C["red"])
            return
        value = _parse_amount(self._value, allow_zero=True)
        if value is None:
            return

        # cost_basis = total versé (compte) ou prix d'achat (investissement)
        # Dans les deux cas : facultatif, >= 0
        raw_cb = (self._cost_basis.get() or "0").replace(",", ".").replace(" ", "").replace(" ", "")
        try:
            cost_basis = float(raw_cb) if raw_cb else 0.0
            if cost_basis < 0:
                raise ValueError
        except ValueError:
            self._cost_basis.configure(border_color=C["red"])
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
    """Popup minimaliste pour mettre à jour la valeur ou le solde d'un actif."""

    def __init__(self, parent, asset_name: str, current_value: float,
                 on_save=None, label: str = "valeur"):
        short_name = asset_name if len(asset_name) <= 30 else asset_name[:28] + "…"
        super().__init__(parent, f"💰  Màj {label} — {short_name}",
                         width=420, height=260)
        self._on_save_cb = on_save

        ctk.CTkLabel(self.body,
                     text=f"Compte / Actif : {asset_name}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(
            row=0, column=0, padx=20, pady=(16, 4), sticky="w")

        field_lbl = f"Nouveau {label} (€) *"
        self._value = self._field(1, field_lbl, "0.00", f"{current_value:.2f}")
        self._value.select_range(0, "end")
        self._value.focus()

    def _on_save(self):
        value = _parse_amount(self._value, allow_zero=True)
        if value is None:
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
                command=lambda _tid=tid, _tt=t["trans_type"]: self._delete_transaction(_tid, _tt),
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

        # Frais (optionnel, mais doit être numérique si renseigné)
        fees_raw = self._fees_entry.get().strip()
        try:
            fees = float(fees_raw.replace(",", ".")) if fees_raw else 0.0
            if fees < 0:
                raise ValueError
            self._fees_entry.configure(border_color=C["border"])
        except ValueError:
            self._fees_entry.configure(border_color=C["red"])
            return

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

    def _delete_transaction(self, trans_id: int, trans_type: str = None):
        # Pour rester safe, on ne réajuste pas la valeur en sens inverse :
        # si l'utilisateur supprime une transaction, qu'il mette la valeur
        # à jour manuellement via le bouton 💰. On recalcule juste le CMUP.
        from ui.components import confirm_delete
        def _do():
            self._db.delete_asset_transaction(trans_id)
            self._sync_after_transaction(trans_type=None, transacted_qty=0.0)
            self._render_all()
        warning = (
            "La valeur actuelle de l'actif ne sera pas recalculée "
            "automatiquement — pensez à la mettre à jour via 💰 si nécessaire."
            if trans_type == "vente" else None
        )
        confirm_delete(self, _do, label="cette transaction", extra_warning=warning)

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


# ──────────────────────────────────────────────────────────
#  Dialogue: Ajouter / Modifier une récurrente
# ──────────────────────────────────────────────────────────
class RecurringEditDialog(_BaseDialog):
    """Formulaire d'édition d'une transaction récurrente."""

    def __init__(self, parent, categories: list, initial: dict = None,
                 on_save=None):
        is_edit = initial is not None
        super().__init__(
            parent,
            "✏  Modifier la récurrente" if is_edit else "＋  Nouvelle récurrente",
            width=500, height=420,
        )
        self._on_save_cb = on_save
        init = initial or {}
        self._cats = categories  # list of dicts with 'id' and 'name'
        self._cat_names = [c["name"] for c in categories]

        # ── Type (Dépense / Revenu) ──────────────────────
        ctk.CTkLabel(self.body, text="Type *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=0, column=0, padx=20, pady=(14, 2), sticky="w")
        self._type_var = ctk.StringVar(
            value="Dépense" if init.get("type", "expense") == "expense" else "Revenu"
        )
        ctk.CTkOptionMenu(
            self.body, values=["Dépense", "Revenu"],
            variable=self._type_var, height=38,
            font=ctk.CTkFont(size=13),
            command=self._on_type_change,
        ).grid(row=1, column=0, padx=20, sticky="ew")

        # ── Label ────────────────────────────────────────
        self._label = self._field(1, "Libellé *", "Ex : Loyer, Netflix…",
                                  init.get("label", ""))

        # ── Montant ──────────────────────────────────────
        self._amount = self._field(2, "Montant par défaut (€) *", "0.00",
                                   str(init.get("amount", "")))

        # ── Catégorie (dépense) ──────────────────────────
        self._cat_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        self._cat_frame.grid(row=6, column=0, padx=20, pady=(14, 2), sticky="ew")
        self._cat_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._cat_frame, text="Catégorie *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(row=0, column=0, sticky="w")
        init_cat = init.get("cat_name", self._cat_names[0] if self._cat_names else "")
        self._cat_var = ctk.StringVar(value=init_cat)
        self._cat_menu = ctk.CTkOptionMenu(
            self._cat_frame, values=self._cat_names or ["—"],
            variable=self._cat_var, height=38, font=ctk.CTkFont(size=13),
        )
        self._cat_menu.grid(row=1, column=0, sticky="ew")

        # ── Enseigne (dépense) ───────────────────────────
        self._payee_lbl = ctk.CTkLabel(self.body, text="Enseigne",
                                        font=ctk.CTkFont(size=11, weight="bold"),
                                        text_color=C["muted"])
        self._payee_lbl.grid(row=8, column=0, padx=20, pady=(14, 2), sticky="w")
        self._payee = ctk.CTkEntry(self.body, placeholder_text="Ex : EDF, Orange…",
                                    height=38, font=ctk.CTkFont(size=13))
        self._payee.grid(row=9, column=0, padx=20, sticky="ew")
        if init.get("payee"):
            self._payee.insert(0, init["payee"])

        # ── Source (revenu) ──────────────────────────────
        self._source_lbl = ctk.CTkLabel(self.body, text="Source",
                                         font=ctk.CTkFont(size=11, weight="bold"),
                                         text_color=C["muted"])
        self._source_lbl.grid(row=10, column=0, padx=20, pady=(14, 2), sticky="w")
        self._source = ctk.CTkEntry(self.body, placeholder_text="Ex : Salaire, Loyer perçu…",
                                     height=38, font=ctk.CTkFont(size=13))
        self._source.grid(row=11, column=0, padx=20, sticky="ew")
        if init.get("source"):
            self._source.insert(0, init["source"])

        self._on_type_change(self._type_var.get())
        self._label.focus()

    def _on_type_change(self, val: str):
        is_expense = (val == "Dépense")
        if is_expense:
            self._cat_frame.grid()
            self._cat_menu.grid()
            self._payee_lbl.grid()
            self._payee.grid()
            self._source_lbl.grid_remove()
            self._source.grid_remove()
        else:
            self._cat_frame.grid_remove()
            self._cat_menu.grid_remove()
            self._payee_lbl.grid_remove()
            self._payee.grid_remove()
            self._source_lbl.grid()
            self._source.grid()

    def _on_save(self):
        label = self._label.get().strip()
        if not label:
            self._label.configure(border_color=C["red"])
            return
        amount = _parse_amount(self._amount)
        if amount is None:
            return
        is_expense = self._type_var.get() == "Dépense"
        cat_id = None
        if is_expense and self._cats:
            sel = self._cat_var.get()
            cat_id = next((c["id"] for c in self._cats if c["name"] == sel), None)
        if self._on_save_cb:
            self._on_save_cb({
                "label":      label,
                "amount":     amount,
                "type":       "expense" if is_expense else "revenue",
                "category_id": cat_id,
                "cat_name":   self._cat_var.get() if is_expense else "",
                "source":     self._source.get().strip(),
                "payee":      self._payee.get().strip(),
            })
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Gestionnaire des récurrentes
# ──────────────────────────────────────────────────────────
class RecurringManagerDialog(ctk.CTkToplevel):
    """Liste CRUD de toutes les transactions récurrentes."""

    def __init__(self, parent, db, on_change=None):
        super().__init__(parent)
        self.title("⚙  Transactions récurrentes")
        self.geometry("700x540")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()
        self._db = db
        self._on_change = on_change

        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=C["sidebar"], corner_radius=0)
        hdr.pack(fill="x")
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="Transactions récurrentes",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").pack(side="left", padx=20, pady=14)
        ctk.CTkButton(
            hdr, text="＋  Ajouter", width=120, height=34,
            command=self._add_new,
        ).pack(side="right", padx=12, pady=10)

        # ── Footer ──
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0,
                               border_width=1, border_color=C["border"])
        footer.pack(fill="x", side="bottom")
        ctk.CTkButton(footer, text="Fermer", width=110, height=38,
                      fg_color=C["light"], text_color=C["text"],
                      hover_color=C["border"],
                      command=self.destroy).pack(side="right", padx=12, pady=10)

        # ── Corps scrollable ──
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0)
        self._scroll.pack(fill="both", expand=True)
        self._scroll.grid_columnconfigure(0, weight=1)
        self._render()

    def _render(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        rows = self._db.get_recurring_transactions()
        if not rows:
            ctk.CTkLabel(self._scroll,
                         text="Aucune transaction récurrente.\nCliquez ＋ Ajouter pour commencer.",
                         font=ctk.CTkFont(size=13), text_color=C["muted"],
                         justify="center").grid(row=0, column=0, pady=60)
            return

        for i, r in enumerate(rows):
            bg = C["card"] if i % 2 == 0 else C["light"]
            row_f = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=6)
            row_f.grid(row=i, column=0, sticky="ew", padx=8, pady=3)
            row_f.grid_columnconfigure(2, weight=1)

            # Badge type
            is_exp = r["type"] == "expense"
            badge_text = "💸 Dépense" if is_exp else "💰 Revenu"
            badge_color = C.get("red_soft", "#FDECEA") if is_exp else C.get("green_soft", "#E8F5E9")
            badge_fg = C["red"] if is_exp else C["green"]
            ctk.CTkLabel(row_f, text=badge_text, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=badge_fg, fg_color=badge_color,
                         corner_radius=4, width=90).grid(
                row=0, column=0, padx=(12, 6), pady=12)

            # Libellé + catégorie/source
            sub = r["cat_name"] or r["source"] or r["payee"] or ""
            label_text = r["label"] + (f"\n{sub}" if sub else "")
            ctk.CTkLabel(row_f, text=label_text,
                         font=ctk.CTkFont(size=12),
                         text_color=C["text"],
                         justify="left", anchor="w").grid(
                row=0, column=2, padx=8, pady=12, sticky="w")

            # Montant
            ctk.CTkLabel(row_f, text=f"{r['amount']:,.2f} €",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=C["text"]).grid(row=0, column=3, padx=8)

            # Toggle actif
            active_var = ctk.BooleanVar(value=bool(r["active"]))
            rec_id = r["id"]

            def _toggle(v=active_var, rid=rec_id, row_data=dict(r)):
                self._db.update_recurring(
                    rid, row_data["label"], row_data["amount"], row_data["type"],
                    row_data["category_id"], row_data["source"] or "",
                    row_data["payee"] or "", 1 if v.get() else 0,
                )
                if self._on_change:
                    self._on_change()

            ctk.CTkSwitch(row_f, text="", variable=active_var,
                          command=_toggle, width=46).grid(row=0, column=4, padx=6)

            # Boutons édition / suppression
            btn_f = ctk.CTkFrame(row_f, fg_color="transparent")
            btn_f.grid(row=0, column=5, padx=8)

            def _edit(row_data=dict(r)):
                self._open_edit(row_data)

            def _del(rid=rec_id):
                self._db.delete_recurring(rid)
                if self._on_change:
                    self._on_change()
                self._render()

            ctk.CTkButton(btn_f, text="✏", width=34, height=30,
                          fg_color=C["primary"],
                          font=ctk.CTkFont(size=12),
                          command=_edit).pack(side="left", padx=2)
            ctk.CTkButton(btn_f, text="🗑", width=34, height=30,
                          fg_color=C["red"],
                          font=ctk.CTkFont(size=12),
                          command=_del).pack(side="left", padx=2)

    def _get_cats(self):
        return [{"id": c["id"], "name": c["name"]}
                for c in self._db.get_categories()]

    def _add_new(self):
        RecurringEditDialog(self, self._get_cats(), on_save=self._save_new)

    def _open_edit(self, row_data: dict):
        RecurringEditDialog(self, self._get_cats(), initial=row_data,
                            on_save=lambda d: self._save_edit(row_data["id"], d))

    def _save_new(self, data: dict):
        self._db.add_recurring(
            data["label"], data["amount"], data["type"],
            data.get("category_id"), data.get("source", ""), data.get("payee", ""),
        )
        if self._on_change:
            self._on_change()
        self._render()

    def _save_edit(self, rec_id: int, data: dict):
        self._db.update_recurring(
            rec_id, data["label"], data["amount"], data["type"],
            data.get("category_id"), data.get("source", ""),
            data.get("payee", ""), 1,
        )
        if self._on_change:
            self._on_change()
        self._render()


# ──────────────────────────────────────────────────────────
#  Dialogue: Appliquer les récurrentes du mois
# ──────────────────────────────────────────────────────────
class RecurringApplyDialog(ctk.CTkToplevel):
    """
    Affiche les transactions récurrentes en attente pour un mois donné.
    L'utilisateur peut cocher/décocher chaque ligne et ajuster les montants
    avant de valider.
    """

    def __init__(self, parent, db, year: int, month: int,
                 month_label: str, on_applied=None):
        super().__init__(parent)
        self.title(f"📅 Récurrentes — {month_label}")
        self.geometry("660x520")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()

        self._db = db
        self._year = year
        self._month = month
        self._on_applied = on_applied
        self._rows: list[dict] = []  # état UI de chaque ligne

        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=C["sidebar"], corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"Transactions récurrentes — {month_label}",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").pack(anchor="w", padx=20, pady=14)

        # ── Footer ──
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0,
                               border_width=1, border_color=C["border"])
        footer.pack(fill="x", side="bottom")
        ctk.CTkButton(footer, text="Annuler", width=110, height=38,
                      fg_color=C["light"], text_color=C["text"],
                      hover_color=C["border"],
                      command=self.destroy).pack(side="right", padx=8, pady=10)
        self._apply_btn = ctk.CTkButton(
            footer, text="✓  Appliquer la sélection",
            width=190, height=38,
            command=self._on_apply,
        )
        self._apply_btn.pack(side="right", padx=(0, 4), pady=10)

        # ── Corps ──
        pending = db.get_pending_recurring(year, month)

        if not pending:
            ctk.CTkLabel(self,
                         text="✅  Toutes les récurrentes ont déjà été appliquées\npour ce mois.",
                         font=ctk.CTkFont(size=14), text_color=C["muted"],
                         justify="center").pack(expand=True)
            self._apply_btn.configure(state="disabled")
            return

        intro = ctk.CTkLabel(
            self,
            text=(f"{len(pending)} transaction(s) à appliquer ce mois-ci.\n"
                  "Ajustez les montants si nécessaire, décochez ce que vous voulez ignorer."),
            font=ctk.CTkFont(size=12), text_color=C["muted"], justify="left",
        )
        intro.pack(anchor="w", padx=20, pady=(10, 0))

        scroll = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=0, pady=8)
        scroll.grid_columnconfigure(2, weight=1)

        # En-tête colonnes
        for col, txt in enumerate(["", "Type", "Libellé", "Montant (€)"]):
            ctk.CTkLabel(scroll, text=txt,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C["muted"]).grid(
                row=0, column=col, padx=(12 if col == 0 else 6, 6),
                pady=(8, 4), sticky="w")

        for i, rec in enumerate(pending):
            row_idx = i + 1
            bg = C["card"] if i % 2 == 0 else C["light"]

            row_f = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=4)
            row_f.grid(row=row_idx, column=0, columnspan=4,
                       sticky="ew", padx=8, pady=2)
            row_f.grid_columnconfigure(2, weight=1)

            # Checkbox sélection
            checked = ctk.BooleanVar(value=True)
            chk = ctk.CTkCheckBox(row_f, text="", variable=checked,
                                   width=28, height=28)
            chk.grid(row=0, column=0, padx=(10, 4), pady=10)

            # Badge type
            is_exp = rec["type"] == "expense"
            badge_text = "💸 Dép." if is_exp else "💰 Rev."
            badge_clr = C["red"] if is_exp else C["green"]
            ctk.CTkLabel(row_f, text=badge_text,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=badge_clr, width=62).grid(
                row=0, column=1, padx=4)

            # Libellé
            sub = rec["cat_name"] or rec["source"] or rec["payee"] or ""
            full_label = rec["label"] + (f"  •  {sub}" if sub else "")
            ctk.CTkLabel(row_f, text=full_label,
                         font=ctk.CTkFont(size=12), text_color=C["text"],
                         anchor="w").grid(row=0, column=2, padx=8, sticky="w")

            # Montant éditable
            amt_entry = ctk.CTkEntry(row_f, width=110, height=34,
                                      font=ctk.CTkFont(size=13))
            amt_entry.insert(0, f"{rec['amount']:.2f}")
            amt_entry.grid(row=0, column=3, padx=(4, 12), pady=10)

            self._rows.append({
                "rec_id": rec["id"],
                "checked": checked,
                "amount_entry": amt_entry,
                "default_amount": rec["amount"],
            })

    def _on_apply(self):
        applied = 0
        errors = []
        for row in self._rows:
            if not row["checked"].get():
                continue
            raw = row["amount_entry"].get().replace(",", ".").strip()
            try:
                amount = float(raw)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                row["amount_entry"].configure(border_color=C["red"])
                errors.append(row["rec_id"])
                continue
            row["amount_entry"].configure(border_color=C["border"])
            self._db.apply_recurring(row["rec_id"], self._year, self._month, amount)
            applied += 1

        if errors:
            return  # ne ferme pas si des montants sont invalides

        if self._on_applied:
            self._on_applied(applied)
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Passif / Dette
# ──────────────────────────────────────────────────────────
class LiabilityDialog(_BaseDialog):
    """Dialogue d'ajout ou de modification d'un passif (dette)."""

    def __init__(self, parent, initial: dict = None, on_save=None):
        from config import LIABILITY_TYPES
        is_edit = initial is not None
        super().__init__(parent,
                         "✏  Modifier le passif" if is_edit else "＋  Ajouter un passif",
                         width=500, height=440)
        self._on_save_cb = on_save
        self._is_edit    = is_edit
        init = initial or {}

        self._type_keys = {label: key for label, key in LIABILITY_TYPES}
        type_labels     = [label for label, _ in LIABILITY_TYPES]
        init_key        = init.get("liability_type", "autre")
        init_label      = next((l for l, k in LIABILITY_TYPES if k == init_key), type_labels[0])

        # ── body à 2 colonnes ────────────────────────────────
        self.body.grid_columnconfigure((0, 1), weight=1)

        # Row 0-1 : Type (colonne 0) + Nom (colonne 1)
        ctk.CTkLabel(self.body, text="Type de dette *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=0, column=0, padx=(20, 8), pady=(16, 2), sticky="w")
        self._type_var = ctk.StringVar(value=init_label)
        ctk.CTkOptionMenu(self.body, values=type_labels, variable=self._type_var,
                          height=38, font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=(20, 8), sticky="ew")

        ctk.CTkLabel(self.body, text="Nom du passif *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=0, column=1, padx=(8, 20), pady=(16, 2), sticky="w")
        self._name = ctk.CTkEntry(self.body,
                                   placeholder_text="Ex : Prêt Cetelem, Crédit auto…",
                                   height=38, font=ctk.CTkFont(size=13),
                                   state="disabled" if is_edit else "normal")
        self._name.grid(row=1, column=1, padx=(8, 20), sticky="ew")
        if init.get("liability_name"):
            self._name.configure(state="normal")
            self._name.insert(0, init["liability_name"])
            if is_edit:
                self._name.configure(state="disabled")

        # Row 2-3 : Capital restant dû (col 0) + Mensualité (col 1)
        ctk.CTkLabel(self.body, text="Capital restant dû (€) *",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=2, column=0, padx=(20, 8), pady=(14, 2), sticky="w")
        self._capital = ctk.CTkEntry(self.body, placeholder_text="Ex : 12 000",
                                     height=38, font=ctk.CTkFont(size=13))
        self._capital.grid(row=3, column=0, padx=(20, 8), sticky="ew")
        if init.get("remaining_capital") is not None and init["remaining_capital"] != "":
            self._capital.insert(0, str(init["remaining_capital"]))

        ctk.CTkLabel(self.body, text="Mensualité (€)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=2, column=1, padx=(8, 20), pady=(14, 2), sticky="w")
        self._monthly = ctk.CTkEntry(self.body, placeholder_text="Ex : 250",
                                     height=38, font=ctk.CTkFont(size=13))
        self._monthly.grid(row=3, column=1, padx=(8, 20), sticky="ew")
        if init.get("monthly_payment"):
            self._monthly.insert(0, str(init["monthly_payment"]))

        # Row 4-5 : Date de fin (pleine largeur)
        ctk.CTkLabel(self.body, text="Date de fin (MM/AAAA)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=4, column=0, columnspan=2, padx=20, pady=(14, 2), sticky="w")
        self._end_date = ctk.CTkEntry(self.body, placeholder_text="Ex : 06/2029",
                                      height=38, font=ctk.CTkFont(size=13))
        self._end_date.grid(row=5, column=0, columnspan=2, padx=20, sticky="ew")
        if init.get("end_date"):
            self._end_date.insert(0, init["end_date"])

        # Row 6-7 : Notes
        ctk.CTkLabel(self.body, text="Notes",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=6, column=0, columnspan=2, padx=20, pady=(14, 2), sticky="w")
        self._notes = ctk.CTkEntry(self.body, placeholder_text="Optionnel",
                                   height=38, font=ctk.CTkFont(size=13))
        self._notes.grid(row=7, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="ew")
        if init.get("notes"):
            self._notes.insert(0, init["notes"])

        self._capital.focus()

    def _on_save(self):
        # Nom : récupéré même si disabled
        name = (self._name.get() if not self._is_edit
                else self._name.cget("placeholder_text")).strip()
        # En mode édition le nom est stocké dans le champ (on réactive brièvement)
        if self._is_edit:
            self._name.configure(state="normal")
            name = self._name.get().strip()
            self._name.configure(state="disabled")

        if not name:
            return

        capital_raw = self._capital.get().replace(",", ".").replace(" ", "").replace(" ", "")
        try:
            capital = float(capital_raw)
        except ValueError:
            self._capital.configure(border_color=C["red"])
            return
        if capital < 0:
            self._capital.configure(border_color=C["red"])
            return
        self._capital.configure(border_color=C["border"])

        monthly_raw = self._monthly.get().replace(",", ".").replace(" ", "").strip()
        try:
            monthly = float(monthly_raw) if monthly_raw else 0.0
        except ValueError:
            monthly = 0.0

        if self._on_save_cb:
            self._on_save_cb({
                "liability_type":    self._type_keys.get(self._type_var.get(), "autre"),
                "liability_name":    name,
                "remaining_capital": capital,
                "monthly_payment":   monthly,
                "end_date":          self._end_date.get().strip(),
                "notes":             self._notes.get().strip(),
            })
        self.destroy()


# ──────────────────────────────────────────────────────────
#  Dialogue: Clôture de mois guidée (wizard 4 étapes)
# ──────────────────────────────────────────────────────────
class MonthCloseDialog(ctk.CTkToplevel):
    """
    Assistant de clôture de mois — wizard 4 étapes :
      1. Bilan / vérification de la saisie
      2. Actifs — rappel de mise à jour
      3. Rapport PDF
      4. Résumé final
    """

    _STEPS = [
        ("📋", "Bilan"),
        ("💰", "Actifs"),
        ("📄", "Rapport PDF"),
        ("✅", "Résumé"),
    ]

    def __init__(self, parent, db, app, year: int, month: int,
                 on_close=None):
        super().__init__(parent)
        self._db       = db
        self._app      = app
        self._year     = year
        self._month    = month
        self._on_close = on_close
        self._step     = 0          # étape courante (0-based)
        self._pdf_path = None       # chemin du PDF généré

        month_label = f"{MONTHS_FR[month - 1]} {year}"
        self.title(f"Clôture du mois — {month_label}")
        self.geometry("780x540")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()

        # ── Layout principal ─────────────────────────────
        self._outer = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self._outer.pack(fill="both", expand=True)
        self._outer.grid_columnconfigure(1, weight=1)
        self._outer.grid_rowconfigure(0, weight=1)

        # ── Panneau gauche : stepper ─────────────────────
        self._side = ctk.CTkFrame(self._outer, fg_color=C["sidebar"],
                                   corner_radius=0, width=180)
        self._side.grid(row=0, column=0, sticky="nsew")
        self._side.grid_propagate(False)

        ctk.CTkLabel(self._side,
                     text=f"🗓  {month_label}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#A5B4FC").pack(anchor="w", padx=18, pady=(22, 18))

        self._step_labels = []
        for i, (icon, label) in enumerate(self._STEPS):
            f = ctk.CTkFrame(self._side, fg_color="transparent", corner_radius=8)
            f.pack(fill="x", padx=10, pady=2)
            lbl = ctk.CTkLabel(f, text=f"  {icon}  {label}",
                               font=ctk.CTkFont(size=12),
                               text_color="#94A3B8", anchor="w",
                               height=36)
            lbl.pack(fill="x", padx=4)
            self._step_labels.append((f, lbl))

        # ── Panneau droit : contenu ──────────────────────
        right = ctk.CTkFrame(self._outer, fg_color="transparent", corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._content = ctk.CTkScrollableFrame(right, fg_color=C["bg"],
                                                corner_radius=0)
        self._content.grid(row=0, column=0, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)

        # ── Footer : navigation ──────────────────────────
        footer = ctk.CTkFrame(self._outer, fg_color=C["card"], corner_radius=0,
                               border_width=1, border_color=C["border"])
        footer.grid(row=1, column=0, columnspan=2, sticky="ew")

        self._prev_btn = ctk.CTkButton(
            footer, text="← Précédent", width=130, height=38,
            fg_color=C["light"], text_color=C["text"],
            hover_color=C["border"], command=self._prev,
        )
        self._prev_btn.pack(side="left", padx=12, pady=10)

        self._next_btn = ctk.CTkButton(
            footer, text="Suivant →", width=140, height=38,
            command=self._next,
        )
        self._next_btn.pack(side="right", padx=12, pady=10)

        ctk.CTkButton(
            footer, text="Fermer", width=100, height=38,
            fg_color=C["light"], text_color=C["muted"],
            hover_color=C["border"], command=self._close,
        ).pack(side="right", padx=(0, 6), pady=10)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _: self._close())
        self._render()

    # ── Navigation ────────────────────────────────────────
    def _prev(self):
        if self._step > 0:
            self._step -= 1
            self._render()

    def _next(self):
        if self._step < len(self._STEPS) - 1:
            self._step += 1
            self._render()
        else:
            self._close()

    def _close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        cb = self._on_close
        self.destroy()
        if cb:
            cb()

    # ── Rendu général ─────────────────────────────────────
    def _render(self):
        # Vider le contenu
        for w in self._content.winfo_children():
            w.destroy()

        # Mettre à jour le stepper
        for i, (f, lbl) in enumerate(self._step_labels):
            if i < self._step:
                f.configure(fg_color="transparent")
                lbl.configure(text_color="#A5B4FC",
                              font=ctk.CTkFont(size=12))
            elif i == self._step:
                f.configure(fg_color=C["sidebar2"])
                lbl.configure(text_color="white",
                              font=ctk.CTkFont(size=12, weight="bold"))
            else:
                f.configure(fg_color="transparent")
                lbl.configure(text_color="#475569",
                              font=ctk.CTkFont(size=12))

        # Bouton Précédent
        self._prev_btn.configure(state="normal" if self._step > 0 else "disabled")

        # Bouton Suivant / Terminer
        if self._step == len(self._STEPS) - 1:
            self._next_btn.configure(text="✓  Terminer", fg_color=C["green"])
        else:
            self._next_btn.configure(text="Suivant →", fg_color=C["primary"])

        # Dispatcher par étape
        [self._step_bilan,
         self._step_actifs,
         self._step_rapport,
         self._step_resume][self._step]()

    # ──────────────────────────────────────────────────────
    #  Étape 1 — Bilan / vérification de la saisie
    # ──────────────────────────────────────────────────────
    def _step_bilan(self):
        y, m, db = self._year, self._month, self._db
        rev  = sum(r["amount"] for r in db.get_revenues(y, m))
        exp  = sum(r["amount"] for r in db.get_expenses(y, m))
        sav  = sum(r["amount"] for r in db.get_savings(y, m))
        rec  = db.get_pending_recurring(y, m)

        ctk.CTkLabel(self._content,
                     text="📋  Vérification de la saisie",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(self._content,
                     text="Contrôlez que toutes les données du mois sont bien renseignées.",
                     font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(
            anchor="w", padx=24, pady=(0, 16))

        checks = [
            (rev > 0,    "Revenus saisis",         f"{rev:,.2f} €" if rev else "Aucun revenu"),
            (exp > 0,    "Dépenses saisies",        f"{exp:,.2f} €" if exp else "Aucune dépense"),
            (sav > 0,    "Épargne saisie",          f"{sav:,.2f} €" if sav else "Aucun versement"),
            (len(rec) == 0, "Récurrentes appliquées",
             "Tout appliqué ✓" if not rec else f"{len(rec)} en attente"),
        ]

        for ok, label, detail in checks:
            row = ctk.CTkFrame(self._content,
                               fg_color="#F0FDF4" if ok else "#FFF7ED",
                               corner_radius=10,
                               border_width=1,
                               border_color="#86EFAC" if ok else "#FED7AA")
            row.pack(fill="x", padx=24, pady=4)
            row.grid_columnconfigure(1, weight=1)

            icon = "✅" if ok else "⚠️"
            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=18),
                         width=40).grid(row=0, column=0, padx=(12, 4), pady=12)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=C["text"]).grid(row=0, column=1, sticky="w", pady=12)
            ctk.CTkLabel(row, text=detail,
                         font=ctk.CTkFont(size=12),
                         text_color=C["green"] if ok else "#B45309").grid(
                row=0, column=2, padx=16, pady=12)

        # Si des récurrentes sont en attente → bouton direct
        if rec:
            def _open_rec():
                from ui.dialogs import RecurringApplyDialog
                month_label = f"{MONTHS_FR[m - 1]} {y}"
                RecurringApplyDialog(
                    self, db, y, m, month_label,
                    on_applied=lambda n: self._render(),
                )
            ctk.CTkButton(
                self._content,
                text=f"📅  Appliquer les {len(rec)} récurrente(s) en attente",
                height=36, fg_color=C["primary"],
                command=_open_rec,
            ).pack(anchor="w", padx=24, pady=(12, 0))

        # Bilan résumé
        bilan = rev - exp
        sep = ctk.CTkFrame(self._content, fg_color=C["border"], height=1)
        sep.pack(fill="x", padx=24, pady=(20, 12))

        summary = ctk.CTkFrame(self._content, fg_color=C["card"],
                                corner_radius=10, border_width=1,
                                border_color=C["border"])
        summary.pack(fill="x", padx=24, pady=(0, 20))
        summary.grid_columnconfigure((0, 1, 2, 3), weight=1)

        kpis = [
            ("Revenus",  f"{rev:,.0f} €",   C["green"]),
            ("Dépenses", f"{exp:,.0f} €",   C["red"]),
            ("Épargne",  f"{sav:,.0f} €",   C["blue"]),
            ("Bilan",    f"{bilan:+,.0f} €", C["green"] if bilan >= 0 else C["red"]),
        ]
        for i, (t, v, clr) in enumerate(kpis):
            f = ctk.CTkFrame(summary, fg_color="transparent")
            f.grid(row=0, column=i, padx=16, pady=14, sticky="ew")
            ctk.CTkLabel(f, text=t, font=ctk.CTkFont(size=10),
                         text_color=C["muted"]).pack(anchor="w")
            ctk.CTkLabel(f, text=v, font=ctk.CTkFont(size=16, weight="bold"),
                         text_color=clr).pack(anchor="w")

    # ──────────────────────────────────────────────────────
    #  Étape 2 — Actifs : rappel de mise à jour
    # ──────────────────────────────────────────────────────
    def _step_actifs(self):
        y, m, db = self._year, self._month, self._db
        all_assets = db.get_assets_current()
        stale      = [a for a in all_assets
                      if a["year"] != y or a["month"] != m]
        up_to_date = [a for a in all_assets
                      if a["year"] == y and a["month"] == m]

        ctk.CTkLabel(self._content,
                     text="💰  Mise à jour des actifs",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=24, pady=(20, 4))

        if not stale:
            ctk.CTkLabel(self._content,
                         text="✅  Tous vos actifs ont été mis à jour ce mois-ci.",
                         font=ctk.CTkFont(size=13), text_color=C["green"]).pack(
                anchor="w", padx=24, pady=(0, 12))
        else:
            ctk.CTkLabel(self._content,
                         text=f"{len(stale)} actif(s) n'ont pas été mis à jour ce mois-ci ↓",
                         font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(
                anchor="w", padx=24, pady=(0, 12))

            for asset in stale:
                last = f"{MONTHS_FR[asset['month']-1][:3]}. {asset['year']}"
                row = ctk.CTkFrame(self._content, fg_color=C["card"],
                                   corner_radius=10, border_width=1,
                                   border_color="#FED7AA")
                row.pack(fill="x", padx=24, pady=3)
                row.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(row, text="⚠️", font=ctk.CTkFont(size=16),
                             width=36).grid(row=0, column=0, padx=(10, 4), pady=10)
                inner = ctk.CTkFrame(row, fg_color="transparent")
                inner.grid(row=0, column=1, sticky="w", pady=10)
                ctk.CTkLabel(inner, text=asset["asset_name"],
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color=C["text"]).pack(anchor="w")
                ctk.CTkLabel(inner,
                             text=f"Dernière valeur : {asset['value']:,.2f} €  ·  {last}",
                             font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(anchor="w")

                def _update(a=asset):
                    from ui.dialogs import QuickValueUpdateDialog
                    is_compte = (a["asset_type"] == "compte")
                    QuickValueUpdateDialog(
                        self, a["asset_name"], a["value"],
                        on_save=lambda v, aid=a["id"]: (
                            db.update_asset_value(aid, v),
                            self._render(),
                        ),
                        label="solde" if is_compte else "valeur",
                    )
                ctk.CTkButton(row, text="💰  Mettre à jour", width=140, height=32,
                              fg_color="#F0FDF4", text_color=C["green"],
                              hover_color="#DCFCE7",
                              command=_update).grid(row=0, column=2, padx=12, pady=10)

        if up_to_date:
            sep = ctk.CTkFrame(self._content, fg_color=C["border"], height=1)
            sep.pack(fill="x", padx=24, pady=(14, 10))
            ctk.CTkLabel(self._content,
                         text=f"✅  {len(up_to_date)} actif(s) déjà à jour ce mois-ci",
                         font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(
                anchor="w", padx=24, pady=(0, 16))

    # ──────────────────────────────────────────────────────
    #  Étape 3 — Rapport PDF
    # ──────────────────────────────────────────────────────
    def _step_rapport(self):
        y, m = self._year, self._month
        month_label = f"{MONTHS_FR[m - 1]}_{y}"

        ctk.CTkLabel(self._content,
                     text="📄  Générer le rapport PDF",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(self._content,
                     text="Exportez un résumé complet du mois en PDF (revenus, dépenses, épargne, patrimoine).",
                     font=ctk.CTkFont(size=12), text_color=C["muted"],
                     wraplength=520, justify="left").pack(anchor="w", padx=24, pady=(0, 20))

        # Carte principale
        card = ctk.CTkFrame(self._content, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", padx=24, pady=(0, 16))
        card.grid_columnconfigure(0, weight=1)

        # Nom de fichier
        ctk.CTkLabel(card, text="Nom du fichier",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C["muted"]).grid(
            row=0, column=0, padx=20, pady=(16, 4), sticky="w")
        default_name = f"Fintrack_{month_label}.pdf"
        name_var = tk.StringVar(value=default_name)
        ctk.CTkEntry(card, textvariable=name_var, height=36,
                     font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=20, pady=(0, 14), sticky="ew")

        # Statut
        status_lbl = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=12),
                                   text_color=C["muted"])
        status_lbl.grid(row=2, column=0, padx=20, pady=(0, 6), sticky="w")

        if self._pdf_path and os.path.exists(self._pdf_path):
            status_lbl.configure(
                text=f"✅  Rapport généré : {os.path.basename(self._pdf_path)}",
                text_color=C["green"])

        def _generate():
            import tkinter.filedialog as fd
            fname = name_var.get().strip() or default_name
            if not fname.endswith(".pdf"):
                fname += ".pdf"
            dest = fd.asksaveasfilename(
                parent=self,
                title="Enregistrer le rapport PDF",
                initialfile=fname,
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
            )
            if not dest:
                return

            status_lbl.configure(text="⏳  Génération en cours…", text_color=C["muted"])
            gen_btn.configure(state="disabled")

            def _worker():
                try:
                    from utils_pdf import generate_monthly_report
                    generate_monthly_report(self._db, y, m, dest)
                    self._pdf_path = dest
                    self.after(0, lambda: (
                        status_lbl.configure(
                            text=f"✅  Rapport enregistré : {os.path.basename(dest)}",
                            text_color=C["green"]),
                        gen_btn.configure(state="normal"),
                    ))
                except Exception as e:
                    self.after(0, lambda: (
                        status_lbl.configure(
                            text=f"❌  Erreur : {e}",
                            text_color=C["red"]),
                        gen_btn.configure(state="normal"),
                    ))

            threading.Thread(target=_worker, daemon=True).start()

        gen_btn = ctk.CTkButton(
            card, text="📄  Générer et enregistrer le PDF",
            height=40, font=ctk.CTkFont(size=13, weight="bold"),
            command=_generate,
        )
        gen_btn.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")

        # Info : étape facultative
        ctk.CTkLabel(self._content,
                     text="ℹ️  Cette étape est facultative. Vous pouvez également générer le PDF\n"
                          "à tout moment depuis Paramètres → Rapport PDF.",
                     font=ctk.CTkFont(size=11), text_color=C["muted"],
                     justify="left").pack(anchor="w", padx=24, pady=(0, 16))

    # ──────────────────────────────────────────────────────
    #  Étape 4 — Résumé final
    # ──────────────────────────────────────────────────────
    def _step_resume(self):
        y, m, db = self._year, self._month, self._db

        # ── Verrouiller définitivement le mois ──────────────
        db.close_month(y, m)

        rev  = sum(r["amount"] for r in db.get_revenues(y, m))
        exp  = sum(r["amount"] for r in db.get_expenses(y, m))
        sav  = sum(r["amount"] for r in db.get_savings(y, m))
        bilan = rev - exp
        total_pat = sum(a["value"] for a in db.get_assets_current())
        month_label = f"{MONTHS_FR[m - 1]} {y}"

        ctk.CTkLabel(self._content,
                     text=f"✅  Clôture de {month_label}",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(self._content,
                     text="Voici le récapitulatif définitif du mois.",
                     font=ctk.CTkFont(size=12), text_color=C["muted"]).pack(
            anchor="w", padx=24, pady=(0, 16))

        # KPIs principaux
        kpi_card_f = ctk.CTkFrame(self._content, fg_color=C["card"],
                                   corner_radius=12, border_width=1,
                                   border_color=C["border"])
        kpi_card_f.pack(fill="x", padx=24, pady=(0, 12))
        kpi_card_f.grid_columnconfigure((0, 1, 2, 3), weight=1)

        kpis = [
            ("💶 Revenus",  f"{rev:,.2f} €",   C["green"]),
            ("💸 Dépenses", f"{exp:,.2f} €",   C["red"]),
            ("🏦 Épargne",  f"{sav:,.2f} €",   C["blue"]),
            ("⚖️ Bilan",   f"{bilan:+,.2f} €", C["green"] if bilan >= 0 else C["red"]),
        ]
        for i, (t, v, clr) in enumerate(kpis):
            f = ctk.CTkFrame(kpi_card_f, fg_color="transparent")
            f.grid(row=0, column=i, padx=16, pady=16, sticky="ew")
            ctk.CTkLabel(f, text=t, font=ctk.CTkFont(size=11),
                         text_color=C["muted"]).pack(anchor="w")
            ctk.CTkLabel(f, text=v,
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=clr).pack(anchor="w", pady=(2, 0))

        # Patrimoine total
        pat_f = ctk.CTkFrame(self._content, fg_color="#EFF6FF",
                              corner_radius=10, border_width=1,
                              border_color="#93C5FD")
        pat_f.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkLabel(pat_f,
                     text=f"📈  Patrimoine total :  {total_pat:,.2f} €",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C["primary"]).pack(side="left", padx=20, pady=14)

        if self._pdf_path and os.path.exists(self._pdf_path):
            ctk.CTkLabel(self._content,
                         text=f"📄  Rapport PDF : {os.path.basename(self._pdf_path)}",
                         font=ctk.CTkFont(size=11), text_color=C["green"]).pack(
                anchor="w", padx=24, pady=(0, 8))

        # Message de félicitations
        congrats = ctk.CTkFrame(self._content, fg_color="#F0FDF4",
                                 corner_radius=10, border_width=1,
                                 border_color="#86EFAC")
        congrats.pack(fill="x", padx=24, pady=(4, 20))
        ctk.CTkLabel(congrats,
                     text="🎉  Mois clôturé avec succès ! Bonne continuation pour le mois prochain.",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#15803D",
                     wraplength=480, justify="left").pack(
            anchor="w", padx=16, pady=14)
