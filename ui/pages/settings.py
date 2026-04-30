"""
ui/pages/settings.py — Paramètres complets :
  import Notion, catégories, email SMTP, PDF, export impôts, mode sombre
"""
import os
import threading
import datetime
import tkinter.filedialog as fd

import customtkinter as ctk
from config import C, DEFAULT_CATEGORIES, DB_PATH
from ui.components import make_card, show_toast


class SettingsPage:
    def render(self, container: ctk.CTkFrame, app):
        db = app.db

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(container, text="⚙️  Paramètres",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).grid(
            row=0, column=0, sticky="w", padx=24, pady=(20, 6)
        )

        scroll = ctk.CTkScrollableFrame(container, fg_color=C["bg"])
        scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        scroll.grid_columnconfigure(0, weight=1)

        row = [0]
        def next_row():
            r = row[0]; row[0] += 1; return r

        # ══════════════════════════════════════════════════════
        #  1. RAPPORTS & EXPORTS
        # ══════════════════════════════════════════════════════
        rc = make_card(scroll)
        rc.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(rc, text="📄  Rapports & Exports",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(rc,
                     text="Générez des rapports PDF ou exportez vos données pour la fiscalité.",
                     text_color=C["muted"], font=ctk.CTkFont(size=12),
                     justify="left").pack(anchor="w", padx=20, pady=(0, 12))

        # ── PDF mensuel ──────────────────────────────────────
        pdf_sec = ctk.CTkFrame(rc, fg_color=C["light"], corner_radius=8)
        pdf_sec.pack(fill="x", padx=16, pady=(0, 8))
        pdf_inner = ctk.CTkFrame(pdf_sec, fg_color="transparent")
        pdf_inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(pdf_inner, text="Rapport PDF mensuel",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        # Sélecteurs mois/année pour le PDF
        from config import MONTHS_FR
        today = datetime.date.today()
        pdf_month_var = ctk.StringVar(value=MONTHS_FR[app.sel_month - 1])
        pdf_year_var  = ctk.StringVar(value=str(app.sel_year))
        pdf_status    = ctk.StringVar(value="")

        sel_row = ctk.CTkFrame(pdf_inner, fg_color="transparent")
        sel_row.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ctk.CTkLabel(sel_row, text="Mois :", font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(sel_row, values=MONTHS_FR, variable=pdf_month_var,
                          width=130, height=30).pack(side="left", padx=(0, 8))
        ctk.CTkOptionMenu(sel_row, values=[str(y) for y in range(2020, today.year + 2)],
                          variable=pdf_year_var, width=90, height=30).pack(side="left")

        ctk.CTkLabel(pdf_inner, textvariable=pdf_status,
                     font=ctk.CTkFont(size=11), text_color=C["green"]).grid(
            row=2, column=0, sticky="w", pady=(4, 0))

        def gen_pdf():
            try:
                from utils_pdf import generate_monthly_report
            except ImportError:
                pdf_status.set("❌  Installez reportlab : pip install reportlab")
                return

            m_num = MONTHS_FR.index(pdf_month_var.get()) + 1
            y_num = int(pdf_year_var.get())
            save_path = fd.asksaveasfilename(
                title="Enregistrer le rapport PDF",
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile=f"Finance_{y_num}_{m_num:02d}.pdf",
            )
            if not save_path:
                return
            pdf_status.set("⏳  Génération en cours…")

            def _run():
                try:
                    generate_monthly_report(db, y_num, m_num, save_path)
                    pdf_status.set(f"✅  PDF généré avec succès")
                    show_toast(app, "Rapport PDF généré !")
                except Exception as e:
                    pdf_status.set(f"❌  Erreur : {e}")
            threading.Thread(target=_run, daemon=True).start()

        ctk.CTkButton(pdf_inner, text="📄  Générer le rapport PDF",
                      height=34, width=200,
                      command=gen_pdf,
                      font=ctk.CTkFont(size=12)).grid(row=3, column=0, sticky="w", pady=(8, 0))

        # ── Export fiscal ─────────────────────────────────────
        tax_sep = ctk.CTkFrame(rc, fg_color="#E2E8F0", height=1)
        tax_sep.pack(fill="x", padx=16, pady=4)

        tax_sec = ctk.CTkFrame(rc, fg_color=C["light"], corner_radius=8)
        tax_sec.pack(fill="x", padx=16, pady=(0, 16))
        tax_inner = ctk.CTkFrame(tax_sec, fg_color="transparent")
        tax_inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(tax_inner, text="Export fiscal (déclaration impôts)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tax_inner,
                     text="Plus-values, dons déductibles, frais de formation…",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(anchor="w")

        tax_year_var  = ctk.StringVar(value=str(today.year - 1))
        tax_status    = ctk.StringVar(value="")

        tax_row = ctk.CTkFrame(tax_inner, fg_color="transparent")
        tax_row.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(tax_row, text="Année :", font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(tax_row, values=[str(y) for y in range(2020, today.year + 1)],
                          variable=tax_year_var, width=100, height=30).pack(side="left")

        ctk.CTkLabel(tax_inner, textvariable=tax_status,
                     font=ctk.CTkFont(size=11), text_color=C["green"]).pack(anchor="w", pady=(4, 0))

        def gen_tax():
            try:
                from utils_taxes import export_tax_summary
            except ImportError:
                tax_status.set("❌  Module utils_taxes introuvable")
                return
            save_path = fd.asksaveasfilename(
                title="Enregistrer l'export fiscal",
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile=f"Fiscal_{tax_year_var.get()}.csv",
            )
            if not save_path:
                return
            tax_status.set("⏳  Export en cours…")

            def _run():
                try:
                    result = export_tax_summary(db, int(tax_year_var.get()), save_path)
                    tax_status.set(f"✅  Exporté ({len(result)} lignes)")
                    show_toast(app, "Export fiscal généré !")
                except Exception as e:
                    tax_status.set(f"❌  {e}")
            threading.Thread(target=_run, daemon=True).start()

        ctk.CTkButton(tax_inner, text="📊  Exporter pour les impôts",
                      height=34, width=220,
                      fg_color="#8B5CF6", hover_color="#7C3AED",
                      command=gen_tax,
                      font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(8, 0))

        # ══════════════════════════════════════════════════════
        #  2. EMAIL SMTP
        # ══════════════════════════════════════════════════════
        ec = make_card(scroll)
        ec.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(ec, text="📧  Envoi d'email (synthèse mensuelle)",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(ec,
                     text="Configurez votre compte SMTP pour recevoir des résumés mensuels par email.",
                     text_color=C["muted"], font=ctk.CTkFont(size=12),
                     justify="left").pack(anchor="w", padx=20, pady=(0, 10))

        # Champs SMTP
        smtp_fields = ctk.CTkFrame(ec, fg_color="transparent")
        smtp_fields.pack(fill="x", padx=20, pady=(0, 6))
        smtp_fields.grid_columnconfigure(1, weight=1)

        def _smtp_row(row_i, label, key, placeholder, show=""):
            ctk.CTkLabel(smtp_fields, text=label, font=ctk.CTkFont(size=11),
                         text_color=C["muted"], width=130, anchor="w").grid(
                row=row_i, column=0, sticky="w", pady=4)
            var = ctk.StringVar(value=db.get_setting(key, ""))
            entry = ctk.CTkEntry(smtp_fields, textvariable=var, height=32,
                                  placeholder_text=placeholder, show=show)
            entry.grid(row=row_i, column=1, sticky="ew", padx=(8, 0), pady=4)
            return var

        smtp_host_var  = _smtp_row(0, "Serveur SMTP",    "smtp_host",  "smtp.gmail.com")
        smtp_port_var  = _smtp_row(1, "Port",             "smtp_port",  "587")
        smtp_user_var  = _smtp_row(2, "Email (login)",    "smtp_user",  "votre@email.com")
        smtp_pass_var  = _smtp_row(3, "Mot de passe",     "smtp_pass",  "App password…", "●")
        smtp_to_var    = _smtp_row(4, "Destinataire",     "smtp_to",    "votre@email.com")

        tls_var = ctk.BooleanVar(value=db.get_setting("smtp_tls", "1") == "1")
        ctk.CTkCheckBox(smtp_fields, text="Utiliser TLS (recommandé)",
                        variable=tls_var,
                        font=ctk.CTkFont(size=11)).grid(
            row=5, column=1, sticky="w", padx=(8, 0), pady=6)

        smtp_status = ctk.StringVar(value="")
        ctk.CTkLabel(ec, textvariable=smtp_status,
                     font=ctk.CTkFont(size=11), text_color=C["green"]).pack(
            anchor="w", padx=20)

        def save_smtp():
            db.set_setting("smtp_host", smtp_host_var.get().strip())
            db.set_setting("smtp_port", smtp_port_var.get().strip())
            db.set_setting("smtp_user", smtp_user_var.get().strip())
            db.set_setting("smtp_pass", smtp_pass_var.get().strip())
            db.set_setting("smtp_to",   smtp_to_var.get().strip())
            db.set_setting("smtp_tls",  "1" if tls_var.get() else "0")
            smtp_status.set("✅  Paramètres SMTP sauvegardés")
            show_toast(app, "Configuration email sauvegardée")

        def send_now():
            save_smtp()
            try:
                from utils_email import send_monthly_summary
            except ImportError:
                smtp_status.set("❌  Module utils_email introuvable")
                return

            host = db.get_setting("smtp_host", "")
            port = int(db.get_setting("smtp_port", "587") or "587")
            user = db.get_setting("smtp_user", "")
            pwd  = db.get_setting("smtp_pass", "")
            to   = db.get_setting("smtp_to", "")
            tls  = db.get_setting("smtp_tls", "1") == "1"

            if not all([host, user, pwd, to]):
                smtp_status.set("❌  Renseignez tous les champs SMTP")
                return

            smtp_status.set("⏳  Envoi en cours…")

            def _run():
                ok, msg = send_monthly_summary(
                    db, app.sel_year, app.sel_month,
                    to, host, port, user, pwd, tls
                )
                smtp_status.set(f"{'✅' if ok else '❌'}  {msg}")
            threading.Thread(target=_run, daemon=True).start()

        btn_row = ctk.CTkFrame(ec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=20, pady=(6, 16))
        ctk.CTkButton(btn_row, text="💾  Sauvegarder SMTP",
                      height=34, width=180,
                      fg_color=C["primary"],
                      command=save_smtp,
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="📧  Envoyer un test maintenant",
                      height=34, width=220,
                      fg_color=C["green"],
                      command=send_now,
                      font=ctk.CTkFont(size=12)).pack(side="left")

        # ══════════════════════════════════════════════════════
        #  3. APPARENCE
        # ══════════════════════════════════════════════════════
        ac = make_card(scroll)
        ac.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(ac, text="🎨  Apparence",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))

        dark_row = ctk.CTkFrame(ac, fg_color=C["light"], corner_radius=8)
        dark_row.pack(fill="x", padx=16, pady=(4, 16))
        dark_inner = ctk.CTkFrame(dark_row, fg_color="transparent")
        dark_inner.pack(fill="x", padx=14, pady=12)

        dark_var = ctk.BooleanVar(value=db.get_setting("dark_mode", "0") == "1")

        def on_dark_toggle():
            app.toggle_dark_mode(dark_var.get())

        ctk.CTkLabel(dark_inner,
                     text="🌙  Mode sombre",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).pack(side="left")
        ctk.CTkSwitch(dark_inner, text="",
                      variable=dark_var,
                      command=on_dark_toggle,
                      onvalue=True, offvalue=False).pack(side="right")

        ctk.CTkLabel(ac,
                     text="Le changement de thème sera appliqué au prochain démarrage.",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]).pack(
            anchor="w", padx=20, pady=(0, 10))

        # ══════════════════════════════════════════════════════
        #  4. SÉCURITÉ
        # ══════════════════════════════════════════════════════
        import auth as Auth
        sc = make_card(scroll)
        sc.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(sc, text="🔐  Sécurité & Accès",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))

        session_lbl = Auth.session_expiry_label(db)
        if session_lbl:
            ctk.CTkLabel(sc, text=f"🔑  {session_lbl}",
                         font=ctk.CTkFont(size=11),
                         text_color=C["muted"]).pack(anchor="w", padx=20, pady=(0, 8))

        # ── Changer le mot de passe ───────────────────────────
        pwd_sec = ctk.CTkFrame(sc, fg_color=C["light"], corner_radius=8)
        pwd_sec.pack(fill="x", padx=16, pady=(0, 8))
        pwd_inner = ctk.CTkFrame(pwd_sec, fg_color="transparent")
        pwd_inner.pack(fill="x", padx=14, pady=12)
        pwd_inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(pwd_inner, text="Modifier le mot de passe",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        show_pwd_form = {"open": False, "widgets": []}

        def _toggle_pwd_form():
            if show_pwd_form["open"]:
                for w in show_pwd_form["widgets"]:
                    try: w.destroy()
                    except Exception: pass
                show_pwd_form["widgets"].clear()
                show_pwd_form["open"] = False
                toggle_pwd_btn.configure(text="✏️  Changer le mot de passe")
                return
            show_pwd_form["open"] = True
            toggle_pwd_btn.configure(text="✕  Annuler")

            lbl1 = ctk.CTkLabel(pwd_inner, text="Nouveau mot de passe",
                                font=ctk.CTkFont(size=11, weight="bold"),
                                text_color=C["muted"])
            lbl1.grid(row=2, column=0, sticky="w", pady=(10, 2))
            npwd_var = ctk.StringVar()
            npwd_entry = ctk.CTkEntry(pwd_inner, textvariable=npwd_var,
                                      show="●", height=36,
                                      font=ctk.CTkFont(size=12),
                                      fg_color=C["card"],
                                      border_color=C["border"])
            npwd_entry.grid(row=3, column=0, sticky="ew")
            npwd_entry.focus()

            lbl2 = ctk.CTkLabel(pwd_inner, text="Confirmer",
                                font=ctk.CTkFont(size=11, weight="bold"),
                                text_color=C["muted"])
            lbl2.grid(row=4, column=0, sticky="w", pady=(8, 2))
            cpwd_var = ctk.StringVar()
            cpwd_entry = ctk.CTkEntry(pwd_inner, textvariable=cpwd_var,
                                      show="●", height=36,
                                      font=ctk.CTkFont(size=12),
                                      fg_color=C["card"],
                                      border_color=C["border"])
            cpwd_entry.grid(row=5, column=0, sticky="ew")

            err_var = ctk.StringVar()
            err_lbl = ctk.CTkLabel(pwd_inner, textvariable=err_var,
                                   font=ctk.CTkFont(size=11),
                                   text_color=C["red"])
            err_lbl.grid(row=6, column=0, sticky="w", pady=(4, 0))

            def _save_pwd():
                np_ = npwd_var.get()
                cp_ = cpwd_var.get()
                if len(np_) < 4:
                    err_var.set("⚠  Au moins 4 caractères.")
                    return
                if np_ != cp_:
                    err_var.set("❌  Les mots de passe ne correspondent pas.")
                    return
                Auth.change_password(db, np_)
                err_var.set("")
                show_toast(app, "✅  Mot de passe modifié !")
                _toggle_pwd_form()

            save_btn = ctk.CTkButton(pwd_inner,
                                     text="✅  Enregistrer",
                                     height=36,
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     fg_color=C["primary"],
                                     hover_color="#2955C9",
                                     command=_save_pwd)
            save_btn.grid(row=7, column=0, sticky="ew", pady=(10, 0))
            show_pwd_form["widgets"] = [lbl1, npwd_entry, lbl2, cpwd_entry,
                                        err_lbl, save_btn]

        toggle_pwd_btn = ctk.CTkButton(pwd_inner,
                                       text="✏️  Changer le mot de passe",
                                       height=34, width=210,
                                       font=ctk.CTkFont(size=12),
                                       fg_color=C["primary"],
                                       hover_color="#2955C9",
                                       command=_toggle_pwd_form)
        toggle_pwd_btn.grid(row=1, column=0, sticky="w", pady=(8, 0))

        # ── Se déconnecter ────────────────────────────────────
        def _logout():
            Auth.clear_session(db)
            show_toast(app, "Session fermée — mot de passe requis au prochain démarrage")

        ctk.CTkButton(sc,
                      text="🚪  Fermer la session (verrouiller)",
                      height=34, width=260,
                      font=ctk.CTkFont(size=12),
                      fg_color="#FEE2E2",
                      text_color=C["red"],
                      hover_color="#FECACA",
                      command=_logout).pack(anchor="w", padx=16, pady=(0, 16))

        # ══════════════════════════════════════════════════════
        #  5. IMPORT NOTION
        # ══════════════════════════════════════════════════════
        ic = make_card(scroll)
        ic.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(ic, text="📥  Importer depuis Notion (ZIP)",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(ic,
                     text="Sélectionnez les exports ZIP depuis Notion (revenus ou dépenses).\n"
                          "Les données seront ajoutées sans doublons.",
                     text_color=C["muted"], font=ctk.CTkFont(size=12),
                     justify="left").pack(anchor="w", padx=20, pady=(0, 12))

        self._import_status = ctk.StringVar(value="")
        ctk.CTkLabel(ic, textvariable=self._import_status,
                     font=ctk.CTkFont(size=12), text_color=C["green"]).pack(anchor="w", padx=20)

        btn_row2 = ctk.CTkFrame(ic, fg_color="transparent")
        btn_row2.pack(anchor="w", padx=20, pady=(6, 16))

        def do_import():
            paths = fd.askopenfilenames(
                title="Sélectionner les fichiers ZIP Notion",
                filetypes=[("ZIP", "*.zip"), ("Tous", "*.*")],
            )
            if not paths:
                return
            self._import_status.set("⏳  Import en cours…")

            def _run():
                total_rev = total_exp = total_sav = 0
                errors = []
                for p in paths:
                    try:
                        r, e, s = db.import_notion_zip(p)
                        total_rev += r; total_exp += e; total_sav += s
                    except Exception as exc:
                        errors.append(str(exc))
                if errors:
                    self._import_status.set("⚠️  Erreur : " + " | ".join(errors))
                else:
                    self._import_status.set(
                        f"✅  {total_rev} revenus, {total_exp} dépenses, {total_sav} épargnes importés"
                    )
            threading.Thread(target=_run, daemon=True).start()

        ctk.CTkButton(btn_row2, text="📂  Choisir ZIP(s) et importer",
                      height=38, command=do_import,
                      font=ctk.CTkFont(size=13)).pack(side="left")

        # ══════════════════════════════════════════════════════
        #  5. CATÉGORIES
        # ══════════════════════════════════════════════════════
        cc = make_card(scroll)
        cc.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(cc, text="🗂️  Catégories de dépenses",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))

        list_frame = ctk.CTkFrame(cc, fg_color="transparent")
        list_frame.pack(fill="x", padx=20, pady=(0, 8))

        def refresh_cat_list():
            for w in list_frame.winfo_children():
                w.destroy()
            cats = db.get_categories()
            for i, cat in enumerate(cats):
                row_f = ctk.CTkFrame(list_frame,
                                     fg_color=C["card"] if i % 2 == 0 else C["light"],
                                     corner_radius=6)
                row_f.pack(fill="x", pady=1)
                ctk.CTkLabel(row_f, text=cat["name"],
                             font=ctk.CTkFont(size=12),
                             text_color=C["text"]).pack(side="left", padx=14, pady=7)

                def make_del(c=cat):
                    return lambda: (
                        db.delete_category(c["id"]),
                        refresh_cat_list(),
                        show_toast(app, f"Catégorie supprimée"),
                    )
                ctk.CTkButton(row_f, text="✕", width=28, height=26,
                              fg_color="#FEE2E2", text_color=C["red"],
                              hover_color="#FECACA",
                              command=make_del()).pack(side="right", padx=8, pady=4)

        refresh_cat_list()

        add_row = ctk.CTkFrame(cc, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(4, 4))
        new_cat_var = ctk.StringVar()
        ctk.CTkEntry(add_row, textvariable=new_cat_var,
                     placeholder_text="Nouvelle catégorie…",
                     height=34, width=220).pack(side="left", padx=(0, 8))

        def add_cat():
            name = new_cat_var.get().strip()
            if not name:
                return
            db.add_category(name)
            new_cat_var.set("")
            refresh_cat_list()
            show_toast(app, f"Catégorie « {name.upper()} » ajoutée")

        ctk.CTkButton(add_row, text="＋  Ajouter", height=34, width=120,
                      command=add_cat).pack(side="left")

        def reset_cats():
            db.reset_categories()
            refresh_cat_list()
            show_toast(app, "Catégories réinitialisées")

        ctk.CTkButton(cc,
                      text="↺  Réinitialiser les catégories par défaut",
                      height=32, fg_color=C["muted"], hover_color="#475569",
                      font=ctk.CTkFont(size=12),
                      command=reset_cats).pack(anchor="e", padx=20, pady=(4, 14))

        # ══════════════════════════════════════════════════════
        #  6. BASE DE DONNÉES
        # ══════════════════════════════════════════════════════
        dbc = make_card(scroll)
        dbc.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(dbc, text="🗄️  Base de données",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(dbc,
                     text=f"Chemin : {db.db_path}",
                     text_color=C["muted"], font=ctk.CTkFont(size=11),
                     justify="left").pack(anchor="w", padx=20)

        def export_csv():
            save_path = fd.asksaveasfilename(
                title="Exporter les données CSV",
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile="finance_export.csv",
            )
            if save_path:
                db.export_csv(save_path)
                show_toast(app, "Export CSV terminé !")

        ctk.CTkButton(dbc, text="📤  Exporter CSV complet",
                      height=32, font=ctk.CTkFont(size=12),
                      fg_color=C["primary"],
                      command=export_csv).pack(anchor="w", padx=20, pady=(8, 16))

        btn_row2 = ctk.CTkFrame(ic, fg_color="transparent")
        btn_row2.pack(anchor="w", padx=20, pady=(6, 16))

        def do_import():
            paths = fd.askopenfilenames(
                title="Sélectionner les fichiers ZIP Notion",
                filetypes=[("ZIP", "*.zip"), ("Tous", "*.*")],
            )
            if not paths:
                return
            self._import_status.set("⏳  Import en cours…")

            def _run():
                total_rev = total_exp = total_sav = 0
                errors = []
                for p in paths:
                    try:
                        r, e, s = db.import_notion_zip(p)
                        total_rev += r; total_exp += e; total_sav += s
                    except Exception as exc:
                        errors.append(str(exc))
                if errors:
                    self._import_status.set("⚠️  Erreur : " + " | ".join(errors))
                else:
                    self._import_status.set(
                        f"✅  {total_rev} revenus, {total_exp} dépenses, {total_sav} épargnes importés"
                    )
            threading.Thread(target=_run, daemon=True).start()

        ctk.CTkButton(btn_row2, text="📂  Choisir ZIP(s) et importer",
                      height=38, command=do_import,
                      font=ctk.CTkFont(size=13)).pack(side="left")

        # ══════════════════════════════════════════════════════
        #  6. CATÉGORIES
        # ══════════════════════════════════════════════════════
        cc = make_card(scroll)
        cc.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(cc, text="🗂️  Catégories de dépenses",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))

        list_frame = ctk.CTkFrame(cc, fg_color="transparent")
        list_frame.pack(fill="x", padx=20, pady=(0, 8))

        def refresh_cat_list():
            for w in list_frame.winfo_children():
                w.destroy()
            cats = db.get_categories()
            for i, cat in enumerate(cats):
                row_f = ctk.CTkFrame(list_frame,
                                     fg_color=C["card"] if i % 2 == 0 else C["light"],
                                     corner_radius=6)
                row_f.pack(fill="x", pady=1)
                ctk.CTkLabel(row_f, text=cat["name"],
                             font=ctk.CTkFont(size=12),
                             text_color=C["text"]).pack(side="left", padx=14, pady=7)

                def make_del(c=cat):
                    return lambda: (
                        db.delete_category(c["id"]),
                        refresh_cat_list(),
                        show_toast(app, f"Catégorie supprimée"),
                    )
                ctk.CTkButton(row_f, text="✕", width=28, height=26,
                              fg_color="#FEE2E2", text_color=C["red"],
                              hover_color="#FECACA",
                              command=make_del()).pack(side="right", padx=8, pady=4)

        refresh_cat_list()

        add_row = ctk.CTkFrame(cc, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(4, 4))
        new_cat_var = ctk.StringVar()
        ctk.CTkEntry(add_row, textvariable=new_cat_var,
                     placeholder_text="Nouvelle catégorie…",
                     height=34, width=220).pack(side="left", padx=(0, 8))

        def add_cat():
            name = new_cat_var.get().strip()
            if not name:
                return
            db.add_category(name)
            new_cat_var.set("")
            refresh_cat_list()
            show_toast(app, f"Catégorie « {name.upper()} » ajoutée")

        ctk.CTkButton(add_row, text="＋  Ajouter", height=34, width=120,
                      command=add_cat).pack(side="left")

        def reset_cats():
            db.reset_categories()
            refresh_cat_list()
            show_toast(app, "Catégories réinitialisées")

        ctk.CTkButton(cc,
                      text="↺  Réinitialiser les catégories par défaut",
                      height=32, fg_color=C["muted"], hover_color="#475569",
                      font=ctk.CTkFont(size=12),
                      command=reset_cats).pack(anchor="e", padx=20, pady=(4, 14))

        # ══════════════════════════════════════════════════════
        #  7. BASE DE DONNÉES
        # ══════════════════════════════════════════════════════
        dbc = make_card(scroll)
        dbc.grid(row=next_row(), column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(dbc, text="🗄️  Base de données",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C["text"]).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(dbc,
                     text=f"Chemin : {db.db_path}",
                     text_color=C["muted"], font=ctk.CTkFont(size=11),
                     justify="left").pack(anchor="w", padx=20)

        def export_csv():
            save_path = fd.asksaveasfilename(
                title="Exporter les données CSV",
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile="finance_export.csv",
            )
            if save_path:
                db.export_csv(save_path)
                show_toast(app, "Export CSV terminé !")

        ctk.CTkButton(dbc, text="📤  Exporter CSV complet",
                      height=32, font=ctk.CTkFont(size=12),
                      fg_color=C["primary"],
                      command=export_csv).pack(anchor="w", padx=20, pady=(8, 16))
