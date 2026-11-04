"""
providers.py — Appels aux fournisseurs IA (Claude via le SDK Anthropic,
Gemini via google-genai). Clés serveur, jamais exposées au navigateur.

Claude : modèle par défaut claude-opus-5-5 (CLAUDE_MODEL pour changer),
pensée adaptative (toujours active sur ce modèle) dosée par `effort`,
replis serveur en cas de refus (`fallbacks: "default"`), invite système
mise en cache (préfixe stable), sorties structurées JSON pour la
catégorisation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ProviderError(RuntimeError):
    """Erreur présentable à l'utilisateur (sans détail technique sensible)."""


@dataclass
class ProviderConfig:
    anthropic_api_key: str
    gemini_api_key: str
    claude_model: str
    gemini_model: str

    def available(self) -> list[str]:
        out = []
        if self.anthropic_api_key:
            out.append("claude")
        if self.gemini_api_key:
            out.append("gemini")
        return out


class Providers:
    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self._anthropic = None
        self._gemini = None

    # ── Clients (créés à la demande, réutilisés) ─────────────
    def _claude(self):
        if not self.cfg.anthropic_api_key:
            raise ProviderError("Claude n'est pas configuré sur ce serveur.")
        if self._anthropic is None:
            import anthropic
            self._anthropic = anthropic.Anthropic(api_key=self.cfg.anthropic_api_key,
                                                  timeout=60.0, max_retries=2)
        return self._anthropic

    def _gem(self):
        if not self.cfg.gemini_api_key:
            raise ProviderError("Gemini n'est pas configuré sur ce serveur.")
        if self._gemini is None:
            from google import genai
            self._gemini = genai.Client(api_key=self.cfg.gemini_api_key)
        return self._gemini

    # ── Texte libre ──────────────────────────────────────────
    def complete(self, provider: str, system: str, messages: list[dict], *,
                 effort: str = "medium", max_tokens: int = 4000) -> str:
        if provider == "claude":
            return self._claude_text(system, messages, effort, max_tokens)
        if provider == "gemini":
            return self._gemini_text(system, messages, max_tokens)
        raise ProviderError("Fournisseur inconnu.")

    def _claude_text(self, system, messages, effort, max_tokens) -> str:
        import anthropic
        try:
            resp = self._claude().beta.messages.create(
                model=self.cfg.claude_model,
                max_tokens=max_tokens,
                betas=[CLAUDE_FALLBACK_BETA],
                fallbacks="default",
                # Préfixe stable (invite système) mis en cache ; le contexte
                # financier et la question, variables, viennent après.
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                output_config={"effort": effort},
                messages=messages,
            )
        except anthropic.RateLimitError as exc:
            raise ProviderError("Quota Claude atteint — réessayez dans un instant.") from exc
        except anthropic.APIStatusError as exc:
            log.warning("Claude HTTP %s (request_id=%s)", exc.status_code,
                        getattr(exc, "request_id", "?"))
            raise ProviderError("Claude est indisponible pour le moment.") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Claude est injoignable.") from exc
        if resp.stop_reason == "refusal":
            raise ProviderError("Claude a décliné cette demande.")
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text:
            raise ProviderError("Réponse vide de Claude.")
        return text

    def _gemini_text(self, system, messages, max_tokens) -> str:
        from google.genai import types
        contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                                  parts=[types.Part(text=m["content"])]) for m in messages]
        try:
            resp = self._gem().models.generate_content(
                model=self.cfg.gemini_model, contents=contents,
                config=types.GenerateContentConfig(system_instruction=system,
                                                   max_output_tokens=max_tokens),
            )
        except Exception as exc:     # le SDK google-genai n'expose pas de hiérarchie stable
            log.warning("Gemini en erreur : %s", exc.__class__.__name__)
            raise ProviderError("Gemini est indisponible pour le moment.") from exc
        text = (resp.text or "").strip()
        if not text:
            raise ProviderError("Réponse vide de Gemini.")
        return text

    # ── Choix contraint dans une liste (catégorisation) ──────
    def choose(self, provider: str, system: str, prompt: str, choices: list[str]) -> str:
        schema = {
            "type": "object",
            "properties": {"category": {"type": "string", "enum": choices}},
            "required": ["category"],
            "additionalProperties": False,
        }
        if provider == "claude":
            import anthropic
            try:
                resp = self._claude().beta.messages.create(
                    model=self.cfg.claude_model, max_tokens=1024,
                    betas=[CLAUDE_FALLBACK_BETA], fallbacks="default",
                    system=[{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}],
                    output_config={"effort": "low",
                                   "format": {"type": "json_schema", "schema": schema}},
                    messages=[{"role": "user", "content": prompt}],
                )
            except anthropic.APIError as exc:
                raise ProviderError("Claude est indisponible pour le moment.") from exc
            if resp.stop_reason == "refusal":
                raise ProviderError("Claude a décliné cette demande.")
            raw = next((b.text for b in resp.content if b.type == "text"), "{}")
        elif provider == "gemini":
            from google.genai import types
            try:
                resp = self._gem().models.generate_content(
                    model=self.cfg.gemini_model, contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system, max_output_tokens=256,
                        response_mime_type="application/json",
                        response_schema={"type": "OBJECT",
                                         "properties": {"category": {"type": "STRING",
                                                                     "enum": choices}},
                                         "required": ["category"]},
                    ),
                )
            except Exception as exc:
                raise ProviderError("Gemini est indisponible pour le moment.") from exc
            raw = resp.text or "{}"
        else:
            raise ProviderError("Fournisseur inconnu.")
        try:
            value = json.loads(raw).get("category", "")
        except (json.JSONDecodeError, AttributeError):
            value = ""
        if value not in choices:        # on ne fait jamais confiance à la sortie brute
            raise ProviderError("Catégorie non reconnue.")
        return value
