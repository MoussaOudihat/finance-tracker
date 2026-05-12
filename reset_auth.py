"""
reset_auth.py — Outil de récupération / migration des identifiants Fintrack
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Utilisation :  python reset_auth.py
               (ou double-clic si Python est associé aux .py)

Ce script ne modifie JAMAIS tes données financières.
Il agit uniquement sur les clés auth_* dans app_settings.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import sys
import sqlite3
import hashlib
import secrets
import datetime

# ── Chemin de la base ────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(SCRIPT_DIR, "data", "finance_tracker.db")

# ── Couleurs console (désactivées sur Windows sans support ANSI) ─────────
_USE_COLOR = sys.platform != "win32" or os.environ.get("TERM")
def _c(code, text): return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text
GREEN  = lambda t: _c("32;1", t)
YELLOW = lambda t: _c("33;1", t)
RED    = lambda t: _c("31;1", t)
CYAN   = lambda t: _c("36;1", t)
BOLD   = lambda t: _c("1",    t)

# ── bcrypt optionnel ─────────────────────────────────────────────────────
try:
    import bcrypt as _bcrypt
    _BCRYPT = True
except ImportError:
    _BCRYPT = False

_BCRYPT_PREFIX = "bcrypt:"

def _hash(value: str) -> tuple[str, str]:
    """Retourne (hash, salt). Utilise bcrypt si dispo, sinon SHA-256."""
    v = value.strip().lower().encode("utf-8")
    if _BCRYPT:
        h = _BCRYPT_PREFIX + _bcrypt.hashpw(v, _bcrypt.gensalt(rounds=12)).decode()
        return h, ""
    salt = secrets.token_hex(16)
    h    = hashlib.sha256((value.strip().lower() + salt).encode()).hexdigest()
    return h, salt

def _verify(value: str, stored_hash: str, stored_salt: str) -> bool:
    if stored_hash.startswith(_BCRYPT_PREFIX):
        if not _BCRYPT:
            return False
        v = value.strip().lower().encode("utf-8")
        return _bcrypt.checkpw(v, stored_hash[len(_BCRYPT_PREFIX):].encode())
    return (hashlib.sha256((value.strip().lower() + stored_salt).encode()).hexdigest()
            == stored_hash)

# ── Helpers DB ───────────────────────────────────────────────────────────
def _get(con, key, default=""):
    row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default

def _set(con, key, value):
    con.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)", (key, value))

def _create_session(con):
    expiry = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    _set(con, "auth_session_token",  secrets.token_urlsafe(32))
    _set(con, "auth_session_expiry", expiry)

# ── Saisie masquée compatible Windows ───────────────────────────────────
def _getpass(prompt="Mot de passe : ") -> str:
    try:
        import getpass
        return getpass.getpass(prompt)
    except Exception:
        return input(prompt)

# ── Affichage de l'état actuel ───────────────────────────────────────────
def _show_status(con):
    username  = _get(con, "auth_username")
    has_pwd   = bool(_get(con, "auth_password_hash"))
    question  = _get(con, "auth_secret_question")
    expiry    = _get(con, "auth_session_expiry")
    months    = con.execute("SELECT COUNT(*) FROM months").fetchone()[0]
    expenses  = con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]

    print()
    print(BOLD("═══ État actuel de la base ═══"))
    print(f"  Username      : {GREEN(username) if username else RED('⚠  non défini')}")
    print(f"  Mot de passe  : {GREEN('✓ configuré') if has_pwd else RED('✗ absent')}")
    print(f"  Question secr.: {CYAN(question) if question else YELLOW('non définie')}")
    print(f"  Session valide: {GREEN(expiry) if expiry else RED('aucune')}")
    print(f"  Données        : {months} mois, {expenses} dépenses")
    print()

# ════════════════════════════════════════════════════════════════════════
#  ACTIONS
# ════════════════════════════════════════════════════════════════════════

def action_set_username(con):
    """Définir ou corriger le username (sans toucher au mot de passe)."""
    current = _get(con, "auth_username")
    if current:
        print(YELLOW(f"  Username actuel : {current!r}"))
    new_name = input("  Nouveau username : ").strip()
    if not new_name:
        print(RED("  Annulé."))
        return
    _set(con, "auth_username", new_name)
    con.commit()
    print(GREEN(f"  ✓ Username défini : {new_name!r}"))


def action_reset_password(con):
    """Réinitialiser le mot de passe (+ question secrète optionnelle)."""
    SECRET_QUESTIONS = [
        "Quel est le prénom de votre mère ?",
        "Quel est le nom de votre premier animal de compagnie ?",
        "Dans quelle ville êtes-vous né(e) ?",
        "Quel est le nom de votre école primaire ?",
        "Quel est votre plat préféré ?",
        "Quel est le prénom de votre meilleur(e) ami(e) d'enfance ?",
        "Quel est le modèle de votre première voiture ?",
    ]

    print()
    print(BOLD("  ── Nouveau mot de passe ──"))
    while True:
        pwd  = _getpass("  Mot de passe (min. 4 car.) : ")
        cpwd = _getpass("  Confirmer                  : ")
        if len(pwd) < 4:
            print(RED("  ⚠  Trop court, minimum 4 caractères."))
            continue
        if pwd != cpwd:
            print(RED("  ⚠  Les mots de passe ne correspondent pas."))
            continue
        break

    h, s = _hash(pwd)
    _set(con, "auth_password_hash", h)
    _set(con, "auth_password_salt", s)

    # Réinitialiser le verrouillage brute-force
    _set(con, "auth_failed_count",  "0")
    _set(con, "auth_locked_until",  "")

    # Question secrète (optionnelle)
    print()
    update_q = input("  Mettre à jour la question secrète aussi ? [o/N] : ").strip().lower()
    if update_q == "o":
        print()
        for i, q in enumerate(SECRET_QUESTIONS, 1):
            print(f"    {i}. {q}")
        while True:
            choice = input("  Numéro de la question : ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(SECRET_QUESTIONS):
                question = SECRET_QUESTIONS[int(choice) - 1]
                break
            print(RED("  Numéro invalide."))
        answer = input("  Votre réponse : ").strip()
        if answer:
            ah, asal = _hash(answer)
            _set(con, "auth_secret_question",   question)
            _set(con, "auth_secret_answer_hash", ah)
            _set(con, "auth_secret_answer_salt", asal)
            print(GREEN("  ✓ Question secrète mise à jour."))

    _create_session(con)
    con.commit()
    print(GREEN("  ✓ Mot de passe réinitialisé. Session créée (30 jours)."))


def action_full_setup(con):
    """Premier lancement : créer username + mot de passe + question secrète."""
    print()
    print(BOLD("  ── Création du compte ──"))

    username = input("  Username : ").strip()
    if not username:
        print(RED("  Annulé."))
        return

    action_set_username_val(con, username)
    action_reset_password(con)
    print(GREEN(f"\n  ✓ Compte créé pour {username!r}. Lance l'application normalement."))


def action_set_username_val(con, value):
    _set(con, "auth_username", value.strip())


def action_renew_session(con):
    """Créer une nouvelle session sans changer le mot de passe."""
    _create_session(con)
    con.commit()
    expiry = _get(con, "auth_session_expiry")
    print(GREEN(f"  ✓ Session renouvelée jusqu'au {expiry}."))


def action_unlock(con):
    """Déverrouiller un compte bloqué par trop de tentatives."""
    _set(con, "auth_failed_count",  "0")
    _set(con, "auth_locked_until",  "")
    con.commit()
    print(GREEN("  ✓ Compte déverrouillé."))


# ════════════════════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ════════════════════════════════════════════════════════════════════════

def main():
    print()
    print(BOLD(CYAN("╔══════════════════════════════════════╗")))
    print(BOLD(CYAN("║  Fintrack — Outil de récupération    ║")))
    print(BOLD(CYAN("╚══════════════════════════════════════╝")))

    if not os.path.exists(DB_PATH):
        print(RED(f"\n  ✗ Base introuvable : {DB_PATH}"))
        print("    Lance l'application au moins une fois pour créer la base.")
        input("\n  Appuie sur Entrée pour quitter…")
        return

    con = sqlite3.connect(DB_PATH)
    _show_status(con)

    username = _get(con, "auth_username")
    has_pwd  = bool(_get(con, "auth_password_hash"))

    # ── Détection automatique du cas ────────────────────────────────────
    if not has_pwd:
        print(YELLOW("  ► Aucun compte configuré. Création d'un nouveau compte…"))
        action_full_setup(con)
        con.close()
        input("\n  Appuie sur Entrée pour quitter…")
        return

    if not username:
        print(YELLOW("  ► Mot de passe trouvé mais username manquant."))
        print(YELLOW("    Ton compte existait avant l'ajout de l'authentification."))
        print()
        print("  Que veux-tu faire ?")
        print(f"  {BOLD('1.')} Définir mon username (garder le mot de passe actuel)")
        print(f"  {BOLD('2.')} Définir mon username + réinitialiser le mot de passe")
        print(f"  {BOLD('3.')} Renouveler la session uniquement")
        print(f"  {BOLD('q.')} Quitter")
        choice = input("\n  Choix : ").strip().lower()
        if choice == "1":
            action_set_username(con)
            _create_session(con)
            con.commit()
        elif choice == "2":
            action_set_username(con)
            action_reset_password(con)
        elif choice == "3":
            action_renew_session(con)
        con.close()
        input("\n  Appuie sur Entrée pour quitter…")
        return

    # ── Compte complet : menu général ───────────────────────────────────
    print(f"  Connecté en tant que {BOLD(username)}")
    print()
    print("  Que veux-tu faire ?")
    print(f"  {BOLD('1.')} Réinitialiser le mot de passe (mot de passe oublié)")
    print(f"  {BOLD('2.')} Changer le username")
    print(f"  {BOLD('3.')} Renouveler la session (30 jours)")
    print(f"  {BOLD('4.')} Déverrouiller le compte (trop de tentatives)")
    print(f"  {BOLD('q.')} Quitter")
    choice = input("\n  Choix : ").strip().lower()

    if choice == "1":
        action_reset_password(con)
    elif choice == "2":
        action_set_username(con)
        con.commit()
    elif choice == "3":
        action_renew_session(con)
    elif choice == "4":
        action_unlock(con)

    con.close()
    input("\n  Appuie sur Entrée pour quitter…")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Annulé.")
