"""
main.py — Point d'entrée de l'application Finance Tracker
"""
import customtkinter as ctk
from logger import log
from config import DB_PATH, APP_VERSION, apply_palette
from database import Database


if __name__ == "__main__":
    # ── Base de données locale (toujours présente) ───────────
    db = Database(DB_PATH)

    # ── Appliquer la config de log depuis la DB ───────────────
    from logger import apply_log_config_from_db
    apply_log_config_from_db(db)

    log.info("=== Fintrack v%s — démarrage ===", APP_VERSION)

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
        log.info("Authentification refusée — arrêt.")
        raise SystemExit(0)
    log.info("Authentification réussie.")
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
            log.info("[Sync] %s", msg)
            if pulled:
                # Le fichier SQLite a été mis à jour → recharger la DB
                db.close() if hasattr(db, "close") else None
                db = Database(DB_PATH)
    except Exception:
        log.warning("[Sync] Initialisation Supabase échouée", exc_info=True)

    # ── Application principale ───────────────────────────────
    from ui.app import App
    app = App(sync=sync)
    app.mainloop()

    # ── Push final à la fermeture ────────────────────────────
    if sync:
        log.info("[Sync] Upload final en cours…")
        sync.push(blocking=True)
    log.info("=== Fermeture propre ===")
