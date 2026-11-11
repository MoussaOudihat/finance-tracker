# Changelog

Tous les changements notables de ce projet sont documentés ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).
Ce projet suit le [Semantic Versioning](https://semver.org/lang/fr/).

---

## [2.3.0] — 2026-11-11

> Migration de la base requise : voir [docs/MIGRATION_V2_3.md](docs/MIGRATION_V2_3.md).

### Ajouté
- 🔌 **Serveur MCP en lecture seule** (`services/mcp_server`, pod `mcp`, image `fintrack-mcp`) : interroger ses données depuis Claude Code, claude.ai ou opencode. Transport Streamable HTTP sans état, authentification OAuth 2.1 via le serveur OAuth de Supabase Auth (découverte RFC 9728, PKCE, enregistrement dynamique), 11 outils de lecture. Voir [docs/MCP.md](docs/MCP.md).
- 🌐 web : page de consentement OAuth `/oauth/consent` (connexion préalable avec retour sur la page, CSRF, liste d'hôtes de retour autorisés `OAUTH_ALLOWED_REDIRECT_HOSTS`).
- ☸️ Chart Helm : `mcp.enabled` (Deployment, Service, NetworkPolicy, routes Ingress `/mcp` et `/.well-known/oauth-protected-resource`).
- 🗄️ `supabase/migration_mcp_readonly.sql` : un jeton OAuth (claim `client_id`) ne peut jamais écrire (politiques RLS restrictives) ; politiques propriétaires réécrites avec `(SELECT auth.uid())` (évaluation unique par requête).

### Corrigé (revue de code v2.2)
- 🔒 **Envoi desktop atomique** : l'envoi « tout supprimer puis réinsérer » se fait désormais en une transaction (`fintrack_replace_snapshot`). Avant, une panne en cours d'envoi laissait Supabase à moitié vide, et les erreurs de suppression étaient ignorées.
- 🕐 **Verrou de synchro fiable** : la version `last_supabase_sync` est comparée par égalité, et non plus en comparant l'horloge du PC à celle du serveur. Un PC dont l'horloge avançait pouvait écraser une saisie web.
- ⚛️ **Écritures web transactionnelles** (`fintrack_apply`) : récurrentes (saisies + marquage), épargne + compte lié, saisies groupées, copie des budgets. La version de synchro avance dans la même transaction. Plus de demi-écriture ni de doublon au nouvel essai.
- 🔢 Identifiants attribués en SQL sous verrou par utilisateur. Le contrôle « mois clôturé » se fait dans la transaction, sans fenêtre de course.
- 🔎 Recherche : les bornes de montant sont filtrées par la base, avant la limite de 2000 lignes (des résultats manquaient).
- 🧮 Quota IA réservé avant l'appel (incrément atomique) et rendu en cas d'échec. Les requêtes simultanées ne dépassent plus la limite. Délai Claude ramené à 2 × 50 s, sous le délai du web (120 s).
- `Counter.decr` atomique (WATCH/MULTI) : le compteur ne passe plus sous zéro.
- Middleware de requêtes en ASGI pur : le `request_id` ne déborde plus d'une requête à l'autre.
- Récurrente dont la catégorie a été supprimée : erreur 422 claire au lieu d'une erreur 500.
- Synchro desktop, récupération (pull) :
  - la version distante est lue **avant** les données : une saisie web faite pendant le téléchargement ne peut plus être écrasée par l'envoi suivant ;
  - une table ou des réglages illisibles annulent la récupération (sauvegarde restaurée) au lieu d'être ignorés.
- Envoi desktop : délai propre de 120 s pour la transaction d'envoi. Erreurs classées par code (`PGRST202`, `57014`), et non plus d'après le texte.
- Épargne → compte lié : l'ajustement est calculé par la base, dans la transaction (deux versements simultanés s'additionnent au lieu de s'écraser).
- Récurrentes appliquées deux fois en même temps : 409 « modifié entre-temps » (au lieu de 404).
- MCP :
  - `search_entries` signale une liste incomplète (`truncated`) ;
  - une panne JWKS répond 503 + `Retry-After` (et non 401, qui forçait une nouvelle autorisation OAuth) ;
  - l'Ingress suit le chemin de `mcp.publicUrl` et accepte `/mcp/`.
- Web :
  - une session expirée pendant le consentement OAuth ramène sur la page de consentement après reconnexion ;
  - une seule règle anti open-redirect (refuse aussi CR/LF et caractères de contrôle) ;
  - un seul point de rafraîchissement du jeton.
- finance-api : paramètre `limit` (≤ 500) sur `/v1/search/{kind}` ; un aller-retour PostgREST de moins par saisie de revenu ou d'épargne ; `max(id)` lu une fois par opération SQL.
- Desktop : boutons d'horizon de la projection (chacun appelait la commande du dernier) ; erreur de génération PDF jamais affichée (`NameError`) et bouton bloqué. Lint `B`/`S` activé sur le code desktop.
- Performance :
  - politiques RLS évaluées une fois par requête ;
  - index `(user_id, …)`, car les id sont attribués par utilisateur ;
  - patrimoine courant et catégories lus une fois par requête.

### Modifié
- ⚠️ **Migration requise avant déploiement** : `supabase/migration_v2_3_atomic.sql`. finance-api et l'app desktop v2.3 l'exigent : sans elle, erreur 503 explicite.
- `fintrack_common.auth.User` expose `client_id` et `expires_at`.
- web : les routes sont réparties par domaine (`routes_auth`, `routes_finance`, `routes_ia`, `routes_settings`, `routes_misc`, `routes_entries`). `main.py` passe de 1 255 à 240 lignes, sans changement de comportement.
- Docker Compose : service `mcp` optionnel (`--profile mcp`).
- Guide de migration et de mise en production : [docs/MIGRATION_V2_3.md](docs/MIGRATION_V2_3.md).
- Connexion web : paramètre `next` (chemin local uniquement) pour revenir sur la page demandée.

---

## [2.2.0] — 2026-11-06

### Ajouté (application web)
- 🏦 **Saisie du patrimoine** (`/patrimoine`) : ajout et mise à jour de la valeur d'un actif pour un mois donné (l'historique est conservé), mise à jour rapide sur chaque ligne, retrait avec confirmation. Même chose pour les passifs (capital restant, mensualité, fin du prêt). Les achats et ventes de titres restent dans l'application desktop.
- 🔒 **Clôturer / Rouvrir le mois** depuis le tableau de bord et les pages Dépenses, Revenus et Épargne, avec confirmation. Un mois clôturé n'accepte plus aucun ajout, modification ni suppression.
- 💰 **Épargne › Vue d'ensemble** (`/epargne/vue`) : total, moyenne et taux d'épargne sur 12 mois, épargne mois par mois (les mois non saisis sont signalés), répartition par compte, soldes des comptes et objectifs d'épargne.
- 🤖 Page **Assistant IA** : choix du mois de fin d'analyse.

### Ajouté (API)
- finance-api : `PUT /v1/months/{y}/{m}/closed`, `PUT /v1/assets`, `POST /v1/assets/delete`, `PUT /v1/liabilities`, `POST /v1/liabilities/delete`, `GET /v1/savings-overview`.

### Modifié
- 🤖 **Assistant IA plus fiable** :
  - l'analyse porte sur les N derniers mois **saisis** : les mois vides sont écartés au lieu de compter pour 0 € dans les moyennes ;
  - le mois en cours est marqué comme partiel et exclu des moyennes ;
  - les mois futurs ne sont jamais analysés ;
  - l'IA reçoit les totaux par catégorie mois par mois et la date du jour ;
  - le chat répond d'abord directement à la question, en citant le mois concerné, et dit quand l'information n'est pas disponible.
- ☰ **Saisie en masse** :
  - la grille s'agrandit : une ligne vide apparaît dès que la dernière est remplie, et un bouton « + Ajouter des lignes » ajoute 10 lignes (fonctionne aussi sans JavaScript) ;
  - compteur et total en direct, lignes ignorées grisées ;
  - les catégories manquantes sont signalées avant l'envoi ;
  - le bouton est désactivé pendant l'enregistrement : plus de double envoi.

### Corrigé
- 📅 **Mois affiché par défaut** : il pouvait rester bloqué sur un mois vidé ou futur, par exemple une saisie de test en 2030. C'est désormais le dernier mois qui contient des saisies, sans jamais dépasser le mois en cours.
- ☰ **Saisie en masse limitée à 12 lignes** : au-delà de 10 lignes remplies, on ne pouvait plus en ajouter.

### Mise à jour
- Aucune migration de base : les tables `assets`, `liabilities`, `savings_goals` et la colonne `months.closed` existent déjà.
- Images modifiées : web, finance-api, ai-service. notifier est inchangé.

---

## [2.1.0] — 2026-11-05

### Ajouté (application web)
- 🌗 **Thème Auto / Clair / Sombre** : bouton dans la barre du haut, choix mémorisé par appareil. Appliqué côté serveur, sans script inline : CSP inchangée.
- 🔁 **Transactions récurrentes** (`/recurrentes`) : loyer, abonnements, salaire… créés une fois, puis appliqués chaque mois en un clic avec des montants ajustables. Même règle que l'app desktop (active et pas encore appliquée ce mois-là) ; une double application est refusée.
- 🔎 **Recherche** (`/recherche`) dans tout l'historique : texte (libellé, enseigne, source), catégorie, montant min/max.
- ⧉ **Dupliquer le mois précédent** : dépenses de M-1 à cocher, montants modifiables, avertissement si le mois contient déjà des dépenses.
- ☰ **Saisie en masse** des dépenses et revenus : coller depuis Excel, un relevé bancaire ou un CSV (en-têtes reconnus, sinon montant, catégorie et dates détectés), vérifier dans une grille modifiable, puis enregistrer **en tout ou rien**. En cas d'erreur, rien n'est écrit et la grille reste à l'écran.
- ✨ **Suggestion IA des catégories** dans la saisie en masse : jusqu'à 50 lignes classées en un seul appel, compté comme une requête du quota IA. Suggestions marquées « IA », à vérifier avant d'enregistrer.
- 📈 **Analyses** (`/analyses`) : tendance sur 12 mois, comparaison au mois précédent, au même mois de l'année précédente et à la moyenne des 6 derniers mois, détail par catégorie.
- ⚠️ **Dépenses inhabituelles** : catégories nettement au-dessus de leur moyenne et dépenses isolées anormalement élevées, signalées sur la page Analyses et **notifiées automatiquement** lors d'une saisie (une alerte par catégorie et par mois, désactivable).
- 📨 **Bilan IA du mois** : généré à la demande, il s'appuie sur les anomalies détectées et peut être envoyé sur TickTick, ntfy ou webhook.

### Ajouté (API)
- finance-api : `POST /v1/expenses/batch` et `/v1/revenues/batch` (une seule insertion, 200 lignes max), `/v1/recurring*`, `GET /v1/search/{kind}`, `GET /v1/analytics`.
- ai-service : `POST /v1/categorize/batch`.
- notifier : événement `spending.unusual`, préférence `unusual_alerts`, `POST /v1/report`.

### Modifié
- 🔔 Alertes de budget : **un seul message par écriture**, celui du seuil le plus haut franchi. Une saisie groupée qui passe de 50 % à 110 % n'annonce plus aussi « 80 % ».
- ⚡ **Performances** : fichiers statiques versionnés par empreinte et mis en cache un an ; appels parallèles vers finance-api (tableau de bord, budgets, saisies).

### Corrigé
- ☸️ **Redis recréé à chaque mise à jour du chart** : les libellés de version (`helm.sh/chart`, `app.kubernetes.io/version`) figuraient dans le modèle de pod. Chaque `helm upgrade` recréait donc Redis et déconnectait tous les utilisateurs, puisque les sessions sont en mémoire. Le modèle de pod Redis ne porte plus que des libellés stables : Redis ne redémarre que si son image ou ses options changent.

### Mise à jour
- La base SQLite du notifier reçoit une colonne (`unusual_alerts`), ajoutée **automatiquement au démarrage**. Aucune action requise.
- Pas d'envoi planifié du bilan IA, par conception : les services n'accèdent aux données qu'avec le jeton de l'utilisateur (RLS, aucune clé `service_role`). Voir `docs/ARCHITECTURE.md`.

---

## [2.0.2] — 2026-11-05

### Corrigé
- 🔗 **Bouton « Connecter » TickTick sans effet** : le clic ne menait nulle part. CSP3 applique `form-action` à toute la chaîne de redirections qui suit l'envoi d'un formulaire, et TickTick redirige ensuite vers ses propres pages (connexion, consentement), absentes de la liste autorisée : Chrome bloquait la navigation en silence. Le formulaire renvoie désormais une page intermédiaire qui part vers TickTick (redirection automatique et lien de secours, sans script). La CSP reste inchangée et l'URL d'autorisation est toujours validée strictement.
- ☸️ **`helm test` échouait** : le pod de test se présentait avec l'identité de `web`. Il était donc bloqué par les NetworkPolicies (web ne s'appelle pas lui-même), devenait un endpoint du Service `web` (risque de recevoir du trafic réel) et était compté par son PDB. Il a désormais sa propre identité (`fintrack-test`) et une NetworkPolicy dédiée, limitée à `web` et `finance-api`.
- 📜 **Logs en partie en texte brut** : le démarrage et le journal d'accès d'uvicorn ne passaient pas par le formateur JSON. Tout est maintenant en JSON, et le journal d'accès uvicorn, en doublon du middleware (qui journalise chaque requête avec son `request_id`) et contenant l'IP client en clair, est désactivé.
- 🔒 **bcrypt 5** : troncature explicite à 72 octets. Sans elle, un mot de passe ou une réponse secrète longue bloquait la connexion à l'app desktop.

