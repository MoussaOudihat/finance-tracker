# Changelog

Tous les changements notables de ce projet sont documentés ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).
Ce projet suit le [Semantic Versioning](https://semver.org/lang/fr/).

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
