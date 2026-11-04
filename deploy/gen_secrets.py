"""
Génère les secrets de déploiement (Compose : fichiers ; Kubernetes : manifeste
Secret prêt à appliquer). Les secrets aléatoires sont créés s'ils n'existent
pas ; les secrets fournisseurs (clé anon Supabase, clés IA, TickTick) sont
demandés de façon interactive (laisser vide = fonctionnalité désactivée).

    python deploy/gen_secrets.py            # Compose : deploy/compose/secrets/
    python deploy/gen_secrets.py --k8s      # + deploy/helm/secrets.env, puis :
        kubectl -n fintrack create secret generic fintrack-secrets --from-env-file=deploy/helm/secrets.env
        helm install … --set secrets.existingSecret=fintrack-secrets

Les fichiers produits sont ignorés par git. Ne jamais les committer.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPOSE_DIR = os.path.join(HERE, "compose", "secrets")
K8S_ENV = os.path.join(HERE, "helm", "secrets.env")

GENERATED = {
    "session_encryption_key": lambda: base64.urlsafe_b64encode(os.urandom(32)).decode(),
    "notifier_encryption_key": lambda: base64.urlsafe_b64encode(os.urandom(32)).decode(),
    "notifier_internal_token": lambda: secrets.token_urlsafe(48),
    "redis_password": lambda: secrets.token_urlsafe(32),
}
PROVIDED = {
    "supabase_anon_key": "Clé anon/publishable Supabase",
    "anthropic_api_key": "Clé API Anthropic (Claude) — vide pour désactiver",
    "gemini_api_key": "Clé API Google Gemini — vide pour désactiver",
    "ticktick_client_secret": "Client secret TickTick — vide pour désactiver",
}


def _write(path: str, value: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(value)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k8s", action="store_true", help="écrire aussi secrets.env pour un Secret Kubernetes")
    ap.add_argument("--non-interactive", action="store_true",
                    help="ne rien demander : secrets fournisseurs laissés vides (CI, scripts)")
    args = ap.parse_args()
    interactive = sys.stdin.isatty() and not args.non_interactive
    os.makedirs(COMPOSE_DIR, exist_ok=True)
    values: dict[str, str] = {}

    for name, gen in GENERATED.items():
        path = os.path.join(COMPOSE_DIR, name)
        if os.path.exists(path):
            values[name] = open(path, encoding="utf-8").read().strip()
        else:
            values[name] = gen()
            _write(path, values[name])
            print(f"généré   {name}")
    for name, prompt in PROVIDED.items():
        path = os.path.join(COMPOSE_DIR, name)
        if os.path.exists(path):
            values[name] = open(path, encoding="utf-8").read().strip()
            continue
        values[name] = getpass.getpass(f"{prompt} : ").strip() if interactive else ""
        _write(path, values[name])
        print(f"enregistré {name}")

    # URL Redis complète (mot de passe inclus) pour Compose
    _write(os.path.join(COMPOSE_DIR, "redis_url"),
           f"redis://:{values['redis_password']}@redis:6379/0")

    if args.k8s:
        os.makedirs(os.path.dirname(K8S_ENV), exist_ok=True)
        lines = [
            f"SUPABASE_ANON_KEY={values['supabase_anon_key']}",
            f"SESSION_ENCRYPTION_KEY={values['session_encryption_key']}",
            f"NOTIFIER_ENCRYPTION_KEY={values['notifier_encryption_key']}",
            f"NOTIFIER_INTERNAL_TOKEN={values['notifier_internal_token']}",
            f"REDIS_PASSWORD={values['redis_password']}",
            f"REDIS_URL=redis://:{values['redis_password']}@redis:6379/0",
            f"ANTHROPIC_API_KEY={values['anthropic_api_key']}",
            f"GEMINI_API_KEY={values['gemini_api_key']}",
            f"TICKTICK_CLIENT_SECRET={values['ticktick_client_secret']}",
        ]
        _write(K8S_ENV, "\n".join(lines) + "\n")
        print(f"écrit    {os.path.relpath(K8S_ENV)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
