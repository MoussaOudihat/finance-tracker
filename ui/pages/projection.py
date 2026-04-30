"""
ui/pages/projection.py — Projection du patrimoine à long terme
"""
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import customtkinter as ctk
from config import C, MONTHS_FR
from ui.components import make_card


class ProjectionPage:
    """Page de projection du patrimoine avec intérêts composés."""

    def render(self, container: ctk.CTkFrame, app):
        """
        Affiche la page de projection du patrimoine.

        Args:
            container: Frame parent
            app: Instance de l'application
        """
        db = app.db

        # Récupérer le patrimoine actuel
        assets_current = db.get_assets_current()
        patrimoine_actuel = sum(a["value"] for a in assets_current)

        # Récupérer la moyenne d'épargne sur les 6 derniers mois
        summary = db.monthly_summary(limit=6)
        avg_epargne = (sum(s["sav"] for s in summary) / len(summary)) if summary else 0

        # State pour stocker les paramètres
        state = {
            "taux_rendement": 7.0,
            "epargne_mensuelle": avg_epargne,
            "horizon_ans": 20,
            "inflation": 2.0,
        }

        # ──────────────────────────────────────────────────────
        # SCROLL PRINCIPAL
        # ──────────────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(container, fg_color=C["bg"])
        scroll.pack(fill="both", expand=True, padx=24, pady=20)

        # ──────────────────────────────────────────────────────
        # TITRE
        # ──────────────────────────────────────────────────────
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(anchor="w", pady=(0, 20))

        ctk.CTkLabel(
            header,
            text="🔮 Projection du Patrimoine",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=C["text"],
        ).pack(anchor="w")

        # ──────────────────────────────────────────────────────
        # PANNEAU DE PARAMÈTRES
        # ──────────────────────────────────────────────────────
        params_card = make_card(scroll, corner_radius=12)
        params_card.pack(fill="x", pady=(0, 20))

        params_inner = ctk.CTkFrame(params_card, fg_color="transparent")
        params_inner.pack(fill="x", padx=16, pady=16)

        # Titre des paramètres
        ctk.CTkLabel(
            params_inner,
            text="Paramètres de projection",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["text"],
        ).pack(anchor="w", pady=(0, 16))

        # --- Taux de rendement ---
        taux_frame = ctk.CTkFrame(params_inner, fg_color="transparent")
        taux_frame.pack(fill="x", pady=8)

        ctk.CTkLabel(
            taux_frame,
            text="Taux de rendement annuel (%)",
            font=ctk.CTkFont(size=11),
            text_color=C["text"],
        ).pack(anchor="w")

        taux_container = ctk.CTkFrame(taux_frame, fg_color="transparent")
        taux_container.pack(fill="x", pady=(4, 0))

        taux_slider = ctk.CTkSlider(
            taux_container,
            from_=0, to=15, number_of_steps=30,
            command=lambda v: state.update({"taux_rendement": v}),
        )
        taux_slider.set(state["taux_rendement"])
        taux_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        taux_label = ctk.CTkLabel(
            taux_container,
            text=f"{state['taux_rendement']:.1f}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C["primary"],
            width=50,
        )
        taux_label.pack(side="left")

        def update_taux_label(v):
            state["taux_rendement"] = v
            taux_label.configure(text=f"{v:.1f}%")

        taux_slider.configure(command=update_taux_label)

        # --- Épargne mensuelle ---
        epargne_frame = ctk.CTkFrame(params_inner, fg_color="transparent")
        epargne_frame.pack(fill="x", pady=8)

        ctk.CTkLabel(
            epargne_frame,
            text="Épargne mensuelle (€)",
            font=ctk.CTkFont(size=11),
            text_color=C["text"],
        ).pack(anchor="w")

        epargne_entry = ctk.CTkEntry(
            epargne_frame,
            placeholder_text=f"Défaut: {state['epargne_mensuelle']:.0f}",
            height=32,
        )
        epargne_entry.pack(fill="x", pady=(4, 0))
        epargne_entry.insert(0, f"{state['epargne_mensuelle']:.0f}")

        def on_epargne_change(*args):
            try:
                val = float(epargne_entry.get() or state["epargne_mensuelle"])
                state["epargne_mensuelle"] = max(0, val)
            except ValueError:
                pass

        epargne_entry.bind("<KeyRelease>", on_epargne_change)

        # --- Horizon (boutons radio) ---
        horizon_frame = ctk.CTkFrame(params_inner, fg_color="transparent")
        horizon_frame.pack(fill="x", pady=8)

        ctk.CTkLabel(
            horizon_frame,
            text="Horizon temporel",
            font=ctk.CTkFont(size=11),
            text_color=C["text"],
        ).pack(anchor="w")

        horizon_buttons_frame = ctk.CTkFrame(horizon_frame, fg_color="transparent")
        horizon_buttons_frame.pack(fill="x", pady=(4, 0))

        horizon_var = ctk.StringVar(value="20")

        for label, value in [("5 ans", "5"), ("10 ans", "10"), ("20 ans", "20"), ("30 ans", "30")]:
            btn = ctk.CTkButton(
                horizon_buttons_frame,
                text=label,
                width=80,
                height=32,
                command=lambda v=value: (
                    horizon_var.set(v),
                    state.update({"horizon_ans": int(v)}),
                ),
            )
            btn.pack(side="left", padx=4)

        # --- Inflation ---
        inflation_frame = ctk.CTkFrame(params_inner, fg_color="transparent")
        inflation_frame.pack(fill="x", pady=8)

        ctk.CTkLabel(
            inflation_frame,
            text="Inflation estimée (%)",
            font=ctk.CTkFont(size=11),
            text_color=C["text"],
        ).pack(anchor="w")

        inflation_entry = ctk.CTkEntry(
            inflation_frame,
            placeholder_text="Défaut: 2",
            height=32,
        )
        inflation_entry.pack(fill="x", pady=(4, 0))
        inflation_entry.insert(0, "2.0")

        def on_inflation_change(*args):
            try:
                val = float(inflation_entry.get() or 2.0)
                state["inflation"] = max(0, val)
            except ValueError:
                pass

        inflation_entry.bind("<KeyRelease>", on_inflation_change)

        # ──────────────────────────────────────────────────────
        # ZONE GRAPHIQUE + RÉSUMÉ
        # ──────────────────────────────────────────────────────
        main_container = ctk.CTkFrame(scroll, fg_color="transparent")
        main_container.pack(fill="both", expand=True, pady=(0, 20))
        main_container.grid_columnconfigure(0, weight=3)
        main_container.grid_columnconfigure(1, weight=1)

        # Graphique (gauche)
        chart_card = make_card(main_container, corner_radius=12)
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        chart_frame = ctk.CTkFrame(chart_card, fg_color="transparent")
        chart_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Conteneur pour matplotlib
        canvas_holder = [None]

        # Résumé (droite)
        summary_card = make_card(main_container, corner_radius=12)
        summary_card.grid(row=0, column=1, sticky="nsew")

        summary_inner = ctk.CTkFrame(summary_card, fg_color="transparent")
        summary_inner.pack(fill="both", expand=True, padx=16, pady=16)

        summary_widgets = {}

        def _create_summary_stat(parent, label, var_key):
            """Crée une ligne de statistique."""
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.pack(fill="x", pady=8)

            ctk.CTkLabel(
                frame,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color=C["muted"],
            ).pack(anchor="w")

            value_label = ctk.CTkLabel(
                frame,
                text="0 €",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=C["primary"],
            )
            value_label.pack(anchor="w", pady=(2, 0))

            return value_label

        summary_widgets["actuel"] = _create_summary_stat(
            summary_inner,
            "Patrimoine actuel",
            "actuel"
        )
        summary_widgets["projete"] = _create_summary_stat(
            summary_inner,
            f"Patrimoine à {state['horizon_ans']} ans",
            "projete"
        )
        summary_widgets["gain_composé"] = _create_summary_stat(
            summary_inner,
            "Gain intérêts composés",
            "gain"
        )
        summary_widgets["valeur_reel"] = _create_summary_stat(
            summary_inner,
            "Valeur réelle (inflation)",
            "reel"
        )

        # ──────────────────────────────────────────────────────
        # FONCTION DE RECALCUL
        # ──────────────────────────────────────────────────────
        def _recalculate():
            # Lire les paramètres
            try:
                epargne_m = float(epargne_entry.get() or state["epargne_mensuelle"])
                epargne_m = max(0, epargne_m)
            except ValueError:
                epargne_m = state["epargne_mensuelle"]

            try:
                inflation = float(inflation_entry.get() or state["inflation"])
                inflation = max(0, inflation)
            except ValueError:
                inflation = state["inflation"]

            horizon = state["horizon_ans"]
            taux = state["taux_rendement"]

            # Calculs de projection
            data = _compute_projection(
                patrimoine_actuel, epargne_m, taux, inflation, horizon
            )

            # Mettre à jour les labels du résumé
            summary_widgets["actuel"].configure(
                text=f"{patrimoine_actuel:,.0f} €"
            )
            summary_widgets["projete"].configure(
                text=f"{data['patrimoines'][-1]:,.0f} €"
            )
            summary_widgets["gain_composé"].configure(
                text=f"{data['gains_composés'][-1]:,.0f} €"
            )
            summary_widgets["valeur_reel"].configure(
                text=f"{data['valeurs_reelles'][-1]:,.0f} €"
            )

            # Redessiner le graphique
            if canvas_holder[0]:
                canvas_holder[0].get_tk_widget().destroy()

            fig, ax = plt.subplots(figsize=(8, 5), facecolor="#F8FBFF")
            ax.set_facecolor("#F8FBFF")

            # Axes
            years = list(range(len(data["patrimoines"])))

            # Courbe "Avec investissement"
            ax.plot(
                years, data["patrimoines"],
                color=C["primary"], linewidth=2.5, label="Avec investissement"
            )

            # Courbe "Sans rendement" (croissance linéaire)
            ax.plot(
                years, data["sans_rendement"],
                color=C["muted"], linewidth=2, linestyle="--", label="Sans rendement"
            )

            # Courbe "Valeur réelle"
            ax.plot(
                years, data["valeurs_reelles"],
                color=C["red"], linewidth=2, linestyle="--", label="Valeur réelle (inflation)"
            )

            # Zone remplie entre les deux
            ax.fill_between(
                years, data["sans_rendement"], data["patrimoines"],
                alpha=0.15, color=C["primary"], label="Gain composé"
            )

            # Formatage des axes
            ax.set_xlabel("Années", fontsize=11, color=C["text"])
            ax.set_ylabel("Montant (€)", fontsize=11, color=C["text"])
            ax.grid(True, alpha=0.2, linestyle="-", linewidth=0.5)
            ax.set_axisbelow(True)

            # Formatter l'axe Y en k€ ou M€
            def format_y(val, pos):
                if val >= 1_000_000:
                    return f"{val / 1_000_000:.1f}M€"
                elif val >= 1_000:
                    return f"{val / 1_000:.0f}k€"
                else:
                    return f"{val:.0f}€"

            ax.yaxis.set_major_formatter(plt.FuncFormatter(format_y))

            # Légende
            ax.legend(loc="upper left", fontsize=10, framealpha=0.9)

            # Spines
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#E2E8F0")
            ax.spines["bottom"].set_color("#E2E8F0")

            # Couleur des ticks
            ax.tick_params(colors=C["text"], labelsize=10)

            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            canvas.draw_idle()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            canvas_holder[0] = canvas

        def _on_slider_release(v):
            """Callback quand on relâche le slider."""
            _recalculate()

        # Attacher à tous les contrôles
        taux_slider.configure(command=lambda v: (
            update_taux_label(v),
            _on_slider_release(v),
        ))
        epargne_entry.bind("<FocusOut>", lambda e: _recalculate())
        inflation_entry.bind("<FocusOut>", lambda e: _recalculate())

        # Bouton "Recalculer"
        def _on_horizon_change(v):
            state["horizon_ans"] = int(v)
            _recalculate()

        # Override les boutons horizon
        for widget in horizon_buttons_frame.winfo_children():
            original_cmd = widget.cget("command")
            widget.configure(command=lambda: (
                original_cmd() if callable(original_cmd) else None,
                _recalculate(),
            ))

        # Calcul initial
        _recalculate()


