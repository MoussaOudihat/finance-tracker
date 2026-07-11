"""
utils_ai.py — Intégration IA (Google Gemini — free tier AI Studio)

Stratégie d'économie de tokens :
  • Prompts système ultra-compacts (~40 tokens chacun)
  • Templates utilisateur condensés (~35 tokens hors données)
  • Résumé financier CSV-like (~120-160 tokens)
  • thinking_budget=0  → désactive le raisonnement interne de Gemini 2.5 Flash
  • max_output_tokens=500  (conseils concis, suffisants)
  • Cache DB par période — zéro appel automatique
"""
import datetime

# Modèle par défaut — gemini-2.5-flash-lite privilégié (plus économe sur free tier)
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",   # léger, idéal free tier
    "gemini-2.5-flash",        # fallback si lite indisponible
    "gemini-1.5-flash",        # fallback ultime
]
GEMINI_MODEL = GEMINI_MODELS[0]

# ─────────────────────────────────────────────────────────────
#  Prompts compacts
# ─────────────────────────────────────────────────────────────

# ~45 tokens — couvre l'essentiel sans répétition
_SYSTEM_PROMPT = """\
Conseiller financier français (PEA, Livret A, assurance-vie, flat tax 30%, ETF/DCA).
Réponds en français. Cite les chiffres fournis. Conseils concrets et chiffrés, pas de généralités.
Structure : 3 sections titrées courtes + 1 action prioritaire finale.\
"""

# ~40 tokens hors données
_USER_TEMPLATE = """\
{nb_months} mois de données financières :{context_block}
{summary}

Fournis : diagnostic 2 phrases | 2-3 points forts | 2-3 problèmes + actions chiffrées | 1 action cette semaine.\
"""

# ~42 tokens hors données
_USER_TEMPLATE_1M = """\
Données du mois :{context_block}
{summary}

Fournis : commentaire conso (notable/raisonnable) | 2-3 économies possibles (montants précis, exemples locaux) | bilan rev/dep | 1 action cette semaine.\
"""

# ~40 tokens hors données
_PROJECTION_SYSTEM_PROMPT = """\
Expert patrimoine français (PEA, AV, SCPI, ETF, flat tax, retraite, intérêts composés).
Réponds en français. Cite les chiffres. Avis critique + pistes concrètes.
Structure : 3 sections courtes + 1 action prioritaire.\
"""

# ~50 tokens hors données — données en format compact clé=valeur
_PROJECTION_USER_TEMPLATE = """\
Scénario patrimoine :{context_block}
pat={patrimoine_actuel:.0f}€ | épargne={epargne_mensuelle:.0f}€/m | taux={taux:.1f}% | inf={inflation:.1f}% | horizon={horizon}a
→ projeté={patrimoine_projete:.0f}€ | réel={valeur_reelle:.0f}€ | gain_composé={gain_compose:.0f}€ | versé_total={epargne_totale:.0f}€

Fournis : réalisme du taux + cohérence | 2-3 leviers optimisation (véhicule, fiscalité) | 2 risques à anticiper | 1 action maintenant.\
"""


# ─────────────────────────────────────────────────────────────
#  Résumé financier compact (format CSV-like, ~120-160 tokens)
# ─────────────────────────────────────────────────────────────
def build_financial_summary(db, nb_months: int) -> str:
    """
    Résumé compact pour l'IA — format clé:valeur / CSV-like.
    Cible : ~120-160 tokens (vs 300-400 avant optimisation).
    """
    summary = db.monthly_summary(nb_months)
    if not summary:
        return ""

    summary_asc = list(reversed(summary))
    all_assets  = db.get_assets_current()
    nb          = len(summary_asc)

    avg_rev = sum(r["rev"] for r in summary_asc) / nb
    avg_exp = sum(r["exp"] for r in summary_asc) / nb
    avg_sav = sum(r["sav"] for r in summary_asc) / nb
    sav_rate   = avg_sav / avg_rev * 100 if avg_rev > 0 else 0
    balance    = avg_rev - avg_exp
    neg_months = sum(1 for m in summary_asc if m["rev"] - m["exp"] < 0)

    lines = []

    # ── Flux (1 ligne par valeur — format compact) ────────────
    lines.append(f"rev={avg_rev:.0f}€ dep={avg_exp:.0f}€ epargne={avg_sav:.0f}€({sav_rate:.0f}%) solde={balance:+.0f}€")
    if neg_months:
        lines.append(f"deficit:{neg_months}/{nb}mois")

    # ── Tendance dépenses ─────────────────────────────────────
    if nb >= 3:
        first_exp = summary_asc[0]["exp"]
        last_exp  = summary_asc[-1]["exp"]
        if first_exp > 0:
            trend = (last_exp - first_exp) / first_exp * 100
            lines.append(f"tendance_dep:{trend:+.0f}%")

    # ── Top-3 catégories (pas 5 — économie tokens) ───────────
    periods  = [(m["year"], m["month"]) for m in summary_asc]
    cat_rows = db.get_expenses_by_category_range(periods)
    if cat_rows:
        top3 = sorted(cat_rows, key=lambda r: -float(r["total"]))[:3]
        cats = " | ".join(
            f"{r['name']}={float(r['total'])/nb:.0f}€/m"
            for r in top3
        )
        lines.append(f"top_dep: {cats}")

    # ── Patrimoine (compact) ──────────────────────────────────
    if all_assets:
        total_pat = sum(a["value"] for a in all_assets)
        by_type: dict = {}
        for a in all_assets:
            by_type[a["asset_type"]] = by_type.get(a["asset_type"], 0.0) + a["value"]

        pat_parts = " | ".join(
            f"{t}={v:.0f}€" for t, v in sorted(by_type.items(), key=lambda x: -x[1])
        )
        lines.append(f"patrimoine={total_pat:.0f}€ ({pat_parts})")

        liq = by_type.get("compte", 0.0)
        if avg_exp > 0:
            lines.append(f"liquidites={liq/avg_exp:.1f}mois_dep")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  Helper — appel Gemini (partagé par toutes les fonctions IA)
