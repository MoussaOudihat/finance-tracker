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
    # ── Ramasse-miettes cyclique désactivé pour toute la durée de vie
    # de l'app ────────────────────────────────────────────────────
    # L'app lance plusieurs threads d'arrière-plan (pré-chargement cache,
    # connexion cloud, appels IA, sync Supabase). Le GC cyclique de Python
    # peut se déclencher sur N'IMPORTE QUEL thread en cours d'exécution,
    # et s'il collecte alors un objet Tkinter (widget, StringVar, image —
    # notamment la fenêtre de login, jamais explicitement détruite, voir
    # plus bas), Tcl/Tk exige que cette destruction ait lieu sur le thread
    # principal : sinon l'app plante ("Tcl_AsyncDelete: async handler
    # deleted by the wrong thread"). On désactive donc la collecte
    # automatique et on la relance manuellement, uniquement depuis le
    # thread principal (ici une fois, puis périodiquement dans App).
    import gc
    gc.disable()

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

    cloud_client  = login.cloud_client
    cloud_user_id = login.cloud_user_id

    # login.destroy() n'est volontairement pas appelé (voir commentaire
    # ci-dessus) : la fenêtre CTk withdraw() reste en mémoire jusqu'à sa
    # collecte. On force cette collecte ici, sur le thread principal,
    # avant que le moindre thread d'arrière-plan ne démarre (cf. note
    # sur gc.disable() en haut du fichier).
    del login
    gc.collect()

    # ── Sync Supabase au démarrage (mode cloud uniquement) ────
    # Le pull a déjà eu lieu pendant l'écran de connexion cloud
    # (cloud_auth / _finish_cloud_login) sauf lors d'une reconnexion
    # silencieuse par refresh token — pull_if_newer() couvre ce cas
    # et ne fait rien si le local est déjà à jour.
    sync = None
    _startup_sync_msg = ""
    if cloud_client and cloud_user_id:
        try:
            from sync_supabase import SupabaseSync
            sync = SupabaseSync.from_session(cloud_client, DB_PATH, cloud_user_id)
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
    app = App(sync=sync, startup_sync_msg=_startup_sync_msg,
              cloud_client=cloud_client, cloud_user_id=cloud_user_id)
    app.mainloop()

    # ── Push final à la fermeture ────────────────────────────
    if sync:
        log.info("[Sync] Upload final en cours…")

        def _log_push_result(msg: str):
            if msg.startswith("⚠️"):
                log.warning("[Sync] %s", msg)
            else:
                log.info("[Sync] %s", msg)

        sync.push(blocking=True, on_done=_log_push_result)
    log.info("=== Fermeture propre ===")
