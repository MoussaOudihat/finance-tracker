"""
fintrack_common — code partagé par les microservices Fintrack :
configuration, logs JSON, vérification des jetons Supabase, authentification
inter-services, middlewares HTTP (request-id, en-têtes de sécurité).
"""
__all__ = ["config", "logs", "auth", "http"]
