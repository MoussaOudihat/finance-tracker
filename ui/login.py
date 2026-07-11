"""
ui/login.py — Authentification Fintrack (redesign visuel)
"""
import os
import sys
import customtkinter as ctk
import tkinter as tk
from config import C
import auth as Auth


def _resource_path(relative: str) -> str:
    """Résout un chemin de ressource compatible PyInstaller (sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

SECRET_QUESTIONS = [
    "Quel est le prénom de votre mère ?",
    "Quel est le nom de votre premier animal de compagnie ?",
    "Dans quelle ville êtes-vous né(e) ?",
    "Quel est le nom de votre école primaire ?",
    "Quel est votre plat préféré ?",
    "Quel est le prénom de votre meilleur(e) ami(e) d'enfance ?",
    "Quel est le modèle de votre première voiture ?",
]

# Palette auth
_BG      = "#0F0E1A"   # fond très sombre
_PANEL   = "#161427"   # panneau gauche
_CARD    = "#1C1A2E"   # carte centrale
_BORDER  = "#2D2B45"   # bordures subtiles
_PRIMARY = "#6366F1"   # indigo vif
_PRIMARY_H = "#4F46E5"
_TEXT    = "#F1F0FF"
_MUTED   = "#7C7A9E"
_INPUT   = "#13111F"
_RED     = "#F87171"
_GREEN   = "#34D399"


def _fallback_badge(parent):
    """Carré indigo avec initiale 'F' — affiché si le logo PNG est absent."""
    badge = ctk.CTkFrame(parent, width=56, height=56,
                         fg_color=_PRIMARY, corner_radius=16)
    badge.pack()
    badge.pack_propagate(False)
    ctk.CTkLabel(badge, text="F",
                 font=ctk.CTkFont(size=26, weight="bold"),
                 text_color="white").place(relx=.5, rely=.5, anchor="center")


class LoginApp(ctk.CTk):

    def __init__(self, db):
        super().__init__()
        self.db           = db
        self.auth_success = False

        self.title("Fintrack")
        self.resizable(False, False)
        self.configure(fg_color=_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        if Auth.has_valid_session(db):
            self.auth_success = True
            self.withdraw()
        elif Auth.has_password(db):
            self._center(420, 580)
            self._show_login()
        else:
            self._center(460, 540)
            self._show_welcome()

    # ── Utilitaires ──────────────────────────────────────────
    def _center(self, w: int, h: int):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def _logo_block(self, parent, row=0, subtitle=""):
        """Bloc logo + titre centré."""
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, pady=(0, 28))

        # Logo PNG — fallback sur carré indigo avec initiale si indisponible
        _logo_png = _resource_path("fintrack_256.png")
        if os.path.isfile(_logo_png):
            try:
                from PIL import Image as _PILImage
                _pil = _PILImage.open(_logo_png)
                _ctk_img = ctk.CTkImage(
                    light_image=_pil,
                    dark_image=_pil,
                    size=(56, 56),
                )
                ctk.CTkLabel(f, text="", image=_ctk_img).pack()
            except Exception:
                _fallback_badge(f)
        else:
            _fallback_badge(f)

        ctk.CTkLabel(f, text="Fintrack",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=_TEXT).pack(pady=(10, 0))
        if subtitle:
            ctk.CTkLabel(f, text=subtitle,
                         font=ctk.CTkFont(size=11),
                         text_color=_MUTED).pack(pady=(2, 0))

    def _input(self, parent, row: int, label: str,
               placeholder: str = "", secret: bool = False):
        """Champ de saisie stylisé. Retourne (StringVar, Entry, next_row)."""
        ctk.CTkLabel(parent, text=label,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_MUTED).grid(row=row, column=0,
                                              sticky="w", pady=(0, 4))
        row += 1
        var = ctk.StringVar()

        if secret:
            frm = ctk.CTkFrame(parent, fg_color="transparent")
            frm.grid(row=row, column=0, sticky="ew")
            frm.grid_columnconfigure(0, weight=1)
            state = {"show": False}
            entry = ctk.CTkEntry(frm, textvariable=var, show="●",
                                 height=44, font=ctk.CTkFont(size=13),
                                 fg_color=_INPUT, border_color=_BORDER,
                                 text_color=_TEXT,
                                 placeholder_text_color=_MUTED,
                                 placeholder_text=placeholder,
                                 corner_radius=10)
            entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

            def _tog():
                state["show"] = not state["show"]
                entry.configure(show="" if state["show"] else "●")
                eye.configure(text="🙈" if state["show"] else "👁")

            eye = ctk.CTkButton(frm, text="👁", width=44, height=44,
                                fg_color=_INPUT, text_color=_MUTED,
                                hover_color=_BORDER,
                                border_width=1, border_color=_BORDER,
                                corner_radius=10,
                                command=_tog)
            eye.grid(row=0, column=1)
        else:
            entry = ctk.CTkEntry(parent, textvariable=var,
                                 height=44, font=ctk.CTkFont(size=13),
                                 fg_color=_INPUT, border_color=_BORDER,
                                 text_color=_TEXT,
                                 placeholder_text_color=_MUTED,
                                 placeholder_text=placeholder,
                                 corner_radius=10)
            entry.grid(row=row, column=0, sticky="ew")

        return var, entry, row + 1

    def _primary_btn(self, parent, text: str, command, row: int):
        btn = ctk.CTkButton(parent, text=text, height=46,
                            font=ctk.CTkFont(size=13, weight="bold"),
                            fg_color=_PRIMARY, hover_color=_PRIMARY_H,
                            corner_radius=10, command=command)
        btn.grid(row=row, column=0, sticky="ew", pady=(20, 0))
        return btn

    def _err_label(self, parent, row: int):
        var = ctk.StringVar()
        ctk.CTkLabel(parent, textvariable=var,
                     font=ctk.CTkFont(size=11),
                     text_color=_RED).grid(row=row, column=0,
                                            sticky="w", pady=(8, 0))
        return var

    def _divider(self, parent, row: int):
        ctk.CTkFrame(parent, height=1,
                     fg_color=_BORDER).grid(row=row, column=0,
                                             sticky="ew", pady=(18, 16))

    # ══════════════════════════════════════════════════════════
    #  BIENVENUE
    # ══════════════════════════════════════════════════════════
    def _show_welcome(self):
        self._clear()

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, padx=40, pady=40, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        self._logo_block(wrap, row=0,
                         subtitle="Votre tracker de finances personnelles")

        # Card Nouveau compte
        nc = ctk.CTkFrame(wrap, fg_color=_CARD, corner_radius=14,
                          border_width=1, border_color=_PRIMARY)
        nc.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        nc.grid_columnconfigure(0, weight=1)

        hf = ctk.CTkFrame(nc, fg_color="transparent")
        hf.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        hf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hf, text="🆕", font=ctk.CTkFont(size=20)).grid(
            row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(hf, text="Nouveau compte",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=_TEXT).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(nc, text="Créer votre username, mot de passe et vos catégories.",
                     font=ctk.CTkFont(size=11), text_color=_MUTED).grid(
            row=1, column=0, sticky="w", padx=18, pady=(0, 10))
        ctk.CTkButton(nc, text="Commencer →", height=38,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color=_PRIMARY, hover_color=_PRIMARY_H,
                      corner_radius=8,
                      command=self._show_setup).grid(
            row=2, column=0, sticky="ew", padx=18, pady=(0, 16))

        # Card Supabase
        sc = ctk.CTkFrame(wrap, fg_color=_CARD, corner_radius=14,
                          border_width=1, border_color=_BORDER)
        sc.grid(row=2, column=0, sticky="ew")
        sc.grid_columnconfigure(0, weight=1)

        hf2 = ctk.CTkFrame(sc, fg_color="transparent")
        hf2.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        hf2.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hf2, text="☁️", font=ctk.CTkFont(size=20)).grid(
            row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(hf2, text="Compte existant (Supabase)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=_TEXT).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(sc, text="Restaurer mes données depuis Supabase.",
                     font=ctk.CTkFont(size=11), text_color=_MUTED).grid(
            row=1, column=0, sticky="w", padx=18, pady=(0, 10))
        ctk.CTkButton(sc, text="Restaurer →", height=38,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color=_BORDER, hover_color="#3D3B5C",
                      text_color=_TEXT, corner_radius=8,
                      command=self._show_existing_account).grid(
            row=2, column=0, sticky="ew", padx=18, pady=(0, 16))

    # ══════════════════════════════════════════════════════════
    #  LOGIN
    # ══════════════════════════════════════════════════════════
    def _show_login(self):
        self._center(420, 620)
        self.resizable(False, True)   # hauteur redimensionnable si écran petit
        self._clear()
        username = Auth.get_username(self.db)

        # Conteneur principal scrollable (pour les petits écrans)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_PRIMARY,
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, padx=44, pady=40, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        scroll.grid_rowconfigure(0, weight=1)

        self._logo_block(wrap, row=0,
                         subtitle=f"Bonjour, {username} 👋" if username else "")

        card = ctk.CTkFrame(wrap, fg_color=_CARD, corner_radius=16,
                            border_width=1, border_color=_BORDER)
        card.grid(row=1, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=0, column=0, padx=24, pady=24, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(inner, text="Connexion",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=_TEXT).grid(row=0, column=0, sticky="w",
                                            pady=(0, 18))

        u_var, u_entry, r = self._input(inner, 1, "NOM D'UTILISATEUR",
                                        placeholder="Votre username")
        if username:
            u_var.set(username)

        pwd_var, pwd_entry, r = self._input(inner, r, "MOT DE PASSE",
                                            placeholder="••••••••", secret=True)
        pwd_entry.focus()

        err_var = self._err_label(inner, r); r += 1

        def _login(event=None):
            # ── Vérification du verrouillage ─────────────────
            locked, lock_msg = Auth.check_lockout(self.db)
            if locked:
                err_var.set(f"🔒  {lock_msg}")
                return

            u = u_var.get().strip()
            p = pwd_var.get()
            if not u:
                err_var.set("⚠  Entrez votre nom d'utilisateur.")
                return
            if not p:
                err_var.set("⚠  Entrez votre mot de passe.")
                return
            if not Auth.verify_username(self.db, u):
                # Ne pas distinguer username/mot de passe incorrect (anti-énumération)
                Auth.record_failed_login(self.db)
                err_var.set("❌  Identifiant ou mot de passe incorrect.")
                pwd_var.set("")
                pwd_entry.focus()
                return
            if Auth.verify_password(self.db, p):
                Auth.clear_failed_logins(self.db)
                Auth.create_session(self.db)
                self.auth_success = True
                self._finish()
            else:
                Auth.record_failed_login(self.db)
                # Re-vérifier si on vient de dépasser le seuil
                locked2, lock_msg2 = Auth.check_lockout(self.db)
                if locked2:
                    err_var.set(f"🔒  {lock_msg2}")
                else:
                    remaining = Auth._LOCKOUT_MAX_ATTEMPTS - int(
                        self.db.get_setting("auth_failed_count", "0"))
                    err_var.set(
                        f"❌  Identifiant ou mot de passe incorrect."
                        f" ({remaining} tentative(s) restante(s))")
                pwd_var.set("")
                pwd_entry.focus()

        pwd_entry.bind("<Return>", _login)
        self._primary_btn(inner, "  Se connecter", _login, r); r += 1

        ctk.CTkButton(inner, text="Mot de passe oublié ?",
                      font=ctk.CTkFont(size=11),
                      fg_color="transparent", text_color=_MUTED,
                      hover_color=_CARD, cursor="hand2",
                      command=self._show_recovery).grid(
            row=r, column=0, pady=(10, 0))

    # ══════════════════════════════════════════════════════════
    #  SETUP (étape 1/2)
    # ══════════════════════════════════════════════════════════
    def _show_setup(self):
        self._center(460, 760)
        self._clear()

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=0)
        wrap.grid_rowconfigure(1, weight=0)
        wrap.grid_rowconfigure(2, weight=1)

        # ── Barre étape ──────────────────────────────────────
        top = ctk.CTkFrame(wrap, fg_color=_CARD, corner_radius=0, height=48)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(top, text="← Retour", width=80, height=28,
                      fg_color="transparent", text_color=_MUTED,
                      hover_color=_BORDER, cursor="hand2",
                      font=ctk.CTkFont(size=11),
                      command=self._show_welcome).grid(
            row=0, column=0, padx=14, pady=10)

        ctk.CTkLabel(top, text="Étape  1 / 2  —  Créer votre compte",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_MUTED).grid(row=0, column=1)

        # ── Barre de progression ─────────────────────────────
        pb = ctk.CTkFrame(wrap, fg_color=_BORDER, height=3, corner_radius=0)
        pb.grid(row=1, column=0, sticky="ew")
        ctk.CTkFrame(pb, fg_color=_PRIMARY, height=3,
                     corner_radius=0).place(relwidth=0.5, relheight=1)

        # ── Contenu scrollable (scrollbar visible seulement si débordement) ──
        inner = ctk.CTkScrollableFrame(wrap, fg_color="transparent",
                                       corner_radius=0,
                                       scrollbar_button_color=_BORDER,
                                       scrollbar_button_hover_color=_PRIMARY)
        inner.grid(row=2, column=0, sticky="nsew", padx=36, pady=(16, 16))
        inner.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(inner, text="Créer votre compte",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=_TEXT).grid(row=0, column=0, sticky="w",
                                            pady=(0, 2))
        ctk.CTkLabel(inner, text="Votre username sera affiché à chaque connexion.",
                     font=ctk.CTkFont(size=11),
                     text_color=_MUTED).grid(row=1, column=0, sticky="w",
                                              pady=(0, 16))

        u_var,    u_entry,    r = self._input(inner, 2, "NOM D'UTILISATEUR",
                                              placeholder="Ex : Moussa")
        pwd_var,  pwd_entry,  r = self._input(inner, r, "MOT DE PASSE",
                                              placeholder="••••••••", secret=True)
        cpwd_var, cpwd_entry, r = self._input(inner, r, "CONFIRMER",
                                              placeholder="••••••••", secret=True)
        u_entry.focus()

        self._divider(inner, r); r += 1

        # ── Question secrète ─────────────────────────────────
        sec_f = ctk.CTkFrame(inner, fg_color=_CARD, corner_radius=10,
                             border_width=1, border_color=_BORDER)
        sec_f.grid(row=r, column=0, sticky="ew", pady=(0, 12))
        sec_f.grid_columnconfigure(0, weight=1)
        r += 1

        sh = ctk.CTkFrame(sec_f, fg_color="transparent")
        sh.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        sh.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sh, text="🔑", font=ctk.CTkFont(size=15)).grid(
            row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(sh, text="Question secrète",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_TEXT).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(sec_f,
                     text="Permet de réinitialiser le mot de passe si oublié.",
                     font=ctk.CTkFont(size=10), text_color=_MUTED).grid(
            row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        inner_q = ctk.CTkFrame(sec_f, fg_color="transparent")
        inner_q.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        inner_q.grid_columnconfigure(0, weight=1)

        q_var = ctk.StringVar(value=SECRET_QUESTIONS[0])
        ctk.CTkOptionMenu(inner_q, values=SECRET_QUESTIONS, variable=q_var,
                          height=40, font=ctk.CTkFont(size=11),
                          fg_color=_INPUT, button_color=_PRIMARY,
                          button_hover_color=_PRIMARY_H,
                          dropdown_fg_color=_CARD,
                          dropdown_text_color=_TEXT,
                          text_color=_TEXT,
                          corner_radius=8).grid(row=0, column=0, sticky="ew")

        ans_var, ans_entry, _ = self._input(inner_q, 1, "VOTRE RÉPONSE",
                                            placeholder="Réponse…")

        err_var = self._err_label(inner, r); r += 1

        def _do_setup(event=None):
            u    = u_var.get().strip()
            pwd  = pwd_var.get()
            cpwd = cpwd_var.get()
            ans  = ans_var.get().strip()
            q    = q_var.get()
            if not u:
                err_var.set("⚠  Entrez un nom d'utilisateur.")
                return
            if len(pwd) < 4:
                err_var.set("⚠  Mot de passe : au moins 4 caractères.")
                return
            if pwd != cpwd:
                err_var.set("❌  Les mots de passe ne correspondent pas.")
                return
            if not ans:
                err_var.set("⚠  La réponse à la question secrète est obligatoire.")
                return
            Auth.setup_password(self.db, u, pwd, q, ans)
            Auth.create_session(self.db)
            # Ne demander les catégories QUE si la base est vide.
            # Si des données existent déjà (app utilisée avant l'ajout de l'auth),
            # on entre directement dans l'app sans toucher aux données existantes.
            has_data = self.db.con.execute(
                "SELECT COUNT(*) FROM months"
            ).fetchone()[0] > 0
            if has_data:
                self.auth_success = True
                self._finish()
            else:
                self._show_category_setup()

        ans_entry.bind("<Return>", _do_setup)
        self._primary_btn(inner, "  Suivant →", _do_setup, r)

    # ══════════════════════════════════════════════════════════
    #  CATÉGORIES (étape 2/2)
    # ══════════════════════════════════════════════════════════
    def _show_category_setup(self):
        from config import DEFAULT_CATEGORIES
        self._center(560, 740)
        self._clear()

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        # Barre d'étape
        top = ctk.CTkFrame(wrap, fg_color=_CARD, corner_radius=0, height=52)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)
        ctk.CTkLabel(top, text="Étape 2 / 2 — Vos catégories de dépenses",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_MUTED).pack(side="left", padx=20)

        pb = ctk.CTkFrame(wrap, fg_color=_BORDER, height=3, corner_radius=0)
        pb.grid(row=1, column=0, sticky="ew")
        ctk.CTkFrame(pb, fg_color=_PRIMARY, height=3,
                     corner_radius=0).place(relwidth=1.0, relheight=1)

        # Corps
        body = ctk.CTkFrame(wrap, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=28, pady=(16, 16))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(body,
                     text="Cochez les catégories que vous utilisez.\nModifiable à tout moment dans Paramètres.",
                     font=ctk.CTkFont(size=11), text_color=_MUTED,
                     justify="left").grid(row=0, column=0, sticky="w",
                                          pady=(0, 10))

        # Grille cases à cocher
        grid_f = ctk.CTkScrollableFrame(body, fg_color=_CARD,
                                        corner_radius=12,
                                        scrollbar_button_color=_BORDER,
                                        scrollbar_button_hover_color=_PRIMARY)
        grid_f.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        grid_f.grid_columnconfigure((0, 1, 2), weight=1)

        check_vars = {}
        for i, name in enumerate(DEFAULT_CATEGORIES):
            var = ctk.BooleanVar(value=True)
            check_vars[name] = var
            ctk.CTkCheckBox(grid_f, text=name, variable=var,
                            font=ctk.CTkFont(size=11), text_color=_TEXT,
                            checkmark_color="white",
                            fg_color=_PRIMARY, hover_color=_PRIMARY_H,
                            border_color=_BORDER,
                            ).grid(row=i // 3, column=i % 3,
                                   sticky="w", padx=12, pady=6)

        # Ajout custom
        add_f = ctk.CTkFrame(body, fg_color=_CARD, corner_radius=10,
                             border_width=1, border_color=_BORDER)
        add_f.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        add_f.grid_columnconfigure(0, weight=1)

        ah = ctk.CTkFrame(add_f, fg_color="transparent")
        ah.grid(row=0, column=0, columnspan=2, sticky="ew",
                padx=14, pady=(12, 6))
        ah.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(ah, text="＋  Catégorie personnalisée",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_TEXT).grid(row=0, column=0, sticky="w")

        ae_f = ctk.CTkFrame(add_f, fg_color="transparent")
        ae_f.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        ae_f.grid_columnconfigure(0, weight=1)

        custom_entry = ctk.CTkEntry(ae_f,
                                    placeholder_text="Ex : ANIMAUX, ENFANTS…",
                                    height=38, fg_color=_INPUT,
                                    border_color=_BORDER, text_color=_TEXT,
                                    corner_radius=8)
        custom_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        custom_list = []
        tags_f = ctk.CTkFrame(add_f, fg_color="transparent")
        tags_f.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))

        def _refresh_tags():
            for w in tags_f.winfo_children():
                w.destroy()
            for name in custom_list:
                tf = ctk.CTkFrame(tags_f, fg_color=_PRIMARY, corner_radius=6)
                tf.pack(side="left", padx=(0, 6), pady=2)
                ctk.CTkLabel(tf, text=name, font=ctk.CTkFont(size=10),
                             text_color="white").pack(side="left",
                                                       padx=(8, 2), pady=3)
                ctk.CTkButton(tf, text="✕", width=20, height=20,
                              fg_color="transparent", text_color="white",
                              hover_color=_PRIMARY_H,
                              command=lambda n=name: (
                                  custom_list.remove(n), _refresh_tags()
                              )).pack(side="left", padx=(0, 4))

        def _add_custom(event=None):
            name = custom_entry.get().strip().upper()
            if name and name not in custom_list and name not in DEFAULT_CATEGORIES:
                custom_list.append(name)
                custom_entry.delete(0, "end")
                _refresh_tags()

        ctk.CTkButton(ae_f, text="Ajouter", width=90, height=38,
                      fg_color=_PRIMARY, hover_color=_PRIMARY_H,
                      corner_radius=8,
                      command=_add_custom).grid(row=0, column=1)
        custom_entry.bind("<Return>", _add_custom)

        err_var = ctk.StringVar()
        ctk.CTkLabel(body, textvariable=err_var,
                     font=ctk.CTkFont(size=11),
                     text_color=_RED).grid(row=3, column=0, sticky="w")

        def _validate():
            selected = [n for n, v in check_vars.items() if v.get()]
            selected += custom_list
            if not selected:
                err_var.set("⚠  Sélectionnez au moins une catégorie.")
                return
            self.db.setup_categories(selected)
            self.auth_success = True
            self._finish()

        ctk.CTkButton(body, text="  Commencer →", height=46,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color=_PRIMARY, hover_color=_PRIMARY_H,
                      corner_radius=10,
                      command=_validate).grid(row=4, column=0, sticky="ew",
                                              pady=(8, 0))

    # ══════════════════════════════════════════════════════════
    #  RÉCUPÉRATION MOT DE PASSE
    # ══════════════════════════════════════════════════════════
    def _show_recovery(self):
        self._center(440, 540)
        self.resizable(False, True)
        self._clear()

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_PRIMARY,
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, padx=40, pady=32, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(wrap, text="← Connexion", width=100, height=28,
                      fg_color="transparent", text_color=_MUTED,
                      hover_color=_BORDER, cursor="hand2",
                      font=ctk.CTkFont(size=11),
                      command=self._show_login).grid(
            row=0, column=0, sticky="w", pady=(0, 16))

        ctk.CTkLabel(wrap, text="🔑  Récupération",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=_TEXT).grid(row=1, column=0, sticky="w",
                                            pady=(0, 4))

        question = Auth.get_secret_question(self.db)
        ctk.CTkLabel(wrap, text=question or "Question secrète",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_PRIMARY,
                     wraplength=360, justify="left").grid(row=2, column=0,
                                                          sticky="w",
                                                          pady=(12, 12))

        ans_var, ans_entry, r = self._input(wrap, 3, "VOTRE RÉPONSE",
                                            placeholder="Réponse…")
        ans_entry.focus()

        err_var = self._err_label(wrap, r); r += 1

        # Zone nouveau mot de passe (cachée)
        new_zone = ctk.CTkFrame(wrap, fg_color="transparent")
        new_zone.grid(row=r, column=0, sticky="ew")
        new_zone.grid_columnconfigure(0, weight=1)
        new_zone.grid_remove()
        r += 1

        verify_btn = ctk.CTkButton(wrap, text="  Vérifier", height=44,
                                   font=ctk.CTkFont(size=13, weight="bold"),
                                   fg_color=_PRIMARY, hover_color=_PRIMARY_H,
                                   corner_radius=10)
        verify_btn.grid(row=r, column=0, sticky="ew", pady=(16, 0))

        def _show_new_pwd():
            err_var.set("")
            ans_entry.configure(state="disabled")
            verify_btn.grid_remove()
            new_zone.grid()
            new_zone.grid_columnconfigure(0, weight=1)

            self._divider(new_zone, 0)
            ctk.CTkLabel(new_zone,
                         text="✅  Identité vérifiée",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=_GREEN).grid(row=1, column=0,
                                                  sticky="w", pady=(0, 12))

            np_var, np_entry, rr = self._input(new_zone, 2,
                                               "NOUVEAU MOT DE PASSE",
                                               placeholder="••••••••",
                                               secret=True)
            cp_var, cp_entry, rr = self._input(new_zone, rr,
                                               "CONFIRMER",
                                               placeholder="••••••••",
                                               secret=True)
            np_entry.focus()

            err2 = self._err_label(new_zone, rr); rr += 1

            def _save(event=None):
                np = np_var.get()
                cp = cp_var.get()
                if len(np) < 4:
                    err2.set("⚠  Au moins 4 caractères.")
                    return
                if np != cp:
                    err2.set("❌  Les mots de passe ne correspondent pas.")
                    return
                Auth.change_password(self.db, np)
                Auth.create_session(self.db)
                self.auth_success = True
                self._finish()

            cp_entry.bind("<Return>", _save)
            ctk.CTkButton(new_zone, text="  Enregistrer", height=44,
                          font=ctk.CTkFont(size=13, weight="bold"),
                          fg_color=_GREEN, hover_color="#16A34A",
                          corner_radius=10,
                          command=_save).grid(row=rr, column=0, sticky="ew",
                                              pady=(16, 0))
            # La fenêtre est scrollable, pas besoin de redimensionner

        def _check(event=None):
            locked, lock_msg = Auth.check_lockout(self.db)
            if locked:
                err_var.set(f"🔒  {lock_msg}")
                return
            if Auth.verify_secret_answer(self.db, ans_var.get()):
                Auth.clear_failed_logins(self.db)
                _show_new_pwd()
            else:
                Auth.record_failed_login(self.db)
                locked2, lock_msg2 = Auth.check_lockout(self.db)
                if locked2:
                    err_var.set(f"🔒  {lock_msg2}")
                else:
                    err_var.set("❌  Réponse incorrecte.")
                ans_var.set("")
                ans_entry.focus()

        ans_entry.bind("<Return>", _check)
        verify_btn.configure(command=_check)

    # ══════════════════════════════════════════════════════════
    #  RESTAURATION SUPABASE
    # ══════════════════════════════════════════════════════════
    def _show_existing_account(self):
        import threading
        self._center(480, 540)
        self.resizable(False, True)
        self._clear()

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_PRIMARY,
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, padx=36, pady=32, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(wrap, text="← Retour", width=90, height=28,
                      fg_color="transparent", text_color=_MUTED,
                      hover_color=_BORDER, cursor="hand2",
                      font=ctk.CTkFont(size=11),
                      command=self._show_welcome).grid(
            row=0, column=0, sticky="w", pady=(0, 16))

        ctk.CTkLabel(wrap, text="☁️  Restaurer mon compte",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=_TEXT).grid(row=1, column=0, sticky="w",
                                            pady=(0, 4))
        ctk.CTkLabel(wrap,
                     text="Entrez vos identifiants Supabase pour récupérer vos données.",
                     font=ctk.CTkFont(size=11), text_color=_MUTED,
                     wraplength=380).grid(row=2, column=0, sticky="w",
                                          pady=(0, 20))

        url_var, url_entry, r = self._input(wrap, 3,
                                            "URL DU PROJET SUPABASE",
                                            placeholder="https://xxxx.supabase.co")
        key_var, key_entry, r = self._input(wrap, r,
                                            "CLÉ SECRÈTE",
                                            placeholder="sb_secret_… ou eyJ…",
                                            secret=True)
        url_entry.focus()

        status_lbl = ctk.CTkLabel(wrap, text="",
                                  font=ctk.CTkFont(size=11),
                                  wraplength=400, justify="left",
                                  text_color=_MUTED)
        status_lbl.grid(row=r, column=0, sticky="w", pady=(10, 0)); r += 1

        btn = ctk.CTkButton(wrap, text="☁️  Restaurer mes données", height=44,
                            font=ctk.CTkFont(size=13, weight="bold"),
                            fg_color=_PRIMARY, hover_color=_PRIMARY_H,
                            corner_radius=10)
        btn.grid(row=r, column=0, sticky="ew", pady=(16, 0))

        def _set(msg, color=_MUTED):
            status_lbl.configure(text=msg, text_color=color)

        def _restore():
            url = url_var.get().strip()
            key = key_var.get().strip()
            if not url or not key:
                _set("⚠️  Entrez l'URL et la clé.", "#F59E0B")
                return
            btn.configure(state="disabled", text="⏳  En cours…")
            _set("Connexion à Supabase…")

            def _run():
                try:
                    from sync_supabase import SupabaseSync
                    from config import DB_PATH
                    s = SupabaseSync(url, key, DB_PATH)
                    ok, msg = s.test_connection()
                    if not ok:
                        self.after(0, lambda m=msg: (
                            _set(m, _RED),
                            btn.configure(state="normal",
                                          text="☁️  Restaurer mes données")))
                        return
                    self.after(0, lambda: _set("⏳  Restauration…"))
                    s._do_pull()

                    def _done():
                        # NE PAS fermer db.con : main.py garde la même référence.
                        # Le pull a écrit dans le fichier SQLite (connexion séparée),
                        # on invalide juste le cache pour lire les nouvelles données.
                        self.db._invalidate()
                        self.db.set_setting("supabase_url", url)
                        self.db.set_setting("supabase_service_key", key)
                        self.db.set_setting("db_mode", "online")
                        _set("\u2705  Données restaurées !", _GREEN)
                        # Si aucun compte local n'existe (auth exclue du sync),
                        # rediriger vers la création de compte plutôt que login.
                        if Auth.has_password(self.db):
                            self.after(1500, self._show_login)
                        else:
                            self.after(1500, self._show_post_restore_setup)

                    self.after(0, _done)
                except Exception as exc:
                    e = str(exc)
                    self.after(0, lambda e=e: (
                        _set(f"\u274c  {e}", _RED),
                        btn.configure(state="normal",
                                      text="\u2601️  Restaurer mes données")))

            threading.Thread(target=_run, daemon=True).start()

        btn.configure(command=_restore)

    # ════════════════════════════════════════════════════════
    #  SETUP POST-RESTAURATION SUPABASE
    #  (quand aucun compte local n'existait avant la restauration)
    # ════════════════════════════════════════════════════════
    def _show_post_restore_setup(self):
        """
        Affiché après une restauration Supabase réussie quand aucun
        mot de passe local n'est configuré (auth exclue du sync).
        """
        self._center(460, 800)
        self.resizable(False, True)
        self._clear()

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=0)
        wrap.grid_rowconfigure(1, weight=0)
        wrap.grid_rowconfigure(2, weight=1)

        # Barre d'info
        top = ctk.CTkFrame(wrap, fg_color=_CARD, corner_radius=0, height=52)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top,
                     text="\u2601️  Restauration réussie — Créez votre accès local",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_GREEN).pack(side="left", padx=20)

        pb = ctk.CTkFrame(wrap, fg_color=_BORDER, height=3, corner_radius=0)
        pb.grid(row=1, column=0, sticky="ew")
        ctk.CTkFrame(pb, fg_color=_GREEN, height=3,
                     corner_radius=0).place(relwidth=1.0, relheight=1)

        inner = ctk.CTkScrollableFrame(wrap, fg_color="transparent",
                                       corner_radius=0,
                                       scrollbar_button_color=_BORDER,
                                       scrollbar_button_hover_color=_PRIMARY)
        inner.grid(row=2, column=0, sticky="nsew", padx=36, pady=(16, 16))
        inner.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(inner, text="\u2705  Données Supabase restaurées !",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=_GREEN).grid(row=0, column=0, sticky="w",
                                              pady=(0, 4))
        ctk.CTkLabel(inner,
                     text="Vos données sont bien là.\n"
                          "Pour des raisons de sécurité, les mots de passe ne sont\n"
                          "jamais stockés dans Supabase. Créez un accès local pour\n"
                          "continuer à utiliser Fintrack sur cet appareil.",
                     font=ctk.CTkFont(size=11), text_color=_MUTED,
                     justify="left").grid(row=1, column=0, sticky="w",
                                          pady=(0, 20))

        u_var,    u_entry,    r = self._input(inner, 2, "NOM D'UTILISATEUR",
                                              placeholder="Ex : Moussa")
        pwd_var,  pwd_entry,  r = self._input(inner, r, "MOT DE PASSE",
                                              placeholder="••••••••", secret=True)
        cpwd_var, cpwd_entry, r = self._input(inner, r, "CONFIRMER",
                                              placeholder="••••••••", secret=True)
        u_entry.focus()

        self._divider(inner, r); r += 1

        # Question secrète
        sec_f = ctk.CTkFrame(inner, fg_color=_CARD, corner_radius=10,
                             border_width=1, border_color=_BORDER)
        sec_f.grid(row=r, column=0, sticky="ew", pady=(0, 12))
        sec_f.grid_columnconfigure(0, weight=1)
        r += 1

        sh = ctk.CTkFrame(sec_f, fg_color="transparent")
        sh.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        sh.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sh, text="\U0001f511", font=ctk.CTkFont(size=15)).grid(
            row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(sh, text="Question secrète",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_TEXT).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(sec_f,
                     text="Permet de réinitialiser le mot de passe si oublié.",
                     font=ctk.CTkFont(size=10), text_color=_MUTED).grid(
            row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        inner_q = ctk.CTkFrame(sec_f, fg_color="transparent")
        inner_q.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        inner_q.grid_columnconfigure(0, weight=1)

        q_var = ctk.StringVar(value=SECRET_QUESTIONS[0])
        ctk.CTkOptionMenu(inner_q, values=SECRET_QUESTIONS, variable=q_var,
                          height=40, font=ctk.CTkFont(size=11),
                          fg_color=_INPUT, button_color=_PRIMARY,
                          button_hover_color=_PRIMARY_H,
                          dropdown_fg_color=_CARD,
                          dropdown_text_color=_TEXT,
                          text_color=_TEXT,
                          corner_radius=8).grid(row=0, column=0, sticky="ew")

        ans_var, ans_entry, _ = self._input(inner_q, 1, "VOTRE RÉPONSE",
                                            placeholder="Réponse…")

        err_var = self._err_label(inner, r); r += 1

        def _do_setup(event=None):
            u    = u_var.get().strip()
            pwd  = pwd_var.get()
            cpwd = cpwd_var.get()
            ans  = ans_var.get().strip()
            q    = q_var.get()
            if not u:
                err_var.set("\u26a0  Entrez un nom d'utilisateur.")
                return
            if len(pwd) < 4:
                err_var.set("\u26a0  Mot de passe : au moins 4 caractères.")
                return
            if pwd != cpwd:
                err_var.set("\u274c  Les mots de passe ne correspondent pas.")
                return
            if not ans:
                err_var.set("\u26a0  La réponse à la question secrète est obligatoire.")
                return
            Auth.setup_password(self.db, u, pwd, q, ans)
            Auth.create_session(self.db)
            self.auth_success = True
            self._finish()

        ans_entry.bind("<Return>", _do_setup)
        self._primary_btn(inner, "  Accéder à mes données \u2192", _do_setup, r)

    # ── Fermeture ────────────────────────────────────────────────
    def _finish(self):
        self.resizable(False, False)
        self.withdraw()
        try:
            ids = self.tk.call("after", "info")
            if ids:
                for aid in str(ids).split():
                    try:
                        self.after_cancel(aid)
                    except Exception:
                        pass
        except Exception:
            pass
        self.quit()

    def _on_close(self):
        self.auth_success = False
        self._finish()
