"""
ui/app.py — Fenêtre principale, sidebar et routage des pages
"""
from datetime import date
import importlib
import os
import sys
import threading

import customtkinter as ctk
import auth as Auth
from config import C, DB_PATH, APP_VERSION, apply_palette, FILTER_ALL_CATS, FILTER_ALL_PAYEES, FILTER_ALL_TYPES
from database import Database
from ui.components import nav_button
from logger import log

# ─── Lazy page loading ──────────────────────────────────────────
# Au lieu d'importer toutes les pages au démarrage (ce qui charge
# matplotlib, openpyxl, etc. même si on ne les utilise jamais),
# on garde juste la référence "module:Classe" et on importe à la
# première visite de la page.
_PAGE_MAP: dict[str, str] = {
    "dashboard":       "ui.pages.dashboard:DashboardPage",
    "revenues":        "ui.pages.revenues:RevenuesPage",
    "expenses":        "ui.pages.expenses:ExpensesPage",
    "savings_entry":   "ui.pages.savings_entry:SavingsEntryPage",
    "analyses":        "ui.pages.analyses:AnalysesPage",
    "budget":          "ui.pages.budget:BudgetPage",
    "objectifs":       "ui.pages.objectifs:ObjectifsPage",
    "patrimoine":      "ui.pages.patrimoine:PatrimoinePage",
    "historique":      "ui.pages.historique:HistoriquePage",
    "settings":        "ui.pages.settings:SettingsPage",
    "recommandations": "ui.pages.recommandations:RecommandationsPage",
    "projection":      "ui.pages.projection:ProjectionPage",
}

# Cache des classes déjà importées (clé page → classe)
_PAGE_CLASS_CACHE: dict[str, type] = {}


