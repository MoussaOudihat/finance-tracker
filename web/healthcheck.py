"""
Sonde de santé sans dépendance externe (l'image n'embarque pas curl).

Usage :  python -m web.healthcheck [/healthz|/readyz]
Code de sortie 0 si le serveur répond 200, 1 sinon. Utilisée par le
HEALTHCHECK du Dockerfile et par les sondes `exec` (Podman, qui traduit les
sondes Kubernetes `httpGet` en appels curl).
"""
import sys
import urllib.request


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "/healthz"
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8000{path}", timeout=2) as r:
            return 0 if r.status == 200 else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