### Mises à jour
- customtkinter 6.0, supabase 2.33+, openpyxl 3.1.5, bcrypt 5, Redis 8.10 (Compose et chart Helm alignés).
- Toutes les GitHub Actions passent sur Node.js 24 (Node 20 est déprécié).
- Release : une seule release à la fois par tag ; la GitHub Release n'est publiée qu'en dernier, si tout a réussi.

Validé sur un cluster kind (3 nœuds, kindnet) : pods répartis sur les workers, NetworkPolicies effectivement appliquées, durcissement des conteneurs et signatures cosign v3 vérifiés.

---

## [2.0.1] — 2026-11-05

Publiée par erreur avant la fusion de ses correctifs : contenu fonctionnellement **identique à 2.0.0**. Utiliser **2.0.2**.

---

## [2.0.0] — 2026-11-04

### Ajouté
- 🌐 **Interface web en microservices** (Docker Compose / Kubernetes) : Fintrack est accessible depuis un navigateur, y compris sur mobile, avec le même compte Supabase que l'application desktop. Quatre services : **web** (pages, sessions), **finance-api** (données, écrites ligne par ligne dans Supabase avec la RLS de l'utilisateur), **ai-service** (IA), **notifier** (notifications). Disponible : tableau de bord, dépenses / revenus / épargne (avec la synchro Épargne → Patrimoine), budgets, patrimoine. Les mois clôturés sont en lecture seule. Voir `docs/ARCHITECTURE.md`.
- 🤖 **Assistant IA avec Claude ou Gemini** : analyse de la période (1, 3 ou 6 mois), questions libres sur ses finances (« combien je dépense en restaurants ? »), suggestion automatique de la catégorie d'une dépense. Seul un résumé agrégé est envoyé, après consentement, avec un quota quotidien par utilisateur.
- 💰 **Budgets depuis le web** : définir, modifier et copier les budgets du mois précédent. Une alerte est envoyée quand un budget atteint 80 % puis 100 %.
- 🔔 **Notifications** : **TickTick** (connexion OAuth, les alertes et rappels deviennent des tâches dans la liste choisie), **ntfy**, webhooks **Discord / Slack**. Rappel mensuel de saisie, au jour choisi.
- ☸️ **Déploiement** : Compose durci (réseau interne sans Internet, secrets en fichiers, conteneurs non-root en lecture seule) et **chart Helm** `fintrack` (NetworkPolicies deny-all, Pod Security `restricted`, HPA, PDB, Ingress TLS, `helm test`, schéma de valeurs). Images et chart publiés et signés sur **GHCR** et, si configuré, **Docker Hub**.
- 🛡️ **Pipeline DevSecOps** : Ruff, Bandit, Semgrep, CodeQL, pip-audit, Gitleaks, Hadolint, Trivy (images et IaC), kubeconform, Dependabot. Actions épinglées par SHA. Images publiées sur GHCR signées avec cosign, avec provenance SLSA et SBOM attestés. Voir `SECURITY.md`.
- ✅ **Tests** : 71 pour les services (dont des tests de bout en bout web → finance-api → base) et 8 pour le desktop.

