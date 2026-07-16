"""Testes do settings.json (defaults, merge, tabela de precos)."""
import json

import pytest

from core import config


@pytest.fixture(autouse=True)
def settings_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARQUIVO_SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(config, "PASTA_CONFIG", tmp_path)
    return tmp_path


def test_carregar_cria_defaults_na_primeira_vez():
    s = config.carregar_settings()
    assert s["openai"]["model"]
    assert config.ARQUIVO_SETTINGS.is_file()


def test_provider_padrao_e_agy():
    s = config.carregar_settings()
    assert s["provider"] == "agy"
    assert s["agy"]["model"] == "Gemini 3.5 Flash (Low)"  # mais barato p/ traduzir


def test_robo_comeca_em_modo_ensaio():
    s = config.carregar_settings()
    assert s["robo"]["ensaio"] is True


def test_default_tem_pastas_recentes_vazia():
    s = config.carregar_settings()
    assert s["pastas_recentes"] == []


def test_tabela_de_precos_padrao():
    s = config.carregar_settings()
    assert s["precos"]["Principal"] == 19.90
    assert s["precos"]["Order Bump"] == 12.90
    assert s["precos"]["Upsell"] == 15.90


def test_tem_tabela_de_precos_do_brasil_separada():
    s = config.carregar_settings()
    assert s["precos_brasil"]["Principal"] == 19.90
    assert s["precos_brasil"]["Order Bump"] == 12.90


def test_tem_segundo_coprodutor_e_cupom_nos_defaults():
    s = config.carregar_settings()
    assert s["coproducao2"] == {"email": "", "percentual": 45}
    assert s["cupom"]["ativo"] is False          # desligado por padrao
    assert s["cupom"]["desconto"] == 10
    assert s["hotmart_api"] == {"client_id": "", "client_secret": ""}


def test_salvar_e_recarregar_preserva_valores():
    s = config.carregar_settings()
    s["openai"]["api_key"] = "sk-teste"
    s["precos"]["Principal"] = 29.90
    config.salvar_settings(s)
    s2 = config.carregar_settings()
    assert s2["openai"]["api_key"] == "sk-teste"
    assert s2["precos"]["Principal"] == 29.90


def test_merge_preenche_chaves_novas_sem_perder_as_do_usuario():
    # simula settings antigo sem a chave "coproducao"
    config.ARQUIVO_SETTINGS.write_text(
        json.dumps({"openai": {"api_key": "sk-velho"}}), encoding="utf-8"
    )
    s = config.carregar_settings()
    assert s["openai"]["api_key"] == "sk-velho"     # preservou
    assert "coproducao" in s                        # completou com default
    assert "precos" in s
