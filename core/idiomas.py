"""Catalogo de idiomas/paises suportados.

Mesma lista e nomenclatura do EbookFlow (que gera os PDFs) — os nomes de pais
aqui sao o CONTRATO com a convencao de arquivos 'Titulo - Tipo - Pais.pdf'.
"""
from __future__ import annotations

import unicodedata
from typing import Optional

IDIOMAS = [
    {"codigo": "pt-br", "pais": "Brasil",     "nome_idioma": "portugues do Brasil"},
    {"codigo": "en",    "pais": "Ingles",     "nome_idioma": "ingles"},
    {"codigo": "es",    "pais": "Espanha",    "nome_idioma": "espanhol"},
    {"codigo": "fr",    "pais": "Franca",     "nome_idioma": "frances"},
    {"codigo": "de",    "pais": "Alemao",     "nome_idioma": "alemao"},
    {"codigo": "it",    "pais": "Italia",     "nome_idioma": "italiano"},
    {"codigo": "nl",    "pais": "Holanda",    "nome_idioma": "holandes (neerlandes)"},
    {"codigo": "sv",    "pais": "Suecia",     "nome_idioma": "sueco"},
    {"codigo": "fi",    "pais": "Finlandia",  "nome_idioma": "finlandes"},
    {"codigo": "pl",    "pais": "Polonia",    "nome_idioma": "polones"},
    {"codigo": "cs",    "pais": "Rep Checa",  "nome_idioma": "tcheco"},
    {"codigo": "sk",    "pais": "Eslovaquia", "nome_idioma": "eslovaco"},
    {"codigo": "sl",    "pais": "Eslovenia",  "nome_idioma": "esloveno"},
    {"codigo": "hu",    "pais": "Hungria",    "nome_idioma": "hungaro"},
    {"codigo": "ro",    "pais": "Romenia",    "nome_idioma": "romeno"},
    {"codigo": "bg",    "pais": "Bulgaria",   "nome_idioma": "bulgaro"},
    {"codigo": "hr",    "pais": "Croacia",    "nome_idioma": "croata"},
    {"codigo": "sr",    "pais": "Servia",     "nome_idioma": "servio (alfabeto latino)"},
    {"codigo": "el",    "pais": "Grecia",     "nome_idioma": "grego"},
    {"codigo": "fil",   "pais": "Filipinas",  "nome_idioma": "filipino (tagalog)"},
    {"codigo": "ru",    "pais": "Russia",       "nome_idioma": "russo"},
    {"codigo": "ko",    "pais": "Coreia do Sul", "nome_idioma": "coreano"},
]

_ORDEM = {info["codigo"]: n for n, info in enumerate(IDIOMAS)}

# Apelidos: nomes de pasta que diferem do nome canonico acima.
# (ex.: a pasta chama "ALEMANHA", mas internamente o pais e "Alemao").
_ALIASES = {
    "alemanha": "de",
    "estados unidos": "en",
    "eua": "en",
    "russia": "ru",
    "russo": "ru",
    "coreia": "ko",
    "coreia do sul": "ko",
    "republica tcheca": "cs",
    "republica checa": "cs",
    "tcheca": "cs",
    "chequia": "cs",
}


def normalizar(texto: str) -> str:
    """Remove acentos, baixa caixa e apara espacos — pra comparacao tolerante."""
    nfkd = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.strip().lower()


def por_pais(nome: str) -> Optional[dict]:
    alvo = normalizar(nome)
    for info in IDIOMAS:
        if normalizar(info["pais"]) == alvo:
            return info
    cod = _ALIASES.get(alvo)  # tenta apelido (ex.: "alemanha" -> de)
    if cod:
        return por_codigo(cod)
    return None


def por_codigo(codigo: str) -> Optional[dict]:
    for info in IDIOMAS:
        if info["codigo"] == codigo:
            return info
    return None


def ordem(codigo: str) -> int:
    """Posicao do idioma na lista canonica (desconhecidos vao pro final)."""
    return _ORDEM.get(codigo, len(IDIOMAS))