# ─────────────────────────────────────────────────────────────
def _call_gemini(api_key: str, system: str, prompt: str) -> tuple[bool, str]:
    """Appel bas niveau Gemini. Retourne (success, texte)."""
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        return False, "Package manquant. Exécutez : python -m pip install google-genai"

    try:
        client = genai.Client(api_key=api_key.strip() or None)

        # thinking_budget=0 — désactive le raisonnement interne de Gemini 2.5
        # (les tokens de thinking ne sont pas visibles mais consomment du quota)
        try:
            cfg = genai_types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=500,
                temperature=0.35,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            )
        except Exception:
            # Fallback : ThinkingConfig peut ne pas exister sur les vieilles versions SDK
            cfg = genai_types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=500,
                temperature=0.35,
            )

        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=cfg,
        )
        return True, resp.text

    except Exception as exc:
        return False, f"Erreur Gemini : {exc}"


# ─────────────────────────────────────────────────────────────
#  Recommandations financières
# ─────────────────────────────────────────────────────────────
def get_ai_recommendations(
    financial_summary: str,
    nb_months: int,
    provider: str = "gemini",
    api_key: str = "",
    user_context: str = "",
) -> tuple[bool, str]:
    """Retourne (success, texte). Cible ~200-220 tokens input."""
    if not financial_summary.strip():
        return False, "Pas assez de données pour l'analyse IA."

    context_block = f" profil={user_context.strip()} |" if user_context.strip() else ""

    if nb_months == 1:
        prompt = _USER_TEMPLATE_1M.format(
            summary=financial_summary,
            context_block=context_block,
        )
    else:
        prompt = _USER_TEMPLATE.format(
            nb_months=nb_months,
            summary=financial_summary,
            context_block=context_block,
        )

    return _call_gemini(api_key, _SYSTEM_PROMPT, prompt)


# ─────────────────────────────────────────────────────────────
#  Analyse de scénario de projection
# ─────────────────────────────────────────────────────────────
def get_projection_advice(
    patrimoine_actuel: float,
    epargne_mensuelle: float,
    taux: float,
    inflation: float,
    horizon: int,
    patrimoine_projete: float,
    valeur_reelle: float,
    gain_compose: float,
    api_key: str,
    user_context: str = "",
) -> tuple[bool, str]:
    """Retourne (success, texte). Cible ~130 tokens input."""
    context_block = f" profil={user_context.strip()} |" if user_context.strip() else ""
    epargne_totale = epargne_mensuelle * horizon * 12

    prompt = _PROJECTION_USER_TEMPLATE.format(
        patrimoine_actuel=patrimoine_actuel,
        epargne_mensuelle=epargne_mensuelle,
        taux=taux,
        inflation=inflation,
        horizon=horizon,
        patrimoine_projete=patrimoine_projete,
        valeur_reelle=valeur_reelle,
        gain_compose=gain_compose,
        epargne_totale=epargne_totale,
        context_block=context_block,
    )

    return _call_gemini(api_key, _PROJECTION_SYSTEM_PROMPT, prompt)


# ─────────────────────────────────────────────────────────────
#  Cache DB — 1 résultat stocké par période
# ─────────────────────────────────────────────────────────────
def _cache_key_result(nb_months: int) -> str:
    return f"ai_cache_{nb_months}m_result"


def _cache_key_ts(nb_months: int) -> str:
    return f"ai_cache_{nb_months}m_ts"


def load_cached_result(db, nb_months: int) -> tuple[str | None, str | None]:
    """Retourne (texte_résultat, timestamp_str) ou (None, None)."""
    result = db.get_setting(_cache_key_result(nb_months), "")
    ts     = db.get_setting(_cache_key_ts(nb_months), "")
    if result and ts:
        return result, ts
    return None, None


def save_cached_result(db, nb_months: int, text: str):
    ts = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")
    db.set_setting(_cache_key_result(nb_months), text)
    db.set_setting(_cache_key_ts(nb_months), ts)


def clear_cached_result(db, nb_months: int):
    db.set_setting(_cache_key_result(nb_months), "")
    db.set_setting(_cache_key_ts(nb_months), "")


# ─────────────────────────────────────────────────────────────
#  Configuration IA
# ─────────────────────────────────────────────────────────────
def get_ai_config(db) -> tuple[bool, str, str]:
    """
    Retourne (configured, provider, api_key).
    Lit la clé depuis le trousseau OS en priorité (migration auto depuis DB).
    """
    from secrets_vault import get_secret
    # Trousseau OS en priorité, fallback DB pour les vieilles configs
    api_key  = get_secret("ai_api_key") or db.get_setting("ai_api_key", "")
    provider = db.get_setting("ai_provider", "gemini") or "gemini"
    return bool(api_key), provider, api_key
