"""Geracao da descricao de venda (PT) e traducao de titulo+descricao por idioma.

Traducao no padrao batch do EbookFlow: 1 chamada por idioma, JSON in/out,
com parsing defensivo (LLM as vezes devolve cercas de codigo em volta).
"""
from __future__ import annotations

import json
import re

from core import idiomas, llm


class TextosError(Exception):
    pass


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_COPYWRITER = (
    "Voce e um copywriter senior especializado em paginas de venda de infoprodutos "
    "(ebooks) na Hotmart. Escreve descricoes persuasivas, claras e honestas. "
    "Responde APENAS com o texto pedido, sem comentarios nem markdown de titulos."
)

PROMPT_DESCRICAO = """Escreva a DESCRICAO DE VENDA de um ebook para a pagina de produto da Hotmart.

DADOS DO PRODUTO:
- Titulo: {titulo}
- Papel na esteira de vendas: {tipo}
- Tom desejado: {tom}

REGRAS:
1. Escreva em portugues do Brasil (a traducao e feita depois, em outra etapa).
2. Entre {tamanho_min} e {tamanho_max} caracteres.
3. Estrutura: gancho inicial (dor/desejo do leitor) -> o que a pessoa vai encontrar/aprender -> beneficios concretos -> chamada final pra acao.
4. Paragrafos curtos. Pode usar ate 4 bullets simples (comecando com "- ") na parte do conteudo.
5. NAO invente numeros de paginas, capitulos, bonus ou garantias que nao foram informados.
6. NAO use emojis, hashtags, CAIXA ALTA em frases inteiras, nem headers de markdown (#).
7. Responda APENAS com a descricao, sem titulo, sem comentarios.

DESCRICAO:"""

SYSTEM_TRADUTOR = (
    "Voce e um tradutor profissional especializado em marketing de infoprodutos. "
    "Responde apenas com o JSON pedido, sem comentarios nem cercas de codigo."
)

PROMPT_TRADUCAO = """Traduza o titulo e a descricao de venda de um ebook do portugues do Brasil para {nome_idioma}.

REGRAS CRITICAS:
1. Tom de COPY DE VENDA: adapte expressoes idiomaticas pra soar natural e persuasivo no idioma destino — NAO traduza literal.
2. PRESERVE a estrutura da descricao: paragrafos, quebras de linha e bullets ("- ") nos mesmos lugares.
3. NAO traduza nomes proprios de pessoas ou marcas.
4. NAO adicione nem omita informacao.
5. RESPOSTA: APENAS um objeto JSON valido com EXATAMENTE as chaves "titulo" e "descricao". Sem texto fora do JSON, sem comentarios, sem cercas de codigo. Comece com {{ e termine com }}.
6. Escape corretamente aspas duplas (\\") e quebras de linha (\\n) dentro dos strings JSON.

INPUT (traduza este JSON):
{json_entrada}"""


# ---------------------------------------------------------------------------
# Parsing defensivo de JSON vindo do LLM
# ---------------------------------------------------------------------------
def _safe_json_loads(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        raw = raw.strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise TextosError(f"Resposta do LLM sem JSON: {raw[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise TextosError(f"JSON invalido na resposta do LLM: {e}") from e


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def gerar_descricao(provider: str, api_key: str, model: str, *, titulo: str, tipo: str,
                    tom: str = "inspirador, acolhedor e persuasivo",
                    tamanho_min: int = 400, tamanho_max: int = 900) -> str:
    """Gera a descricao de venda em PT a partir do titulo e do tipo do produto."""
    if not (titulo or "").strip():
        raise TextosError("Titulo vazio — preencha o titulo antes de gerar a descricao.")

    prompt = PROMPT_DESCRICAO.format(
        titulo=titulo.strip(),
        tipo=tipo or "Principal",
        tom=tom,
        tamanho_min=tamanho_min,
        tamanho_max=tamanho_max,
    )
    try:
        resposta = llm.gerar(provider, api_key, model, SYSTEM_COPYWRITER, prompt, temperature=0.8)
    except llm.LLMError as e:
        raise TextosError(str(e)) from e

    descricao = (resposta or "").strip()
    if not descricao:
        raise TextosError("O LLM retornou uma descricao vazia. Tente de novo.")
    return descricao


def traduzir_textos(provider: str, api_key: str, model: str, titulo: str, descricao: str,
                    codigo_idioma: str) -> dict:
    """Traduz titulo+descricao pra um idioma em 1 chamada. Retorna {titulo, descricao}."""
    if not (descricao or "").strip():
        raise TextosError("Descricao vazia — gere ou escreva a descricao em PT antes de traduzir.")
    if not (titulo or "").strip():
        raise TextosError("Titulo vazio — preencha o titulo antes de traduzir.")

    if codigo_idioma == "pt-br":
        return {"titulo": titulo.strip(), "descricao": descricao.strip()}

    info = idiomas.por_codigo(codigo_idioma)
    if info is None:
        raise TextosError(f"Idioma desconhecido: '{codigo_idioma}'")

    json_entrada = json.dumps(
        {"titulo": titulo.strip(), "descricao": descricao.strip()},
        ensure_ascii=False, indent=2,
    )
    prompt = PROMPT_TRADUCAO.format(nome_idioma=info["nome_idioma"], json_entrada=json_entrada)

    try:
        raw = llm.gerar(provider, api_key, model, SYSTEM_TRADUTOR, prompt, temperature=0.3)
    except llm.LLMError as e:
        raise TextosError(str(e)) from e

    dados = _safe_json_loads(raw)
    titulo_tr = str(dados.get("titulo") or "").strip()
    descricao_tr = str(dados.get("descricao") or "").strip()
    if not titulo_tr or not descricao_tr:
        raise TextosError(
            f"Traducao incompleta pra '{info['pais']}' — chaves recebidas: {list(dados.keys())}"
        )
    return {"titulo": titulo_tr, "descricao": descricao_tr}
