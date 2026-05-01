"""
main.py — Point d'entrée de l'application Finance Tracker
"""
import customtkinter as ctk
from config import DB_PATH, apply_palette
from database import Database


if __name__ == "__main__":
    # ── Base de données locale (toujours présente) ───────────
    db = Database(DB_PATH)

    # ── Palette (dark/light) doit être appliquée avant tout CTk ──
    dark = db.get_setting("dark_mode", "0") == "1"
    apply_palette(dark)
    ctk.set_appearance_mode("dark" if dark else "light")
    ctk.set_default_color_theme("blue")

    # ── Authentification ─────────────────────────────────────
    from ui.login import LoginApp
    login = LoginApp(db)
    if not login.auth_success:
        login.mainloop()
    if not login.auth_success:
        raise SystemExit(0)
    # Ne pas appeler login.destroy() : CTk schedule de nouveaux after()
    # pendant la destruction qui tireraient sur le mainloop de App.
    # La fenêtre est déjà withdraw() par _finish() — le GC s'en chargera.

    # ── Sync Supabase au démarrage (si mode online) ──────────
    sync = None
    try:
        from sync_supabase import SupabaseSync
        sync = SupabaseSync.from_db(db)
        if sync:
            pulled, msg = sync.pull_if_newer()
            if pulled:
                # Le fichier SQLite a été mis à jour → recharger la DB
                db.close() if hasattr(db, "close") else None
                db = Database(DB_PATH)
                print(f"[Sync] {msg}")
    except Exception as e:
        print(f"[Sync] Initialisation échouée : {e}")

    # ── Application principale ───────────────────────────────
    from ui.app import App
    app = App(sync=sync)
    app.mainloop()

    # ── Push final à la fermeture ────────────────────────────
    if sync:
        print("[Sync] Upload final en cours…")
        sync.push(blocking=True)
