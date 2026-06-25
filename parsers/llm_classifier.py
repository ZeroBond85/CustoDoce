"""
Classificador LLM via Groq API.
Usa llama-3.1-8b-instant (grátis, 14k req/dia).
Fallback silencioso se chave não configurada ou erro.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_CLASSIFICATION_PROMPT = """
Classifique o produto em UM dos ingredientes abaixo.
Responda APENAS JSON válido: {"ingredient": "NOME EXATO", "confidence": 0-1, "reason": "breve motivo"}
Se nenhum ingrediente encaixar, retorne: {"ingredient": null, "confidence": 0, "reason": "Nenhum ingrediente corresponde"}

PRODUTO: "{product_text}"
INGREDIENTES DISPONÍVEIS: {ingredients_list}
"""

class LLMClassifier:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
        return self._client

    def classify_sync(self, product_text: str, candidates: list[dict]) -> Optional[dict]:
        """Classifica produto vs candidatos. Retorna dict ou None."""
        client = self._get_client()
        if not client:
            logger.debug("LLMClassifier: GROQ_API_KEY não configurada")
            return None

        ing_list = "\n".join([f"- {c['canonical_name']} (alias: {', '.join(c.get('aliases',[]))})" for c in candidates])
        prompt = _CLASSIFICATION_PROMPT.format(
            product_text=product_text,
            ingredients_list=ing_list,
        )

        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=150,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip() if response.choices else ""
            result = json.loads(raw)
            return result
        except Exception as e:
            logger.warning(f"LLMClassifier error: {e}")
            return None

