# 💰 Finance Tracker

> Application desktop Windows pour suivre ses finances personnelles — **locale, gratuite, open source.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22C55E)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows)
![DB](https://img.shields.io/badge/Database-SQLite%20local-F59E0B)

Aucun cloud, aucun abonnement, aucune inscription. Vos données restent sur votre machine dans une base SQLite locale.

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

### Confort
- 🔐 **Accès par mot de passe** + question secrète + session 30 jours
- 🌙 Mode sombre / clair
- Import depuis **Notion** (ZIP export)

---

## 🖥️ Aperçu des vues

| Vue | Description |
|-----|-------------|
| **Tableau de bord** | KPIs du mois (revenus, dépenses, épargne, bilan) + graphiques filtrables par catégorie ou enseigne |
| **Revenus / Dépenses / Épargne** | Saisie et gestion des entrées mensuelles avec tableau éditable |
| **Budget mensuel** | Plafonds par catégorie avec barre de progression et alertes de dépassement |
| **Objectifs d'épargne** | Cartes de suivi avec jauge de progression et date cible |
| **Analyses détaillées** | Graphiques évolutifs multi-mois, répartition par catégorie, top enseignes |
| **Patrimoine & Investissements** | Vue consolidée du patrimoine, évolution, transactions, diversification |
| **Projection** | Simulation à long terme avec taux de rendement paramétrable |
| **Historique** | Vue agrégée sur l'ensemble des mois saisis |
| **Recommandations** | Alertes automatiques et suggestions d'optimisation |
| **Paramètres** | SMTP, catégories, PDF, export fiscal, sécurité, mode sombre |

---

## 🚀 Installation

### Prérequis
- **Python 3.10 ou supérieur** — [télécharger ici](https://www.python.org/downloads/)
- Windows 10 / 11 (testé principalement sur Windows)

### Étapes

```bash
# 1. Cloner le dépôt
git clone https://github.com/MoussaOudihat/finance-tracker.git
cd finance-tracker

# 2. (Optionnel) Créer un environnement virtuel
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux

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

### Optionnel (fonctionnalités avancées)

```bash
pip install reportlab    # Génération de rapports PDF
```

### Lancer avec l'exécutable (Windows)
Un `.exe` standalone peut être généré avec PyInstaller :

```bash
pip install pyinstaller
pyinstaller "Finance Tracker.spec"
# L'exécutable se trouve dans dist/
```

---

## 📋 Utilisation rapide

1. **Premier lancement** : créez votre mot de passe et votre question secrète
2. **Chaque mois** : saisissez vos revenus → dépenses → épargne
3. **Suivi patrimoine** : ajoutez vos actifs dans *Patrimoine & Investissements*
4. **Analyse** : explorez les graphiques dans *Analyses détaillées*

> 💡 La base de données SQLite est stockée dans `data/finance_tracker.db` — pensez à la sauvegarder régulièrement.

---

## 🗺️ Roadmap

### ✅ v3.0 — Actuel
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

### 🔜 v3.1 — Prochaines améliorations
- [ ] Import automatique de relevés bancaires (OFX/CSV banque)
- [ ] Notifications Windows (rappel de saisie mensuelle)
- [ ] Thèmes de couleurs personnalisables
- [ ] Graphique en chandelier pour l'évolution patrimoniale
- [ ] Multi-devise (€, $, £…)
- [ ] Sauvegarde automatique chiffrée

### 💡 Idées futures
- [ ] Application mobile compagnon (lecture seule)
- [ ] Synchronisation cloud optionnelle (Dropbox, Google Drive)
- [ ] Import depuis Bankin / Linxo

---

## 🤝 Contribuer

Les contributions sont les bienvenues ! Voici comment participer :

### Signaler un bug
1. Vérifiez que le bug n'est pas déjà [reporté](https://github.com/MoussaOudihat/finance-tracker/issues)
2. Ouvrez une **Issue** avec :
   - Description du problème
   - Étapes pour reproduire
   - Version Python et OS
   - Message d'erreur complet (si applicable)

### Proposer une fonctionnalité
Ouvrez une **Issue** avec le label `enhancement` en décrivant :
- Le problème que ça résout
- Comment vous imaginez la solution

### Soumettre du code
```bash
# 1. Forker le repo sur GitHub
# 2. Cloner votre fork
git clone https://github.com/VOTRE_USERNAME/finance-tracker.git

# 3. Créer une branche pour votre feature
git checkout -b feature/ma-fonctionnalite

# 4. Faire vos modifications et tester
python main.py

# 5. Committer avec un message clair
git commit -m "feat: ajouter l'import CSV bancaire"

# 6. Pousser et ouvrir une Pull Request
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
├── utils_pdf.py         # Génération de rapports PDF
├── utils_email.py       # Envoi d'emails SMTP
├── utils_taxes.py       # Export fiscal
├── requirements.txt
├── Finance Tracker.spec # Configuration PyInstaller
├── data/                # Base de données locale (non versionnée)
└── ui/
    ├── app.py           # Fenêtre principale + navigation
    ├── login.py         # Écran d'authentification
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

Vous êtes libre d'utiliser, modifier et distribuer ce code, y compris à des fins commerciales, à condition de conserver la mention de copyright.

---

## 👤 Auteur

**Moussa Oudihat**
- GitHub : [@MoussaOudihat](https://github.com/MoussaOudihat)

---

*Si ce projet vous est utile, n'hésitez pas à lui donner une ⭐ sur GitHub !*
