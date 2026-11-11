# Migration vers la v2.3

La v2.3 apporte deux changements côté base : des écritures transactionnelles
(`fintrack_apply`, `fintrack_replace_snapshot`) et un accès MCP en lecture
seule. **L'ordre compte** : la base d'abord, puis les services, puis les PC.

| Étape | Bloquant ? | Durée |
|---|---|---|
| 1. Sauvegarde | oui | 2 min |
| 2. Migration `migration_v2_3_atomic.sql` | **oui, avant le déploiement** | < 1 min |
| 3. Migration `migration_mcp_readonly.sql` | oui, avant d'activer le MCP | < 1 min |
| 4. Vérifications SQL | recommandé | 2 min |
| 5. Déploiement des services (Helm / Compose) | — | 5 min |
| 6. Mise à jour de l'app desktop sur chaque PC | oui | 2 min / PC |
| 7. (Optionnel) Serveur MCP : OAuth Supabase + clients | — | 10 min |

> ℹ️ **Sans risque pour la v2.2 en place** : les migrations ne suppriment
> aucune donnée et la v2.2 (web et desktop) continue de fonctionner avec la
> base migrée. Il n'y a donc pas de coupure entre l'étape 2 et l'étape 5, et
> un **retour arrière applicatif** (images v2.2) ne demande aucun retour
> arrière SQL.

---

## 1. Sauvegarde

1. Fermer l'app desktop sur **tous** les PC (l'envoi à la fermeture ne doit
   pas tomber pendant la migration).
2. Supabase → **Database → Backups** : vérifier la dernière sauvegarde
   automatique (plan payant) ou exporter :
   ```bash
   # Chaîne de connexion : Supabase → Project Settings → Database → Connection string (URI)
   pg_dump "postgresql://postgres:<mot-de-passe>@db.<projet>.supabase.co:5432/postgres" \
     --schema=public --data-only -Fc -f fintrack-avant-v2.3.dump
   ```
3. Garder aussi une copie du fichier SQLite du desktop (`finance.db`).

## 2. Écritures atomiques — `supabase/migration_v2_3_atomic.sql`

Supabase → **SQL Editor** → *New query* → coller le fichier entier →
**Run**. Le script est idempotent : on peut le relancer sans risque.

Il crée :
- le schéma `fintrack_private` (fonctions internes, non exposées par l'API) ;
- `public.fintrack_apply(jsonb)` : chaque écriture du web en une
  transaction ;
- `public.fintrack_replace_snapshot(...)` : l'envoi desktop en une
  transaction, avec contrôle de version ;
- des index `(user_id, …)` qui remplacent les anciens index ;
- `NOTIFY pgrst, 'reload schema'` : PostgREST voit immédiatement les
  nouvelles fonctions.

## 3. Accès MCP en lecture seule — `supabase/migration_mcp_readonly.sql`

Même procédure. Elle :
- réécrit les politiques `*_owner` avec `(SELECT auth.uid())` (même règle,
  plus rapide) ;
- ajoute 3 politiques `RESTRICTIVE` par table : un jeton OAuth (claim
  `client_id`, clients MCP) ne peut **jamais** écrire.

> ⚠️ À exécuter **avant** `mcp.enabled: true`. À faire même si vous
> n'activez pas le MCP tout de suite : sans effet sur le web et le desktop.

## 4. Vérifications SQL

```sql
-- a) Les 2 fonctions existent
SELECT proname FROM pg_proc
 WHERE proname IN ('fintrack_apply', 'fintrack_replace_snapshot');      -- 2 lignes

-- b) 4 politiques par table (owner + 3 restrictives)
SELECT tablename, count(*) FROM pg_policies
 WHERE schemaname = 'public' GROUP BY tablename ORDER BY tablename;      -- 4 partout

-- c) Les fonctions ne sont pas appelables sans être connecté
SELECT has_function_privilege('anon', 'public.fintrack_apply(jsonb)', 'EXECUTE');  -- false
```

## 5. Déploiement des services

Les images sont publiées par la CI au tag `v2.3.0` (voir « Construire la
release » plus bas) : `fintrack-web`, `fintrack-finance-api`,
`fintrack-ai-service`, `fintrack-notifier` et **`fintrack-mcp`** (nouvelle).

### Kubernetes (Helm)

```bash
# Chart publié par la CI (OCI). Le MCP reste désactivé par défaut.
helm upgrade --install fintrack oci://ghcr.io/moussaoudihat/charts/fintrack \
  --version 2.3.0 -n fintrack -f values-production.yaml --wait

kubectl -n fintrack rollout status deploy/web deploy/finance-api deploy/ai-service
helm test fintrack -n fintrack
```

> Vérifiez l'adresse OCI exacte du chart dans la page de la release GitHub
> (GHCR ou Docker Hub selon votre configuration).

Avec des images épinglées par digest (recommandé en production), recopiez
les digests affichés dans le résumé du workflow Release dans
`image.digests` (clés `web`, `finance-api`, `ai-service`, `notifier`,
`mcp`).

### Docker Compose

```bash
cd deploy/compose
FINTRACK_TAG=2.3.0 docker compose pull
FINTRACK_TAG=2.3.0 docker compose up -d
# avec le MCP : ajouter --profile mcp (et MCP_PUBLIC_URL dans .env)
```

### Contrôle

- Web : ajouter puis supprimer une dépense de test.
- Logs finance-api : aucune ligne `fintrack_apply introuvable`. Si elle
  apparaît (erreur 503 « Base de données non migrée »), l'étape 2 n'a pas été
  faite : exécutez-la, sans redéployer.

## 6. App desktop (chaque PC)

Installez `Fintrack.exe` v2.3.0 depuis la release GitHub. Au premier
lancement, l'app **récupère** les données (sa version locale diffère de la
version serveur). C'est normal.

