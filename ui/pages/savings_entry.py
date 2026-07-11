"""
ui/pages/savings_entry.py — Page Épargne autonome avec refresh inline
"""

def _oneliner(text: str, maxlen: int = 55) -> str:
    if not text:
        return "—"
    first = text.split("\n")[0].strip()
    return (first[: maxlen - 1] + "…") if len(first) > maxlen else (first or "—")

import customtkinter as ctk
from config import C, MONTHS_FR
from ui.components import make_card, table_header, table_row, month_selector
from ui.dialogs import SavingDialog


class SavingsEntryPage:
    def render(self, container: ctk.CTkFrame, app):
        db   = app.db
        y, m = app.sel_year, app.sel_month

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="🏦  Épargne",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        def on_month_change(new_m, new_y):
            app.sel_month = new_m
            app.sel_year  = new_y
            app._go("savings_entry")

        month_selector(top, MONTHS_FR, y, m, on_month_change).grid(
            row=0, column=2, sticky="e")

        # ── Card principale ──────────────────────────────────
        card = make_card(container)
        card.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        # ── Liste scrollable ─────────────────────────────────
        list_f = ctk.CTkScrollableFrame(card, fg_color=C["card"])
        list_f.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        list_f.grid_columnconfigure((0, 1, 2), weight=1)

        # ── Bandeau clôture ──────────────────────────────────
        is_closed = db.is_month_closed(y, m)
        if is_closed:
            lock_band = ctk.CTkFrame(card, fg_color="#FEF3C7", corner_radius=10,
                                     border_width=1, border_color="#FCD34D")
            lock_band.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 6))
            ctk.CTkLabel(lock_band,
                         text="🔒  Ce mois a été clôturé — la saisie est verrouillée.",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#92400E").pack(anchor="w", padx=16, pady=12)
            return

        # ── Inline add ───────────────────────────────────────
        band = ctk.CTkFrame(card, fg_color="#EFF6FF", corner_radius=10)
        band.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 6))

        ctk.CTkLabel(band, text="＋  Nouvelle épargne :",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["blue"]).pack(anchor="w", padx=12, pady=(8, 4))

        fields = ctk.CTkFrame(band, fg_color="transparent")
        fields.pack(fill="x", padx=12)
        fields.grid_columnconfigure((0, 1, 2), weight=1)

        e_account = ctk.CTkEntry(fields, placeholder_text="Compte (ex: Livret A)", height=34)
        e_account.grid(row=0, column=0, padx=(0, 4), pady=(0, 8), sticky="ew")
        e_amount  = ctk.CTkEntry(fields, placeholder_text="Montant (€)", height=34)
        e_amount.grid(row=0, column=1, padx=4, pady=(0, 8), sticky="ew")
        e_label   = ctk.CTkEntry(fields, placeholder_text="Description (optionnel)", height=34)
        e_label.grid(row=0, column=2, padx=(4, 0), pady=(0, 8), sticky="ew")

        # ── Total ────────────────────────────────────────────
        total_f = ctk.CTkFrame(card, fg_color="#EFF6FF", corner_radius=8,
                               border_width=1, border_color="#93C5FD")
        total_f.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 8))
        total_lbl = ctk.CTkLabel(total_f, text="",
                                  font=ctk.CTkFont(size=14, weight="bold"),
                                  text_color=C["blue"])
        total_lbl.pack(side="right", padx=16, pady=9)

        # ── Refresh inline ───────────────────────────────────
        def _refresh():
            for w in list_f.winfo_children():
                w.destroy()
            data = db.get_savings(y, m)
            table_header(list_f, [(2, "Compte"), (1, "Montant"), (2, "Description")])
            for idx, r in enumerate(data):
                def make_edit(row=r):
                    def _edit():
                        SavingDialog(app, initial=dict(row), on_save=lambda d: (
                            db.update_saving(row["id"], d["account"], d["amount"], d["label"]),
                            _refresh(),
                        ))
                    return _edit
                table_row(list_f, idx,
                          [(2, r["account"] or "—",     C["text"]),
                           (1, f"{r['amount']:,.2f} €", C["blue"]),
                           (2, _oneliner(r["label"]),   C["muted"])],
                          on_edit=make_edit(),
                          on_delete=lambda rid=r["id"]: (db.delete_saving(rid), _refresh()))
            total_lbl.configure(
                text=f"Total épargne : {sum(r['amount'] for r in data):,.2f} €")

        _refresh()

        # ── Bouton + logique ajout ────────────────────────────
        def save_and_clear(event=None):
            raw = e_amount.get().replace(",", ".").replace(" ", "").replace("\u202f", "")
            try:
                amount = float(raw)
            except ValueError:
                e_amount.configure(border_color=C["red"]); return
            if amount <= 0:
                e_amount.configure(border_color=C["red"]); return
            db.add_saving(y, m, e_account.get().strip(), amount, e_label.get().strip())
            e_account.delete(0, "end"); e_amount.delete(0, "end"); e_label.delete(0, "end")
            e_account.configure(border_color=C["primary"])
            e_amount.configure(border_color=C["primary"])
            _refresh()
            e_account.focus()

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
