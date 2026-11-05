# Politique de sécurité

## Signaler une vulnérabilité

Merci de **ne pas ouvrir d'issue publique**. Utilisez le signalement privé
GitHub : onglet *Security* → *Report a vulnerability*. Réponse sous 7 jours.

## Versions maintenues

| Version | Correctifs de sécurité |
|---|---|
| 2.x | ✅ |
| < 2.0 | ❌ |

## Contrôles automatisés (CI)

| Contrôle | Outil | Bloquant |
|---|---|---|
| Lint + règles sécurité Python | Ruff (règles `S`) | oui |
| SAST | Bandit, Semgrep (Python, OWASP Top 10, secrets, Dockerfile, Kubernetes), CodeQL (`security-extended`) | oui (Bandit ≥ moyen, Semgrep), CodeQL en alerte |
| Dépendances (SCA) | pip-audit (par service), Dependabot (pip, Docker, Compose, Actions) | oui |
| Secrets dans l'historique | Gitleaks | oui |
| Dockerfile | Hadolint | oui |
| Images | Trivy (CRITICAL/HIGH corrigeables) | oui, et avant toute publication |
| IaC | `helm lint --strict`, rendu du chart (défaut/local/production) + kubeconform strict, Trivy config (manifestes rendus, Compose, Dockerfile), `docker compose config` | oui (CRITICAL/HIGH) |
| Chaîne d'approvisionnement | actions épinglées par SHA, permissions minimales par job, cosign (keyless), provenance SLSA, SBOM SPDX attesté | — |

Exceptions acceptées : voir `.trivyignore` et `trivy-secret.yaml` (chacune justifiée, au périmètre le plus étroit possible).

## Vérifier une image publiée

```bash
cosign verify ghcr.io/moussaoudihat/fintrack-web:2.0.0 \
  --certificate-identity-regexp 'https://github.com/MoussaOudihat/finance-tracker/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
gh attestation verify oci://ghcr.io/moussaoudihat/fintrack-web:2.0.0 --owner MoussaOudihat

# Chart Helm (même identité de signature)
cosign verify ghcr.io/moussaoudihat/charts/fintrack:2.0.0 \
  --certificate-identity-regexp 'https://github.com/MoussaOudihat/finance-tracker/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```
Les images publiées sur Docker Hub portent les mêmes digests et signatures.

## Mesures applicatives (interface web)

- Sessions côté serveur (Redis, chiffrées) : le cookie ne contient qu'un identifiant aléatoire, la déconnexion révoque réellement la session.
- Cookie `HttpOnly`, `Secure`, `SameSite=Lax` ; CSRF sur tout formulaire et appel JSON ; CSP stricte sans script ni style inline.
- Limitation des tentatives de connexion par (IP, compte) et par IP — un tiers ne peut pas bloquer votre compte. IP réelle uniquement depuis le proxy de confiance (`FORWARDED_ALLOW_IPS`).
- JWT Supabase vérifiés par chaque service (JWKS, algorithmes asymétriques uniquement) ; RLS PostgreSQL.
- Validation stricte des montants (finis, > 0) et des mois ; IA : résumé agrégé uniquement, consentement, quota quotidien, sortie validée.
- Anti-SSRF : URLs de notification limitées à une liste d'hôtes HTTPS, pas de redirection suivie, NetworkPolicy excluant les plages privées.
- Secrets de notifier (jeton TickTick, URLs de webhook) chiffrés au repos (Fernet).
