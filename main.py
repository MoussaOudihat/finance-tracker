"""
main.py — Point d'entrée de l'application Finance Tracker
"""
import customtkinter as ctk
from config import DB_PATH, apply_palette
from database import Database


if __name__ == "__main__":
    # ── Base de données ──────────────────────────────────────
    db = Database(DB_PATH)

    # ── Palette (dark/light) doit être appliquée avant tout CTk ──
    dark = db.get_setting("dark_mode", "0") == "1"
    apply_palette(dark)
    ctk.set_appearance_mode("dark" if dark else "light")
    ctk.set_default_color_theme("blue")

    # ── Authentification ─────────────────────────────────────
    from ui.login import LoginApp
    login = LoginApp(db)
    login.mainloop()

    if not login.auth_success:
        # L'utilisateur a fermé la fenêtre sans se connecter
        raise SystemExit(0)

    # ── Application principale ───────────────────────────────
    from ui.app import App
    App().mainloop()