def _compute_projection(patrimoine_initial: float, epargne_mensuelle: float,
                        taux_rendement: float, inflation: float,
                        horizon_ans: int) -> dict:
    """
    Calcule les projections du patrimoine.

    Args:
        patrimoine_initial: Patrimoine initial (€)
        epargne_mensuelle: Épargne mensuelle (€)
        taux_rendement: Taux annuel (%)
        inflation: Taux d'inflation annuel (%)
        horizon_ans: Nombre d'années à projeter

    Returns:
        dict avec:
        - patrimoines : list des patrimoines nominaux par année
        - sans_rendement : list des patrimoines sans rendement (croissance linéaire)
        - valeurs_reelles : list des patrimoines nominaux divisé par inflation
        - gains_composés : list des gains des intérêts composés
    """

    # Conversion taux annuel -> mensuel
    taux_mensuel = (1 + taux_rendement / 100) ** (1 / 12) - 1

    patrimoines = [patrimoine_initial]
    sans_rendement = [patrimoine_initial]
    valeurs_reelles = [patrimoine_initial]
    gains_composés = [0]

    capital = patrimoine_initial
    capital_lineaire = patrimoine_initial

    for annee in range(1, horizon_ans + 1):
        # Croissance avec intérêts composés
        for mois in range(12):
            capital = capital * (1 + taux_mensuel) + epargne_mensuelle

        # Croissance linéaire (sans rendement)
        capital_lineaire += epargne_mensuelle * 12

        # Valeur réelle (ajustée pour l'inflation)
        capital_reel = capital / ((1 + inflation / 100) ** annee)

        # Gain des intérêts composés
        gain = capital - capital_lineaire

        patrimoines.append(capital)
        sans_rendement.append(capital_lineaire)
        valeurs_reelles.append(capital_reel)
        gains_composés.append(max(0, gain))

    return {
        "patrimoines": patrimoines,
        "sans_rendement": sans_rendement,
        "valeurs_reelles": valeurs_reelles,
        "gains_composés": gains_composés,
    }