### Réorganisation
- 📁 Dépôt séparé en `desktop/` (application Windows), `services/` (plateforme web), `deploy/` (Compose, Helm), `supabase/` (schémas SQL) et `docs/`. En mode source, la base locale (`data/`) et `VERSION` restent à la racine : rien ne change pour une installation existante. Lancement : `python desktop/main.py`.
- 🧹 Nettoyage : code mort supprimé (méthodes jamais appelées de `database.py`, utilitaires et imports inutilisés, mécanisme de rafraîchissement jamais déclenché), manifestes Kustomize remplacés par le chart Helm, helpers dupliqués (mois, euros, décalage de mois) regroupés dans `fintrack_common`.

### Sécurité
- 🛡️ **Plus d'écrasement entre appareils** : l'app desktop vérifie avant d'envoyer que les données Supabase n'ont pas été modifiées ailleurs (web ou autre PC) depuis sa dernière synchronisation. Si c'est le cas, elle refuse au lieu d'effacer ces modifications.
- 🔐 **Déconnexion limitée à l'appareil** : se déconnecter (desktop ou web) ne ferme plus les sessions Supabase des autres appareils.
- 🤖 L'appel Claude de l'app desktop n'envoie plus `temperature`, refusé par l'API Messages depuis la version 2026-10-21.

