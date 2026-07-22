"""Acesso a settings.json e paths globais do HotmartFlow."""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CONFIG = RAIZ / "config"
PASTA_DATA = RAIZ / "data"
ARQUIVO_SETTINGS = PASTA_CONFIG / "settings.json"

_DEFAULTS = {
    "provider": "agy",  # "agy" (Antigravity CLI, igual EbookFlow) ou "openai"
    "agy": {"model": "Gemini 3.5 Flash (Low)"},  # mais barato/rapido p/ traduzir
    "openai": {"api_key": "", "model": "gpt-4o"},
    # tabela INTERNACIONAL (USD) — todos os países MENOS o Brasil
    "precos": {"Principal": 19.90, "Order Bump": 12.90, "Upsell": 15.90},
    # tabela do BRASIL (BRL) — separada; o Brasil NÃO puxa da internacional
    "precos_brasil": {"Principal": 19.90, "Order Bump": 12.90, "Upsell": 15.90},
    "moeda": "USD",
    "hotmart": {"categoria": "Espiritualidade", "reembolso_dias": 7},
    "coproducao": {"email": "", "percentual": 45},
    # 2º coprodutor (opcional) — convidado DEPOIS do 1º, com intervalo de 40s
    # pra não misturar os códigos 2FA no Gmail
    "coproducao2": {"email": "", "percentual": 45},
    # cupons automáticos no ebook PRINCIPAL — o robô cria CLICANDO na tela de
    # Cupons (a API é bugada). Cada cupom tem desconto por MOEDA: 'padrao' vale
    # pra USD e BRL; 'eur' vale pros países do euro.
    "cupons": [
        {"ativo": True, "codigo": "25OFF", "desconto_padrao": 25,    "desconto_eur": 25},
        {"ativo": True, "codigo": "35OFF", "desconto_padrao": 35.18, "desconto_eur": 40},
    ],
    # Leitura automatica do codigo 2FA no Gmail (IMAP + App Password)
    "gmail": {"email": "", "app_password": "", "auto": False},
    "descricao": {
        "tom": "inspirador, acolhedor e persuasivo",
        "tamanho_min": 400,
        "tamanho_max": 900,
    },
    "pastas_recentes": [],
    # quantas gerações/traduções rodam AO MESMO TEMPO no "Gerar e traduzir tudo"
    "traduzir_simultaneas": 15,
    # robo: ensaio = modo seguro; delay_digitacao_ms = ms por tecla (anti-bot Hotmart)
    "robo": {"ensaio": True, "delay_digitacao_ms": 45, "cdp_port": 9222, "alarme": True},
}


def carregar_settings() -> dict:
    if not ARQUIVO_SETTINGS.is_file():
        salvar_settings(_deep_copy(_DEFAULTS))
        return _deep_copy(_DEFAULTS)
    with open(ARQUIVO_SETTINGS, "r", encoding="utf-8") as f:
        dados = json.load(f)
    merged = _deep_copy(_DEFAULTS)
    for k, v in dados.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def salvar_settings(settings: dict) -> None:
    PASTA_CONFIG.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def _deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))
