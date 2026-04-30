"""
ui/pages/objectifs.py — Page de suivi des objectifs d'épargne personnels
"""
import customtkinter as ctk
from datetime import date
from config import C
from ui.components import make_card, show_toast


class ObjectifsPage:
    def render(self, container: ctk.CTkFrame, app):
        self._app = app
        db = app.db

        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="🎯 Objectifs d'épargne",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C["text"]).pack(side="left")

        ctk.CTkButton(
            top, text="＋ Nouvel objectif",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=C["green"], text_color="white",
            command=self._on_new_goal
        ).pack(side="right")

        # ── Zone principale ──────────────────────────────────
        main = ctk.CTkFrame(container, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # ── Scrollable ──────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(main, fg_color=C["bg"])
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure((0, 1), weight=1)

        # ── Charger les objectifs ───────────────────────────
        goals = db.get_savings_goals()

        if not goals:
            self._render_empty_state(scroll)
        else:
            row = 0
            for goal in goals:
                self._render_goal_card(scroll, row, goal, db)
                row += 1

    def _render_empty_state(self, parent):
        """Affiche un message vide avec bouton."""
        empty = ctk.CTkFrame(parent, fg_color="transparent")
        empty.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=40)

        ctk.CTkLabel(
            empty, text="Aucun objectif pour le moment",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C["muted"],
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            empty, text="Créez votre premier objectif d'épargne",
            font=ctk.CTkFont(size=12),
            text_color=C["muted"],
        ).pack(pady=(0, 16))

        ctk.CTkButton(
            empty, text="🎯 Créer un objectif",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C["green"], text_color="white", height=40, width=200,
            command=self._on_new_goal
        ).pack()

    def _render_goal_card(self, parent, row, goal, db):
        """Crée une card pour un objectif."""
        card = make_card(parent)
        card.grid(row=row // 2, column=row % 2, sticky="nsew", padx=8, pady=8)
        card.grid_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=16)
        inner.pack_propagate(False)

        goal_id = goal["id"]
        name = goal["name"]
        target = goal["target_amount"]
        current = goal["current_amount"]
        notes = goal["notes"]

        # Titre de l'objectif
        ctk.CTkLabel(
            inner, text=name,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C["text"],
        ).pack(anchor="w", pady=(0, 12))

        # Calculer les infos
        today = date.today()
        try:
            target_date = date.fromisoformat(goal["target_date"])
        except (ValueError, TypeError):
            target_date = today

        months_left = max(1, (target_date.year - today.year) * 12 +
                         (target_date.month - today.month))
        monthly_needed = (target - current) / months_left if months_left > 0 else 0

        pct = (current / target * 100) if target > 0 else 0
        pct = min(pct, 100)  # Max 100%

        # Couleur selon % atteint
        if pct < 33:
            bar_color = C["red"]
        elif pct < 66:
            bar_color = C["amber"]
        elif pct < 100:
            bar_color = C["blue"]
        else:
            bar_color = C["green"]

        # Barre de progression
        bar_bg = ctk.CTkFrame(inner, fg_color="#E2E8F0", corner_radius=6, height=12)
        bar_bg.pack(fill="x", pady=(0, 8))
        bar_bg.pack_propagate(False)

        ctk.CTkFrame(
            bar_bg, fg_color=bar_color, corner_radius=6, height=12
        ).place(relx=0, rely=0, relwidth=min(pct / 100, 1.0), relheight=1)

        # Montants : actuel / cible
        amounts_frame = ctk.CTkFrame(inner, fg_color="transparent")
        amounts_frame.pack(fill="x", pady=(0, 2))

        ctk.CTkLabel(
            amounts_frame, text=f"{current:.2f} € / {target:.2f} €",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["text"],
        ).pack(side="left")

        ctk.CTkLabel(
            amounts_frame, text=f"{pct:.1f} %",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=bar_color,
        ).pack(side="right")

        # Date cible + mois restants
        date_str = target_date.strftime("%d/%m/%Y")
        ctk.CTkLabel(
            inner, text=f"Date cible : {date_str} ({months_left} mois restants)",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"],
        ).pack(anchor="w", pady=(2, 0))

        # Montant à épargner/mois
        ctk.CTkLabel(
            inner, text=f"À épargner/mois : {monthly_needed:.2f} €",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C["primary"],
        ).pack(anchor="w", pady=(0, 6))

        # Notes si présentes
        if notes:
            ctk.CTkLabel(
                inner, text=f"Notes : {notes}",
                font=ctk.CTkFont(size=10),
                text_color=C["muted"],
            ).pack(anchor="w", pady=(0, 8))

        # Boutons d'action
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 0))
        btn_frame.pack_propagate(False)

        ctk.CTkButton(
            btn_frame, text="✏ Modifier",
            font=ctk.CTkFont(size=11),
            fg_color=C["blue"], text_color="white", height=28, width=80,
            command=lambda: self._on_edit_goal(goal_id, db)
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btn_frame, text="💰 Mettre à jour",
            font=ctk.CTkFont(size=11),
            fg_color=C["amber"], text_color="white", height=28, width=120,
            command=lambda: self._on_update_amount(goal_id, current, db)
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="✕ Supprimer",
            font=ctk.CTkFont(size=11),
            fg_color=C["red"], text_color="white", height=28, width=80,
            command=lambda: self._on_delete_goal(goal_id, db)
        ).pack(side="right")

    def _on_new_goal(self):
        """Ouvre le dialog pour créer un nouvel objectif."""
        self._show_goal_dialog(None)

    def _on_edit_goal(self, goal_id, db):
        """Ouvre le dialog pour éditer un objectif."""
        goal = db.con.execute("SELECT * FROM savings_goals WHERE id=?", (goal_id,)).fetchone()
        if goal:
            self._show_goal_dialog(goal)

    def _on_update_amount(self, goal_id, current_amount, db):
        """Dialog rapide pour mettre à jour le montant actuel."""
        dlg = ctk.CTkToplevel(self._app)
        dlg.title("Mettre à jour le montant")
        dlg.geometry("400x150")
        dlg.attributes("-topmost", True)

        ctk.CTkLabel(
            dlg, text="Nouveau montant actuel (€) :",
            font=ctk.CTkFont(size=12),
        ).pack(pady=(16, 8))

        amount_var = ctk.StringVar(value=f"{current_amount:.2f}")
        amount_entry = ctk.CTkEntry(dlg, textvariable=amount_var, font=ctk.CTkFont(size=12))
        amount_entry.pack(pady=(0, 16), padx=16, fill="x")
        amount_entry.focus()

        def save():
            try:
                new_amount = float(amount_var.get().replace(",", "."))
                if new_amount < 0:
                    new_amount = 0
                db.update_goal_progress(goal_id, new_amount)
                dlg.destroy()
                show_toast(self._app, "Montant mis à jour !")
                self._app._go("objectifs")
            except ValueError:
                show_toast(self._app, "Montant invalide !")

        def on_enter(*_):
            save()

        amount_entry.bind("<Return>", on_enter)

        ctk.CTkButton(
            dlg, text="✓ Enregistrer",
            fg_color=C["green"], text_color="white",
            command=save
        ).pack(pady=(0, 12))

    def _on_delete_goal(self, goal_id, db):
        """Supprime un objectif après confirmation."""
        dlg = ctk.CTkToplevel(self._app)
        dlg.title("Confirmer la suppression")
        dlg.geometry("350x120")
        dlg.attributes("-topmost", True)

        ctk.CTkLabel(
            dlg, text="Êtes-vous sûr de vouloir supprimer cet objectif ?",
            font=ctk.CTkFont(size=12),
        ).pack(pady=16)

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(pady=(0, 12))

        def confirm():
            db.delete_savings_goal(goal_id)
            dlg.destroy()
            show_toast(self._app, "Objectif supprimé")
            self._app._go("objectifs")

        ctk.CTkButton(
            btn_frame, text="✓ Supprimer",
            fg_color=C["red"], text_color="white", width=100,
            command=confirm
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_frame, text="✕ Annuler",
            fg_color=C["muted"], text_color="white", width=100,
            command=dlg.destroy
        ).pack(side="left", padx=4)

    def _show_goal_dialog(self, goal):
        """Affiche le dialog de création/édition d'objectif."""
        dlg = ctk.CTkToplevel(self._app)
        dlg.title("Nouvel objectif" if not goal else "Modifier l'objectif")
        dlg.geometry("450x400")
        dlg.attributes("-topmost", True)

        is_new = goal is None

        # Titre du dialog
        ctk.CTkLabel(
            dlg, text="Nouvel objectif d'épargne" if is_new else "Modifier l'objectif",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(16, 20), padx=16)

        # Frame scrollable pour les champs
        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Champ Nom
        ctk.CTkLabel(form, text="Nom de l'objectif :", font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 4))
        name_var = ctk.StringVar(value=goal["name"] if goal else "")
        ctk.CTkEntry(form, textvariable=name_var, font=ctk.CTkFont(size=12),
                    placeholder_text="Ex: Vacances Japon").pack(fill="x", pady=(0, 12))

        # Champ Montant cible
        ctk.CTkLabel(form, text="Montant cible (€) :", font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 4))
        target_var = ctk.StringVar(value=f"{goal['target_amount']:.2f}" if goal else "")
        ctk.CTkEntry(form, textvariable=target_var, font=ctk.CTkFont(size=12),
                    placeholder_text="3000").pack(fill="x", pady=(0, 12))

        # Champ Montant actuel
        ctk.CTkLabel(form, text="Montant actuel (€) :", font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 4))
        current_var = ctk.StringVar(value=f"{goal['current_amount']:.2f}" if goal else "0.00")
        ctk.CTkEntry(form, textvariable=current_var, font=ctk.CTkFont(size=12),
                    placeholder_text="0").pack(fill="x", pady=(0, 12))

        # Champ Date cible
        ctk.CTkLabel(form, text="Date cible (AAAA-MM-DD) :", font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 4))
        today_str = date.today().isoformat()
        date_var = ctk.StringVar(value=goal["target_date"] if goal else today_str)
        ctk.CTkEntry(form, textvariable=date_var, font=ctk.CTkFont(size=12),
                    placeholder_text="2025-12-31").pack(fill="x", pady=(0, 12))

        # Champ Notes
        ctk.CTkLabel(form, text="Notes (optionnel) :", font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 4))
        notes_var = ctk.StringVar(value=goal["notes"] if goal else "")
        ctk.CTkEntry(form, textvariable=notes_var, font=ctk.CTkFont(size=12),
                    placeholder_text="Mes notes...").pack(fill="x", pady=(0, 12))

        # Boutons
        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))

        def save():
            name = name_var.get().strip()
            try:
                target = float(target_var.get().replace(",", "."))
                current = float(current_var.get().replace(",", "."))
            except ValueError:
                show_toast(self._app, "Montants invalides !")
                return

            target_date = date_var.get().strip()
            notes = notes_var.get().strip()

            # Valider la date
            try:
                date.fromisoformat(target_date)
            except (ValueError, TypeError):
                show_toast(self._app, "Format de date invalide (AAAA-MM-DD) !")
                return

            if not name:
                show_toast(self._app, "Entrez un nom pour l'objectif !")
                return

            if target <= 0:
                show_toast(self._app, "Le montant cible doit être positif !")
                return

            if is_new:
                self._app.db.add_savings_goal(name, target, target_date, current, notes)
            else:
                self._app.db.update_savings_goal(goal["id"], name, target, target_date, current, notes)

            dlg.destroy()
            show_toast(self._app, "Objectif enregistré !")
            self._app._go("objectifs")

        ctk.CTkButton(
            btn_frame, text="✓ Enregistrer",
            fg_color=C["green"], text_color="white",
            command=save
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            btn_frame, text="✕ Annuler",
            fg_color=C["muted"], text_color="white",
            command=dlg.destroy
        ).pack(side="right", padx=4)
