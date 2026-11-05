# 💜 Fintrack

> Application desktop Windows pour suivre ses finances personnelles — **locale, sécurisée, open source.**  
> Synchronisation Supabase optionnelle pour le multi-appareils.

![Version](https://img.shields.io/badge/Version-2.0.0-4F46E5)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22C55E)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows)
![DB](https://img.shields.io/badge/Database-SQLite%20local-F59E0B)
![Sync](https://img.shields.io/badge/Sync-Supabase%20optionnel-3ECF8E?logo=supabase&logoColor=white)

Aucun abonnement, aucune inscription obligatoire. Vos données restent sur votre machine dans une base SQLite locale. La synchronisation Supabase est entièrement optionnelle et gratuite.

---

## ✨ Fonctionnalités

### Saisie mensuelle
- **Revenus** — salaire, primes, revenus passifs, freelance…
- **Dépenses** — par catégorie et enseigne, avec filtres interactifs
- **Épargne** — versements mensuels sur différents supports

### Suivi du patrimoine
- Portefeuille multi-actifs : Bourse/ETF/PEA, Immobilier, Crypto, Or, Livrets…
- **Compte / Épargne** : saisie adaptée (solde + total versé → intérêts gagnés calculés automatiquement)
- Évolution historique de la valeur nette
- Analyse de diversification (score Herfindahl)
- Transactions (achats / ventes) par actif avec calcul CMUP

### Analyses & visualisation
- Graphiques interactifs (camembert, barres, courbes) avec survol souris
- Dépenses par catégorie et par enseigne — clic = filtre instantané
- Évolution mensuelle sur 6 ou 12 mois
- Comparaison budgétaire prévu vs réel

### Outils financiers
- **Budget mensuel** — fixez des plafonds par catégorie
- **Objectifs d'épargne** — suivi de progression avec date cible
- **Projection financière** — simulation à N ans avec taux de rendement
- **Recommandations IA** — analyse automatique par Gemini, rendu Markdown natif
- **Analyse IA on-demand** — bouton "Analyser ce scénario avec l'IA" sur la page Projection
- **Historique** — vue consolidée sur plusieurs mois

### Exports & rapports
- Rapport **PDF** mensuel
- Export **CSV** complet
- Export fiscal (plus-values, dons, formation)
- Envoi par **email SMTP** (résumé mensuel)

### Maintenance & récupération
- **`desktop/tools/reset_auth.py`** — récupération des identifiants (username oublié, mot de passe perdu, compte bloqué) sans toucher aux données
- **`supabase/migration_multiuser.sql`** — mise à jour d'un projet Supabase existant vers le schéma multi-utilisateur
- **`supabase/schema.sql`** — schéma complet pour une nouvelle installation Supabase

### Synchronisation Supabase (optionnel)
- ☁️ Sync multi-appareils via **Supabase PostgreSQL** (tables réelles, pas Storage)
- 🔄 Auto-sync toutes les **5 minutes** en session + push à la fermeture
- 💾 **Backup automatique** local (`.bak`) avant chaque pull
- 🔁 Arbitrage par timestamp — pull uniquement si les données distantes sont plus récentes
- 🔑 Clés sensibles jamais synchronisées (URL, clé API, mot de passe SMTP)

### Confort
- 🔐 **Accès par mot de passe** + question secrète + session 30 jours
- 👋 **Écran de bienvenue** au premier lancement : choix Nouveau compte ou Restauration Supabase
- 🌙 Mode sombre / clair
- 👤 **Profil IA** configurable dans Paramètres → section IA (personnalise les analyses)
- Import depuis **Notion** (ZIP export)

---

## 🖥️ Aperçu des vues

| Vue | Description |
|-----|-------------|
| **Tableau de bord** | KPIs du mois (revenus, dépenses, épargne, bilan) + graphiques filtrables |
| **Revenus / Dépenses / Épargne** | Saisie et gestion des entrées mensuelles avec tableau éditable |
| **Budget mensuel** | Plafonds par catégorie avec barre de progression et alertes |
| **Objectifs d'épargne** | Cartes de suivi avec jauge de progression et date cible |
| **Analyses détaillées** | Graphiques évolutifs multi-mois, répartition, top enseignes |
| **Patrimoine & Investissements** | Vue consolidée, évolution, transactions, diversification, intérêts livrets |
| **Projection** | Simulation à long terme + analyse IA on-demand |
| **Historique** | Vue agrégée sur l'ensemble des mois saisis |
| **Recommandations** | Alertes automatiques et suggestions d'optimisation par IA |
| **Paramètres** | SMTP, catégories, PDF, export fiscal, sécurité, Supabase, IA, mode sombre |

---

## 🚀 Installation

### Option A — Exécutable Windows (recommandé)

1. Téléchargez la dernière release : **`Fintrack-vX.Y.Z-windows.zip`**
2. Décompressez le dossier
3. Lancez **`Fintrack.exe`**
4. Créez votre mot de passe au premier lancement

> ⚠️ Windows peut afficher "Application inconnue" — cliquez *Informations complémentaires* → *Exécuter quand même*

### Option B — Depuis les sources (Python)

**Prérequis :** Python 3.10+ — [télécharger ici](https://www.python.org/downloads/)

```bash
# 1. Cloner le dépôt
git clone https://github.com/MoussaOudihat/fintrack.git
cd fintrack

# 2. (Optionnel) Créer un environnement virtuel
python -m venv venv
venv\Scripts\activate

# 3. Installer les dépendances
pip install -r desktop/requirements.txt

# 4. Lancer l'application (ou double-clic sur desktop/run.bat)
python desktop/main.py
```

### Dépendances principales

| Package | Rôle |
|---------|------|
| `customtkinter` | Interface graphique moderne (thème light/dark) |
| `matplotlib` | Graphiques interactifs |
| `openpyxl` | Import/export Excel |
| `google-genai` | Analyse IA via Gemini (recommandations, projection) |
| `supabase` | Synchronisation cloud optionnelle |

### Optionnel

```bash
pip install reportlab    # Génération de rapports PDF
```

---

## 📋 Utilisation rapide

1. **Premier lancement** : choisissez *Nouveau compte* (local) ou *Restaurer depuis Supabase*
2. **Créez votre mot de passe** et votre question secrète
3. **Chaque mois** : saisissez vos revenus → dépenses → épargne
4. **Suivi patrimoine** : ajoutez vos actifs dans *Patrimoine & Investissements*
   - Pour un **Livret A / Bourso+** : type "Compte / Épargne" → renseignez le solde actuel et le total versé → les intérêts gagnés s'affichent automatiquement
   - Pour des **actions / ETF / crypto** : renseignez la valeur actuelle et le prix d'achat total
5. **Analyse** : explorez les graphiques dans *Analyses détaillées*
6. **IA** : configurez votre profil dans *Paramètres → IA* pour des recommandations personnalisées

> 💡 La base de données SQLite est dans `data/fintrack.db` — pensez à la sauvegarder régulièrement (ou activez Supabase pour un backup automatique).

---

## 🤖 Fonctionnalité IA

Fintrack intègre **Gemini** (Google AI) pour l'analyse de vos finances. Optimisé pour le tier gratuit (faible consommation de tokens).

### Configuration

Dans **Paramètres → IA** :
1. Entrez votre clé API Gemini (gratuite sur [aistudio.google.com](https://aistudio.google.com))
2. Renseignez votre **profil** (ex : "Couple 30 ans, CDI, propriétaires, 2 enfants") pour personnaliser les analyses

### Ce que l'IA peut faire
- **Recommandations mensuelles** : analyse revenus/dépenses/épargne et suggère des optimisations
- **Analyse de projection** : évalue le réalisme d'un scénario d'épargne à long terme et propose des leviers

---

## ☁️ Configurer la synchronisation Supabase

La sync est entièrement optionnelle. Elle vous permet d'accéder à vos données depuis plusieurs machines.

### 1. Créer un projet Supabase (gratuit)

1. Créez un compte sur [supabase.com](https://supabase.com)
2. Créez un nouveau projet
3. Dans **SQL Editor**, copiez-collez et exécutez le contenu de [`supabase/schema.sql`](supabase/schema.sql)

### 2. Récupérer vos identifiants

Dans votre projet Supabase → **Settings → API** :
- **URL du projet** : `https://xxxx.supabase.co`
- **Clé anon / publishable** : les comptes sont gérés par Supabase Auth et protégés par Row Level Security. La clé `service_role` n'est plus jamais utilisée (depuis la v1.3.0).

### 3. Activer dans l'application

**Au premier lancement** → choisissez le mode en ligne, puis créez votre compte ou connectez-vous (email + mot de passe).

**Ou depuis les Paramètres** → section *Synchronisation Supabase* → activez et entrez vos identifiants.

---

## 🌐 Interface web — microservices (Docker / Kubernetes) — v2.0

Accédez à Fintrack depuis un navigateur (mobile compris) avec **le même compte Supabase** que l'application desktop. Architecture détaillée : [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Sécurité : [SECURITY.md](SECURITY.md) · Chaîne DevSecOps : [docs/DEVSECOPS.md](docs/DEVSECOPS.md).

| Service | Rôle | État |
|---|---|---|
| **web** | Pages HTML, sessions (Redis), orchestration | sans état · HPA |
| **finance-api** | Données : écrit ligne par ligne dans Supabase Postgres avec le jeton de l'utilisateur (RLS) | sans état · HPA |
| **ai-service** | Analyse, assistant conversationnel, catégorisation — Claude ou Gemini | sans état · HPA |
| **notifier** | TickTick (OAuth), ntfy, Discord/Slack : alertes budget, rappel mensuel | volume · 1 réplica |
| **redis** | Sessions et compteurs (quotas IA, tentatives de connexion) | éphémère |

**Dans le navigateur** : tableau de bord, dépenses / revenus / épargne (avec la synchro Épargne → Patrimoine), **budgets** (alertes à 80 % et 100 %), patrimoine, **assistant IA** (analyse de la période, questions libres, suggestion de catégorie), **notifications** (TickTick, ntfy, webhooks). L'analyse avancée, la projection, les exports et la clôture de mois restent dans l'app desktop.

> **Desktop + web** : le web écrit ligne par ligne et ne peut plus écraser les données. L'app desktop refuse désormais d'envoyer sa base si des modifications ont été faites ailleurs depuis sa dernière synchro : elle demande de récupérer d'abord.

### Docker Compose (ou Podman Compose)
```bash
python deploy/gen_secrets.py                 # secrets dans deploy/compose/secrets/ (ignorés par git)
cp deploy/compose/.env.example deploy/compose/.env   # SUPABASE_URL, TickTick, modèles IA…
docker compose -f deploy/compose/compose.yaml up -d --build   # → http://localhost:8080
```
Réseau `backend` interne (sans Internet), seul `web` publié sur 127.0.0.1, conteneurs non-root en lecture seule, secrets en fichiers, healthchecks, limites de ressources.

### Kubernetes (chart Helm)
Le chart est publié à chaque release (OCI, signé cosign) sur GHCR et Docker Hub.
```bash
kubectl create namespace fintrack
kubectl label ns fintrack pod-security.kubernetes.io/enforce=restricted
python deploy/gen_secrets.py --k8s                 # → deploy/helm/secrets.env (ignoré par git)
kubectl -n fintrack create secret generic fintrack-secrets --from-env-file=deploy/helm/secrets.env

helm upgrade --install fintrack oci://ghcr.io/moussaoudihat/charts/fintrack --version 2.0.0 -n fintrack \
  --set config.supabaseUrl=https://<projet>.supabase.co \
  --set secrets.existingSecret=fintrack-secrets \
  --set ingress.host=fintrack.mondomaine.fr
helm test fintrack -n fintrack
```
Depuis les sources : `helm install fintrack deploy/helm/fintrack -f deploy/helm/fintrack/values-local.yaml …` (cluster local, images `localhost/fintrack-*:dev`). Exemple de production : [`values-production.yaml`](deploy/helm/fintrack/values-production.yaml).

Le chart applique : NetworkPolicies « deny-all » + flux explicites (sortie Internet limitée au 443, plages privées et métadonnées cloud exclues), Pod Security `restricted`, ServiceAccounts sans jeton, HPA + PDB, topologySpread, Ingress TLS (cert-manager), redémarrage auto si la configuration change, clés internes générées une fois puis conservées, `values.schema.json`, `helm test`.

### Registres d'images
| Registre | Images | Chart |
|---|---|---|
| **GHCR** (toujours) | `ghcr.io/moussaoudihat/fintrack-{web,finance-api,ai-service,notifier}` | `oci://ghcr.io/moussaoudihat/charts/fintrack` |
| **Docker Hub** (si configuré) | `docker.io/<utilisateur>/fintrack-…` | `oci://registry-1.docker.io/<utilisateur>/fintrack` |

Pour activer Docker Hub : créer un jeton d'accès *Read & Write* sur hub.docker.com, puis dans GitHub → *Settings → Secrets and variables → Actions* : variable `DOCKERHUB_USERNAME`, secret `DOCKERHUB_TOKEN`.

### Intégrations
- **Claude / Gemini** : clés serveur `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` (secrets de ai-service). Modèles : `CLAUDE_MODEL` (défaut `claude-opus-5-5`), `GEMINI_MODEL`. Quota `AI_DAILY_LIMIT` par utilisateur et par jour. Seul un **résumé agrégé** est envoyé au fournisseur, après consentement explicite.
- **TickTick** : créer une application sur [developer.ticktick.com](https://developer.ticktick.com), URL de redirection `https://<votre-hôte>/parametres/ticktick/callback`, puis renseigner `TICKTICK_CLIENT_ID`, `TICKTICK_REDIRECT_URI` et le secret `ticktick_client_secret`. L'utilisateur clique ensuite « Connecter TickTick » dans Notifications.
- **ntfy / Discord / Slack** : URL saisie par l'utilisateur, limitée aux hôtes de `NOTIFIER_ALLOWED_HOSTS` (anti-SSRF).

### Développement
```bash
pip install -r services/requirements-dev.txt
cd services && python -m pytest -q tests      # tests des 4 services (dont bout en bout web → API)
```

---

## 🗺️ Roadmap

### ✅ v2.0 — Actuel
- [x] Interface web en 4 microservices (Docker Compose / Kubernetes), mêmes comptes Supabase que l'app desktop
- [x] Assistant IA (Claude, Gemini) : analyse, questions libres, catégorisation automatique
- [x] Budgets depuis le web avec alertes 80 % / 100 %, rappel mensuel — TickTick, ntfy, Discord/Slack
- [x] Pipeline DevSecOps : SAST, SCA, secrets, scan d'images et d'IaC, images signées + SBOM

### ✅ v1.2
- [x] Import / export Excel par page (Dépenses et Revenus)
- [x] Template Excel avec liste déroulante de catégories
- [x] Autocomplétion sur le champ Enseigne (suggestions basées sur l'historique)
- [x] Visualisation en lecture seule des mois clôturés
- [x] Fonctionnalité Excel activable depuis les Paramètres

### ✅ v1.1
- [x] Saisie revenus / dépenses / épargne
- [x] Tableau de bord avec filtres interactifs
- [x] Patrimoine multi-actifs avec transactions (CMUP)
- [x] Compte / Épargne : suivi solde + intérêts gagnés
- [x] Budget mensuel par catégorie
- [x] Objectifs d'épargne avec progression
- [x] Analyses graphiques (évolution, répartition, top enseignes)
- [x] Projection financière à long terme + analyse IA on-demand
- [x] Recommandations IA mensuelles (Gemini, rendu Markdown)
- [x] Mode sombre / clair
- [x] Authentification par mot de passe + session persistante
- [x] Export PDF, CSV, fiscal
- [x] Envoi par email SMTP
- [x] Synchronisation Supabase PostgreSQL (multi-appareils)
- [x] Transactions récurrentes (préchargement mensuel)

### 🔜 Prochaines améliorations
- [ ] Alertes dépassement budget (notifications en temps réel)
- [ ] Import automatique de relevés bancaires (OFX/CSV banque)
- [ ] Notifications Windows (rappel de saisie mensuelle)
- [ ] Multi-devise (€, $, £…)

### 💡 Idées futures
- [ ] Application mobile compagnon (lecture seule)
- [ ] Import depuis Bankin / Linxo

---

## 🤝 Contribuer

Les contributions sont les bienvenues !

### Signaler un bug
1. Vérifiez que le bug n'est pas déjà [reporté](https://github.com/MoussaOudihat/fintrack/issues)
2. Ouvrez une **Issue** avec : description, étapes pour reproduire, version Python et OS, message d'erreur complet

### Proposer une fonctionnalité
Ouvrez une **Issue** avec le label `enhancement`.

### Soumettre du code

```bash
# 1. Forker le repo sur GitHub
git clone https://github.com/VOTRE_USERNAME/fintrack.git

# 2. Créer une branche feature depuis develop
git checkout develop
git checkout -b feature/ma-fonctionnalite

# 3. Faire vos modifications et tester
python desktop/main.py                                   # app desktop
(cd desktop && python -m pytest -q tests)                # tests desktop
(cd services && python -m pytest -q tests)               # tests microservices

# 4. Committer
git commit -m "feat: ajouter l'import CSV bancaire"

# 5. Pousser et ouvrir une PR vers develop
git push origin feature/ma-fonctionnalite
```

### Convention de commits
```
feat:     nouvelle fonctionnalité
fix:      correction de bug
ui:       amélioration visuelle
perf:     optimisation de performance
docs:     documentation
refactor: refactoring sans changement de comportement
release:  préparation d'une release
```

### Structure du projet
```
finance-tracker/
├── desktop/                 # Application Windows (customtkinter, SQLite + synchro Supabase)
│   ├── main.py              # Point d'entrée
│   ├── config.py · database.py · auth.py · cloud_auth.py · sync_supabase.py
│   ├── utils_*.py           # IA, PDF, email, Excel, fiscalité
│   ├── ui/                  # Fenêtres, composants, pages
│   ├── tools/               # reset_auth.py (récupération), generate_icon.py
│   ├── tests/               # pytest (couche données, synchro)
│   ├── fintrack.spec        # Build PyInstaller
│   └── requirements.txt · run.bat · fintrack.ico
├── services/                # Plateforme web (microservices FastAPI)
│   ├── common/              # fintrack_common : auth JWT, logs, HTTP, quotas, formatage
│   ├── web/ · finance_api/ · ai_service/ · notifier/
│   ├── tests/               # pytest (dont bout en bout web → API)
│   └── Dockerfile           # image commune (build-arg SERVICE)
├── deploy/
│   ├── compose/             # Docker / Podman Compose
│   ├── helm/fintrack/       # Chart Helm (Kubernetes)
│   └── gen_secrets.py       # génération des secrets
├── supabase/                # schema.sql, migration_multiuser.sql
├── docs/                    # ARCHITECTURE.md, ROADMAP.md
├── .github/                 # CI DevSecOps, release, CodeQL, Dependabot
├── data/                    # Base locale de l'app desktop (non versionnée)
└── VERSION · CHANGELOG.md · SECURITY.md · pyproject.toml
```

---

## 📄 Licence

Ce projet est sous licence **MIT** — voir le fichier [LICENSE](LICENSE) pour les détails.

---

## 👤 Auteur

**Moussa Oudihat**  
GitHub : [@MoussaOudihat](https://github.com/MoussaOudihat)

---

*Si ce projet vous est utile, n'hésitez pas à lui donner une ⭐ sur GitHub !*
