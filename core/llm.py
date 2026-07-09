"""Roteador de LLM — despacha pro provider configurado.

Providers:
  - "agy"    (padrao): Antigravity CLI, conta Google — igual ao EbookFlow.
  - "openai": API da OpenAI (paga por uso), fallback pra quem nao tem agy.
"""
from __future__ import annotations


class LLMError(Exception):
    pass


def gerar(provider: str, api_key: str, model: str, system: str, prompt: str,
          temperature: float = 0.7) -> str:
    """Chama o LLM do provider e retorna o texto da resposta."""
    p = (provider or "agy").strip().lower()

    if p == "agy":
        from core import agy  # import tardio evita ciclo (agy usa LLMError daqui)
        return agy.gerar(system, prompt, model)

    if p == "openai":
        return _gerar_openai(api_key, model, system, prompt, temperature)

    raise LLMError(f"Provider desconhecido: '{provider}' (use 'agy' ou 'openai')")


def _gerar_openai(api_key: str, model: str, system: str, prompt: str,
                  temperature: float) -> str:
    if not (api_key or "").strip():
        raise LLMError("API key da OpenAI nao configurada. Cole a chave na aba Config.")

    from openai import OpenAI  # import tardio: nao trava testes/startup sem a lib

    try:
        cliente = OpenAI(api_key=api_key)
        resp = cliente.chat.completions.create(
            model=model or "gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
    except Exception as e:  # rede, auth, quota — vira erro legivel pro usuario
        raise LLMError(f"Erro chamando a OpenAI: {e}") from e

    texto = (resp.choices[0].message.content or "").strip()
    if not texto:
        raise LLMError("A OpenAI retornou resposta vazia. Tente de novo.")
    return texto
