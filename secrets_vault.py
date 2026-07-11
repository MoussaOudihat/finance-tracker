"""
secrets_vault.py — Stockage sécurisé des secrets via le trousseau OS

Sur Windows : Windows Credential Manager (DPAPI — chiffrement lié au compte Windows)
Sur macOS   : macOS Keychain
Sur Linux   : Secret Service (GNOME Keyring / KWallet)

Fallback silencieux vers SQLite si keyring est indisponible —
l'app continue de fonctionner, les secrets restent dans la DB.

Clés gérées ici (jamais stockées en clair dans SQLite) :
  ai_api_key            — clé API Gemini / Anthropic / OpenAI
  supabase_service_key  — clé service Supabase (accès total DB distante)
  smtp_pass             — mot de passe du compte email SMTP
"""

from logger import log

_SERVICE = "Fintrack"

# Ensemble des clés considérées comme des secrets.
# Toute clé listée ici est lue/écrite via le trousseau,
# jamais directement en clair dans app_settings.
SECRET_KEYS: frozenset[str] = frozenset({
    "ai_api_key",
    "supabase_service_key",
    "smtp_pass",
})

# ── Détection keyring ──────────────────────────────────────────
try:
    import keyring as _keyring
    import keyring.errors as _kr_errors
    _KEYRING_OK = True
except ImportError:
    _keyring      = None
    _kr_errors    = None
    _KEYRING_OK   = False
    log.warning(
        "Module 'keyring' non installé — secrets stockés dans SQLite. "
        "Sécurité renforcée disponible avec : pip install keyring"
    )

# Cache mémoire (durée du process) — évite de rappeler le trousseau OS
# (appel bloquant) à chaque ouverture de la page Paramètres.
_cache: dict = {}


# ─────────────────────────────────────────────────────────────
#  API publique
# ─────────────────────────────────────────────────────────────

def get_secret(key: str) -> str:
    """
    Lit un secret depuis le trousseau OS (mis en cache pour la durée du
    process — évite de rappeler ce trousseau, un appel bloquant, à chaque
    ouverture de la page Paramètres).
    Retourne '' si absent, si keyring est indisponible, ou en cas d'erreur.
    """
    if not _KEYRING_OK:
        return ""
    if key in _cache:
        return _cache[key]
    try:
        val = _keyring.get_password(_SERVICE, key) or ""
    except Exception as exc:
        log.warning("vault.get_secret(%s) échoué : %s", key, exc)
        return ""
    _cache[key] = val
    return val


def save_secret(key: str, value: str) -> bool:
    """
    Enregistre un secret dans le trousseau OS.
    Retourne True si succès, False si keyring indisponible ou erreur.
    L'appelant doit stocker en fallback DB si False.
    """
    if not _KEYRING_OK:
        return False
    try:
        if value:
            _keyring.set_password(_SERVICE, key, value)
        else:
            _delete_silent(key)
        _cache[key] = value
        return True
    except Exception as exc:
        log.warning("vault.save_secret(%s) échoué : %s", key, exc)
        return False


def delete_secret(key: str) -> None:
    """Supprime un secret du trousseau OS. Silencieux si absent ou keyring indisponible."""
    _cache.pop(key, None)
    if not _KEYRING_OK:
        return
    _delete_silent(key)


def keyring_available() -> bool:
    """Retourne True si le trousseau OS est fonctionnel."""
    return _KEYRING_OK


# ─────────────────────────────────────────────────────────────
#  Migration one-shot (DB → trousseau)
# ─────────────────────────────────────────────────────────────

def migrate_from_db(db) -> None:
    """
    Migration transparente : déplace les secrets encore présents en clair
    dans app_settings vers le trousseau OS, puis les efface de la DB.

    Appelé une fois au démarrage. Idempotent — sans effet si déjà migré.
    Ne fait rien si keyring est indisponible.
    """
    if not _KEYRING_OK:
        return

    migrated: list[str] = []
    for key in SECRET_KEYS:
        db_val = db.get_setting(key, "")
        if not db_val:
            continue  # Déjà vide en DB (migré ou jamais configuré)

        vault_val = get_secret(key)
        if vault_val:
            # Le trousseau a déjà une valeur plus récente — effacer la DB uniquement
            db.set_setting(key, "")
            migrated.append(f"{key}(db→effacé)")
        else:
            # Déplacer vers le trousseau
            if save_secret(key, db_val):
                db.set_setting(key, "")
                migrated.append(key)
            # Si save_secret échoue, on laisse en DB (fallback)

    if migrated:
        log.info("Secrets migrés vers le trousseau OS : %s", ", ".join(migrated))


# ─────────────────────────────────────────────────────────────
#  Interne
# ─────────────────────────────────────────────────────────────

def _delete_silent(key: str) -> None:
    """Supprime une entrée du trousseau sans lever d'exception si absente."""
    try:
        _keyring.delete_password(_SERVICE, key)
    except Exception:
        pass  # PasswordDeleteError ou NoKeyringError — déjà absent, c'est OK
