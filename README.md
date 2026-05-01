# 💰 Finance Tracker

> Application desktop Windows pour suivre ses finances personnelles — **locale, sécurisée, open source.**  
> Synchronisation Supabase optionnelle pour le multi-appareils.

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
- Évolution historique de la valeur nette
- Analyse de diversification (score Herfindahl)
- Transactions (achats / ventes) par actif

### Analyses & visualisation
- Graphiques interactifs (camembert, barres, courbes) avec survol souris
- Dépenses par catégorie et par enseigne — clic = filtre instantané
- Évolution mensuelle sur 6 ou 12 mois
- Comparaison budgétaire prévu vs réel

### Outils financiers
- **Budget mensuel** — fixez des plafonds par catégorie
- **Objectifs d'épargne** — suivi de progression avec date cible
- **Projection financière** — simulation à N ans avec taux de rendement
- **Recommandations automatiques** — alertes sur les dépassements
- **Historique** — vue consolidée sur plusieurs mois

### Exports & rapports
- Rapport **PDF** mensuel
- Export **CSV** complet
- Export fiscal (plus-values, dons, formation)
- Envoi par **email SMTP** (résumé mensuel)

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
| **Patrimoine & Investissements** | Vue consolidée, évolution, transactions, diversification |
| **Projection** | Simulation à long terme avec taux de rendement paramétrable |
| **Historique** | Vue agrégée sur l'ensemble des mois saisis |
| **Recommandations** | Alertes automatiques et suggestions d'optimisation |
| **Paramètres** | SMTP, catégories, PDF, export fiscal, sécurité, Supabase, mode sombre |

---

## 🚀 Installation

### Option A — Exécutable Windows (recommandé)

1. Téléchargez la dernière release : **`FinanceTracker-vX.Y.Z-windows.zip`**
2. Décompressez le dossier
3. Lancez **`Finance Tracker.exe`**
4. Créez votre mot de passe au premier lancement

> ⚠️ Windows peut afficher "Application inconnue" — cliquez *Informations complémentaires* → *Exécuter quand même*

### Option B — Depuis les sources (Python)

**Prérequis :** Python 3.10+ — [télécharger ici](https://www.python.org/downloads/)

```bash
# 1. Cloner le dépôt
git clone https://github.com/MoussaOudihat/finance-tracker.git
cd finance-tracker

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
5. **Analyse** : explorez les graphiques dans *Analyses détaillées*

> 💡 La base de données SQLite est dans `data/finance_tracker.db` — pensez à la sauvegarder régulièrement (ou activez Supabase pour un backup automatique).

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

### ✅ v1.0 — Actuel
- [x] Saisie revenus / dépenses / épargne
- [x] Tableau de bord avec filtres interactifs
- [x] Patrimoine multi-actifs avec transactions
- [x] Budget mensuel par catégorie
- [x] Objectifs d'épargne avec progression
- [x] Analyses graphiques (évolution, répartition, top enseignes)
- [x] Projection financière à long terme
- [x] Recommandations automatiques
- [x] Mode sombre / clair
- [x] Authentification par mot de passe + session persistante
- [x] Export PDF, CSV, fiscal
- [x] Envoi par email SMTP
- [x] Synchronisation Supabase PostgreSQL (multi-appareils)
- [x] Écran bienvenue + restauration depuis Supabase au premier lancement

### 🔜 Prochaines améliorations
- [ ] Import automatique de relevés bancaires (OFX/CSV banque)
- [ ] Notifications Windows (rappel de saisie mensuelle)
- [ ] Thèmes de couleurs personnalisables
- [ ] Graphique en chandelier pour l'évolution patrimoniale
- [ ] Multi-devise (€, $, £…)

### 💡 Idées futures
- [ ] Application mobile compagnon (lecture seule)
- [ ] Import depuis Bankin / Linxo

---

## 🤝 Contribuer

Les contributions sont les bienvenues !

### Signaler un bug
1. Vérifiez que le bug n'est pas déjà [reporté](https://github.com/MoussaOudihat/finance-tracker/issues)
2. Ouvrez une **Issue** avec : description, étapes pour reproduire, version Python et OS, message d'erreur complet

### Proposer une fonctionnalité
Ouvrez une **Issue** avec le label `enhancement`.

### Soumettre du code

```bash
# 1. Forker le repo sur GitHub
git clone https://github.com/VOTRE_USERNAME/finance-tracker.git

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
```

### Structure du projet
```
finance-tracker/
├── main.py              # Point d'entrée
├── auth.py              # Authentification (hash, sessions)
├── config.py            # Constantes, palette de couleurs
├── database.py          # Toutes les opérations SQLite
├── sync_supabase.py     # Synchronisation Supabase PostgreSQL
├── supabase_schema.sql  # Schéma SQL à exécuter dans Supabase
├── utils_pdf.py         # Génération de rapports PDF
├── utils_email.py       # Envoi d'emails SMTP
├── utils_taxes.py       # Export fiscal
├── requirements.txt
├── Finance Tracker.spec # Configuration PyInstaller
├── data/                # Base de données locale (non versionnée)
└── ui/
    ├── app.py           # Fenêtre principale + navigation
    ├── login.py         # Écran d'authentification + bienvenue
    ├── components.py    # Widgets réutilisables
    ├── dialogs.py       # Boîtes de dialogue
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
