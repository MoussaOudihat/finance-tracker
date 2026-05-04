"""
ui/pages/expenses.py — Page Dépenses autonome avec refresh inline
"""

def _oneliner(text: str, maxlen: int = 55) -> str:
    """Retourne la première ligne tronquée — pour l'affichage en tableau."""
    if not text:
        return "—"
    first = text.split("\n")[0].strip()
    return (first[: maxlen - 1] + "…") if len(first) > maxlen else (first or "—")

import tkinter as tk
import customtkinter as ctk
from config import C, MONTHS_FR
from ui.components import make_card, table_header, table_row, month_selector
from ui.dialogs import ExpenseDialog


def _attach_autocomplete(entry: ctk.CTkEntry, parent_win, values: list):
    """
    Attache un menu déroulant de suggestions à un CTkEntry.
    Apparaît sous le champ dès la 1ère frappe, se ferme au clic ou Escape.
    """
    popup = {"win": None}

    def _show(matches):
        _hide()
        try:
            x = entry.winfo_rootx()
            y = entry.winfo_rooty() + entry.winfo_height() + 2
            w = max(entry.winfo_width(), 180)
        except Exception:
            return

        win = tk.Toplevel(parent_win)
        win.overrideredirect(True)
        win.geometry(f"{w}x{min(len(matches) * 26, 180)}+{x}+{y}")
        win.configure(bg="#FFFFFF")
        win.lift()
        win.attributes("-topmost", True)

        lb = tk.Listbox(
            win, font=("Calibri", 11),
            activestyle="none",
            selectbackground="#4F46E5", selectforeground="white",
            bg="#FFFFFF", fg="#1E293B",
            bd=0, relief="flat",
            highlightthickness=1, highlightbackground="#E2E8F0",
        )
        lb.pack(fill="both", expand=True)
        for m in matches:
            lb.insert("end", f"  {m}")

        def _pick(event=None):
            sel = lb.curselection()
            if sel:
                val = lb.get(sel[0]).strip()
                entry.delete(0, "end")
                entry.insert(0, val)
            _hide()
            entry.focus()

        lb.bind("<ButtonRelease-1>", _pick)
        lb.bind("<Return>", _pick)
        popup["win"] = win

    def _hide(event=None):
        if popup["win"]:
            try:
                popup["win"].destroy()
            except Exception:
                pass
            popup["win"] = None

    def _on_key(event=None):
        if event and event.keysym in ("Up", "Down", "Return", "Tab"):
            return
        if event and event.keysym == "Escape":
            _hide()
            return
        typed = entry.get().strip()
        if len(typed) < 1:
            _hide()
            return
        matches = [v for v in values if typed.upper() in v.upper()][:8]
        if not matches:
            _hide()
        else:
            _show(matches)

    entry.bind("<KeyRelease>", _on_key)
    entry.bind("<FocusOut>", lambda e: parent_win.after(200, _hide))
    entry.bind("<Escape>", lambda e: _hide())


def _show_budget_alert(parent, cat_name: str, budget: float, actual: float):
    """Affiche une alerte non-modale pour dépassement de budget."""
    overage = actual - budget
    alert = ctk.CTkToplevel(parent)
    alert.title("Budget dépassé")
    alert.geometry("400x200")
    alert.resizable(False, False)
    alert.update_idletasks()
    x = max(50, alert.winfo_screenwidth() - 450)
    alert.geometry(f"400x200+{x}+100")
    alert.grid_rowconfigure(0, weight=0)
    alert.grid_rowconfigure(1, weight=1)
    alert.grid_rowconfigure(2, weight=0)
    alert.grid_columnconfigure(0, weight=1)

    header = ctk.CTkFrame(alert, fg_color=C["red"], corner_radius=0)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(header, text="⚠️  Budget dépassé",
                 font=ctk.CTkFont(size=14, weight="bold"),
                 text_color="white").pack(anchor="w", padx=16, pady=12)

    body = ctk.CTkFrame(alert, fg_color=C["card"])
    body.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
    body.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(body,
                 text=(f"La catégorie {cat_name} a dépassé son budget.\n"
                       f"Budget : {budget:.2f} € · Dépensé : {actual:.2f} €"
                       f" · Dépassement : +{overage:.2f} €"),
                 font=ctk.CTkFont(size=11), text_color=C["text"],
                 justify="left", wraplength=360).pack(anchor="w", pady=8)

    bf = ctk.CTkFrame(alert, fg_color=C["card"])
    bf.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
    bf.grid_columnconfigure(0, weight=1)
    ctk.CTkButton(bf, text="OK", width=80,
                  fg_color=C["primary"], hover_color=C["primary_hover"],
                  command=alert.destroy).pack(side="right")
    alert.after(8000, alert.destroy)


