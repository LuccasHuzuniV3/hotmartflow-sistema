"""Testes da leitura automática do código 2FA no Gmail (IMAP mockado)."""
import pytest

from core import gmail_code


# ---------------------------------------------------------------------------
# extrair_codigo — parsing do corpo do e-mail
# ---------------------------------------------------------------------------
def test_extrai_codigo_perto_da_palavra_chave():
    assert gmail_code.extrair_codigo("Seu código de segurança é 203491.") == "203491"


def test_extrai_code_em_ingles():
    assert gmail_code.extrair_codigo("Your security code: 460098") == "460098"


def test_prefere_codigo_perto_de_palavra_chave_e_ignora_outros_numeros():
    txt = "Pedido 123456 confirmado. Sua chave de segurança é 654321. Ref 999999."
    assert gmail_code.extrair_codigo(txt) == "654321"


def test_sem_palavra_chave_pega_primeiro_6_digitos():
    assert gmail_code.extrair_codigo("Olá! 852147 é o que você precisa.") == "852147"


def test_ignora_numeros_com_mais_de_6_digitos():
    assert gmail_code.extrair_codigo("ID 12345678 sem código aqui") is None


def test_texto_vazio_retorna_none():
    assert gmail_code.extrair_codigo("") is None
    assert gmail_code.extrair_codigo(None) is None


# ---------------------------------------------------------------------------
# buscar_codigo — polling (fetch injetado, sem rede)
# ---------------------------------------------------------------------------
def test_buscar_codigo_acha_de_primeira():
    def fake_fetch(email, senha, desde):
        return ["código de segurança: 111222"]

    cod = gmail_code.buscar_codigo("x@gmail.com", "senha", timeout=1, intervalo=0, fetch=fake_fetch)
    assert cod == "111222"


def test_buscar_codigo_espera_email_chegar():
    chamadas = {"n": 0}

    def fake_fetch(email, senha, desde):
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            return []  # ainda nao chegou
        return ["seu código é 333444"]

    cod = gmail_code.buscar_codigo("x@gmail.com", "senha", timeout=5, intervalo=0, fetch=fake_fetch)
    assert cod == "333444"
    assert chamadas["n"] >= 3


def test_buscar_codigo_timeout_retorna_none():
    cod = gmail_code.buscar_codigo("x@gmail.com", "senha", timeout=0, intervalo=0,
                                   fetch=lambda e, s, d: [])
    assert cod is None


def test_buscar_codigo_sem_credenciais_erro():
    with pytest.raises(gmail_code.GmailError):
        gmail_code.buscar_codigo("", "", timeout=1, intervalo=0, fetch=lambda e, s, d: [])
