# Changelog

Tous les changements notables de ce projet sont documentés ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).
Ce projet suit le [Semantic Versioning](https://semver.org/lang/fr/).

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
