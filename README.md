# 💜 Fintrack

> Application desktop Windows pour suivre ses finances personnelles — **locale, sécurisée, open source.**  
> Synchronisation Supabase optionnelle pour le multi-appareils.

![Version](https://img.shields.io/badge/Version-1.2.2-4F46E5)
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
- **`reset_auth.py`** — récupération des identifiants (username oublié, mot de passe perdu, compte bloqué) sans toucher aux données
- **`supabase_migration.sql`** — mise à jour du schéma Supabase existant vers la dernière version
- **`supabase_schema.sql`** — schéma complet pour une nouvelle installation Supabase

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
pip install -r requirements.txt

# 4. Lancer l'application
python main.py
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
3. Dans **SQL Editor**, copiez-collez et exécutez le contenu de [`supabase_schema.sql`](supabase_schema.sql)

### 2. Récupérer vos identifiants

Dans votre projet Supabase → **Settings → API** :
- **URL du projet** : `https://xxxx.supabase.co`
- **Secret key** : section *Secret keys* (commence par `sb_secret_…` ou `eyJ…` pour les clés legacy)

### 3. Activer dans l'application

**Au premier lancement** → cliquez *Restaurer mon compte* et entrez vos identifiants.

**Ou depuis les Paramètres** → section *Synchronisation Supabase* → activez et entrez vos identifiants.

---

## 🗺️ Roadmap

### ✅ v1.2 — Actuel
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
python main.py

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
fintrack/
├── main.py              # Point d'entrée
├── auth.py              # Authentification (hash, sessions)
├── config.py            # Constantes, palette de couleurs
├── database.py          # Toutes les opérations SQLite
├── sync_supabase.py     # Synchronisation Supabase PostgreSQL
├── supabase_schema.sql  # Schéma SQL à exécuter dans Supabase
├── utils_ai.py          # Intégration Gemini (recommandations, projection)
├── utils_pdf.py         # Génération de rapports PDF
├── utils_email.py       # Envoi d'emails SMTP
├── utils_taxes.py       # Export fiscal
├── generate_icon.py     # Générateur d'icône Fintrack (Pillow)
├── fintrack.ico         # Icône application
├── requirements.txt
├── Finance Tracker.spec # Configuration PyInstaller
├── VERSION              # Version courante (ex : 1.1.0)
├── CHANGELOG.md
├── data/                # Base de données locale (non versionnée)
└── ui/
    ├── app.py           # Fenêtre principale + navigation
    ├── login.py         # Écran d'authentification + bienvenue
    ├── components.py    # Widgets réutilisables (cards, tables, render_ai_text…)
    ├── dialogs.py       # Boîtes de dialogue (actifs, dépenses, récurrentes…)
    └── pages/
        ├── dashboard.py
        ├── revenues.py
        ├── expenses.py
        ├── savings_entry.py
        ├── budget.py
        ├── objectifs.py
        ├── analyses.py
        ├── patrimoine.py
        ├── projection.py
        ├── historique.py
        ├── recommandations.py
        └── settings.py
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
