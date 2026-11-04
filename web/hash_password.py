"""
Génère le hash bcrypt à mettre dans FINTRACK_WEB_PASSWORD_HASH (mode local).

Usage :  python -m web.hash_password
"""
import getpass
import sys

import bcrypt


def main() -> int:
    pwd = getpass.getpass("Mot de passe : ")
    if len(pwd) < 12:
        print("Choisissez au moins 12 caractères.", file=sys.stderr)
        return 1
    if getpass.getpass("Confirmation : ") != pwd:
        print("Les mots de passe ne correspondent pas.", file=sys.stderr)
        return 1
    print(bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