def _resource_path(relative: str) -> str:
    """Résout un chemin de ressource compatible PyInstaller (sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        # En développement, les ressources sont à la racine du projet
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def _load_page_class(key: str):
    """Importe la classe de page à la demande et la met en cache."""
    cls = _PAGE_CLASS_CACHE.get(key)
    if cls is not None:
        return cls
    spec = _PAGE_MAP.get(key)
    if not spec:
        return None
    module_path, class_name = spec.split(":")
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    _PAGE_CLASS_CACHE[key] = cls
    return cls

# Structure du menu latéral :
# None         = séparateur fin
# str          = label de section (texte en petites majuscules)
# tuple        = (label, page_key, tooltip)
_NAV_ITEMS = [
    ("🏠  Tableau de bord",  "dashboard",      "Vue d'ensemble du mois"),
    None,
    "SAISIE DU MOIS",
    ("💶  Revenus",          "revenues",       "Saisir et consulter vos revenus"),
    ("💸  Dépenses",         "expenses",       "Saisir et consulter vos dépenses"),
    ("🏦  Épargne",          "savings_entry",  "Enregistrer vos versements d'épargne"),
    None,
    "SUIVI & OBJECTIFS",
    ("💰  Budget",           "budget",         "Définir et suivre votre budget par catégorie"),
    ("🎯  Objectifs",        "objectifs",      "Gérer vos objectifs d'épargne"),
    None,
    "ANALYSES",
    ("📊  Analyses",         "analyses",       "Graphiques et statistiques détaillées"),
    ("📈  Patrimoine",       "patrimoine",     "Suivi de vos actifs et investissements"),
    ("🔮  Projection",       "projection",     "Simuler l'évolution future de votre patrimoine"),
    ("📋  Historique",       "historique",     "Historique complet et export"),
    None,
    "OUTILS",
    ("🧠  Conseils IA",      "recommandations","Conseils personnalisés par l'IA"),
    ("⚙️  Paramètres",      "settings",       "Préférences, sécurité et compte"),
]


class App(ctk.CTk):
    def __init__(self, sync=None, startup_sync_msg: str = ""):
        super().__init__()

        # ── Sync Supabase (optionnel) ────────────────────────
        self.sync = sync

        # ── DB ──────────────────────────────────────────────
        self.db = Database(DB_PATH)

        # ── Mode sombre ──────────────────────────────────────
        dark = self.db.get_setting("dark_mode", "0")
        is_dark = dark == "1"
        apply_palette(is_dark)
        ctk.set_appearance_mode("dark" if is_dark else "light")
        ctk.set_default_color_theme("blue")

        # ── État : dernier mois avec données ────────────────
        today = date.today()
        last = self.db.get_last_month_with_data()
        if last:
            self.sel_year, self.sel_month = last
        else:
            self.sel_year  = today.year
            self.sel_month = today.month

        # Filtres persistants
        self.dash_cat_filter   = FILTER_ALL_CATS
        self.dash_payee_filter = FILTER_ALL_PAYEES
        self.ana_cat_filter    = FILTER_ALL_CATS
        self.ana_payee_filter  = FILTER_ALL_PAYEES
        self.pat_type_filter   = FILTER_ALL_TYPES
        self.stacked_period    = 6

        # Callbacks soft-refresh
        self._dash_soft_refresh = None
        self._ana_soft_refresh  = None

        # Fermeture propre : IDs after() en cours + drapeau de fermeture
        # consulté par les threads d'arrière-plan avant de toucher self.db.
        self._after_ids: list = []
        self._closing = False

        # ── Fenêtre ─────────────────────────────────────────
        self.title("Fintrack")
        self.geometry("1280x800")
        self.minsize(960, 620)
        self.configure(fg_color=C["bg"])

        # Icône de la fenêtre (fichier généré par generate_icon.py)
        import os
        _ico = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fintrack.ico")
        if os.path.isfile(_ico):
            try:
                self.iconbitmap(_ico)
            except Exception:
                pass   # Silencieux — icône non critique

        # ── Fermeture propre (évite les process zombies) ─────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Layout principal ─────────────────────────────────
        # row 0 = barre supérieure (colonne contenu uniquement), row 1 = corps
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_sidebar()
        self._build_topbar()
        self._build_content_area()

        self._current_page = None
        self._go("dashboard")

        # ── Pré-chargement DB en arrière-plan ────────────────
        threading.Thread(target=self._warm_cache, daemon=True).start()

        # ── Alertes au démarrage (légèrement différé) ────────
        self._track_after(800, self._run_startup_checks)

        # ── Erreur sync au démarrage (pull) ──────────────────
        if startup_sync_msg and startup_sync_msg.startswith("⚠️"):
            self._track_after(1200, lambda m=startup_sync_msg: self._show_sync_error(m))

        # ── Auto-sync Supabase toutes les 5 minutes ──────────
        if self.sync:
            self._schedule_auto_sync()

    # ────────────────────────────────────────────────────────
    #  FERMETURE PROPRE
    # ────────────────────────────────────────────────────────
    def _track_after(self, ms, fn):
        """Comme self.after(), mais garde l'ID pour pouvoir l'annuler à la fermeture."""
        after_id = self.after(ms, fn)
        self._after_ids.append(after_id)
        return after_id

    def _on_close(self):
        """Fermeture propre — évite les process zombies."""
        log.info("Fermeture demandée par l'utilisateur.")
        # Empêche les threads d'arrière-plan de relancer un after() ou de
        # toucher self.db une fois la fermeture entamée.
        self._closing = True
        # Annuler les after() suivis (self.after_cancel("all") n'existe pas
        # côté Tk — "all" ne correspond à aucun ID réel et ne fait rien).
        for after_id in self._after_ids:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._after_ids.clear()
        # Fermer la connexion DB proprement (avec checkpoint WAL)
        try:
            self.db.close()
        except Exception:
            pass
        self.quit()
        self.destroy()

    # ────────────────────────────────────────────────────────
    #  PRÉ-CHARGEMENT CACHE DB
    # ────────────────────────────────────────────────────────
    def _warm_cache(self):
        """Pré-charge les requêtes fréquentes dans le cache DB en arrière-plan."""
        # Revérifié entre chaque requête : _on_close peut fermer self.db
        # pendant que cette boucle est en cours (thread séparé).
        try:
            if self._closing:
                return
            self.db.get_categories()
            if self._closing:
                return
            self.db.get_assets_current()
            if self._closing:
                return
            y, m = self.sel_year, self.sel_month
            self.db.get_expenses(y, m)
            if self._closing:
                return
            self.db.get_revenues(y, m)
            if self._closing:
                return
            self.db.monthly_summary(6)
        except Exception:
            log.warning("Préchauffage cache DB échoué", exc_info=True)

    # ────────────────────────────────────────────────────────
    #  AUTO-SYNC SUPABASE (toutes les 5 minutes)
    # ────────────────────────────────────────────────────────
    _AUTO_SYNC_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes

    def _schedule_auto_sync(self):
        """Planifie un push Supabase en arrière-plan toutes les 5 minutes."""
        def _on_done(msg: str):
            if msg.startswith("⚠️"):
                log.warning("[AutoSync] %s", msg)
                if self._closing:
                    return
                try:
                    self._track_after(0, lambda m=msg: self._show_sync_error(m))
                except Exception:
                    pass

        def _do():
            if self._closing:
                return
            if self.sync:
                self.sync.push(blocking=False, on_done=_on_done)
            # Replanifier seulement si la fenêtre existe encore
            if self._closing:
                return
            try:
                self._track_after(self._AUTO_SYNC_INTERVAL_MS, _do)
            except Exception:
                pass
        self._track_after(self._AUTO_SYNC_INTERVAL_MS, _do)

    # ────────────────────────────────────────────────────────
    #  POPUP ERREUR SYNC (dismissable)
    # ────────────────────────────────────────────────────────
    def _show_sync_error(self, msg: str):
        """Affiche un popup non bloquant pour informer d'un échec Supabase."""
        import datetime
        log.warning("[Sync] Erreur affichée à l'utilisateur : %s", msg)

        dlg = ctk.CTkToplevel(self)
        dlg.title("Synchronisation Supabase")
        dlg.geometry("460x190")
        dlg.resizable(False, False)
        # Non bloquant : pas de grab_set → l'utilisateur peut continuer à travailler

        ctk.CTkLabel(dlg, text="☁️  Erreur de synchronisation Supabase",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C.get("amber", "#F59E0B")).pack(padx=24, pady=(18, 6))

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        detail = msg.replace("⚠️  ", "").replace("⚠️", "").strip()
        ctk.CTkLabel(dlg, text=f"{ts} — {detail}",
                     font=ctk.CTkFont(size=11),
                     text_color=C["muted"],
                     wraplength=400, justify="left").pack(padx=24, pady=(0, 6))

        ctk.CTkLabel(dlg,
                     text="Vos données locales sont intactes. Vous pouvez réessayer\n"
                          "depuis Paramètres → Synchronisation Supabase.",
                     font=ctk.CTkFont(size=11),
                     text_color=C["text"],
                     justify="left").pack(padx=24, pady=(0, 14))

        ctk.CTkButton(dlg, text="Ignorer", width=120, height=32,
                      fg_color=C["muted"], hover_color="#475569",
                      font=ctk.CTkFont(size=12),
                      command=dlg.destroy).pack()

    # ────────────────────────────────────────────────────────
    #  ALERTES AU DÉMARRAGE
    # ────────────────────────────────────────────────────────
    def _run_startup_checks(self):
        """Lance les vérifications d'alertes dans le thread principal.
        Déjà différé de 800 ms via after() — pas besoin d'un thread séparé
        (appeler self.after() depuis un thread secondaire est interdit en Tkinter)."""
        self._check_alerts()

    def _check_alerts(self):
        alerts = []

        # ── 1. Rappel de saisie mensuelle ───────────────────
        today   = date.today()
        if today.day <= 5:
            prev_month = today.month - 1 if today.month > 1 else 12
            prev_year  = today.year if today.month > 1 else today.year - 1
            mid = self.db.month_id(prev_year, prev_month, create=False)
            has_data = mid and (
                len(self.db.get_revenues(prev_year, prev_month)) > 0 or
                len(self.db.get_expenses(prev_year, prev_month)) > 0
            )
            if not has_data:
                from config import MONTHS_FR
                alerts.append({
                    "type":  "reminder",
                    "title": "Rappel de saisie mensuelle",
                    "body":  f"Aucune donnée saisie pour {MONTHS_FR[prev_month-1]} {prev_year}.\n"
                             f"Pensez à enregistrer vos revenus et dépenses du mois passé.",
                    "action_label": "Saisir maintenant",
                    "action_page":  "revenues",
                })

        # ── 2. Dépenses inhabituelles ────────────────────────
        unusual = _detect_unusual_expenses(self.db)
        alerts.extend(unusual)

        # ── 3. Objectifs en retard ────────────────────────────
        late_goals = _check_late_goals(self.db)
        alerts.extend(late_goals)

        if alerts:
            _show_alerts_popup(self, alerts)

    # ────────────────────────────────────────────────────────
    #  SIDEBAR
    # ────────────────────────────────────────────────────────
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=C["sidebar"],
                          corner_radius=0)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        # row 0 = logo, row 1 = sep, row 2 = nav (expand), row 3 = footer
        sb.grid_rowconfigure(2, weight=1)

        # ── Logo ──────────────────────────────────────────────
        logo_f = ctk.CTkFrame(sb, fg_color="transparent")
        logo_f.grid(row=0, column=0, padx=16, pady=(18, 10), sticky="w")

        _logo_png = _resource_path("fintrack_256.png")
        if os.path.isfile(_logo_png):
            try:
                from PIL import Image as _PILImage
                _pil_logo = _PILImage.open(_logo_png)
                _ctk_logo = ctk.CTkImage(
                    light_image=_pil_logo,
                    dark_image=_pil_logo,
                    size=(34, 34),
                )
                ctk.CTkLabel(logo_f, text="", image=_ctk_logo).pack(side="left")
            except Exception:
                # Fallback si PIL/image indisponible
                ctk.CTkLabel(logo_f, text="📊",
                             font=ctk.CTkFont(size=22),
                             text_color="#A5B4FC").pack(side="left")
        else:
            ctk.CTkLabel(logo_f, text="📊",
                         font=ctk.CTkFont(size=22),
                         text_color="#A5B4FC").pack(side="left")

        ctk.CTkLabel(logo_f, text=" Fintrack",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="white", justify="left").pack(side="left")

        ctk.CTkFrame(sb, height=1, fg_color="#334155").grid(
            row=1, column=0, sticky="ew", padx=14, pady=(0, 2)
        )

        # ── Zone de navigation scrollable ─────────────────────
        # Permet au menu de défiler si la fenêtre est trop petite
        nav_scroll = ctk.CTkScrollableFrame(
            sb, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=C["sidebar"],
            scrollbar_button_hover_color="#334155",
        )
        nav_scroll.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        nav_scroll.grid_columnconfigure(0, weight=1)

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for item in _NAV_ITEMS:
            if item is None:
                # Séparateur fin
                ctk.CTkFrame(nav_scroll, height=1,
                             fg_color="#1E2D45").pack(
                    fill="x", padx=16, pady=(2, 2)
                )
            elif isinstance(item, str):
                # Label de section — compact
                ctk.CTkLabel(nav_scroll, text=item,
                             font=ctk.CTkFont(size=9, weight="bold"),
                             text_color="#475569",
                             anchor="w").pack(
                    fill="x", padx=20, pady=(7, 1)
                )
            else:
                label, key, tip = item
                btn = nav_button(nav_scroll, label,
                                 command=lambda k=key: self._go(k),
                                 tooltip=tip)
                btn.pack(fill="x", padx=6, pady=1)
                self._nav_buttons[key] = btn

        # ── Pied de page ──────────────────────────────────────
        db_mode  = self.db.get_setting("db_mode", "local")
        mode_str = "☁ Supabase" if db_mode == "online" else "💾 local"
        ctk.CTkLabel(sb, text=f"v{APP_VERSION}  ·  {mode_str}",
                     font=ctk.CTkFont(size=10),
                     text_color="#475569").grid(
            row=3, column=0, padx=18, pady=(4, 14), sticky="sw"
        )

    # ────────────────────────────────────────────────────────
    #  ZONE DE CONTENU
    # ────────────────────────────────────────────────────────
    def _build_content_area(self):
        self._content = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self._content.grid(row=1, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

    # ────────────────────────────────────────────────────────
    #  BARRE SUPÉRIEURE (nom d'utilisateur, coin haut-droit)
    # ────────────────────────────────────────────────────────
    def _build_topbar(self):
        topbar = ctk.CTkFrame(self, height=40, fg_color=C["bg"], corner_radius=0)
        topbar.grid(row=0, column=1, sticky="new")
        topbar.grid_propagate(False)

        username = Auth.get_username(self.db)
        if username:
            ctk.CTkLabel(
                topbar, text=f"👤  {username}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=C["muted"],
            ).pack(side="right", padx=20, pady=10)

    # ────────────────────────────────────────────────────────
    #  NAVIGATION
    # ────────────────────────────────────────────────────────
    def _go(self, page_key: str):
        self._dash_soft_refresh = None
        self._ana_soft_refresh  = None
        self._current_page = page_key

        # Mettre en surbrillance la nav immédiatement (réactivité)
        self._update_nav_highlight(page_key)

        # Libérer toutes les figures matplotlib avant de détruire les frames :
        # évite l'accumulation de figures en mémoire au fil des navigations.
        try:
            import sys
            if "matplotlib" in sys.modules:
                import matplotlib.pyplot as plt
                plt.close("all")
        except Exception:
            pass

        # Détruire l'ancienne page
        for w in self._content.winfo_children():
            w.destroy()

        container = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        # ── Placeholder anti-flash ───────────────────────────
        # Remplit immédiatement le container avec la couleur de fond,
        # évitant toute zone noire entre la destruction et le rendu.
        ph = ctk.CTkFrame(container, fg_color=C["bg"], corner_radius=0)
        ph.grid(row=0, column=0, sticky="nsew")
        ph.grid_columnconfigure(0, weight=1)
        ph.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(
            ph, text="",
            fg_color=C["bg"],
        ).grid(row=0, column=0, sticky="nsew")

        page_cls = _load_page_class(page_key)
        if page_cls:
            # Délai court : laisse l'UI peindre le placeholder (nav + fond coloré)
            # avant de lancer le rendu — plus fluide, sans flash noir.
            self._track_after(8, lambda: self._render_page(page_cls, container))

    def _render_page(self, page_cls, container):
        """Rend la page dans le container donné (appelé en différé)."""
        # Vérifie que le container n'a pas déjà été détruit par un _go() concurrent
        try:
            if not container.winfo_exists():
                return
        except Exception:
            return
        # Supprimer le placeholder avant de rendre la vraie page
        for w in container.winfo_children():
            w.destroy()
        try:
            page_cls().render(container, self)
        except Exception as exc:
            log.error("Erreur rendu page : %s", exc, exc_info=True)

    def _update_nav_highlight(self, active_key: str):
        for key, btn in self._nav_buttons.items():
            if key == active_key:
                btn.configure(fg_color=C["primary"],
                              hover_color=C["primary"],
                              text_color="white")
            else:
                btn.configure(fg_color="transparent",
                              hover_color="#2D3F5E",
                              text_color="#CBD5E1")

    # ────────────────────────────────────────────────────────
    #  TOGGLE MODE SOMBRE (appelé depuis Settings)
    # ────────────────────────────────────────────────────────
    def toggle_dark_mode(self, enable: bool):
        self.db.set_setting("dark_mode", "1" if enable else "0")
        # Appliquer immédiatement sans redémarrage
        apply_palette(enable)
        ctk.set_appearance_mode("dark" if enable else "light")
        # Recharger la page courante avec la nouvelle palette
        self.configure(fg_color=C["bg"])
        self._track_after(50, lambda: None if self._closing else self._go(self._current_page or "dashboard"))


# ─────────────────────────────────────────────────────────────
#  Détection dépenses inhabituelles
# ─────────────────────────────────────────────────────────────
def _detect_unusual_expenses(db) -> list[dict]:
    """Détecte les catégories avec dépenses > 2x la moyenne des 3 mois précédents."""
    alerts = []
    today  = date.today()

    # Mois le plus récent avec données
    last = db.get_last_month_with_data()
    if not last:
        return alerts
    ly, lm = last

    # Récupère les dépenses du mois récent
    recent_cats = {r["name"]: r["total"]
                   for r in db.get_expenses_by_category(ly, lm)}
    if not recent_cats:
        return alerts

    # Calcule la moyenne des mois précédents pour chaque catégorie
    history = db.monthly_summary(6)  # jusqu'à 6 mois
    # On exclut le mois le plus récent (index 0 = le plus récent)
    prev_months = list(reversed(history))[:-1]   # du plus ancien au plus récent, sans le dernier
    if len(prev_months) < 2:
        return alerts

    # 1 seule requête pour tous les mois (remplace le N+1 précédent)
    nb_prev = len(prev_months)
    periods  = [(m["year"], m["month"]) for m in prev_months]
    cat_rows = db.get_expenses_by_category_range(periods)

    # Moyenne mensuelle = total sur la période / nb de mois étudiés
    # (diviser par nb_prev est intentionnellement conservateur : si une catégorie
    #  n'a de données que 2 mois sur 5, sa moyenne sera basse → moins de faux positifs)
    cat_avgs: dict = {
        r["name"]: float(r["total"]) / nb_prev
        for r in cat_rows
    }

    from config import MONTHS_FR
    month_label = f"{MONTHS_FR[lm-1]} {ly}"

    for cat, current in recent_cats.items():
        if cat not in cat_avgs:
            continue
        avg = cat_avgs[cat]
        if avg > 0 and current > avg * 2 and current > 50:   # seuil min 50 € pour éviter le bruit
            alerts.append({
                "type":  "unusual",
                "title": f"Dépense inhabituelle — {cat.title()}",
                "body":  f"En {month_label}, vous avez dépensé {current:,.0f} € en {cat.title()},\n"
                         f"soit {current/avg:.1f}x votre moyenne habituelle ({avg:,.0f} €/mois).",
                "action_label": "Voir les dépenses",
                "action_page":  "expenses",
            })

    return alerts[:3]   # max 3 alertes pour ne pas surcharger


# ─────────────────────────────────────────────────────────────
#  Vérification objectifs en retard
# ─────────────────────────────────────────────────────────────
def _check_late_goals(db) -> list[dict]:
    alerts = []
    try:
        goals = db.get_savings_goals()
    except Exception:
        return alerts

    today = date.today()
    for g in goals:
        try:
            td = date.fromisoformat(g["target_date"])
        except Exception:
            continue
        if g["current_amount"] >= g["target_amount"]:
            continue
        pct = g["current_amount"] / g["target_amount"] * 100 if g["target_amount"] else 0
        months_left = (td.year - today.year) * 12 + (td.month - today.month)
        if 0 < months_left <= 3 and pct < 80:
            alerts.append({
                "type":  "goal",
                "title": f"Objectif bientôt échu — {g['name']}",
                "body":  f"Il vous reste {months_left} mois pour atteindre votre objectif\n"
                         f"« {g['name']} » ({pct:.0f}% atteint sur {g['target_amount']:,.0f} €).",
                "action_label": "Voir les objectifs",
                "action_page":  "objectifs",
            })
    return alerts


# ─────────────────────────────────────────────────────────────
#  Popup d'alertes
# ─────────────────────────────────────────────────────────────
def _show_alerts_popup(app, alerts: list[dict]):
    """Affiche une fenêtre modale avec toutes les alertes du démarrage."""
    win = ctk.CTkToplevel(app)
    win.title("Alertes & Notifications")
    win.geometry("520x520")
    win.resizable(False, False)
    win.lift()
    win.focus_force()
    win.grab_set()

    # ── Header ──────────────────────────────────────────────
    hdr = ctk.CTkFrame(win, fg_color=C["sidebar"], corner_radius=0, height=52)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)
    ctk.CTkLabel(hdr,
                 text=f"  🔔  {len(alerts)} notification{'s' if len(alerts) > 1 else ''}",
                 font=ctk.CTkFont(size=15, weight="bold"),
                 text_color="white").pack(side="left", padx=16, pady=12)

    # ── Scroll ───────────────────────────────────────────────
    scroll = ctk.CTkScrollableFrame(win, fg_color="#F8FAFC")
    scroll.pack(fill="both", expand=True, padx=14, pady=10)

    _ALERT_STYLE = {
        "reminder": {"icon": "📅", "bg": "#EFF6FF", "border": "#BFDBFE", "color": "#1D4ED8"},
        "unusual":  {"icon": "⚠️", "bg": "#FFFBEB", "border": "#FDE68A", "color": "#B45309"},
        "goal":     {"icon": "🎯", "bg": "#FEF2F2", "border": "#FCA5A5", "color": "#DC2626"},
    }

    for alert in alerts:
        style = _ALERT_STYLE.get(alert["type"], _ALERT_STYLE["reminder"])

        card = ctk.CTkFrame(scroll, fg_color=style["bg"], corner_radius=10,
                             border_width=1, border_color=style["border"])
        card.pack(fill="x", pady=5)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        title_f = ctk.CTkFrame(inner, fg_color="transparent")
        title_f.pack(fill="x")
        ctk.CTkLabel(title_f, text=style["icon"],
                     font=ctk.CTkFont(size=16)).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(title_f, text=alert["title"],
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=style["color"]).pack(side="left")

        ctk.CTkLabel(inner, text=alert["body"],
                     font=ctk.CTkFont(size=11), text_color=C["text"],
                     justify="left", wraplength=420).pack(anchor="w", pady=(6, 4))

        def make_action(page, w=win):
            def go():
                w.destroy()
                app._go(page)
            return go

        ctk.CTkButton(inner,
                      text=f"→  {alert['action_label']}",
                      height=28, width=180,
                      font=ctk.CTkFont(size=11),
                      fg_color=style["color"],
                      hover_color=style["color"],
                      text_color="white",
                      command=make_action(alert["action_page"])
                      ).pack(anchor="e")

    # ── Footer ───────────────────────────────────────────────
    foot = ctk.CTkFrame(win, fg_color="transparent", height=50)
    foot.pack(fill="x", padx=14, pady=(0, 10))
    foot.pack_propagate(False)
    ctk.CTkButton(foot, text="✓  Fermer",
                  height=34, fg_color=C["primary"],
                  font=ctk.CTkFont(size=12),
                  command=win.destroy).pack(side="right")


