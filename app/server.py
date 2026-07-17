"""API do HotmartFlow — FastAPI servindo a UI estatica + endpoints da fila de publicacao."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import agy, config, dialogo, historico, hotmart_api, idiomas, produtos, robo, scanner, textos, titulos, updater

PASTA_WEB = Path(__file__).resolve().parent / "web"

app = FastAPI(title="HotmartFlow", docs_url=None, redoc_url=None)


@app.middleware("http")
async def sem_cache(request, call_next):
    """App local, arquivos mudam a cada versao — navegador NUNCA deve cachear."""
    resposta = await call_next(request)
    resposta.headers["Cache-Control"] = "no-store, must-revalidate"
    return resposta


# ---------------------------------------------------------------------------
# Modelos de entrada
# ---------------------------------------------------------------------------
class ScanIn(BaseModel):
    pasta: str


class GrupoRef(BaseModel):
    titulo: str
    tipo: str


class ImportarIn(BaseModel):
    pasta: str
    grupos: Optional[list[GrupoRef]] = None  # None = importa todos os detectados


class ProdutoPatchIn(BaseModel):
    titulo_pt: Optional[str] = None
    descricao_pt: Optional[str] = None


class ItemPatchIn(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    preco: Optional[float] = None
    status: Optional[str] = None


class PublicarIn(BaseModel):
    modo: str = "ensaio"  # "real" | "ensaio" | "simulado"


class CodigoIn(BaseModel):
    codigo: str


class TitulosIn(BaseModel):
    texto: str
    pasta: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _erro(msg: str, codigo: int = 400):
    raise HTTPException(status_code=codigo, detail=msg)


def _llm_cfg() -> tuple[str, str, str]:
    """Retorna (provider, api_key, model) conforme o provider configurado."""
    s = config.carregar_settings()
    provider = s.get("provider", "agy")
    if provider == "openai":
        return provider, s["openai"]["api_key"], s["openai"]["model"]
    return provider, "", s.get("agy", {}).get("model", "")


def _patch_sem_nones(modelo: BaseModel) -> dict:
    return {k: v for k, v in modelo.model_dump().items() if v is not None}


# ---------------------------------------------------------------------------
# UI estatica
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(PASTA_WEB / "index.html")


app.mount("/static", StaticFiles(directory=str(PASTA_WEB)), name="static")


# ---------------------------------------------------------------------------
# Status / settings / idiomas
# ---------------------------------------------------------------------------
@app.get("/api/status")
def status():
    s = config.carregar_settings()
    provider = s.get("provider", "agy")
    if provider == "agy":
        diag = agy.diagnostico()
        detalhe = diag["detalhe"] if not diag["disponivel"] else diag["tipo"]
        return {"ok": True, "provider": provider,
                "pronto": diag["disponivel"], "detalhe": detalhe}
    pronto = bool(s["openai"]["api_key"].strip())
    return {"ok": True, "provider": provider, "pronto": pronto,
            "detalhe": "" if pronto else "API key nao configurada"}


@app.get("/api/settings")
def settings_obter():
    return config.carregar_settings()


@app.post("/api/settings")
def settings_salvar(body: dict):
    atual = config.carregar_settings()
    for k, v in body.items():
        if isinstance(v, dict) and isinstance(atual.get(k), dict):
            atual[k] = {**atual[k], **v}
        else:
            atual[k] = v
    config.salvar_settings(atual)
    return atual


@app.post("/api/hotmart-api/testar")
def hotmart_api_testar():
    """Valida as credenciais da API da Hotmart (Config) sem publicar nada."""
    s = config.carregar_settings()
    api = s.get("hotmart_api", {})
    hotmart_api.limpar_cache_token()  # forca autenticacao de verdade (sem cache)
    try:
        hotmart_api.obter_token(api.get("client_id", ""), api.get("client_secret", ""))
        return {"ok": True}
    except hotmart_api.HotmartApiError as e:
        return {"ok": False, "erro": str(e)}


@app.get("/api/idiomas")
def idiomas_listar():
    return idiomas.IDIOMAS


# ---------------------------------------------------------------------------
# Histórico de publicações
# ---------------------------------------------------------------------------
@app.get("/api/historico")
def historico_listar():
    return {"arvore": historico.agrupado(), "total": len(historico.listar())}


@app.delete("/api/historico")
def historico_limpar():
    return {"ok": True, "removidos": historico.remover_tudo()}


# ---------------------------------------------------------------------------
# Auto-atualizacao (baixa a versao nova do GitHub)
# ---------------------------------------------------------------------------
@app.get("/api/versao")
def versao():
    r = updater.checar_versao()
    r["configurado"] = updater.ler_rawbase() is not None
    return r


@app.post("/api/atualizar")
def atualizar_sistema():
    resultado = updater.atualizar()
    if resultado.get("deps_changed"):
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                cwd=str(config.RAIZ), capture_output=True, timeout=600,
            )
        except Exception:
            pass  # falha de pip nao derruba o update; usuario reabre o start.bat
    return resultado


# ---------------------------------------------------------------------------
# Scan / importacao
# ---------------------------------------------------------------------------
@app.post("/api/escolher-pasta")
def escolher_pasta():
    """Abre o seletor de pasta nativo do Windows (o servidor roda na maquina do usuario)."""
    s = config.carregar_settings()
    recentes = s.get("pastas_recentes", [])
    try:
        caminho = dialogo.escolher_pasta(inicial=recentes[0] if recentes else None)
    except dialogo.DialogoError as e:
        _erro(str(e))
    return {"pasta": caminho}


def _registrar_recente(pasta: str) -> None:
    s = config.carregar_settings()
    recentes = [pasta] + [p for p in s.get("pastas_recentes", []) if p != pasta]
    s["pastas_recentes"] = recentes[:8]
    config.salvar_settings(s)


@app.post("/api/scan")
def scan(body: ScanIn):
    try:
        resultado = scanner.analisar_auto(body.pasta)
    except scanner.ScannerError as e:
        _erro(str(e))
    pasta_norm = str(Path(body.pasta))
    _registrar_recente(pasta_norm)
    # marca grupos que ja foram importados dessa mesma pasta
    existentes = {
        (p["titulo_pt"], p["tipo"], str(Path(p["pasta"])))
        for p in produtos.listar()
    }
    for g in resultado["grupos"]:
        g["ja_importado"] = (g["titulo"], g["tipo"], pasta_norm) in existentes
    return resultado


@app.post("/api/produtos")
def produtos_importar(body: ImportarIn):
    s = config.carregar_settings()
    try:
        resultado = scanner.analisar_auto(body.pasta)
    except scanner.ScannerError as e:
        _erro(str(e))
    selecionados = resultado["grupos"]
    if body.grupos is not None:
        chaves = {(g.titulo, g.tipo) for g in body.grupos}
        selecionados = [g for g in selecionados if (g["titulo"], g["tipo"]) in chaves]
    if not selecionados:
        _erro("Nenhum grupo pra importar — confira a pasta e a convencao de nomes.")
    criados = [produtos.criar(g, pasta_origem=body.pasta, precos=s["precos"],
                              precos_brasil=s["precos_brasil"]) for g in selecionados]
    return {"criados": criados}


# ---------------------------------------------------------------------------
# CRUD de produtos
# ---------------------------------------------------------------------------
@app.get("/api/produtos")
def produtos_listar():
    return produtos.listar()


@app.delete("/api/produtos")
def produtos_remover_todos():
    """Limpa a fila inteira (nao apaga os arquivos PDF/capas em disco)."""
    n = produtos.remover_todos()
    return {"ok": True, "removidos": n}


@app.get("/api/produtos/{produto_id}")
def produto_obter(produto_id: str):
    try:
        return produtos.obter(produto_id)
    except produtos.ProdutoError as e:
        _erro(str(e), 404)


@app.delete("/api/produtos/{produto_id}")
def produto_remover(produto_id: str):
    produtos.remover(produto_id)
    return {"ok": True}


@app.patch("/api/produtos/{produto_id}")
def produto_atualizar(produto_id: str, body: ProdutoPatchIn):
    try:
        return produtos.atualizar(produto_id, _patch_sem_nones(body))
    except produtos.ProdutoError as e:
        _erro(str(e))


@app.patch("/api/produtos/{produto_id}/idiomas/{codigo}")
def item_atualizar(produto_id: str, codigo: str, body: ItemPatchIn):
    try:
        return produtos.atualizar_item(produto_id, codigo, _patch_sem_nones(body))
    except produtos.ProdutoError as e:
        _erro(str(e))


# ---------------------------------------------------------------------------
# Titulos em portugues (colados do Discord)
# ---------------------------------------------------------------------------
@app.post("/api/titulos/aplicar")
def titulos_aplicar(body: TitulosIn):
    mapa = titulos.parse_titulos(body.texto)
    pasta_norm = str(Path(body.pasta))
    aplicados, sem_match = [], []
    bonus_ok = 0

    for p in produtos.listar():
        if str(Path(p["pasta"])) != pasta_norm:
            continue
        numero = p.get("numero")
        if numero is None:
            numero = titulos.numero_do_produto(p["titulo_pt"])
        novo = None
        if p["tipo"] == "Principal":
            novo = mapa["principal"]
        elif p["tipo"] == "Order Bump" and numero is not None:
            novo = mapa["bumps"].get(numero)
        elif p["tipo"] == "Upsell" and numero is not None:
            novo = mapa["upsells"].get(numero)

        if novo:
            produtos.atualizar(p["id"], {"titulo_pt": novo})
            aplicados.append({"id": p["id"], "tipo": p["tipo"], "numero": numero, "titulo": novo})
        else:
            sem_match.append(f"{p['tipo']}{f' {numero}' if numero else ''} — {p['titulo_pt'][:40]}")

        # titulos dos anexos (bonus no Principal, extra no Upsell) — casados por numero
        if mapa["bonus"] or mapa["extras"]:
            bonus_ok += produtos.definir_titulo_pt_anexos(p["id"], mapa["bonus"], mapa["extras"])

    return {"aplicados": aplicados, "sem_match": sem_match,
            "bonus_nomeados": bonus_ok, "ignoradas": len(mapa["ignoradas"])}


# ---------------------------------------------------------------------------
# Capas
# ---------------------------------------------------------------------------
@app.post("/api/produtos/{produto_id}/idiomas/{codigo}/escolher-capa")
def escolher_capa(produto_id: str, codigo: str):
    """Abre o seletor de arquivo do Windows pra apontar a capa na mao."""
    try:
        reg = produtos.obter(produto_id)
    except produtos.ProdutoError as e:
        _erro(str(e), 404)
    try:
        caminho = dialogo.escolher_arquivo_imagem(inicial=reg.get("pasta"))
    except dialogo.DialogoError as e:
        _erro(str(e))
    if not caminho:
        return {"ok": False, "item": None}  # usuario cancelou
    try:
        item = produtos.atualizar_item(produto_id, codigo, {"capa": caminho})
    except produtos.ProdutoError as e:
        _erro(str(e))
    return {"ok": True, "item": item}


@app.post("/api/produtos/{produto_id}/detectar-capas")
def detectar_capas(produto_id: str):
    """Reprocura capas pela convencao de nomes (pra quem jogou as imagens na pasta depois)."""
    try:
        reg = produtos.obter(produto_id)
    except produtos.ProdutoError as e:
        _erro(str(e), 404)
    achadas = 0
    for item in reg["idiomas"]:
        if item.get("capa") and Path(item["capa"]).is_file():
            continue
        capa = scanner.achar_capa(Path(reg["pasta"]), Path(item["pdf"]).stem)
        if capa:
            produtos.atualizar_item(produto_id, item["codigo"], {"capa": capa})
            achadas += 1
    return {"achadas": achadas, "produto": produtos.obter(produto_id)}


# ---------------------------------------------------------------------------
# Publicacao (Fase B — robo)
# ---------------------------------------------------------------------------
@app.post("/api/produtos/{produto_id}/publicar/{codigo}")
def publicar(produto_id: str, codigo: str, body: PublicarIn):
    try:
        job = robo.iniciar(produto_id, codigo, body.modo)
    except (robo.RoboError, produtos.ProdutoError) as e:
        _erro(str(e))
    return job.snapshot()


@app.get("/api/publicacao")
def publicacao_status():
    job = robo.job_atual()
    if job is None:
        return {"ativo": False, "job": None}
    return {"ativo": job.estado in robo.ESTADOS_ATIVOS, "job": job.snapshot()}


@app.post("/api/publicacao/codigo")
def publicacao_codigo(body: CodigoIn):
    job = robo.job_atual()
    if job is None:
        _erro("Nenhuma publicação em andamento.")
    try:
        job.entregar_codigo(body.codigo)
    except robo.RoboError as e:
        _erro(str(e))
    return {"ok": True}


@app.post("/api/publicacao/confirmar")
def publicacao_confirmar():
    job = robo.job_atual()
    if job is None:
        _erro("Nenhuma publicação em andamento.")
    try:
        job.confirmar()
    except robo.RoboError as e:
        _erro(str(e))
    return {"ok": True}


@app.post("/api/publicacao/cancelar")
def publicacao_cancelar():
    job = robo.job_atual()
    if job is None:
        _erro("Nenhuma publicação em andamento.")
    job.cancelar()
    return {"ok": True}


@app.post("/api/hotmart/login")
def hotmart_login():
    try:
        robo.abrir_login()
    except robo.RoboError as e:
        _erro(str(e))
    return {"ok": True, "detalhe": "Janela do navegador abrindo — faça o login e feche a janela."}


# ---------------------------------------------------------------------------
# Geracao de textos
# ---------------------------------------------------------------------------
@app.post("/api/produtos/{produto_id}/descricao")
def gerar_descricao(produto_id: str):
    try:
        reg = produtos.obter(produto_id)
    except produtos.ProdutoError as e:
        _erro(str(e), 404)
    provider, api_key, model = _llm_cfg()
    s = config.carregar_settings()
    try:
        descricao = textos.gerar_descricao(
            provider, api_key, model,
            titulo=reg["titulo_pt"],
            tipo=reg["tipo"],
            tom=s["descricao"]["tom"],
            tamanho_min=s["descricao"]["tamanho_min"],
            tamanho_max=s["descricao"]["tamanho_max"],
        )
    except textos.TextosError as e:
        _erro(str(e))
    return produtos.atualizar(produto_id, {"descricao_pt": descricao})


@app.post("/api/produtos/{produto_id}/traduzir/{codigo}")
def traduzir(produto_id: str, codigo: str):
    try:
        reg = produtos.obter(produto_id)
    except produtos.ProdutoError as e:
        _erro(str(e), 404)
    provider, api_key, model = _llm_cfg()
    # titulos de bonus (unicos, ordem estavel) — traduzidos na MESMA chamada
    bonus_pt: list[str] = []
    vistos = set()
    for it in reg["idiomas"]:
        for a in it.get("anexos", []):
            t = (a.get("titulo_pt") or "").strip()
            if t and t not in vistos:
                vistos.add(t)
                bonus_pt.append(t)
    try:
        traduzido = textos.traduzir_textos(
            provider, api_key, model, reg["titulo_pt"], reg["descricao_pt"], codigo,
            extras=bonus_pt,
        )
    except textos.TextosError as e:
        _erro(str(e))
    item_atual = next((i for i in reg["idiomas"] if i["codigo"] == codigo), None)
    if item_atual is None:
        _erro(f"Idioma '{codigo}' nao existe nesse produto.")
    patch = {"titulo": traduzido["titulo"], "descricao": traduzido["descricao"]}
    # avanca o status so se ainda estava no comeco (nao rebaixa 'revisado')
    if item_atual["status"] == "rascunho":
        patch["status"] = "textos_gerados"
    try:
        item = produtos.atualizar_item(produto_id, codigo, patch)
    except produtos.ProdutoError as e:
        _erro(str(e))
    # grava os titulos de bonus traduzidos nos anexos deste idioma
    if bonus_pt:
        traducao_por_pt = dict(zip(bonus_pt, traduzido.get("extras", [])))
        produtos.definir_titulo_traduzido_anexos(produto_id, codigo, traducao_por_pt)
        item = produtos.obter(produto_id)  # devolve ja com os anexos atualizados
        item = next((i for i in item["idiomas"] if i["codigo"] == codigo), item)
    return item
