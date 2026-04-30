"""
ui/app.py — Fenêtre principale, sidebar et routage des pages
"""
from datetime import date
import importlib
import threading

import customtkinter as ctk
from config import C, DB_PATH, apply_palette
from database import Database
from ui.components import nav_button

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

# None = séparateur  |  (label, key, tooltip)
_NAV_ITEMS = [
    ("🏠  Tableau de bord",             "dashboard",      "Vue d'ensemble — revenus, dépenses et solde du mois"),
    None,
    ("💶  Revenus",                      "revenues",       "Saisir et consulter vos revenus"),
    ("💸  Dépenses",                     "expenses",       "Saisir et consulter vos dépenses"),
    ("🏦  Épargne",                      "savings_entry",  "Enregistrer vos versements d'épargne"),
    None,
    ("💰  Budget mensuel",              "budget",         "Définir et suivre votre budget par catégorie"),
    ("🎯  Objectifs d'épargne",         "objectifs",      "Gérer vos objectifs d'épargne à long terme"),
    None,
    ("📊  Analyses détaillées",         "analyses",       "Graphiques et statistiques détaillées"),
    ("📈  Patrimoine & Investissements", "patrimoine",     "Suivi de vos actifs et investissements"),
    ("🔮  Projection",                  "projection",     "Simuler l'évolution future de votre patrimoine"),
    ("📋  Historique",                  "historique",     "Historique complet et export de rapports"),
    None,
    ("🧠  Recommandations",             "recommandations","Conseils personnalisés basés sur vos données"),
    ("⚙️  Paramètres",                 "settings",       "Préférences, sécurité et gestion du compte"),
]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

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
        self.dash_cat_filter   = "Toutes catégories"
        self.dash_payee_filter = "Toutes enseignes"
        self.ana_cat_filter    = "Toutes catégories"
        self.ana_payee_filter  = "Toutes enseignes"
        self.pat_type_filter   = "Tous types"
        self.stacked_period    = 6

        # Callbacks soft-refresh
        self._dash_soft_refresh = None
        self._ana_soft_refresh  = None

        # ── Fenêtre ─────────────────────────────────────────
        self.title("Finance Tracker")
        self.geometry("1280x800")
        self.minsize(960, 620)
        self.configure(fg_color=C["bg"])

        # ── Layout principal ─────────────────────────────────
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content_area()

        self._current_page = None
        self._go("dashboard")

        # ── Pré-chargement DB en arrière-plan ────────────────
        threading.Thread(target=self._warm_cache, daemon=True).start()

        # ── Alertes au démarrage (légèrement différé) ────────
        self.after(800, self._run_startup_checks)

    # ────────────────────────────────────────────────────────
    #  PRÉ-CHARGEMENT CACHE DB
    # ────────────────────────────────────────────────────────
    def _warm_cache(self):
        """Pré-charge les requêtes fréquentes dans le cache DB en arrière-plan."""
        try:
            self.db.get_categories()
            self.db.get_assets_current()
            y, m = self.sel_year, self.sel_month
            self.db.get_expenses(y, m)
            self.db.get_revenues(y, m)
            self.db.monthly_summary(6)
        except Exception:
            pass  # Silencieux — juste un préchauffage

    # ────────────────────────────────────────────────────────
    #  ALERTES AU DÉMARRAGE
    # ────────────────────────────────────────────────────────
    def _run_startup_checks(self):
        """Lance les vérifications d'alertes dans un thread secondaire."""
        threading.Thread(target=self._check_alerts, daemon=True).start()

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
            self.after(0, lambda: _show_alerts_popup(self, alerts))

    # ────────────────────────────────────────────────────────
    #  SIDEBAR
    # ────────────────────────────────────────────────────────
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=235, fg_color=C["sidebar"],
                          corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(99, weight=1)

        ctk.CTkLabel(sb,
                     text="💰 Finance\n   Tracker",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="white",
                     justify="left").grid(
            row=0, column=0, padx=22, pady=(28, 18), sticky="w"
        )
        ctk.CTkFrame(sb, height=1, fg_color="#334155").grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 6)
        )

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        row_idx = 2
        for item in _NAV_ITEMS:
            if item is None:
                ctk.CTkFrame(sb, height=1, fg_color="#2D3F5E").grid(
                    row=row_idx, column=0, sticky="ew", padx=20, pady=(4, 4)
                )
            else:
                label, key, tip = item
                btn = nav_button(sb, label, command=lambda k=key: self._go(k), tooltip=tip)
                btn.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=1)
                self._nav_buttons[key] = btn
            row_idx += 1

        ctk.CTkLabel(sb, text="v3.0  |  sqlite local",
                     font=ctk.CTkFont(size=10),
                     text_color="#64748B").grid(
            row=100, column=0, padx=22, pady=(8, 18), sticky="sw"
        )

    # ────────────────────────────────────────────────────────
    #  ZONE DE CONTENU
    # ────────────────────────────────────────────────────────
    def _build_content_area(self):
        self._content = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

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
            self.after(8, lambda: self._render_page(page_cls, container))

    def _render_page(self, page_cls, container):
        """Rend la page dans le container donné (appelé en différé)."""
        # Supprimer le placeholder avant de rendre la vraie page
        for w in container.winfo_children():
            w.destroy()
        try:
            page_cls().render(container, self)
        except Exception as exc:
            import traceback
            print(f"[Finance Tracker] Erreur lors du rendu : {exc}")
            traceback.print_exc()

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
        self.after(50, lambda: self._go(self._current_page or "dashboard"))


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

    # Calcule la moyenne des 3 mois précédents pour chaque catégorie
    history = db.monthly_summary(6)  # jusqu'à 6 mois
    # On exclut le mois le plus récent (index 0 = le plus récent)
    prev_months = list(reversed(history))[:-1]   # du plus ancien au plus récent, sans le dernier
    if len(prev_months) < 2:
        return alerts

    cat_avgs: dict = {}
    for m in prev_months:
        for r in db.get_expenses_by_category(m["year"], m["month"]):
            if r["name"] not in cat_avgs:
                cat_avgs[r["name"]] = []
            cat_avgs[r["name"]].append(r["total"])

    from config import MONTHS_FR
    month_label = f"{MONTHS_FR[lm-1]} {ly}"

    for cat, current in recent_cats.items():
        if cat not in cat_avgs or len(cat_avgs[cat]) < 2:
            continue
        avg = sum(cat_avgs[cat]) / len(cat_avgs[cat])
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


# ─────────────────────────────────────────────────────────────
#  Avis de redémarrage (mode sombre)
# ─────────────────────────────────────────────────────────────
def _show_restart_notice(app):
    win = ctk.CTkToplevel(app)
    win.title("Redémarrage requis")
    win.geometry("380x180")
    win.resizable(False, False)
    win.lift()
    win.grab_set()

    ctk.CTkLabel(win,
                 text="🌙  Changement de thème",
                 font=ctk.CTkFont(size=15, weight="bold"),
                 text_color=C["text"]).pack(pady=(24, 6))
    ctk.CTkLabel(win,
                 text="Le nouveau thème sera appliqué\nau prochain démarrage de l'application.",
                 font=ctk.CTkFont(size=12),
                 text_color=C["muted"],
                 justify="center").pack(pady=(0, 18))

    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack()
    ctk.CTkButton(btns, text="OK",
                  width=120, height=34,
                  fg_color=C["primary"],
                  command=win.destroy).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="Redémarrer maintenant",
                  width=180, height=34,
                  fg_color=C["muted"],
                  command=lambda: (win.destroy(), app.destroy())).pack(side="left", padx=6)