class ExpensesPage:
    def render(self, container: ctk.CTkFrame, app):
        db        = app.db
        y, m      = app.sel_year, app.sel_month
        cats      = db.get_categories()
        cat_names = [c["name"] for c in cats]
        cat_map   = {c["name"]: c["id"] for c in cats}
        is_closed = db.is_month_closed(y, m)

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="💸  Dépenses",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        def on_month_change(new_m, new_y):
            app.sel_month = new_m
            app.sel_year  = new_y
            app._go("expenses")

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
        list_f.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # ── Total (row=2, toujours visible) ──────────────────
        total_f = ctk.CTkFrame(card, fg_color="#FEF2F2", corner_radius=8,
                               border_width=1, border_color="#FCA5A5")
        total_f.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 8))
        total_lbl = ctk.CTkLabel(total_f, text="",
                                  font=ctk.CTkFont(size=14, weight="bold"),
                                  text_color=C["red"])
        total_lbl.pack(side="right", padx=16, pady=9)

        # ── Refresh inline ───────────────────────────────────
        def _refresh():
            for w in list_f.winfo_children():
                w.destroy()
            data = db.get_expenses(y, m)
            table_header(list_f, [(2, "Catégorie"), (2, "Enseigne"),
                                   (1, "Montant"), (2, "Description")])
            for idx, r in enumerate(data):
                if is_closed:
                    # Lecture seule — pas de boutons édition/suppression
                    table_row(list_f, idx,
                              [(2, r["cat"],                C["text"]),
                               (2, r["payee"] or "—",       C["muted"]),
                               (1, f"{r['amount']:,.2f} €", C["red"]),
                               (2, _oneliner(r["label"]),   C["muted"])])
                else:
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
                              [(2, r["cat"],                C["text"]),
                               (2, r["payee"] or "—",       C["muted"]),
                               (1, f"{r['amount']:,.2f} €", C["red"]),
                               (2, _oneliner(r["label"]),   C["muted"])],
                              on_edit=make_edit(),
                              on_delete=lambda rid=r["id"]: (db.delete_expense(rid), _refresh()))
            total_lbl.configure(
                text=f"Total dépenses : {sum(r['amount'] for r in data):,.2f} €")

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

        # ── Inline add ───────────────────────────────────────
        band = ctk.CTkFrame(card, fg_color="#FEF2F2", corner_radius=10)
        band.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 6))

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

        all_payees = db.get_all_payees()
        e_payee  = ctk.CTkEntry(fields, placeholder_text="Enseigne (ex: Carrefour)", height=34)
        e_payee.grid(row=0, column=1, padx=4, pady=(0, 8), sticky="ew")
        _attach_autocomplete(e_payee, app, all_payees)

        e_amount = ctk.CTkEntry(fields, placeholder_text="Montant (€)", height=34)
        e_amount.grid(row=0, column=2, padx=4, pady=(0, 8), sticky="ew")
        e_label  = ctk.CTkEntry(fields, placeholder_text="Description (optionnel)", height=34)
        e_label.grid(row=0, column=3, padx=(4, 0), pady=(0, 8), sticky="ew")

        # ── Bande Excel (row=3, si feature activée) ──────────
        if db.get_setting("excel_import_enabled", "0") == "1":
            xband = ctk.CTkFrame(card, fg_color="#EEF2FF", corner_radius=8,
                                  border_width=1, border_color="#C7D2FE")
            xband.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 6))

            ctk.CTkLabel(xband, text="📊  Via Excel :",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C["primary"]).pack(side="left", padx=(12, 8), pady=7)

            def _dl_template_exp():
                from tkinter import filedialog, messagebox
                from utils_excel import generate_template_excel
                month_name = f"{MONTHS_FR[m - 1]}_{y}"
                path = filedialog.asksaveasfilename(
                    title="Enregistrer le template dépenses",
                    defaultextension=".xlsx",
                    filetypes=[("Excel", "*.xlsx")],
                    initialfile=f"Template_Depenses_{month_name}.xlsx",
                )
                if not path:
                    return
                try:
                    generate_template_excel(db, y, m, path, sheet_type="expenses")
                    messagebox.showinfo(
                        "Template créé",
                        f"Template enregistré :\n{path}\n\n"
                        "Remplissez-le puis cliquez sur « Importer ».\n"
                        "Colonne Catégorie = menu déroulant ▼",
                    )
                except Exception as exc:
                    messagebox.showerror("Erreur", str(exc))

            def _import_exp():
                from tkinter import filedialog, messagebox
                from utils_excel import import_month_excel
                path = filedialog.askopenfilename(
                    title="Importer template dépenses rempli",
                    filetypes=[("Excel", "*.xlsx")],
                )
                if not path:
                    return
                try:
                    res = import_month_excel(db, y, m, path)
                    msg = f"✅  {res['expenses_added']} dépense(s) importée(s)"
                    if res["errors"]:
                        msg += "\n\n⚠ " + "\n".join(res["errors"][:5])
                    messagebox.showinfo("Import terminé", msg)
                    _refresh()
                except Exception as exc:
                    messagebox.showerror("Erreur import", str(exc))

            ctk.CTkButton(
                xband, text="⬇  Template", height=28, width=110,
                fg_color=C["primary"], hover_color=C.get("primary_hover", "#3730A3"),
                text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
                command=_dl_template_exp,
            ).pack(side="left", padx=(0, 6), pady=6)

            ctk.CTkButton(
                xband, text="⬆  Importer", height=28, width=110,
                fg_color="#22C55E", hover_color="#16A34A",
                text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
                command=_import_exp,
            ).pack(side="left", pady=6)

            ctk.CTkLabel(xband,
                         text="Activé dans Paramètres → Rapports",
                         font=ctk.CTkFont(size=9), text_color=C["muted"],
                         ).pack(side="right", padx=10)

        # ── Logique ajout ─────────────────────────────────────
        recurring_var = tk.BooleanVar(value=False)

        def save_and_clear(event=None):
            raw = e_amount.get().replace(",", ".").replace(" ", "").replace(" ", "")
            try:
                amount = float(raw)
            except ValueError:
                e_amount.configure(border_color=C["red"]); return
            cat_id = cat_map.get(cat_var.get())
            if not cat_id:
                return
            payee = e_payee.get().strip()
            label = e_label.get().strip()
            db.add_expense(y, m, cat_id, amount, label, payee)
            status = db.get_category_budget_status(y, m, cat_var.get())
            if status is not None and status[1] > status[0]:
                _show_budget_alert(app, cat_var.get(), status[0], status[1])
            if recurring_var.get():
                rec_label = label or payee or cat_var.get()
                db.add_recurring(rec_label, amount, "expense", cat_id, "", payee)
                recurring_var.set(False)
            e_payee.delete(0, "end"); e_amount.delete(0, "end"); e_label.delete(0, "end")
            e_amount.configure(border_color=C["primary"])
            _refresh()
            e_amount.focus()

        btn_row = ctk.CTkFrame(band, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(btn_row, text="✓  Ajouter", height=34, width=120,
                      fg_color=C["red"], hover_color="#B91C1C",
                      command=save_and_clear).pack(side="left", padx=(0, 12))

        ctk.CTkCheckBox(
            btn_row,
            text="🔁  Récurrente (se répète chaque mois)",
            variable=recurring_var,
            font=ctk.CTkFont(size=12),
            text_color=C["muted"],
            fg_color=C["primary"],
            hover_color=C["primary"],
            checkmark_color="white",
            border_color=C["border"],
        ).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(btn_row, text="↵ Entrée pour valider",
                     font=ctk.CTkFont(size=10), text_color=C["muted"]).pack(side="left")

        for e in (e_payee, e_amount, e_label):
            e.bind("<Return>", save_and_clear)
        e_amount.focus()
