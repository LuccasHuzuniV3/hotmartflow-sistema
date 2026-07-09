"""Testes do roteador de LLM (dispatch por provider — nada bate na rede)."""
import pytest

from core import agy, llm


def test_dispatch_agy(monkeypatch):
    capturado = {}

    def fake(system, prompt, model):
        capturado.update(system=system, prompt=prompt, model=model)
        return "resposta do agy"

    monkeypatch.setattr(agy, "gerar", fake)
    out = llm.gerar("agy", "", "modelo-x", "voce e tradutor", "traduza isso")
    assert out == "resposta do agy"
    assert capturado["system"] == "voce e tradutor"
    assert capturado["model"] == "modelo-x"


def test_provider_padrao_vazio_cai_no_agy(monkeypatch):
    monkeypatch.setattr(agy, "gerar", lambda *a, **kw: "ok")
    assert llm.gerar("", "", "", "s", "p") == "ok"
    assert llm.gerar(None, "", "", "s", "p") == "ok"


def test_openai_sem_key_levanta_erro():
    with pytest.raises(llm.LLMError):
        llm.gerar("openai", "", "gpt-4o", "s", "p")


def test_provider_desconhecido_levanta_erro():
    with pytest.raises(llm.LLMError):
        llm.gerar("banana", "", "", "s", "p")
