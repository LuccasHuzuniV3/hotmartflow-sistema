"""Testes da geracao de descricao e traducao (LLM mockado — nenhum teste bate na rede)."""
import pytest

from core import textos


# ---------------------------------------------------------------------------
# Geracao de descricao (PT)
# ---------------------------------------------------------------------------
def test_gerar_descricao_retorna_texto_limpo(monkeypatch):
    capturado = {}

    def fake_gerar(provider, api_key, model, system, prompt, **kw):
        capturado["provider"] = provider
        capturado["prompt"] = prompt
        return "  Uma descricao vendedora.\n\nCom dois paragrafos.  "

    monkeypatch.setattr(textos.llm, "gerar", fake_gerar)
    out = textos.gerar_descricao("agy", "", "", titulo="Meu Ebook", tipo="Principal")
    assert out == "Uma descricao vendedora.\n\nCom dois paragrafos."
    assert "Meu Ebook" in capturado["prompt"]
    assert capturado["provider"] == "agy"


def test_gerar_descricao_titulo_vazio_levanta_erro():
    with pytest.raises(textos.TextosError):
        textos.gerar_descricao("agy", "", "", titulo="   ", tipo="Principal")


def test_gerar_descricao_resposta_vazia_levanta_erro(monkeypatch):
    monkeypatch.setattr(textos.llm, "gerar", lambda *a, **kw: "   ")
    with pytest.raises(textos.TextosError):
        textos.gerar_descricao("agy", "", "", titulo="Meu Ebook", tipo="Principal")


# ---------------------------------------------------------------------------
# Traducao (titulo + descricao em 1 chamada, JSON in/out)
# ---------------------------------------------------------------------------
def test_traduzir_parseia_json_da_resposta(monkeypatch):
    capturado = {}

    def fake_gerar(provider, api_key, model, system, prompt, **kw):
        capturado["prompt"] = prompt
        return '{"titulo": "Ang Aking Ebook", "descricao": "Isang paglalarawan"}'

    monkeypatch.setattr(textos.llm, "gerar", fake_gerar)
    out = textos.traduzir_textos("agy", "", "", "Meu Ebook", "Uma descricao", "fil")
    assert out == {"titulo": "Ang Aking Ebook", "descricao": "Isang paglalarawan"}
    # o prompt precisa indicar o idioma destino por extenso
    assert "tagalog" in capturado["prompt"].lower()


def test_traduzir_aceita_json_com_cercas_de_codigo(monkeypatch):
    resposta = '```json\n{"titulo": "T", "descricao": "D"}\n```'
    monkeypatch.setattr(textos.llm, "gerar", lambda *a, **kw: resposta)
    out = textos.traduzir_textos("agy", "", "", "Titulo", "Desc", "en")
    assert out == {"titulo": "T", "descricao": "D"}


def test_traduzir_resposta_sem_json_levanta_erro(monkeypatch):
    monkeypatch.setattr(textos.llm, "gerar", lambda *a, **kw: "desculpa, nao consegui")
    with pytest.raises(textos.TextosError):
        textos.traduzir_textos("agy", "", "", "Titulo", "Desc", "en")


def test_traduzir_json_sem_chaves_obrigatorias_levanta_erro(monkeypatch):
    monkeypatch.setattr(textos.llm, "gerar", lambda *a, **kw: '{"outra_coisa": 1}')
    with pytest.raises(textos.TextosError):
        textos.traduzir_textos("agy", "", "", "Titulo", "Desc", "en")


def test_traduzir_para_ptbr_retorna_original_sem_chamar_llm(monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("nao deveria chamar o LLM pra pt-br")

    monkeypatch.setattr(textos.llm, "gerar", explode)
    out = textos.traduzir_textos("agy", "", "", "Meu Ebook", "Minha desc", "pt-br")
    assert out == {"titulo": "Meu Ebook", "descricao": "Minha desc"}


def test_traduzir_idioma_desconhecido_levanta_erro():
    with pytest.raises(textos.TextosError):
        textos.traduzir_textos("agy", "", "", "T", "D", "klingon")


def test_traduzir_descricao_vazia_levanta_erro():
    with pytest.raises(textos.TextosError):
        textos.traduzir_textos("agy", "", "", "Titulo", "", "en")