### Corrigé
- 🐛 **Import Notion : nouvelles catégories rangées dans « Autres »** : depuis la v1.4.0, l'import utilisait une liste de catégories en cache, sans celles qu'il venait de créer. Toutes les dépenses d'une catégorie inédite partaient dans « Autres ».
- 🐛 **Import Notion : catégories en minuscules non reconnues** : « Courses » (enregistrée « COURSES ») n'était jamais retrouvée, et les dépenses étaient rangées dans « Autres » ou ignorées.
- 🐛 **Transactions récurrentes appliquées en double** : si l'une des lignes cochées avait un montant invalide, les lignes valides étaient enregistrées quand même et restaient cochées. Elles étaient donc ajoutées une deuxième fois au clic suivant. Désormais, rien n'est enregistré tant que tout n'est pas valide.
- 🌙 **Changement de thème** : basculer le mode sombre fermait aussi les fenêtres et notifications ouvertes.
- 🌙 **Positions vendues (Patrimoine) illisibles en mode sombre** : fond clair figé sous du texte clair.
- 🤖 **Analyse IA** : les « dépenses notables » et « sources de revenus » répétaient le même poste récurrent (« Loyer=900€ | Loyer=900€ | … »). Elles sont maintenant regroupées par libellé, en €/mois.
- 📅 **Sélecteur d'année limité à 2029** : il s'étend désormais automatiquement.

### Performance / nettoyage
- Replier une section ou un groupe du menu ne vide plus tout le cache de requêtes.
- Résumé IA : 1 requête SQL groupée au lieu de 2 requêtes par mois analysé.
- Le dépli des groupes du menu n'est plus lu deux fois en base, et le composant ne gère plus lui-même la persistance.
- La modification d'une dépense ou d'un revenu refuse désormais un montant nul ou négatif, comme à la création.
- README : la section Supabase décrivait encore la clé `service_role`, supprimée en v1.3.0.
- `FINTRACK_DATA_DIR` permet de placer la base et les logs dans un autre dossier (volume de conteneur).

---

## [1.4.0] — 2026-09-06

### Ajouté
- 📂 **Paramètres réorganisés en sections repliables** : les 11 blocs de la page Paramètres (Rapports, Email, Apparence, Sécurité, Import Notion, Catégories, Base de données, Transactions récurrentes, Synchronisation, IA…) peuvent maintenant être repliés/dépliés individuellement — état mémorisé. Fini le long défilement pour tout voir.
- 📋 **Menu latéral repliable par catégorie** : les 4 groupes de navigation (Saisie du mois, Suivi & Objectifs, Analyses, Outils) sont eux aussi repliables, pour un menu plus clair. Le groupe de la page active se déplie automatiquement s'il était replié.
- 🤖 **Analyse IA plus concrète** : les conseils IA (Recommandations) citent maintenant les libellés des dépenses/revenus les plus importants du mois (ex. "Loyer=850€"), pas seulement des totaux par catégorie.