> ⚠️ N'utilisez plus une app desktop v2.2 après la migration. Elle
> fonctionne encore, mais son envoi « tout supprimer puis réinsérer » n'est
> pas transactionnel : c'est précisément ce que la v2.3 corrige.

### Délai d'envoi (bases volumineuses)

L'envoi desktop est désormais **une seule transaction**. La fonction
`fintrack_replace_snapshot` déclare son propre délai (`SET statement_timeout
= '120s'`), que PostgREST ≥ 12.2 (Supabase actuel) applique à la place des
8 s du rôle `authenticated`. Seul cet envoi en bénéficie.

Si l'app affiche malgré tout « délai dépassé côté Supabase » (PostgREST plus
ancien, ou base énorme), rien n'a été modifié. Augmentez alors la limite du
rôle :

```sql
ALTER ROLE authenticated SET statement_timeout = '30s';
NOTIFY pgrst, 'reload config';
```

## 7. (Optionnel) Serveur MCP

Voir [MCP.md](MCP.md). En résumé :

1. Supabase → **Authentication → URL Configuration** : *Site URL* =
   `https://<votre-hôte>`.
2. Supabase → **Authentication → OAuth Server** : activer, *Authorization
   path* = `/oauth/consent`, activer l'enregistrement dynamique des clients.
3. Helm : `mcp.enabled: true`, puis `helm upgrade` (même commande qu'à
   l'étape 5).
4. Contrôle :
   `curl https://<hôte>/.well-known/oauth-protected-resource/mcp` renvoie
   `authorization_servers`.
5. Client : `claude mcp add --transport http fintrack https://<hôte>/mcp`,
   puis `/mcp` → *Authenticate*.

---

## Retour arrière

| Problème | Action |
|---|---|
| Services v2.3 en erreur | `helm rollback fintrack -n fintrack` (ou `FINTRACK_TAG=2.2.0`). La base migrée reste compatible avec la v2.2. |
| MCP indésirable | `mcp.enabled: false` + `helm upgrade`. Révoquer les clients : Supabase → Authentication → OAuth Apps. |
| Données incorrectes | Restaurer la sauvegarde de l'étape 1 (`pg_restore --data-only --disable-triggers`). |

Il n'est pas nécessaire de supprimer les fonctions SQL v2.3 pour revenir à
la v2.2. Pour le faire malgré tout :

```sql
DROP FUNCTION IF EXISTS public.fintrack_apply(jsonb);
DROP FUNCTION IF EXISTS public.fintrack_replace_snapshot(jsonb, jsonb, text[], text, boolean);
DROP SCHEMA IF EXISTS fintrack_private CASCADE;
```

---

## Construire la release (mainteneur)

La release est **entièrement construite par la CI** (`.github/workflows/release.yml`)
quand on pousse un tag `vX.Y.Z` :

- l'exécutable Windows (attesté Sigstore) ;
- les 5 images, signées cosign, avec provenance SLSA et SBOM, publiées sur
  GHCR et Docker Hub ;
- le chart Helm (OCI) ;
- la Release GitHub.

```bash
# 1. Fusionner la PR de la fonctionnalité, puis la PR « chore: préparer la release v2.3.0 »
git switch main && git pull --ff-only

# 2. Vérifier la version
cat VERSION                       # 2.3.0

# 3. Tag annoté puis push : déclenche la release
git tag -a v2.3.0 -m "Fintrack v2.3.0 — écritures atomiques, synchro fiable, serveur MCP"
git push origin v2.3.0

# 4. Suivre la construction
gh run watch "$(gh run list --workflow Release --limit 1 --json databaseId -q '.[0].databaseId')"
gh release view v2.3.0
```

Construction locale (test uniquement) :

```bash
for pair in web:web finance_api:finance-api ai_service:ai-service notifier:notifier mcp_server:mcp; do
  dir=${pair%%:*}; name=${pair##*:}
  docker build -f services/Dockerfile --build-arg SERVICE=$dir --build-arg VERSION=2.3.0 \
    -t fintrack-$name:2.3.0 services/
done
```
