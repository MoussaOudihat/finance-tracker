"""
main.py — Point d'entrée de l'application Finance Tracker
"""
import sys
import customtkinter as ctk
from logger import log
from config import DB_PATH, APP_VERSION, apply_palette
from database import Database

# ── Instance unique (Windows) ────────────────────────────────
# Empêche d'ouvrir plusieurs fois l'application : le 2e lancement
# détecte le mutex existant et s'arrête immédiatement.
_mutex = None
if sys.platform == "win32":
    import ctypes as _ct
    _mutex = _ct.windll.kernel32.CreateMutexW(None, False, "FintrackSingleInstance")
    if _ct.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        import tkinter as _tk
        import tkinter.messagebox as _mb
        _r = _tk.Tk()
        _r.withdraw()
        _mb.showinfo(
            "Fintrack",
            "Fintrack est déjà ouvert.\nVérifiez la barre des tâches.",
        )
        _r.destroy()
        sys.exit(0)


if __name__ == "__main__":
    # ── Base de données locale (toujours présente) ───────────
    db = Database(DB_PATH)

    # ── Appliquer la config de log depuis la DB ───────────────
    from logger import apply_log_config_from_db
    apply_log_config_from_db(db)

    log.info("=== Fintrack v%s — démarrage ===", APP_VERSION)

    # ── Migration secrets DB → trousseau OS (one-shot) ────────
    from secrets_vault import migrate_from_db
    migrate_from_db(db)

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
    _startup_sync_msg = ""
    try:
        from sync_supabase import SupabaseSync
        sync = SupabaseSync.from_db(db)
        if sync:
            pulled, msg = sync.pull_if_newer()
            log.info("[Sync] %s", msg)
            if msg.startswith("⚠️"):
                _startup_sync_msg = msg   # sera affiché dans l'app
            if pulled:
                # Le fichier SQLite a été mis à jour → recharger la DB
                db.close()
                db = Database(DB_PATH)
    except Exception as _sync_exc:
        log.warning("[Sync] Initialisation Supabase échouée", exc_info=True)
        _startup_sync_msg = f"⚠️  Sync échoué au démarrage : {_sync_exc}"

    # ── Application principale ───────────────────────────────
    from ui.app import App
    app = App(sync=sync, startup_sync_msg=_startup_sync_msg)
    app.mainloop()

    # ── Push final à la fermeture ────────────────────────────
    if sync:
        log.info("[Sync] Upload final en cours…")
        sync.push(blocking=True)
    log.info("=== Fermeture propre ===")
