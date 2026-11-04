"""
web — Interface web de Fintrack (FastAPI), conçue pour tourner en
conteneur Docker / Kubernetes.

Réutilise la couche de données de l'application desktop (database.py) et
la synchronisation Supabase (sync_supabase.py) : une base SQLite par
utilisateur dans le volume de données, synchronisée avec le même projet
Supabase que l'application desktop.
"""
