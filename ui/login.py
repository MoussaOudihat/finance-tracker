"""
ui/login.py — Fenêtre d'authentification (Login / Setup / Récupération)

Flux :
  • 1er lancement → _show_setup()
  • Session valide → auth_success=True, destroy immédiat
  • Sinon → _show_login()
"""
import customtkinter as ctk
from config import C
import auth as Auth


# ─────────────────────────────────────────────────────────────
#  Questions secrètes prédéfinies
# ─────────────────────────────────────────────────────────────
SECRET_QUESTIONS = [
    "Quel est le prénom de votre mère ?",
    "Quel est le nom de votre premier animal de compagnie ?",
    "Dans quelle ville êtes-vous né(e) ?",
    "Quel est le nom de votre école primaire ?",
    "Quel est votre plat préféré ?",
    "Quel est le prénom de votre meilleur(e) ami(e) d'enfance ?",
    "Quel est le modèle de votre première voiture ?",
]


# ─────────────────────────────────────────────────────────────
#  Fenêtre principale d'authentification
# ─────────────────────────────────────────────────────────────
class LoginApp(ctk.CTk):
    """
    Fenêtre CTk qui gère toute l'authentification avant l'app principale.
    Après destroy(), lire self.auth_success pour savoir si on peut lancer App.
    """

    def __init__(self, db):
        super().__init__()
        self.db           = db
        self.auth_success = False

        self.title("Fintrack — Connexion")
        self.resizable(False, False)
        self.configure(fg_color=C["sidebar"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Centrer la fenêtre
        self._center(480, 560)

        # Colonne unique qui s'étire
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # En-tête fixe (logo)
        self._build_header()

        # Zone centrale (contenu variable selon l'écran)
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.grid(row=1, column=0, sticky="nsew", padx=32, pady=(0, 28))
        self._body.grid_columnconfigure(0, weight=1)

        # Routage initial
        if Auth.has_valid_session(db):
            # Session encore valide → on passe directement
            self.auth_success = True
            self.withdraw()  # hide before caller destroys, avoids mainloop entirely
        elif Auth.has_password(db):
            self._show_login()
        else:
            self._show_welcome()  # Nouveau compte ou restauration Supabase

    # ── Centrage ────────────────────────────────────────────
    def _center(self, w: int, h: int):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── En-tête ─────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=90)
        hdr.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 0))
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr,
                     text="  Fintrack",
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color="white").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="Accès sécurisé à vos finances personnelles",
                     font=ctk.CTkFont(size=12),
                     text_color="#94A3B8").grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ── Effacer le body ─────────────────────────────────────
    def _clear_body(self):
        for w in self._body.winfo_children():
            w.destroy()

    # ── Carte centrale ───────────────────────────────────────
    def _make_card(self) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._body,
                            fg_color=C["card"],
                            corner_radius=16,
                            border_width=1,
                            border_color=C["border"])
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        return card

    # ══════════════════════════════════════════════════════════
    #  VUE LOGIN
    # ══════════════════════════════════════════════════════════
    def _show_login(self):
        self._clear_body()
        card = self._make_card()

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, padx=28, pady=28, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        # Titre
        ctk.CTkLabel(inner,
                     text="🔐  Connexion",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w", pady=(0, 20))

        # Champ mot de passe
        ctk.CTkLabel(inner, text="Mot de passe",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["muted"]).grid(row=1, column=0, sticky="w", pady=(0, 4))

        pwd_frame = ctk.CTkFrame(inner, fg_color="transparent")
        pwd_frame.grid(row=2, column=0, sticky="ew")
        pwd_frame.grid_columnconfigure(0, weight=1)

        pwd_var  = ctk.StringVar()
        show_pwd = {"visible": False}

        pwd_entry = ctk.CTkEntry(pwd_frame,
                                 textvariable=pwd_var,
                                 show="●",
                                 height=42,
                                 font=ctk.CTkFont(size=14),
                                 fg_color=C["light"],
                                 border_color=C["border"],
                                 placeholder_text="Entrez votre mot de passe…")
        pwd_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        pwd_entry.focus()

        def _toggle_pwd():
            show_pwd["visible"] = not show_pwd["visible"]
            pwd_entry.configure(show="" if show_pwd["visible"] else "●")
            toggle_btn.configure(text="🙈" if show_pwd["visible"] else "👁")

        toggle_btn = ctk.CTkButton(pwd_frame, text="👁", width=42, height=42,
                                   fg_color=C["light"],
                                   text_color=C["muted"],
                                   hover_color=C["border"],
                                   border_width=1,
                                   border_color=C["border"],
                                   command=_toggle_pwd)
        toggle_btn.grid(row=0, column=1)

        # Message d'erreur
        err_var = ctk.StringVar()
        err_lbl = ctk.CTkLabel(inner, textvariable=err_var,
                               font=ctk.CTkFont(size=11),
                               text_color=C["red"])
        err_lbl.grid(row=3, column=0, sticky="w", pady=(6, 0))

        # Bouton connexion
        def _do_login(event=None):
            pwd = pwd_var.get()
            if not pwd:
                err_var.set("⚠  Veuillez entrer votre mot de passe.")
                return
            if Auth.verify_password(self.db, pwd):
                Auth.create_session(self.db)
                self.auth_success = True
                self._finish()
            else:
                err_var.set("❌  Mot de passe incorrect. Réessayez.")
                pwd_var.set("")
                pwd_entry.focus()

        pwd_entry.bind("<Return>", _do_login)

        ctk.CTkButton(inner,
                      text="  Se connecter",
                      height=44,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color=C["primary"],
                      hover_color="#2955C9",
                      command=_do_login).grid(row=4, column=0, sticky="ew",
                                              pady=(18, 0))

        # Lien mot de passe oublié
        forgot = ctk.CTkButton(inner,
                               text="Mot de passe oublié ?",
                               font=ctk.CTkFont(size=11),
                               fg_color="transparent",
                               text_color=C["muted"],
                               hover_color="transparent",
                               cursor="hand2",
                               command=self._show_recovery)
        forgot.grid(row=5, column=0, pady=(10, 0))

    # ══════════════════════════════════════════════════════════
    #  VUE SETUP (premier lancement)
    # ══════════════════════════════════════════════════════════
    def _show_setup(self):
        self.resizable(False, True)
        self._center(480, 720)
        self._clear_body()
        card = self._make_card()

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, padx=28, pady=28, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        # Bouton retour vers l'écran de bienvenue
        ctk.CTkButton(inner, text="← Retour",
                      font=ctk.CTkFont(size=11),
                      fg_color="transparent", text_color=C["muted"],
                      hover_color=C["light"], cursor="hand2", width=80,
                      command=self._show_welcome).grid(row=0, column=0,
                                                       sticky="w",
                                                       pady=(0, 8))

        ctk.CTkLabel(inner,
                     text="🛡  Créer votre mot de passe",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"]).grid(row=1, column=0, sticky="w",
                                                pady=(0, 4))
        ctk.CTkLabel(inner,
                     text="Premier lancement — sécurisez votre accès.",
                     font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=2, column=0, sticky="w",
                                                 pady=(0, 20))

        show_state = {"pwd": False, "cpwd": False}

        def _pwd_row(parent, row_idx, label, key):
            ctk.CTkLabel(parent, text=label,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=C["muted"]).grid(
                row=row_idx, column=0, sticky="w", pady=(0, 4))
            row_idx += 1
            frm = ctk.CTkFrame(parent, fg_color="transparent")
            frm.grid(row=row_idx, column=0, sticky="ew")
            frm.grid_columnconfigure(0, weight=1)
            var = ctk.StringVar()
            entry = ctk.CTkEntry(frm, textvariable=var, show="●",
                                 height=40, font=ctk.CTkFont(size=13),
                                 fg_color=C["light"], border_color=C["border"])
            entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

            def _tog(e=entry, k=key):
                show_state[k] = not show_state[k]
                e.configure(show="" if show_state[k] else "●")
                tbtn.configure(text="🙈" if show_state[k] else "👁")

            tbtn = ctk.CTkButton(frm, text="👁", width=40, height=40,
                                 fg_color=C["light"], text_color=C["muted"],
                                 hover_color=C["border"],
                                 border_width=1, border_color=C["border"],
                                 command=_tog)
            tbtn.grid(row=0, column=1)
            return var, entry, row_idx + 1

        # Mot de passe
        pwd_var,  pwd_entry,  r = _pwd_row(inner, 3,  "Mot de passe", "pwd")
        cpwd_var, cpwd_entry, r = _pwd_row(inner, r,   "Confirmer le mot de passe", "cpwd")

        # Séparateur
        ctk.CTkFrame(inner, height=1, fg_color=C["border"]).grid(
            row=r, column=0, sticky="ew", pady=(16, 14))
        r += 1

        # Question secrète
        ctk.CTkLabel(inner, text="Question secrète",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["muted"]).grid(row=r, column=0, sticky="w",
                                                 pady=(0, 4))
        r += 1
        q_var = ctk.StringVar(value=SECRET_QUESTIONS[0])
        ctk.CTkOptionMenu(inner, values=SECRET_QUESTIONS, variable=q_var,
                          height=38, font=ctk.CTkFont(size=11),
                          fg_color=C["light"], button_color=C["primary"],
                          text_color=C["text"]).grid(
            row=r, column=0, sticky="ew")
        r += 1

        ctk.CTkLabel(inner, text="Votre réponse",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["muted"]).grid(row=r, column=0, sticky="w",
                                                 pady=(10, 4))
        r += 1
        ans_var = ctk.StringVar()
        ctk.CTkEntry(inner, textvariable=ans_var, height=40,
                     font=ctk.CTkFont(size=13),
                     fg_color=C["light"], border_color=C["border"],
                     placeholder_text="Votre réponse…").grid(
            row=r, column=0, sticky="ew")
        r += 1

        # Erreur
        err_var = ctk.StringVar()
        ctk.CTkLabel(inner, textvariable=err_var,
                     font=ctk.CTkFont(size=11),
                     text_color=C["red"],
                     wraplength=380).grid(row=r, column=0, sticky="w",
                                         pady=(6, 0))
        r += 1

        def _do_setup():
            pwd   = pwd_var.get()
            cpwd  = cpwd_var.get()
            ans   = ans_var.get().strip()
            q     = q_var.get()

            if len(pwd) < 4:
                err_var.set("⚠  Le mot de passe doit faire au moins 4 caractères.")
                return
            if pwd != cpwd:
                err_var.set("❌  Les mots de passe ne correspondent pas.")
                return
            if not ans:
                err_var.set("⚠  La réponse à la question secrète est obligatoire.")
                return

            Auth.setup_password(self.db, pwd, q, ans)
            Auth.create_session(self.db)
            self.auth_success = True
            self._finish()  # Nouveau compte = local par défaut (Supabase dans Paramètres)

        ctk.CTkButton(inner,
                      text="  Créer mon accès",
                      height=44,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color=C["primary"],
                      hover_color="#2955C9",
                      command=_do_setup).grid(row=r, column=0, sticky="ew",
                                              pady=(16, 0))
        pwd_entry.focus()

    # ══════════════════════════════════════════════════════════
    #  VUE RÉCUPÉRATION (question secrète)
    # ══════════════════════════════════════════════════════════
    def _show_recovery(self):
        self._center(480, 580)
        self._clear_body()
        card = self._make_card()

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, padx=28, pady=28, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(inner,
                     text="🔑  Récupération",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w",
                                                pady=(0, 20))

        question = Auth.get_secret_question(self.db)
        ctk.CTkLabel(inner,
                     text=question,
                     font=ctk.CTkFont(size=12),
                     text_color=C["text"],
                     wraplength=380,
                     justify="left").grid(row=1, column=0, sticky="w",
                                          pady=(0, 6))

        ans_var = ctk.StringVar()
        ans_entry = ctk.CTkEntry(inner, textvariable=ans_var, height=40,
                                 font=ctk.CTkFont(size=13),
                                 fg_color=C["light"], border_color=C["border"],
                                 placeholder_text="Votre réponse…")
        ans_entry.grid(row=2, column=0, sticky="ew")
        ans_entry.focus()

        err_var = ctk.StringVar()
        err_lbl = ctk.CTkLabel(inner, textvariable=err_var,
                               font=ctk.CTkFont(size=11),
                               text_color=C["red"])
        err_lbl.grid(row=3, column=0, sticky="w", pady=(6, 0))

        # ── Vérification de la réponse
        def _check_answer(event=None):
            if Auth.verify_secret_answer(self.db, ans_var.get()):
                # Bonne réponse → formulaire nouveau mot de passe
                _show_new_pwd_form()
            else:
                err_var.set("❌  Réponse incorrecte.")
                ans_var.set("")
                ans_entry.focus()

        ans_entry.bind("<Return>", _check_answer)

        ctk.CTkButton(inner,
                      text="  Vérifier",
                      height=42,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      fg_color=C["primary"],
                      hover_color="#2955C9",
                      command=_check_answer).grid(row=4, column=0, sticky="ew",
                                                  pady=(14, 0))

        ctk.CTkButton(inner,
                      text="← Retour à la connexion",
                      font=ctk.CTkFont(size=11),
                      fg_color="transparent",
                      text_color=C["muted"],
                      hover_color="transparent",
                      cursor="hand2",
                      command=self._show_login).grid(row=5, column=0,
                                                     pady=(10, 0))

        # ── Formulaire nouveau mot de passe (inséré dynamiquement)
        new_pwd_frame = {"f": None}

        def _show_new_pwd_form():
            err_var.set("")
            ans_entry.configure(state="disabled")
            for w in inner.winfo_children():
                if w.cget("text") in ("  Vérifier",
                                      "← Retour à la connexion"):
                    w.destroy()

            sep = ctk.CTkFrame(inner, height=1, fg_color=C["border"])
            sep.grid(row=6, column=0, sticky="ew", pady=(18, 14))

            ctk.CTkLabel(inner,
                         text="✅  Identité vérifiée — choisissez un nouveau mot de passe",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C["green"],
                         wraplength=380).grid(row=7, column=0, sticky="w",
                                              pady=(0, 12))

            ctk.CTkLabel(inner, text="Nouveau mot de passe",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=C["muted"]).grid(row=8, column=0,
                                                     sticky="w", pady=(0, 4))
            npwd_var = ctk.StringVar()
            npwd_entry = ctk.CTkEntry(inner, textvariable=npwd_var,
                                      show="●", height=40,
                                      font=ctk.CTkFont(size=13),
                                      fg_color=C["light"],
                                      border_color=C["border"])
            npwd_entry.grid(row=9, column=0, sticky="ew")
            npwd_entry.focus()

            ctk.CTkLabel(inner, text="Confirmer",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=C["muted"]).grid(row=10, column=0,
                                                     sticky="w", pady=(8, 4))
            cpwd_var = ctk.StringVar()
            ctk.CTkEntry(inner, textvariable=cpwd_var,
                         show="●", height=40,
                         font=ctk.CTkFont(size=13),
                         fg_color=C["light"],
                         border_color=C["border"]).grid(row=11, column=0,
                                                        sticky="ew")

            err2_var = ctk.StringVar()
            ctk.CTkLabel(inner, textvariable=err2_var,
                         font=ctk.CTkFont(size=11),
                         text_color=C["red"]).grid(row=12, column=0,
                                                   sticky="w", pady=(4, 0))

            def _save_new_pwd():
                np = npwd_var.get()
                cp = cpwd_var.get()
                if len(np) < 4:
                    err2_var.set("⚠  Au moins 4 caractères.")
                    return
                if np != cp:
                    err2_var.set("❌  Les mots de passe ne correspondent pas.")
                    return
                Auth.change_password(self.db, np)
                Auth.create_session(self.db)
                self.auth_success = True
                self._finish()

            ctk.CTkButton(inner,
                          text="  Enregistrer le nouveau mot de passe",
                          height=44,
                          font=ctk.CTkFont(size=13, weight="bold"),
                          fg_color=C["green"],
                          hover_color="#16A34A",
                          command=_save_new_pwd).grid(row=13, column=0,
                                                      sticky="ew",
                                                      pady=(14, 0))

    # ══════════════════════════════════════════════════════════
    #  VUE CHOIX BASE DE DONNÉES (après setup initial)
    # ══════════════════════════════════════════════════════════
    def _show_db_setup(self):
        """Proposé uniquement au premier lancement, après création du mot de passe."""
        self.resizable(False, True)   # hauteur ajustable dynamiquement
        self._center(500, 480)
        self._clear_body()
        card = self._make_card()

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, padx=28, pady=28, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(inner,
                     text="🗄️  Stockage des données",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w",
                                                pady=(0, 6))
        ctk.CTkLabel(inner,
                     text="Où souhaitez-vous stocker votre base de données ?",
                     font=ctk.CTkFont(size=12),
                     text_color=C["muted"]).grid(row=1, column=0, sticky="w",
                                                 pady=(0, 20))

        mode_var = ctk.StringVar(value="local")

        # ── Carte Local ─────────────────────────────────────
        local_card = ctk.CTkFrame(inner, fg_color=C["light"],
                                  corner_radius=10,
                                  border_width=2,
                                  border_color=C["primary"])
        local_card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        local_card.grid_columnconfigure(1, weight=1)

        ctk.CTkRadioButton(local_card, text="", variable=mode_var,
                           value="local",
                           fg_color=C["primary"]).grid(
            row=0, column=0, padx=(14, 8), pady=14)
        ctk.CTkLabel(local_card,
                     text="💾  Local uniquement",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(local_card,
                     text="Données sur cet ordinateur. Rapide, simple, privé.",
                     font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=1, column=1, sticky="w",
                                                 pady=(0, 10))

        # ── Carte Supabase ───────────────────────────────────
        online_card = ctk.CTkFrame(inner, fg_color=C["light"],
                                   corner_radius=10,
                                   border_width=2,
                                   border_color=C["border"])
        online_card.grid(row=3, column=0, sticky="ew")
        online_card.grid_columnconfigure(1, weight=1)

        ctk.CTkRadioButton(online_card, text="", variable=mode_var,
                           value="online",
                           fg_color=C["primary"]).grid(
            row=0, column=0, padx=(14, 8), pady=14)
        ctk.CTkLabel(online_card,
                     text="☁️  En ligne (Supabase)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(online_card,
                     text="Sync multi-appareils + backup automatique. Gratuit.",
                     font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=1, column=1, sticky="w",
                                                 pady=(0, 10))

        # ── Champs Supabase (visibles si mode=online) ────────
        supabase_frame = ctk.CTkFrame(inner, fg_color="transparent")
        supabase_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        supabase_frame.grid_columnconfigure(0, weight=1)
        supabase_frame.grid_remove()  # caché par défaut

        ctk.CTkLabel(supabase_frame, text="URL du projet Supabase",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["muted"]).grid(row=0, column=0, sticky="w",
                                                 pady=(0, 4))
        url_var = ctk.StringVar()
        ctk.CTkEntry(supabase_frame, textvariable=url_var, height=38,
                     font=ctk.CTkFont(size=12),
                     fg_color=C["light"], border_color=C["border"],
                     placeholder_text="https://xxxx.supabase.co").grid(
            row=1, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(supabase_frame, text="Clé secrète (Secret key)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["muted"]).grid(row=2, column=0, sticky="w",
                                                 pady=(0, 4))
        key_var = ctk.StringVar()
        ctk.CTkEntry(supabase_frame, textvariable=key_var, height=38,
                     show="●", font=ctk.CTkFont(size=12),
                     fg_color=C["light"], border_color=C["border"],
                     placeholder_text="sb_secret_…").grid(
            row=3, column=0, sticky="ew")

        status_lbl = ctk.CTkLabel(supabase_frame, text="",
                                   font=ctk.CTkFont(size=11),
                                   wraplength=380, justify="left")
        status_lbl.grid(row=4, column=0, sticky="w", pady=(6, 0))

        def _set_status(msg: str):
            status_lbl.configure(text=msg)
            status_lbl.update()

        def _test_connection():
            import threading
            url = url_var.get().strip()
            key = key_var.get().strip()
            if not url or not key:
                _set_status("⚠️  Entrez l'URL et la clé.")
                return
            _set_status("⏳  Test en cours…")

            def _run():
                try:
                    from sync_supabase import SupabaseSync
                    s = SupabaseSync(url, key, "")
                    ok, msg = s.test_connection()
                    self.after(0, lambda: _set_status(msg))
                except Exception as e:
                    self.after(0, lambda: _set_status(f"❌  {e}"))

            threading.Thread(target=_run, daemon=True).start()

        ctk.CTkButton(supabase_frame, text="🔌  Tester la connexion",
                      height=36, font=ctk.CTkFont(size=12),
                      fg_color=C["muted"], hover_color="#475569",
                      command=_test_connection).grid(row=5, column=0,
                                                     sticky="w", pady=(10, 0))

        # ── Afficher/masquer les champs Supabase + resize fenêtre ──
        def _on_mode_change(*_):
            if mode_var.get() == "online":
                supabase_frame.grid()
                online_card.configure(border_color=C["primary"])
                local_card.configure(border_color=C["border"])
                self._center(500, 760)
            else:
                supabase_frame.grid_remove()
                local_card.configure(border_color=C["primary"])
                online_card.configure(border_color=C["border"])
                self._center(500, 480)

        mode_var.trace_add("write", _on_mode_change)

        # ── Bouton Continuer ─────────────────────────────────
        err_var = ctk.StringVar()
        ctk.CTkLabel(inner, textvariable=err_var,
                     font=ctk.CTkFont(size=11),
                     text_color=C["red"]).grid(row=5, column=0, sticky="w",
                                               pady=(10, 0))

        def _confirm():
            mode = mode_var.get()
            if mode == "online":
                url = url_var.get().strip()
                key = key_var.get().strip()
                if not url or not key:
                    err_var.set("⚠  Renseignez l'URL et la clé Supabase.")
                    return
                self.db.set_setting("supabase_url", url)
                self.db.set_setting("supabase_service_key", key)
            self.db.set_setting("db_mode", mode)
            self._finish()

        ctk.CTkButton(inner,
                      text="  Continuer →",
                      height=44,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color=C["primary"],
                      hover_color="#2955C9",
                      command=_confirm).grid(row=6, column=0, sticky="ew",
                                             pady=(16, 0))

    # ══════════════════════════════════════════════════════════
    #  VUE BIENVENUE (premier lancement)
    # ══════════════════════════════════════════════════════════
    def _show_welcome(self):
        """Choix : Nouveau compte (local) ou Compte existant (Supabase)."""
        self.resizable(False, True)
        self._center(500, 580)
        self._clear_body()
        card = self._make_card()

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, padx=28, pady=28, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(inner,
                     text="👋  Bienvenue !",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w",
                                                pady=(0, 6))
        ctk.CTkLabel(inner,
                     text="Êtes-vous un nouvel utilisateur ou avez-vous déjà un compte ?",
                     font=ctk.CTkFont(size=12),
                     text_color=C["muted"],
                     wraplength=400).grid(row=1, column=0, sticky="w",
                                          pady=(0, 24))

        # ── Carte Nouveau compte ─────────────────────────────
        new_card = ctk.CTkFrame(inner, fg_color=C["light"],
                                corner_radius=10,
                                border_width=2,
                                border_color=C["primary"])
        new_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        new_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(new_card,
                     text="🆕  Nouveau compte",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w",
                                                padx=16, pady=(14, 2))
        ctk.CTkLabel(new_card,
                     text="Créer un mot de passe et démarrer en local.",
                     font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=1, column=0, sticky="w",
                                                 padx=16, pady=(0, 6))
        ctk.CTkButton(new_card,
                      text="  Créer mon compte →",
                      height=36, font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color=C["primary"], hover_color="#2955C9",
                      command=self._show_setup).grid(row=2, column=0,
                                                      sticky="ew",
                                                      padx=16, pady=(4, 14))

        # ── Carte Compte existant ────────────────────────────
        ex_card = ctk.CTkFrame(inner, fg_color=C["light"],
                               corner_radius=10,
                               border_width=2,
                               border_color=C["border"])
        ex_card.grid(row=3, column=0, sticky="ew")
        ex_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(ex_card,
                     text="☁️  Compte existant (Supabase)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=0, sticky="w",
                                                padx=16, pady=(14, 2))
        ctk.CTkLabel(ex_card,
                     text="Restaurer mes données depuis Supabase.",
                     font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=1, column=0, sticky="w",
                                                 padx=16, pady=(0, 6))
        ctk.CTkButton(ex_card,
                      text="☁️  Restaurer mon compte →",
                      height=36, font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color=C["muted"], hover_color="#475569",
                      command=self._show_existing_account).grid(row=2, column=0,
                                                                 sticky="ew",
                                                                 padx=16,
                                                                 pady=(4, 14))

    # ══════════════════════════════════════════════════════════
    #  VUE COMPTE EXISTANT (restauration Supabase)
    # ══════════════════════════════════════════════════════════
    def _show_existing_account(self):
        """Restaure les données depuis Supabase puis redirige vers le login."""
        import threading
        self.resizable(False, True)
        self._center(500, 560)
        self._clear_body()
        card = self._make_card()

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, padx=28, pady=28, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        # ── En-tête + retour ─────────────────────────────────
        hdr = ctk.CTkFrame(inner, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(hdr, text="← Retour",
                      font=ctk.CTkFont(size=11),
                      fg_color="transparent", text_color=C["muted"],
                      hover_color=C["light"], cursor="hand2", width=80,
                      command=self._show_welcome).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(hdr,
                     text="☁️  Restaurer mon compte",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=C["text"]).grid(row=0, column=1, sticky="w",
                                                padx=(8, 0))

        ctk.CTkLabel(inner,
                     text="Entrez vos identifiants Supabase pour récupérer vos données.",
                     font=ctk.CTkFont(size=12),
                     text_color=C["muted"],
                     wraplength=400).grid(row=1, column=0, sticky="w",
                                          pady=(0, 18))

        # ── Champs ───────────────────────────────────────────
        ctk.CTkLabel(inner, text="URL du projet Supabase",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["muted"]).grid(row=2, column=0, sticky="w",
                                                 pady=(0, 4))
        url_var = ctk.StringVar()
        url_entry = ctk.CTkEntry(inner, textvariable=url_var, height=38,
                                 font=ctk.CTkFont(size=12),
                                 fg_color=C["light"], border_color=C["border"],
                                 placeholder_text="https://xxxx.supabase.co")
        url_entry.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        url_entry.focus()

        ctk.CTkLabel(inner, text="Clé secrète (Secret key)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C["muted"]).grid(row=4, column=0, sticky="w",
                                                 pady=(0, 4))
        key_var = ctk.StringVar()
        ctk.CTkEntry(inner, textvariable=key_var, height=38,
                     show="●", font=ctk.CTkFont(size=12),
                     fg_color=C["light"], border_color=C["border"],
                     placeholder_text="sb_secret_… ou eyJ…").grid(
            row=5, column=0, sticky="ew")

        # ── Status ───────────────────────────────────────────
        status_lbl = ctk.CTkLabel(inner, text="",
                                  font=ctk.CTkFont(size=11),
                                  wraplength=400, justify="left",
                                  text_color=C["muted"])
        status_lbl.grid(row=6, column=0, sticky="w", pady=(8, 0))

        # ── Bouton principal ─────────────────────────────────
        btn_restore = ctk.CTkButton(inner, text="☁️  Restaurer mes données",
                                    height=44,
                                    font=ctk.CTkFont(size=13, weight="bold"),
                                    fg_color=C["primary"],
                                    hover_color="#2955C9")
        btn_restore.grid(row=7, column=0, sticky="ew", pady=(14, 0))

        # ── Helpers ──────────────────────────────────────────
        def _set_status(msg: str, color: str = C["muted"]):
            """Toujours appelé depuis le main thread (via self.after ou directement)."""
            status_lbl.configure(text=msg, text_color=color)

        def _reset_btn():
            btn_restore.configure(state="normal", text="☁️  Restaurer mes données")

        # ── Action restauration ──────────────────────────────
        def _restore():
            url = url_var.get().strip()
            key = key_var.get().strip()
            if not url or not key:
                _set_status("⚠️  Entrez l'URL et la clé Supabase.", C["amber"])
                return

            btn_restore.configure(state="disabled", text="⏳  En cours…")
            _set_status("Connexion à Supabase…", C["muted"])

            def _run():
                try:
                    from sync_supabase import SupabaseSync
                    from config import DB_PATH

                    s = SupabaseSync(url, key, DB_PATH)

                    # 1. Test connexion + présence des tables
                    ok, conn_msg = s.test_connection()
                    if not ok:
                        self.after(0, lambda m=conn_msg: (
                            _set_status(m, C["red"]), _reset_btn()))
                        return

                    # 2. Pull
                    self.after(0, lambda: _set_status(
                        "⏳  Restauration des données depuis Supabase…", C["muted"]))
                    s._do_pull()

                    # 3. Recharger la DB + sauvegarder les credentials
                    def _done():
                        try:
                            self.db.con.close()
                        except Exception:
                            pass
                        from database import Database
                        self.db = Database(DB_PATH)
                        self.db.set_setting("supabase_url", url)
                        self.db.set_setting("supabase_service_key", key)
                        self.db.set_setting("db_mode", "online")
                        _set_status(
                            "✅  Données restaurées ! Redirection vers la connexion…",
                            C["green"])
                        self.after(1500, self._show_login)

                    self.after(0, _done)

                except Exception as exc:
                    err = str(exc)
                    self.after(0, lambda e=err: (
                        _set_status(f"❌  {e}", C["red"]), _reset_btn()))

            threading.Thread(target=_run, daemon=True).start()

        btn_restore.configure(command=_restore)

    # ── Fermeture propre ────────────────────────────────────
    def _finish(self):
        """Stoppe le mainloop proprement.
        Les callbacks after() de CTk (DPI, focus, titlebar…) sont dans la file
        Tcl globale : si on les laisse, App() les exécutera sur un widget mort.
        On les annule tous avant de quitter."""
        self.resizable(False, False)
        self.withdraw()
        self._purge_after_callbacks()
        self.quit()

    def _purge_after_callbacks(self):
        try:
            ids = self.tk.call("after", "info")
            if ids:
                for after_id in str(ids).split():
                    try:
                        self.after_cancel(after_id)
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_close(self):
        self.auth_success = False
        self._finish()
