# Roadmap d'amélioration — Finance Tracker

Plan d'upgrade séquentiel, du plus rentable au plus ambitieux.
Chaque phase est autonome : tu peux t'arrêter à n'importe quelle étape.

---

## Phase 1 — Performance SQLite (30 min, gain immédiat)

1. **Activer le mode WAL** dans `database.py` après la connexion
   - Écritures non bloquantes, lectures concurrentes
   - 3 lignes : `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`

2. **Ajouter les index manquants** dans `_init_schema()`
   - `idx_expenses_month`, `idx_expenses_cat`
   - `idx_revenues_month`, `idx_savings_month`
   - `idx_assets_period`, `idx_asset_tx_period`
   - Effet : requêtes 10-100× plus rapides quand l'historique grossit

3. **Vérifier les requêtes lentes** avec `EXPLAIN QUERY PLAN`
   - Repérer les `SCAN TABLE` restants
   - Ajouter index ciblés si besoin

---

## Phase 2 — Démarrage et navigation plus rapides (1-2h)

4. **Lazy-load des pages**
   - Ne créer chaque frame qu'à la première visite
   - Stocker dans un dict `self.pages = {}` peuplé à la demande
   - L'app démarre 2-3× plus vite

5. **Réutiliser les figures matplotlib**
   - `ax.clear()` au lieu de recréer `Figure` à chaque refresh
   - Une figure persistante par graphique
   - Refresh des graphiques 5× plus rapide

6. **Pagination de l'historique**
   - LIMIT/OFFSET ou tranche par année
   - Évite de charger 5 ans de données pour afficher 1 mois

---

## Phase 3 — Refactor architectural (2-4h, prépare le futur)

7. **Extraire un dossier `repositories/`**
   - Un fichier par entité : `expenses_repo.py`, `revenues_repo.py`, `assets_repo.py`, `savings_repo.py`, `budgets_repo.py`
   - Chaque repo expose : `list()`, `get()`, `add()`, `update()`, `delete()`
   - `database.py` devient juste la connexion + le schéma

8. **Créer des dataclasses pour les entités**
   - `models/expense.py`, `models/revenue.py`, etc.
   - Plus de `sqlite3.Row` qui traîne dans l'UI
   - Type hints partout, autocomplétion qui fonctionne

9. **Centraliser la couche service**
   - `services/budget_service.py`, `services/patrimoine_service.py`
   - La logique métier sort des fichiers UI
   - Cette étape est **clé** : elle rendra la migration cloud quasi triviale plus tard

---

## Phase 4 — Robustesse et qualité (1-2h)

10. **Ajouter un logger**
    - Module `logging` standard, rotation de fichier
    - Logs dans `~/.finance_tracker/logs/app.log`
    - Indispensable pour debug en prod

11. **Externaliser la config utilisateur**
    - Préférences UI, taux d'épargne cibles, seuils d'alerte
    - Fichier `~/.finance_tracker/config.json`
    - Aujourd'hui c'est dans `config.py` (code), il faudrait du paramétrable

12. **Backup automatique**
    - Copie de la base SQLite à chaque démarrage (rotation 7 jours)
    - Bouton "Restaurer" depuis Paramètres
    - Sécurité minimale avant tout passage cloud

---

## Phase 5 — Fonctionnel et UX (variable selon envies)

13. **Dashboard widgets configurables**
    - Drag & drop pour réorganiser les blocs
    - Choisir quels KPIs afficher

14. **Notifications / rappels**
    - "Tu n'as pas saisi le mois de mars"
    - Alerte budget dépassé
    - Toast natif Windows

15. **Import bancaire CSV**
    - Parser des relevés bancaires (BNP, Boursorama, Revolut)
    - Mapping auto vers catégories
    - Énorme gain de temps si tu saisis manuellement aujourd'hui

16. **Mode sombre / thèmes**
    - CustomTkinter le supporte nativement
    - 30 min de boulot

17. **Tests automatisés sur les repositories**
    - `pytest` + base SQLite en mémoire (`:memory:`)
    - Au minimum : add / update / delete / aggregations
    - Filet de sécurité pour les futurs refactors

---

## Phase 6 — Packaging et distribution (optionnel)

18. **Installateur Windows propre**
    - PyInstaller en mode `--onefile` ou Inno Setup
    - Icône, raccourci menu démarrer
    - Tu as déjà un dossier `build/`, donc tu y es presque

19. **Auto-update**
    - Vérifier une version GitHub Releases au démarrage
    - Téléchargement de la nouvelle version
    - Pas urgent tant que l'app tourne sur ton PC uniquement

---

## Phase 7 — [À ÉTUDIER] Base de données en ligne + mobile

À planifier après la Phase 3 (le refactor repository la rendra simple).

Pistes à comparer : **Turso** (SQLite cloud, migration triviale), **Supabase**
(Postgres + auth + API REST, idéal mobile), **PocketBase** (auto-hébergé,
ultra-léger). Décision à prendre selon : budget mobile (Flutter / React Native /
PWA), besoin multi-utilisateur, exigence d'auth.

---

## Ordre recommandé pour démarrer

**Aujourd'hui** : Phase 1 (1, 2, 3) — gros gain pour 30 min de boulot.
**Cette semaine** : Phase 2 (4, 5, 6).
**Ce mois** : Phase 3 (7, 8, 9) — la plus structurante.
**Quand tu veux** : Phases 4-6 selon priorités personnelles.
**Plus tard** : Phase 7 quand tu auras choisi ton stack mobile.
