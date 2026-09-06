"""
cloud_auth.py — Authentification Supabase Auth (mode "online")

auth.py reste inchangé et gère exclusivement le mode local/offline
(bcrypt + question secrète, jamais synchronisé).

Ce module gère l'identité pour le mode cloud : email + mot de passe
vérifiés par Supabase, session persistée via un refresh token stocké
dans le trousseau OS (secrets_vault). La récupération de mot de passe
passe par un code OTP à 6 chiffres (pas de lien magique — une app
desktop ne peut pas recevoir de redirection web proprement).
"""
from supabase import create_client, Client

from secrets_vault import get_secret, save_secret, delete_secret
from logger import log


def build_client(url: str, anon_key: str) -> Client:
    return create_client(url.strip(), anon_key.strip())


# ─────────────────────────────────────────────────────────────
#  INSCRIPTION / CONNEXION / DÉCONNEXION
# ─────────────────────────────────────────────────────────────

def sign_up(client: Client, email: str, password: str):
    """Retourne (ok, message_erreur, session|None)."""
    try:
        res = client.auth.sign_up({"email": email.strip(), "password": password})
        return True, "", res.session
    except Exception as exc:
        log.warning("cloud_auth.sign_up échoué : %s", exc)
        return False, _friendly_error(exc), None


def sign_in(client: Client, email: str, password: str):
    """Retourne (ok, message_erreur, session|None)."""
    try:
        res = client.auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
        return True, "", res.session
    except Exception as exc:
        log.warning("cloud_auth.sign_in échoué : %s", exc)
        return False, _friendly_error(exc), None


def sign_out(client: Client) -> None:
    """Best-effort — ne lève jamais (ex. hors ligne)."""
    try:
        client.auth.sign_out()
    except Exception as exc:
        log.info("cloud_auth.sign_out : déconnexion locale seulement (%s)", exc)


# ─────────────────────────────────────────────────────────────
#  RÉCUPÉRATION DE MOT DE PASSE — CODE OTP (pas de lien magique)
# ─────────────────────────────────────────────────────────────
# Nécessite que le template email "Reset Password" du projet Supabase
# utilise {{ .Token }} (code) plutôt que le lien magique par défaut.

def request_password_reset(client: Client, email: str):
    """Retourne (ok, message)."""
    try:
        client.auth.reset_password_for_email(email.strip())
        return True, "Code envoyé par email."
    except Exception as exc:
        log.warning("cloud_auth.request_password_reset échoué : %s", exc)
        return False, _friendly_error(exc)


def verify_recovery_otp(client: Client, email: str, token: str):
    """Vérifie le code reçu par email. Retourne (ok, message, session|None).
    En cas de succès, `client` porte désormais la session temporaire de
    récupération — utiliser ce même client pour set_new_password()."""
    try:
        res = client.auth.verify_otp(
            {"email": email.strip(), "token": token.strip(), "type": "recovery"}
        )
        return True, "", res.session
    except Exception as exc:
        log.warning("cloud_auth.verify_recovery_otp échoué : %s", exc)
        return False, _friendly_error(exc), None


def set_new_password(client: Client, new_password: str):
    """Retourne (ok, message). Nécessite une session active sur `client`
    (issue de verify_recovery_otp, ou une session déjà connectée pour un
    changement de mot de passe classique depuis les Paramètres)."""
    try:
        client.auth.update_user({"password": new_password})
        return True, "Mot de passe mis à jour."
    except Exception as exc:
        log.warning("cloud_auth.set_new_password échoué : %s", exc)
        return False, _friendly_error(exc)


# ─────────────────────────────────────────────────────────────
#  CONFIRMATION D'INSCRIPTION PAR CODE OTP (si activée côté projet)
# ─────────────────────────────────────────────────────────────

def verify_signup_otp(client: Client, email: str, token: str):
    """Retourne (ok, message, session|None)."""
    try:
        res = client.auth.verify_otp(
            {"email": email.strip(), "token": token.strip(), "type": "email"}
        )
        return True, "", res.session
    except Exception as exc:
        log.warning("cloud_auth.verify_signup_otp échoué : %s", exc)
        return False, _friendly_error(exc), None


# ─────────────────────────────────────────────────────────────
#  PERSISTANCE DE SESSION (trousseau OS + app_settings non sensibles)
# ─────────────────────────────────────────────────────────────

def persist_session(db, session) -> None:
    """Stocke le refresh token dans le trousseau OS, l'identité (non
    sensible) dans app_settings. Ces clés sont exclues de la sync table
    (voir sync_supabase.SETTINGS_EXCLUDE)."""
    save_secret("supabase_refresh_token", session.refresh_token)
    db.set_setting("supabase_user_id", session.user.id)
    db.set_setting("supabase_user_email", session.user.email or "")


def clear_persisted_session(db) -> None:
    delete_secret("supabase_refresh_token")
    db.set_setting("supabase_user_id", "")
    db.set_setting("supabase_user_email", "")


def try_silent_refresh(db):
    """Appelé à chaque démarrage quand db_mode == 'online'.
    Retourne (ok, client_authentifié|None, user_id|None)."""
    url       = db.get_setting("supabase_url", "")
    anon_key  = db.get_setting("supabase_anon_key", "")
    refresh_token = get_secret("supabase_refresh_token")
    if not (url and anon_key and refresh_token):
        return False, None, None
    try:
        client = build_client(url, anon_key)
        res = client.auth.refresh_session(refresh_token)
        persist_session(db, res.session)  # le refresh token tourne à chaque usage
        return True, client, res.session.user.id
    except Exception as exc:
        log.info("cloud_auth.try_silent_refresh : session expirée/invalide (%s)", exc)
        return False, None, None


# ─────────────────────────────────────────────────────────────
#  Messages d'erreur
# ─────────────────────────────────────────────────────────────

def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "Invalid login credentials" in msg:
        return "Email ou mot de passe incorrect."
    if "User already registered" in msg:
        return "Un compte existe déjà avec cet email."
    if "Token has expired" in msg or "invalid" in msg.lower() and "otp" in msg.lower():
        return "Code invalide ou expiré."
    return msg