### Corrigé
- 🌙 **Mode sombre illisible par endroits** : plusieurs fenêtres (agrandissement de graphique, évolution d'un actif, plein écran Patrimoine) avaient un fond blanc figé sous du texte clair — devenu quasi invisible en mode sombre. Les graphiques eux-mêmes gardaient une zone de tracé blanche, des titres et des légendes en gris sombre, contrastant mal avec un fond de page sombre. Tout est maintenant aligné sur le thème actif.
- ✨ **Flash blanc lors des changements de page / bascule mode sombre** : bug connu de customtkinter sous Windows — la barre de titre et le fond natifs de la fenêtre restent clairs par défaut jusqu'à ce que l'app finisse de peindre par-dessus. Contourné en forçant Windows à utiliser son propre chrome sombre dès l'activation du mode sombre.
- 📊 **Analyses → "Personnaliser" laissait un espace vide** : décocher une section (ex. "Détail du mois") ne masquait que son contenu, pas son emplacement — la zone vide restait visible. Les sections décochées ne réservent plus de place du tout.
- ☁️ **Erreur de synchronisation Supabase** (`ON CONFLICT DO UPDATE command cannot affect row a second time`) : l'horodatage de synchronisation pouvait se retrouver en double dans le même envoi. Corrigé.

### Performance
- Graphiques "Évolution par catégorie" et "Dépenses empilées" (Analyses) : remplacement de N requêtes par mois par une seule requête groupée.
- Page Patrimoine : les calculs de statut de position (déjà coûteux) étaient recalculés deux fois par actif à chaque affichage (vue d'ensemble + ligne détaillée) — mis en cache.
- Page Projection : la figure du graphique n'était jamais libérée à chaque recalcul (glissière, champs, changement d'horizon) — fuite mémoire corrigée.
- Import Notion (ZIP) et application groupée de transactions récurrentes : le cache interne était entièrement vidé à chaque ligne/transaction au lieu d'une seule fois à la fin — accélère nettement les imports/applications de plusieurs éléments.

---

## [1.3.0] — 2026-09-06

### Ajouté
- ☁️ **Comptes Supabase Auth réels (multi-utilisateur)** : remplace la restauration par clé `service_role` par de vrais comptes email + mot de passe gérés par Supabase Auth, avec Row Level Security — chaque compte ne voit et ne modifie que ses propres données, même sur un projet Supabase partagé. Récupération de mot de passe par code reçu par email (pas de lien magique, incompatible avec une app desktop).
- 🤖 **Support IA réellement multi-fournisseur** : Anthropic (Claude Haiku) et OpenAI (GPT-4o-mini) sont maintenant réellement implémentés — jusqu'ici, les choisir dans Paramètres échouait systématiquement car le code n'appelait en réalité que l'API Gemini, quel que soit le fournisseur sélectionné.
- ⚙️ **Page Analyses personnalisable** : bouton « Personnaliser » pour cocher/décocher chacune des 4 sections (Évolution 6 mois, Détail du mois, Dépenses empilées par catégorie, Évolution par catégorie) et n'afficher que ce qui est utile. Choix mémorisé.

### Corrigé
- 🐛 **Fournisseur IA figé sur Gemini** : `utils_ai.py` ignorait le paramètre `provider` et appelait toujours Gemini ; la page Projection ne transmettait même pas ce paramètre. Les deux pages utilisent maintenant le même registre `PROVIDER_INFO`.
- 🐛 **Pop-up de consentement IA incorrect** : affichait toujours "envoyé à Google" même avec Anthropic/OpenAI configuré ; affiche maintenant le vrai fournisseur. Ce pop-up, absent sur la page Projection, y a été ajouté par cohérence.
- 🐛 **Plantage aléatoire de l'app** (`Tcl_AsyncDelete: async handler deleted by the wrong thread`) : le ramasse-miettes cyclique de Python pouvait se déclencher sur un thread d'arrière-plan (pré-chargement du cache, appel IA, sync) et y détruire un objet Tkinter — notamment la fenêtre de connexion, jamais explicitement fermée — ce que Tcl/Tk interdit hors du thread principal. Le ramassage automatique est désormais désactivé au profit d'une collecte manuelle déclenchée uniquement depuis le thread principal. Au passage, les threads d'arrière-plan IA ne consultent plus Tkinter (`winfo_exists`) pour savoir si la fenêtre est encore ouverte, remplacé par un simple indicateur Python (`app._closing`).
- 🐛 **Écrasement accidentel des données Supabase** : l'activation du mode en ligne sans avoir d'abord récupéré les données, et l'envoi manuel ("Sync maintenant") sans confirmation, pouvaient écraser des données distantes plus complètes que la base locale. Un garde-fou compare désormais les comptages avant tout envoi destructeur et demande confirmation.
- 🎨 **Vue "Détail du mois" (Analyses) trop condensée** : camembert et graphique des enseignes agrandis, légende moins compressée.

### Sécurité / robustesse
- Row Level Security activée sur toutes les tables de données ; la clé `service_role` (accès total) n'est plus utilisée par l'application.
- `liabilities` et `recurring_transactions` sont désormais incluses dans la synchronisation Supabase (absentes par oubli jusqu'ici).

---

## [1.2.3] — 2026-07-12

### Ajouté
- 🔄 **Synchronisation automatique Épargne → Patrimoine** : ajouter une épargne sur un compte déjà suivi dans Patrimoine (ex. "bourso" ou "boursobank" → « Bourso+ ») met à jour automatiquement le solde et le total versé de ce compte. Correspondance approximative (insensible casse/ponctuation), mais uniquement si elle est unique — un nom ambigu ou inconnu (ex. "Fortuneo" non suivi) n'est jamais synchronisé, pour ne jamais toucher au mauvais compte. Modifier ou supprimer une épargne liée ajuste le solde en conséquence. Un message confirme chaque synchronisation.
- 📊 **Refonte de la page Patrimoine** : découpée en 5 sous-onglets (Vue d'ensemble, Actifs, Passifs, Clôturées, Graphiques) avec un bandeau permanent (patrimoine total, valeur nette, cash en attente) toujours visible, pour remplacer l'ancienne page surchargée en une seule colonne.

### Corrigé
- 🐛 **Épargne (mois clôturé)** : la liste des épargnes existantes s'affichait vide au lieu d'apparaître en lecture seule.
- 🐛 **Budget mensuel** : les lignes du tableau s'étiraient sur ~200px de haut (taille par défaut CustomTkinter non corrigée), rendant la page illisible dès qu'il y avait plusieurs catégories.
- 🐛 **Patrimoine (liste Actifs)** : chevauchement de cellules dans la grille des lignes d'actifs, et le même bug d'étirement à 200px sur les barres d'accent colorées.
- 🐛 **Projection** : les boutons d'horizon (5/10/20/30 ans) n'indiquaient jamais visuellement lequel était sélectionné.
- 🔐 **Transactions d'actifs** : le champ "Frais" acceptait silencieusement du texte invalide comme 0€ ; avertissement ajouté avant de supprimer une transaction de vente.

### Sécurité / robustesse
- Garde-fou empêchant la synchronisation Épargne → Patrimoine de corrompre l'historique lors de la saisie rétroactive d'un mois passé.
- Plancher à 0 sur les soldes/totaux versés (jamais de solde négatif affiché).
- Longueur minimale sur la correspondance de nom de compte (évite les faux positifs sur des noms trop courts).

---

## [1.2.2] — 2026-07-11

### Corrigé
- 🔐 **Récupération par question secrète non protégée contre le brute-force** : le flux "mot de passe oublié" applique désormais le même verrouillage (5 tentatives) que la connexion normale
- 🤖 **Cache d'analyse IA qui s'auto-effaçait** : `database.py` invalidait le cache IA à chaque écriture, y compris celle qui venait de l'enregistrer — chaque analyse retapait l'API payante à chaque affichage
- 🛠️ **`reset_auth.py` désynchronisé de la politique de sécurité** : réimplémentait son propre hachage et une session fixe de 30 jours au lieu des 7 jours actuels, et ne respectait pas le verrouillage brute-force. Utilise maintenant directement `auth.py` / `database.py`
- 💰 **Montants à 0 ou négatifs** : les formulaires dépenses/revenus/épargne rejettent maintenant la saisie invalide avant l'enregistrement au lieu de laisser remonter une erreur non gérée
- 🧹 **Fermeture de l'application** : les rappels différés (`after()`) sont maintenant correctement annulés à la fermeture, évitant un risque de plantage si un thread d'arrière-plan (préchargement, analyse IA) était encore actif
- 📊 **Export Excel cassé dans le build packagé** : la tentative d'installation à la volée d'`openpyxl` ne fonctionnait pas dans l'exécutable PyInstaller — le module est maintenant inclus dans le build
- 🔑 **Appels bloquants au trousseau Windows** : mise en cache mémoire des secrets (`secrets_vault.py`) pour éviter de re-solliciter le gestionnaire d'identifiants à chaque ouverture de Paramètres

### Ajouté
- 👤 **Nom d'utilisateur affiché en haut à droite** de l'application, sur toutes les pages

### Sécurité
- 🔒 Purge d'un secret Supabase qui se trouvait accidentellement suivi dans l'historique git

---

## [1.2.1] — 2026-05-12

### Corrigé
- 🔐 **Login scrollable** : la fenêtre de connexion utilise maintenant un `CTkScrollableFrame` — tout le contenu est accessible sur les petits écrans, la hauteur est redimensionnable
- 🔐 **Récupération & restauration scrollables** : même correctif sur les vues "Mot de passe oublié" et "Restaurer depuis Supabase"
- ☁️ **Crash "Cannot operate on a closed database"** : la connexion SQLite n'est plus fermée après une restauration Supabase — `main.py` conserve une référence valide pour le sync au démarrage
- 💾 **Données protégées à la création de compte** : `_show_category_setup` ne s'exécute plus si la base contient déjà des données (évite l'écrasement des catégories et dépenses existantes lors d'une reconnexion)
- ☁️ **Restauration Supabase → redirect correcte** : après un pull Supabase, si aucun compte local n'existe (auth jamais synchronisée), l'app redirige vers la création d'accès local au lieu de bloquer sur l'écran de login

### Ajouté
- 🛠️ **`reset_auth.py`** : outil de récupération autonome (double-clic ou `python reset_auth.py`) — gère 4 cas : username manquant sur données existantes, mot de passe oublié, compte bloqué, base sans auth. Ne touche jamais aux données financières
- 📋 **`supabase_migration.sql`** : script SQL idempotent pour mettre à jour un projet Supabase existant — ajoute les tables `recurring_transactions` et `liabilities`, les colonnes `months.closed`, `assets.cost_basis`, `asset_transactions.reinvested` et `reinvested_into`
- 📋 **`supabase_schema.sql`** mis à jour : schéma complet v1.2.1 incluant toutes les tables et colonnes actuelles

### Technique
- `ui/login.py` — `_show_login`, `_show_recovery`, `_show_existing_account` : passage en `CTkScrollableFrame` + `resizable(False, True)`
- `ui/login.py` — `_show_existing_account._done()` : remplace `db.con.close()` + `Database()` par `db._invalidate()` pour préserver la référence partagée avec `main.py`
- `ui/login.py` — `_show_setup._do_setup()` : vérifie `COUNT(*) FROM months` avant de lancer le setup catégories
- `ui/login.py` — ajout de `_show_post_restore_setup()` : formulaire dédié post-restauration Supabase (username + mot de passe + question secrète)

---
## [1.1.0] — 2026-05-03

### Ajouté
- 🎨 **Rebranding complet** : Finance Tracker → **Fintrack** (titre, sidebar, login, email, PDF, .spec)
- 🖼️ **Icône & identité visuelle** : nouveau logo indigo généré via Pillow (16/32/48/64/128/256 px), schéma de couleurs indigo (`#4F46E5`) appliqué à toute l'interface
- ✨ **Analyse IA projection on-demand** : bouton "Analyser ce scénario avec l'IA" sur la page Projection — déclenche une analyse en thread background, affiche le résultat sans bloquer l'UI, bouton "Relancer" pour forcer une nouvelle analyse
- 💬 **Rendu Markdown pour les réponses IA** : composant `render_ai_text()` dans `ui/components.py` — formatage natif des titres (`###`), **gras**, • puces et → actions avec `tk.Text` et tags colorés
- 🏦 **Compte/Épargne — saisie adaptative** : le formulaire d'ajout d'actif détecte automatiquement le type "Compte / Épargne" et affiche *Solde actuel* + *Total versé* (facultatif) au lieu des champs investissement (quantité × prix)
- 💰 **Suivi des intérêts** : colonne "Intérêts gagnés" dans le tableau Patrimoine pour les comptes (= solde − total versé), remplace "Plus-value" non pertinente ; intitulé "Total versé" remplace "Prix achat"
- 👤 **Profil IA déplacé dans Paramètres** : le champ de contexte utilisateur (profil) est maintenant dans Paramètres → section IA, plus accessible et persistant entre les sessions

### Corrigé
- 🐛 **Recommandations 1 mois** : condition `len(summary) < 2` remplacée par `not summary` — les données d'un seul mois s'affichaient comme "pas assez de données"
- 🐛 **Colonnes Patrimoine pour comptes** : "Prix achat" et "Plus-value" affichaient des valeurs trompeuses (égale au solde) pour les livrets/comptes épargne — maintenant affichent "—" ou intérêts réels
- 🐛 **Bouton Transactions désactivé pour les comptes** : le bouton 📋 est maintenant `state=disabled` pour les actifs de type "Compte / Épargne" (sans objet)

### Amélioré
- ⚡ **Économie de tokens Gemini (free tier)** : modèle `gemini-2.5-flash-lite`, `thinking_budget=0`, prompts compressés format `clé=valeur`, `max_output_tokens=500` — réduction d'environ 65% des tokens en entrée
- 🎯 **Tooltip mise à jour Patrimoine** : "Mettre à jour le solde" pour les comptes, "Mettre à jour la valeur" pour les investissements
- 📋 **Labels colonne adaptatifs** : quand le filtre "Compte / Épargne" est actif, les en-têtes du tableau deviennent "Solde actuel / Total versé / Intérêts gagnés"

### Technique
- `ui/components.py` : nouveau composant `render_ai_text(parent, text, bg_color)` — parser Markdown-like inline avec regex pour le gras
- `ui/dialogs.py` — `AssetDialog` : méthode `_on_type_change()` masque/affiche les champs selon le type ; `QuickValueUpdateDialog` accepte un paramètre `label` ("solde" vs "valeur")
- `utils_ai.py` : ajout de `get_projection_advice()` + template `_PROJECTION_USER_TEMPLATE` compact
- `generate_icon.py` : script standalone Pillow pour générer `fintrack.ico` multi-résolutions
- `Finance Tracker.spec` → nom `Fintrack`, `icon='fintrack.ico'`, `hiddenimports` enrichis (`google.genai`, `utils_ai`)

---

## [1.0.2] — 2026-05-01

### Ajouté
- 👋 Écran de bienvenue au premier lancement : choix "Nouveau compte" ou "Compte existant (Supabase)"
- ☁️ Restauration depuis Supabase au premier lancement : pull complet avec backup automatique local
- ← Boutons "Retour" dans les écrans de création de compte et de restauration Supabase

### Corrigé
- 🐛 Bouton "Restaurer mes données" sans effet : mise à jour UI thread-safe via `self.after()` (suppression de `status_lbl.update()` appelé hors main thread)
- 🐛 Fenêtres de login tronquées en bas : hauteur augmentée (`_show_welcome` 460→580px, `_show_setup` 660→720px)
- 🐛 CI GitHub Actions : permission `attestations: write` manquante pour Sigstore

### Technique
- `ui/login.py` : `_show_welcome()` — point d'entrée unique du premier lancement
- `ui/login.py` : `_show_existing_account()` — flow de restauration Supabase complet avec feedback visuel
- `ui/login.py` : fenêtres redimensionnables verticalement (`resizable(False, True)`)
- `.github/workflows/release.yml` : job `cleanup-on-failure` — suppression automatique du tag si le build échoue

---

## [1.0.1] — 2026-05-01

### Ajouté
- ☁️ Synchronisation Supabase PostgreSQL (tables réelles, pas Storage)
- 🔄 Auto-sync toutes les 5 minutes pendant la session
- 🗄️ Écran de choix Local / Supabase au premier lancement
- 📋 Script `supabase_schema.sql` pour initialiser le schéma en une commande

### Corrigé
- 🐛 `invalid command name` au démarrage : suppression de `login.destroy()` dans `main.py` (CTk schedule des callbacks pendant la destruction)
- 🐛 `RuntimeError: main thread is not in main loop` dans `_check_alerts` : exécution dans le thread principal (après le délai de 800 ms) plutôt qu'un thread secondaire
- 🐛 Labels "anon key" / "service_role" → "Clé secrète (Secret key)" pour les nouvelles API keys Supabase

### Technique
- `sync_supabase.py` : réécriture complète — sync table par table avec respect des FK, pagination BATCH_SIZE=500, timestamp `last_supabase_sync` pour arbitrer pull/push
- `ui/app.py` : `_schedule_auto_sync()` — push background toutes les 5 min via `after()`
- `ui/app.py` : `_check_alerts()` exécuté dans le thread principal (plus de thread secondaire)
- `main.py` : suppression de `login.destroy()` post-mainloop

---

## [3.1.0] — 2026-04-30

### Ajouté
- 🏷️ Tooltips sur les boutons icônes de la vue Patrimoine (Modifier, Mettre à jour la valeur, Transactions, Évolution, Supprimer, Réinvesti)

### Corrigé
- 🐛 `invalid command name` au démarrage : les callbacks `after()` de CTk étaient purgés avant de quitter `LoginApp`, empêchant les erreurs Tcl au lancement de l'app principale
- 🐛 `SyntaxError: unmatched ')'` dans `settings.py` (fragment de code orphelin ligne 576)

### Technique
- `ui/login.py` : `_finish()` purge la file `after()` Tcl avant `quit()` — `destroy()` délégué à `main.py` après le mainloop
- `ui/pages/patrimoine.py` : utilisation de la classe `Tooltip` de `ui/components.py`

---

## [3.0.0] — 2025-04-30

### Ajouté
- 🔐 Authentification par mot de passe (SHA-256 + sel aléatoire)
- 🔑 Question secrète pour récupération du mot de passe
- 💾 Session persistante 30 jours (auto-login)
- 🔒 Section Sécurité dans les Paramètres (changement de mot de passe, verrouillage)
- 📊 Graphiques non-bloquants (`draw_idle`) pour une UI plus fluide
- 🎨 Couleurs de fond dynamiques sur les graphiques matplotlib (support dark mode)

### Corrigé
- ⚡ Zones noires lors de la navigation entre pages (placeholder coloré anti-flash)
- ⚡ `CTkScrollableFrame` avec `fg_color="transparent"` → couleurs explicites (14 fichiers)
- 🐛 Graphiques matplotlib bloquant le thread principal lors du rendu

### Technique
- `auth.py` : module d'authentification standalone
- `ui/login.py` : fenêtre de connexion (Setup / Login / Récupération)
- `main.py` : refactorisé pour lancer LoginApp avant App
- `.gitignore`, `LICENSE` MIT, `README.md`, `CHANGELOG.md` : préparation open source

---

## [2.1.0] — 2025

### Ajouté
- 📈 Page Projection financière à long terme
- 🧠 Page Recommandations automatiques
- 📋 Historique consolidé multi-mois
- 🌙 Mode sombre / clair avec bascule instantanée
- 📧 Envoi de résumé mensuel par email SMTP
- 📄 Génération de rapport PDF mensuel (`reportlab`)
- 📊 Export fiscal (plus-values, dons, formation)
- 🗂️ Gestion des catégories personnalisées

### Amélioré
- Navigation lazy-loading (import des pages à la première visite)
- Pré-chargement DB en arrière-plan au démarrage
- Soft-refresh sur Dashboard et Analyses (filtres sans rechargement de page)
- Alertes au démarrage (rappel de saisie, dépenses inhabituelles, objectifs en retard)

---

## [2.0.0] — 2025

### Ajouté
- 💰 Budget mensuel par catégorie avec alertes de dépassement
- 🎯 Objectifs d'épargne avec suivi de progression et date cible
- 📈 Patrimoine & Investissements multi-actifs (bourse, immo, crypto, or, livrets)
- 🔄 Transactions par actif (achats / ventes)
- 🎯 Analyse de diversification du portefeuille
- 📊 Graphiques interactifs avec survol (tooltips)
- 🖱️ Clic sur graphique = filtre toggle (catégorie / enseigne)

---

## [1.0.0] — 2025

### Ajouté
- Interface principale avec sidebar de navigation
- Saisie mensuelle revenus / dépenses / épargne
- Tableau de bord avec KPIs (revenus, dépenses, épargne, bilan)
- Analyses basiques (camembert catégories, top enseignes)
- Base de données SQLite locale
- Sélecteur mois/année persistant

---

## Convention de versionnement

`MAJEUR.MINEUR.PATCH`

- **MAJEUR** : changements incompatibles avec les versions précédentes (ex: migration DB)
- **MINEUR** : nouvelles fonctionnalités rétro-compatibles
- **PATCH** : corrections de bugs

### Labels de commits
```
feat:     nouvelle fonctionnalité
fix:      correction de bug
ui:       amélioration visuelle / UX
perf:     optimisation de performance
docs:     documentation uniquement
refactor: refactoring sans changement fonctionnel
security: correctif de sécurité
```
