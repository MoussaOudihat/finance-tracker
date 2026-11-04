"""
Sonde de santé sans dépendance externe (les images n'embarquent pas curl).

Usage :  python -m fintrack_common.healthcheck [/healthz|/readyz] [port]
Code de sortie 0 si le service répond 200, 1 sinon. Utilisée par le
HEALTHCHECK des Dockerfile, docker compose et les sondes `exec` Podman.
"""
import sys
import urllib.request


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else "/healthz"
    port = int(argv[1]) if len(argv) > 1 else 8000
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:  # nosec B310 - URL locale fixe
            return 0 if r.status == 200 else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
