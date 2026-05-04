"""
ui/pages/revenues.py — Page Revenus autonome avec refresh inline
"""

def _oneliner(text: str, maxlen: int = 55) -> str:
    if not text:
        return "—"
    first = text.split("\n")[0].strip()
    return (first[: maxlen - 1] + "…") if len(first) > maxlen else (first or "—")

import customtkinter as ctk
from config import C, MONTHS_FR
from ui.components import make_card, table_header, table_row, month_selector
from ui.dialogs import RevenueDialog


class RevenuesPage:
    def render(self, container: ctk.CTkFrame, app):
        db   = app.db
        y, m = app.sel_year, app.sel_month
        is_closed = db.is_month_closed(y, m)

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="💶  Revenus",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        def on_month_change(new_m, new_y):
            app.sel_month = new_m
            app.sel_year  = new_y
            app._go("revenues")

        month_selector(top, MONTHS_FR, y, m, on_month_change).grid(
            row=0, column=2, sticky="e")

        # ── Card principale ──────────────────────────────────
        card = make_card(container)
        card.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        # ── Liste scrollable (row=0, toujours visible) ───────
        list_f = ctk.CTkScrollableFrame(card, fg_color=C["card"])
        list_f.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        list_f.grid_columnconfigure((0, 1, 2), weight=1)

        # ── Total (row=2, toujours visible) ──────────────────
        total_f = ctk.CTkFrame(card, fg_color="#F0FDF4", corner_radius=8,
                               border_width=1, border_color="#86EFAC")
        total_f.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 8))
        total_lbl = ctk.CTkLabel(total_f, text="",
                                  font=ctk.CTkFont(size=14, weight="bold"),
                                  text_color=C["green"])
        total_lbl.pack(side="right", padx=16, pady=9)

        # ── Refresh inline ───────────────────────────────────
        def _refresh():
            for w in list_f.winfo_children():
                w.destroy()
            data = db.get_revenues(y, m)
            table_header(list_f, [(2, "Source"), (1, "Montant"), (2, "Description")])
            for idx, r in enumerate(data):
                if is_closed:
                    # Lecture seule — pas de boutons édition/suppression
                    table_row(list_f, idx,
                              [(2, r["source"],             C["text"]),
                               (1, f"{r['amount']:,.2f} €", C["green"]),
                               (2, _oneliner(r["label"]),   C["muted"])])
                else:
                    def make_edit(row=r):
                        def _edit():
                            RevenueDialog(app, initial=dict(row), on_save=lambda d: (
                                db.update_revenue(row["id"], d["source"], d["amount"], d["label"]),
                                _refresh(),
                            ))
                        return _edit
                    table_row(list_f, idx,
                              [(2, r["source"],             C["text"]),
                               (1, f"{r['amount']:,.2f} €", C["green"]),
                               (2, _oneliner(r["label"]),   C["muted"])],
                              on_edit=make_edit(),
                              on_delete=lambda rid=r["id"]: (db.delete_revenue(rid), _refresh()))
            total_lbl.configure(
                text=f"Total revenus : {sum(r['amount'] for r in data):,.2f} €")

        _refresh()

        # ── row=1 : bandeau clôture OU formulaire de saisie ──
        if is_closed:
            lock_band = ctk.CTkFrame(card, fg_color="#FEF3C7", corner_radius=10,
                                     border_width=1, border_color="#FCD34D")
            lock_band.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 6))
            ctk.CTkLabel(lock_band,
                         text="🔒  Mois clôturé — consultation uniquement.",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#92400E").pack(anchor="w", padx=16, pady=12)
            return  # Pas de formulaire ni de bande Excel

        # ── Bande Excel (row=3, si feature activée) ──────────
        if db.get_setting("excel_import_enabled", "0") == "1":
            xband = ctk.CTkFrame(card, fg_color="#EEF2FF", corner_radius=8,
                                  border_width=1, border_color="#C7D2FE")
            xband.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 4))

            ctk.CTkLabel(xband, text="📊  Via Excel :",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#4F46E5").pack(side="left", padx=(12, 8), pady=7)

            def _dl_template_rev():
                from tkinter import filedialog, messagebox
                from utils_excel import generate_template_excel
                month_name = f"{MONTHS_FR[m - 1]}_{y}"
                path = filedialog.asksaveasfilename(
                    title="Enregistrer le template revenus",
                    defaultextension=".xlsx",
                    filetypes=[("Excel", "*.xlsx")],
                    initialfile=f"Template_Revenus_{month_name}.xlsx",
                )
                if not path:
                    return
                try:
                    generate_template_excel(db, y, m, path, sheet_type="revenues")
                    messagebox.showinfo(
                        "Template créé",
                        f"Template enregistré :\n{path}\n\n"
                        "Remplissez puis cliquez sur « Importer ».",
                    )
                except Exception as exc:
                    messagebox.showerror("Erreur", str(exc))

            def _import_rev():
                from tkinter import filedialog, messagebox
                from utils_excel import import_month_excel
                path = filedialog.askopenfilename(
                    title="Importer template revenus rempli",
                    filetypes=[("Excel", "*.xlsx")],
                )
                if not path:
                    return
                try:
                    res = import_month_excel(db, y, m, path)
                    msg = f"✅  {res['revenues_added']} revenu(s) importé(s)"
                    if res["errors"]:
                        msg += "\n\n⚠ " + "\n".join(res["errors"][:5])
                    messagebox.showinfo("Import terminé", msg)
                    _refresh()
                except Exception as exc:
                    messagebox.showerror("Erreur import", str(exc))

            ctk.CTkButton(
                xband, text="⬇  Template", height=28, width=110,
                fg_color="#4F46E5", hover_color="#3730A3",
                text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
                command=_dl_template_rev,
            ).pack(side="left", padx=(0, 6), pady=6)

            ctk.CTkButton(
                xband, text="⬆  Importer", height=28, width=110,
                fg_color="#22C55E", hover_color="#16A34A",
                text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
                command=_import_rev,
            ).pack(side="left", pady=6)

            ctk.CTkLabel(xband,
                         text="Activé dans Paramètres → Rapports",
                         font=ctk.CTkFont(size=9), text_color="#64748B",
                         ).pack(side="right", padx=10)
            bottom_row = 4
        else:
            bottom_row = 3

        # ── Inline add ───────────────────────────────────────
        band = ctk.CTkFrame(card, fg_color="#F0FDF4", corner_radius=10)
        band.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 6))

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
        e_label  = ctk.CTkEntry(fields, placeholder_text="Description (optionnel)", height=34)
        e_label.grid(row=0, column=2, padx=(4, 0), pady=(0, 8), sticky="ew")

        # ── Logique ajout ─────────────────────────────────────
        def save_and_clear(event=None):
            source = e_source.get().strip()
            raw = e_amount.get().replace(",", ".").replace(" ", "").replace(" ", "")
            try:
                amount = float(raw)
            except ValueError:
                e_amount.configure(border_color=C["red"]); return
            if not source:
                e_source.configure(border_color=C["red"]); return
            db.add_revenue(y, m, source, amount, e_label.get().strip())
            e_source.delete(0, "end"); e_amount.delete(0, "end"); e_label.delete(0, "end")
            e_source.configure(border_color=C["primary"])
            e_amount.configure(border_color=C["primary"])
            _refresh()
            e_source.focus()

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
