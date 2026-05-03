# Changelog

Tous les changements notables de ce projet sont documentés ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).
Ce projet suit le [Semantic Versioning](https://semver.org/lang/fr/).

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
