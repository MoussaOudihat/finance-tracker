"""
reset_auth.py — Outil de récupération / migration des identifiants Fintrack
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Utilisation :  python reset_auth.py
               (ou double-clic si Python est associé aux .py)

Ce script ne modifie JAMAIS tes données financières.
Il agit uniquement sur les clés auth_* dans app_settings, via les mêmes
fonctions que l'application (auth.py + database.py) pour rester toujours
cohérent avec la politique de sécurité en vigueur (hachage, durée de
session, verrouillage brute-force).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from config import DB_PATH
from database import Database
import auth as Auth

# ── Couleurs console (désactivées sur Windows sans support ANSI) ─────────
_USE_COLOR = sys.platform != "win32" or os.environ.get("TERM")
def _c(code, text): return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text
GREEN  = lambda t: _c("32;1", t)
YELLOW = lambda t: _c("33;1", t)
RED    = lambda t: _c("31;1", t)
CYAN   = lambda t: _c("36;1", t)
BOLD   = lambda t: _c("1",    t)

SECRET_QUESTIONS = [
    "Quel est le prénom de votre mère ?",
    "Quel est le nom de votre premier animal de compagnie ?",
    "Dans quelle ville êtes-vous né(e) ?",
    "Quel est le nom de votre école primaire ?",
    "Quel est votre plat préféré ?",
    "Quel est le prénom de votre meilleur(e) ami(e) d'enfance ?",
    "Quel est le modèle de votre première voiture ?",
]

# ── Saisie masquée compatible Windows ───────────────────────────────────
def _getpass(prompt="Mot de passe : ") -> str:
    try:
        import getpass
        return getpass.getpass(prompt)
    except Exception:
        return input(prompt)

# ── Affichage de l'état actuel ───────────────────────────────────────────
def _show_status(db: Database):
    username = Auth.get_username(db)
    has_pwd  = Auth.has_password(db)
    question = Auth.get_secret_question(db)
    expiry   = db.get_setting("auth_session_expiry")
    locked, lock_msg = Auth.check_lockout(db)
    months   = db.con.execute("SELECT COUNT(*) FROM months").fetchone()[0]
    expenses = db.con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]

    print()
    print(BOLD("═══ État actuel de la base ═══"))
    print(f"  Username      : {GREEN(username) if username else RED('⚠  non défini')}")
    print(f"  Mot de passe  : {GREEN('✓ configuré') if has_pwd else RED('✗ absent')}")
    print(f"  Question secr.: {CYAN(question) if question else YELLOW('non définie')}")
    print(f"  Session valide: {GREEN(expiry) if expiry else RED('aucune')}")
    print(f"  Verrouillage  : {RED(lock_msg) if locked else GREEN('aucun')}")
    print(f"  Données        : {months} mois, {expenses} dépenses")
    print()

# ════════════════════════════════════════════════════════════════════════
#  ACTIONS
# ════════════════════════════════════════════════════════════════════════

def _ask_secret_question():
    """Demande une nouvelle question secrète + réponse. Retourne (question, answer) ou (None, None)."""
    print()
    for i, q in enumerate(SECRET_QUESTIONS, 1):
        print(f"    {i}. {q}")
    while True:
        choice = input("  Numéro de la question : ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(SECRET_QUESTIONS):
            question = SECRET_QUESTIONS[int(choice) - 1]
            break
        print(RED("  Numéro invalide."))
    while True:
        answer = input("  Votre réponse : ").strip()
        if answer:
            break
        print(RED("  ⚠  La réponse ne peut pas être vide."))
    return question, answer


def action_set_username(db: Database):
    """Définir ou corriger le username (sans toucher au mot de passe)."""
    current = Auth.get_username(db)
    if current:
        print(YELLOW(f"  Username actuel : {current!r}"))
    new_name = input("  Nouveau username : ").strip()
    if not new_name:
        print(RED("  Annulé."))
        return
    db.set_setting("auth_username", new_name)
    print(GREEN(f"  ✓ Username défini : {new_name!r}"))


def action_reset_password(db: Database):
    """Réinitialiser le mot de passe (+ question secrète optionnelle)."""
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

    Auth.change_password(db, pwd)
    # Réinitialiser le verrouillage brute-force via la même API que l'app
    Auth.clear_failed_logins(db)

    print()
    update_q = input("  Mettre à jour la question secrète aussi ? [o/N] : ").strip().lower()
    if update_q == "o":
        question, answer = _ask_secret_question()
        if answer:
            Auth.update_secret_question(db, question, answer)
            print(GREEN("  ✓ Question secrète mise à jour."))

    Auth.create_session(db)
    print(GREEN(f"  ✓ Mot de passe réinitialisé. Session créée ({Auth.SESSION_DAYS} jours)."))


def action_full_setup(db: Database):
    """Premier lancement : créer username + mot de passe + question secrète."""
    print()
    print(BOLD("  ── Création du compte ──"))

    username = input("  Username : ").strip()
    if not username:
        print(RED("  Annulé."))
        return

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

    question, answer = _ask_secret_question()
    Auth.setup_password(db, username, pwd, question or "", answer or "")
    Auth.create_session(db)
    print(GREEN(f"\n  ✓ Compte créé pour {username!r}. Lance l'application normalement."))


def action_renew_session(db: Database):
    """Créer une nouvelle session sans changer le mot de passe."""
    Auth.create_session(db)
    expiry = db.get_setting("auth_session_expiry")
    print(GREEN(f"  ✓ Session renouvelée jusqu'au {expiry}."))


def action_unlock(db: Database):
    """Déverrouiller un compte bloqué par trop de tentatives."""
    Auth.clear_failed_logins(db)
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

    db = Database(DB_PATH)
    _show_status(db)

    username = Auth.get_username(db)
    has_pwd  = Auth.has_password(db)

    # ── Détection automatique du cas ────────────────────────────────────
    if not has_pwd:
        print(YELLOW("  ► Aucun compte configuré. Création d'un nouveau compte…"))
        action_full_setup(db)
        db.close()
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
            action_set_username(db)
            Auth.create_session(db)
        elif choice == "2":
            action_set_username(db)
            action_reset_password(db)
        elif choice == "3":
            action_renew_session(db)
        db.close()
        input("\n  Appuie sur Entrée pour quitter…")
        return

    # ── Compte complet : menu général ───────────────────────────────────
    print(f"  Connecté en tant que {BOLD(username)}")
    print()
    print("  Que veux-tu faire ?")
    print(f"  {BOLD('1.')} Réinitialiser le mot de passe (mot de passe oublié)")
    print(f"  {BOLD('2.')} Changer le username")
    print(f"  {BOLD('3.')} Renouveler la session ({Auth.SESSION_DAYS} jours)")
    print(f"  {BOLD('4.')} Déverrouiller le compte (trop de tentatives)")
    print(f"  {BOLD('q.')} Quitter")
    choice = input("\n  Choix : ").strip().lower()

    if choice == "1":
        action_reset_password(db)
    elif choice == "2":
        action_set_username(db)
    elif choice == "3":
        action_renew_session(db)
    elif choice == "4":
        action_unlock(db)

    db.close()
    input("\n  Appuie sur Entrée pour quitter…")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Annulé.")
