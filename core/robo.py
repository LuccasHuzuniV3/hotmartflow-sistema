"""Robo de publicacao na Hotmart (Fase B).

Arquitetura:
  - Job: maquina de estados de UMA publicacao (1 produto x 1 idioma), com as
    pausas humanas embutidas (codigo 2FA da coproducao e confirmacao final).
  - So existe 1 job ativo por vez (1 navegador, 1 operador).
  - 3 modos:
      "real"     -> faz o cadastro completo na Hotmart (para antes de Finalizar,
                    que so acontece com confirmacao humana pela UI).
      "ensaio"   -> abre a Hotmart, preenche a 1a tela e PARA sem avancar nada.
                    Serve pra calibrar seletores sem risco.
      "simulado" -> nao abre navegador; percorre as etapas com delays. Serve
                    pra testar a UI e treinar o operador.

Regras de projeto:
  - Finaliza o cadastro DIRETO (sem pausa de confirmacao) — a pedido do usuario.
  - Codigo 2FA da coproducao: automatico via Gmail se configurado, senao pausa
    pro humano colar na UI.
  - Antes de convidar coprodutor, checa se ja existe convite Pendente.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from core import checkouts
from core import produtos
from core import gmail_code
from core import historico
from core import hotmart_map as hm

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PERFIL = RAIZ / "data" / "hotmart_profile"
PASTA_PUBLICACOES = RAIZ / "data" / "publicacoes"
def _porta_cdp() -> int:
    """Porta de controle do Chrome (CDP). Vem da CONFIG (robo.cdp_port) — assim
    cada cópia do app (2 contas) usa uma porta diferente SEM depender do start.bat
    (que o 'Atualizar' sobrescreve). Fallback: env var, senão 9222."""
    try:
        from core import config as _cfg
        p = _cfg.carregar_settings().get("robo", {}).get("cdp_port")
        if p:
            return int(p)
    except Exception:
        pass
    return int(os.environ.get("HOTMARTFLOW_CDP_PORT", "9222"))


def _url_cdp() -> str:
    return f"http://127.0.0.1:{_porta_cdp()}"

ESTADOS_ATIVOS = ("iniciando", "rodando", "aguardando_2fa", "aguardando_confirmacao")
# "checkout" = monta a pagina de checkout (custom-checkout.hotmart.com) de um
# Principal JA PUBLICADO — nao mexe no status do produto na fila.
MODOS = ("real", "ensaio", "simulado", "checkout")

# Delay entre etapas do modo simulado (env pra acelerar nos testes)
_DELAY_SIMULADO = float(os.environ.get("HOTMARTFLOW_SIM_DELAY", "0.8"))

# Delay (ms) POR CARACTERE ao digitar nos campos — a Hotmart bloqueia
# preenchimento instantaneo (anti-bot). Configuravel na aba Config.
_DELAY_DIGITACAO = int(os.environ.get("HOTMARTFLOW_DELAY_DIGITACAO", "45"))


class RoboError(Exception):
    pass


class CanceladoError(Exception):
    pass


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------
class Job:
    def __init__(self, produto: dict, item: dict, modo: str):
        self.produto_id = produto["id"]
        self.titulo = item["titulo"] or produto["titulo_pt"]
        self.codigo_idioma = item["codigo"]
        self.pais = item["pais"]
        self.modo = modo
        self.hotmart_id = ""  # ID do produto na Hotmart (capturado da URL)
        self.link_checkout = ""  # link pay.hotmart.com capturado no modo checkout
        self.estado = "iniciando"
        self.etapa = ""
        self.mensagens: list[dict] = []
        self.iniciado_em = datetime.now().isoformat(timespec="seconds")
        # cronometro por etapa (pra medir onde o tempo vai) — fechado a cada marca
        self.tempos: list[dict] = []
        self._t_ini_etapa: float | None = None
        self._etapa_cron: str = ""
        # cronometro FINO por sub-passo (lap) — pra achar a gordura dentro da etapa
        self.subtempos: list[dict] = []
        self._t_lap: float | None = None
        self._codigo_2fa: str | None = None
        self._evento_codigo = threading.Event()
        self._evento_confirmacao = threading.Event()
        self._cancelado = False

    # ---- log / snapshot -------------------------------------------------
    def log(self, texto: str, nivel: str = "info") -> None:
        self.mensagens.append({
            "hora": datetime.now().strftime("%H:%M:%S"),
            "texto": texto,
            "nivel": nivel,
        })

    def snapshot(self) -> dict:
        return {
            "produto_id": self.produto_id,
            "titulo": self.titulo,
            "codigo_idioma": self.codigo_idioma,
            "pais": self.pais,
            "modo": self.modo,
            "estado": self.estado,
            "etapa": self.etapa,
            "mensagens": self.mensagens[-40:],
            "iniciado_em": self.iniciado_em,
            "link_checkout": self.link_checkout,
        }

    # ---- pausas humanas --------------------------------------------------
    def aguardar_codigo(self, timeout: float = 900.0) -> str:
        """Pausa ate o operador colar o codigo 2FA na UI do app."""
        self.estado = "aguardando_2fa"
        self.log("Aguardando código de verificação (chegou no Gmail) — cole na tela.", "pausa")
        if not self._evento_codigo.wait(timeout):
            raise RoboError("Tempo esgotado esperando o código de verificação.")
        self._evento_codigo.clear()
        self._checar_cancelamento()
        self.estado = "rodando"
        return self._codigo_2fa or ""

    def aguardar_confirmacao(self, timeout: float = 900.0) -> None:
        """Pausa ate o operador confirmar a finalizacao na UI do app."""
        self.estado = "aguardando_confirmacao"
        self.log("Tudo pronto. Confirme na tela pra finalizar o cadastro.", "pausa")
        if not self._evento_confirmacao.wait(timeout):
            raise RoboError("Tempo esgotado esperando a confirmação final.")
        self._evento_confirmacao.clear()
        self._checar_cancelamento()
        self.estado = "rodando"

    # ---- controles chamados pela API --------------------------------------
    def entregar_codigo(self, codigo: str) -> None:
        if self.estado != "aguardando_2fa":
            raise RoboError("O robô não está esperando código agora.")
        self._codigo_2fa = (codigo or "").strip()
        self._evento_codigo.set()

    def confirmar(self) -> None:
        if self.estado != "aguardando_confirmacao":
            raise RoboError("O robô não está esperando confirmação agora.")
        self._evento_confirmacao.set()

    def cancelar(self) -> None:
        self._cancelado = True
        self.log("Cancelamento solicitado pelo operador.", "aviso")
        # destrava qualquer pausa em andamento
        self._evento_codigo.set()
        self._evento_confirmacao.set()

    def _checar_cancelamento(self) -> None:
        if self._cancelado:
            raise CanceladoError()

    def marcar_etapa(self, etapa: str, texto: str) -> None:
        self._checar_cancelamento()
        self._fechar_etapa()   # cronometra a etapa que acabou
        self.etapa = etapa
        self._etapa_cron = etapa
        self._t_ini_etapa = time.monotonic()
        self._t_lap = time.monotonic()   # reinicia o cronometro fino na etapa nova
        self.log(texto)

    def lap(self, nome: str) -> None:
        """Marca o tempo de um SUB-PASSO (desde o ultimo lap/inicio da etapa).
        So instrumentacao — nao muda o fluxo. Cai no resumo e no tempos.txt."""
        agora = time.monotonic()
        if self._t_lap is not None:
            dur = round(agora - self._t_lap, 1)
            self.subtempos.append({"nome": nome, "segundos": dur})
            self.log(f"  ⏲ {nome}: {dur:.1f}s")
        self._t_lap = agora

    def _fechar_etapa(self) -> None:
        """Fecha o cronometro da etapa atual e guarda a duracao."""
        if self._t_ini_etapa is not None and self._etapa_cron:
            dur = time.monotonic() - self._t_ini_etapa
            self.tempos.append({"etapa": self._etapa_cron, "segundos": round(dur, 1)})
        self._t_ini_etapa = None
        self._etapa_cron = ""

    def resumo_tempos(self) -> str:
        """Fecha a ultima etapa e devolve um resumo (etapas mais lentas no topo)."""
        self._fechar_etapa()
        if not self.tempos:
            return ""
        total = sum(t["segundos"] for t in self.tempos)
        linhas = [f"⏱ Tempo por etapa (total {total / 60:.1f} min):"]
        for t in sorted(self.tempos, key=lambda x: x["segundos"], reverse=True):
            linhas.append(f"   {t['segundos']:6.1f}s  {t['etapa']}")
        if self.subtempos:
            linhas.append("— detalhe dos sub-passos (ordem do fluxo) —")
            for s in self.subtempos:
                linhas.append(f"   {s['segundos']:6.1f}s  {s['nome']}")
        return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Registro global (1 job por vez — 1 navegador, 1 operador)
# ---------------------------------------------------------------------------
_TRAVA = threading.Lock()
_JOB: Job | None = None


def job_atual() -> Job | None:
    return _JOB


def iniciar(produto_id: str, codigo_idioma: str, modo: str) -> Job:
    global _JOB
    if modo not in MODOS:
        raise RoboError(f"Modo inválido: '{modo}' (use real, ensaio ou simulado)")

    with _TRAVA:
        if _JOB is not None and _JOB.estado in ESTADOS_ATIVOS:
            raise RoboError(
                "Já existe uma publicação em andamento. "
                "Aguarde terminar (ou cancele) antes de iniciar outra."
            )

        produto = produtos.obter(produto_id)
        item = next((i for i in produto["idiomas"] if i["codigo"] == codigo_idioma), None)
        if item is None:
            raise RoboError(f"Idioma '{codigo_idioma}' não existe nesse produto.")
        _validar_item(produto, item, modo)

        job = Job(produto, item, modo)
        _JOB = job

    if modo != "checkout":  # checkout NAO altera o status (produto ja publicado)
        produtos.atualizar_item(produto_id, codigo_idioma, {"status": "publicando", "erro": ""})
    threading.Thread(target=_rodar, args=(job, produto, item), daemon=True).start()
    return job


def _validar_item(produto: dict, item: dict, modo: str) -> None:
    if modo == "checkout":
        # monta a pagina de checkout: exige Principal JA publicado
        if produto.get("tipo") != "Principal":
            raise RoboError("Checkout é montado só no ebook PRINCIPAL.")
        if item["status"] != "publicado":
            raise RoboError(
                f"{item['pais']}: publique o produto primeiro — o checkout precisa "
                f"do produto existindo na Hotmart (está '{item['status']}')."
            )
        if not (item["titulo"] or "").strip():
            raise RoboError(f"{item['pais']}: sem título traduzido.")
        return
    if item["status"] == "publicado":
        raise RoboError(f"{item['pais']}: já está publicado.")
    if item["status"] != "revisado":
        raise RoboError(
            f"{item['pais']}: precisa estar 'revisado' pra publicar (está '{item['status']}')."
        )
    if not (item["titulo"] or "").strip() or not (item["descricao"] or "").strip():
        raise RoboError(f"{item['pais']}: título/descrição vazios.")
    if modo == "simulado":
        return  # simulado nao toca em arquivo nenhum
    if not item.get("pdf") or not Path(item["pdf"]).is_file():
        raise RoboError(f"{item['pais']}: PDF não encontrado em {item.get('pdf')!r}.")
    if modo == "real" and (not item.get("capa") or not Path(item["capa"]).is_file()):
        raise RoboError(f"{item['pais']}: capa não encontrada — obrigatória pra publicar de verdade.")
    for anexo in item.get("anexos", []):
        if not anexo.get("pdf") or not Path(anexo["pdf"]).is_file():
            raise RoboError(f"{item['pais']}: anexo '{anexo.get('nome')}' sem PDF em {anexo.get('pdf')!r}.")


def _bumps_do_checkout(produto: dict, codigo: str) -> list[dict]:
    """Order Bumps da MESMA rede (pasta) no idioma do checkout, em ordem de
    número — só os PUBLICADOS (precisam existir na Hotmart pra entrar no bump).
    Retorna [{numero, titulo, descricao(≤500)}]."""
    pasta = str(produto.get("pasta", ""))
    bumps: list[dict] = []
    for p in produtos.listar():
        if p.get("tipo") != "Order Bump" or str(p.get("pasta", "")) != pasta:
            continue
        it = next((i for i in p["idiomas"] if i["codigo"] == codigo), None)
        if not it or it.get("status") != "publicado":
            continue
        if not (it.get("titulo") or "").strip():
            continue
        bumps.append({
            "numero": p.get("numero") or 0,
            "titulo": it["titulo"].strip(),
            "descricao": (it.get("descricao") or "").strip()[:500],  # limite da Hotmart
        })
    bumps.sort(key=lambda b: b["numero"])
    return bumps


def _imagem_checkout(pasta_rede: str, codigo: str) -> str | None:
    """Imagem do checkout do país: dentro da subpasta com 'checkout' no nome
    (ZPAG DE CHECKOUT etc.), o arquivo cujo nome é o país (ALEMANHA, BRASIL,
    INGLES...) — casado com a mesma tolerância de nomes do scanner."""
    from core import idiomas as _idiomas
    base = Path(pasta_rede or "")
    if not base.is_dir():
        return None
    exts = (".jpg", ".jpeg", ".png", ".webp")
    for sub in sorted(base.iterdir()):
        if not sub.is_dir() or "checkout" not in _idiomas.normalizar(sub.name):
            continue
        for arq in sorted(sub.iterdir()):
            if not arq.is_file() or arq.suffix.lower() not in exts:
                continue
            info = _idiomas.por_pais(arq.stem.strip())
            if info and info["codigo"] == codigo:
                return str(arq)
    return None


def _rodar_checkout(job: Job, produto: dict, item: dict) -> None:
    """Monta a página de checkout de um Principal publicado. NUNCA mexe no
    status do produto na fila (ele continua 'publicado')."""
    try:
        _executar_checkout(job, produto, item)
        if job.link_checkout:
            try:
                rede = Path(produto.get("pasta", "")).name or produto.get("pasta", "")
                checkouts.registrar(rede=rede, pais=item["pais"],
                                    titulo=item["titulo"] or produto["titulo_pt"],
                                    link=job.link_checkout)
            except Exception:
                pass  # registro nunca derruba o resultado
            job.log(f"Link salvo no histórico de checkouts ✔ {job.link_checkout}", "ok")
        else:
            job.log("Página publicada, mas NÃO capturei o link — copie na mão na tela "
                    "de sucesso e confira o print.", "aviso")
        job.estado = "concluido"
    except CanceladoError:
        job.estado = "cancelado"
        job.log("Montagem do checkout cancelada.", "aviso")
    except Exception as e:
        job.estado = "erro"
        job.log(f"ERRO: {str(e)[:400]}", "erro")


def _rodar(job: Job, produto: dict, item: dict) -> None:
    if job.modo == "checkout":
        _rodar_checkout(job, produto, item)
        return
    try:
        if job.modo == "simulado":
            _executar_simulado(job)
        else:
            _executar_navegador(job, produto, item)
        if job.modo == "real":
            produtos.atualizar_item(job.produto_id, job.codigo_idioma, {"status": "publicado"})
            job.log("Publicado com sucesso ✔", "ok")
            try:  # grava no historico (rede = nome da pasta de origem)
                rede = Path(produto.get("pasta", "")).name or produto.get("pasta", "")
                # tipo especifico: "Upsell 1", "Order Bump 2"... (Principal nao tem numero)
                tipo = produto["tipo"]
                if produto.get("numero"):
                    tipo = f"{tipo} {produto['numero']}"
                historico.registrar(
                    rede=rede, pais=item["pais"],
                    titulo=item["titulo"] or produto["titulo_pt"],
                    tipo=tipo, hotmart_id=job.hotmart_id)
            except Exception:
                pass  # historico nunca derruba a publicacao
        else:
            produtos.atualizar_item(job.produto_id, job.codigo_idioma, {"status": "revisado"})
            job.log(f"Modo {job.modo} concluído — nada foi enviado de verdade.", "ok")
        # 'concluido' SO no final — se vier antes, o painel para de atualizar e a
        # mensagem do cupom (logada depois) nunca aparece pro operador
        job.estado = "concluido"
    except CanceladoError:
        job.estado = "cancelado"
        produtos.atualizar_item(job.produto_id, job.codigo_idioma, {"status": "revisado"})
        job.log("Publicação cancelada. Nada foi finalizado.", "aviso")
    except Exception as e:  # RoboError, Playwright, IO... — tudo vira erro legivel
        job.estado = "erro"
        msg = str(e)[:400]
        job.log(f"ERRO: {msg}", "erro")
        try:
            produtos.atualizar_item(job.produto_id, job.codigo_idioma,
                                    {"status": "erro", "erro": msg})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Executor SIMULADO (sem navegador — testa UI e treina operador)
# ---------------------------------------------------------------------------
def _executar_simulado(job: Job) -> None:
    passos = [
        ("abrir", "Abrindo a Hotmart (simulado)..."),
        ("criar_produto", "Criando produto tipo eBook (simulado)..."),
        ("informacoes_basicas", "Preenchendo nome, descrição, idioma, país, capa e categoria (simulado)..."),
        ("preco", "Definindo moeda e preço (simulado)..."),
        ("conteudo", "Subindo o PDF (simulado)..."),
    ]
    job.estado = "rodando"
    for etapa, texto in passos:
        job.marcar_etapa(etapa, texto)
        time.sleep(_DELAY_SIMULADO)

    job.marcar_etapa("coproducao", "Convidando coprodutor (simulado)...")
    codigo = job.aguardar_codigo()
    job.log(f"Código recebido ({codigo[:2]}****) — convite enviado (simulado).")
    time.sleep(_DELAY_SIMULADO)

    job.marcar_etapa("finalizar", "Finalizando o cadastro (simulado)...")
    job.log("Finalizar Cadastro clicado (simulado).")
    time.sleep(_DELAY_SIMULADO)


# ---------------------------------------------------------------------------
# Executor de NAVEGADOR (real e ensaio) — Playwright + mapa de seletores
# ---------------------------------------------------------------------------
class Tela:
    """Wrapper fino do Playwright: acha elementos pelo MAPA e tira screenshots."""

    def __init__(self, page, job: Job, pasta_shots: Path, delay_digitacao: int = _DELAY_DIGITACAO):
        self.page = page
        self.job = job
        self.pasta = pasta_shots
        self.delay_digitacao = max(0, int(delay_digitacao))
        self._n = 0

    def shot(self, nome: str) -> None:
        self._n += 1
        try:
            self.page.screenshot(path=str(self.pasta / f"{self._n:02d}_{nome}.png"),
                                 full_page=False)
        except Exception:
            pass  # screenshot nunca derruba o fluxo

    def _loc_no_ctx(self, ctx, c):
        """Monta o locator de um candidato num contexto (página OU iframe)."""
        import re
        if c["tipo"] == "role":
            return ctx.get_by_role(c["role"], name=re.compile(c["nome"], re.I))
        if c["tipo"] == "texto":
            return ctx.get_by_text(re.compile(c["texto"], re.I))
        if c["tipo"] == "label":
            return ctx.get_by_label(re.compile(c["texto"], re.I))
        if c["tipo"] == "placeholder":
            return ctx.get_by_placeholder(re.compile(c["texto"], re.I))
        return ctx.locator(c["css"])

    def _localizar(self, chave: str, timeout: int = 4000):
        """Procura o elemento na página E em TODOS os iframes, tentando de novo
        ate 'timeout' — a Hotmart embute telas (coprodução etc.) em iframe, e um
        get_by_role na página principal nao enxerga o que esta dentro do frame."""
        candidatos = hm.MAPA[chave]
        fim = time.time() + timeout / 1000.0
        primeira = True
        while True:
            contextos = [self.page] + list(self.page.frames)  # pagina + iframes
            for c in candidatos:
                for ctx in contextos:
                    try:
                        loc = self._loc_no_ctx(ctx, c).first
                        loc.wait_for(state="visible", timeout=600)
                        return loc
                    except Exception:
                        continue
            if time.time() >= fim and not primeira:
                break
            primeira = False
            self.page.wait_for_timeout(500)
        self.shot(f"erro_{chave}")
        raise RoboError(
            f"Não achei '{chave}' na tela da Hotmart (procurei na página e nos iframes). "
            f"Print salvo em data/publicacoes. Corrija o seletor em core/hotmart_map.py."
        )

    def _contextos(self):
        """Página principal + todos os iframes (a Hotmart embute telas em iframe)."""
        return [self.page] + list(self.page.frames)

    def clicar(self, chave: str, timeout: int = 4000) -> None:
        self._localizar(chave, timeout=timeout).click()

    def preencher(self, chave: str, valor: str, delay: int | None = None) -> None:
        """Digita LETRA POR LETRA com delay — a Hotmart reseta o form se o
        preenchimento for instantaneo (fill). press_sequentially simula humano.

        CRITICO: texto longo (descricao de 500+ chars) leva mais que o timeout
        padrao de 20s pra digitar. Calculamos um timeout proporcional ao tamanho
        (senao estoura no meio da digitacao).

        delay: override do ms/tecla (ex.: checkout builder nao tem anti-bot,
        entao textos longos podem ir mais rapido)."""
        campo = self._localizar(chave)
        campo.click()
        self.page.wait_for_timeout(300)
        try:
            campo.fill("")  # limpa o que tiver
        except Exception:
            pass
        d = self.delay_digitacao if delay is None else max(0, int(delay))
        # tempo total = n_chars * delay + folga generosa
        tmo = max(30000, len(valor) * d + 20000)
        try:
            campo.press_sequentially(valor, delay=d, timeout=tmo)
        except Exception:
            campo.type(valor, delay=d, timeout=tmo)  # fallback API antiga
        self.page.wait_for_timeout(250)

    def escolher_opcao(self, chave_campo: str, texto_opcao: str) -> None:
        """Dropdown de busca (hot-select / selectize): abre, tenta clicar direto na
        opção (rápido, p/ opções já visíveis como a 1ª); se não achar, DIGITA pra
        filtrar e tenta de novo. A opção fica 'hidden' com o dropdown fechado."""
        import re
        campo = self._localizar(chave_campo)
        campo.click()               # abre o dropdown
        self.page.wait_for_timeout(200)
        alvo = re.compile(rf"^\s*{re.escape(texto_opcao)}\s*$", re.I)
        sel = "hot-select-option, .selectize-dropdown .option, [data-selectable]"

        # candidatos EXATOS (nao clicam opcao errada) — usados na tentativa rapida
        def exatas(ctx):
            return [
                ctx.locator(sel).filter(has_text=alvo),
                ctx.get_by_role("option", name=texto_opcao, exact=True),
                ctx.locator(sel, has_text=texto_opcao),
                ctx.get_by_text(alvo),
            ]

        def tentar(fabricas, tmo):
            # POLLING rápido: varre página+iframes com is_visible (instantâneo) num
            # loop de ate 'tmo' ms, e clica assim que aparece — em vez de esperar
            # 'tmo' BLOQUEANDO em cada candidato (o que fazia o select 'Sócio' levar
            # 16s varrendo os iframes). Clique com timeout curto: candidato ruim
            # falha rápido e passa pro próximo.
            fim = time.time() + tmo / 1000.0
            while True:
                for ctx in self._contextos():
                    for loc in fabricas(ctx):
                        try:
                            el = loc.first
                            if el.is_visible():
                                el.click(timeout=2500)
                                self.page.wait_for_timeout(150)
                                return True
                        except Exception:
                            continue
                if time.time() >= fim:
                    return False
                self.page.wait_for_timeout(100)

        # 1) tentativa RÁPIDA sem digitar (pega opções já visíveis, ex.: a 1ª = Sócio)
        if tentar(exatas, 250):
            return

        # 2) digita pra filtrar (rápido — dropdown nao sofre anti-bot) e tenta de novo
        delay_filtro = min(self.delay_digitacao, 8)
        try:
            campo.press_sequentially(texto_opcao, delay=delay_filtro)
        except Exception:
            try:
                campo.type(texto_opcao, delay=delay_filtro)
            except Exception:
                pass
        self.page.wait_for_timeout(250)

        def com_fallback(ctx):
            return exatas(ctx) + [ctx.locator(sel).first]  # 1a opcao da lista filtrada

        for _ in range(2):
            if tentar(com_fallback, 700):
                return
            self.page.wait_for_timeout(300)
        self.shot(f"erro_opcao_{texto_opcao}")
        raise RoboError(
            f"Não consegui selecionar '{texto_opcao}' no campo {chave_campo}. "
            "Print salvo em data/publicacoes."
        )

    def garantir_valor(self, chave: str, esperado: str, tentativas: int = 3) -> bool:
        """Confere se o campo tem valor; se ficou VAZIO (a Hotmart as vezes da um
        'reset'/F5 depois do 1o campo e apaga o Nome), repreenche ate ter valor."""
        for _ in range(tentativas):
            try:
                atual = self._localizar(chave).input_value()
            except Exception:
                atual = ""
            if atual.strip():
                return True
            self.job.log(f"Campo '{chave}' ficou vazio (a Hotmart resetou?) — repreenchendo.", "aviso")
            self.preencher(chave, esperado)
            self.page.wait_for_timeout(500)
        try:
            return bool(self._localizar(chave).input_value().strip())
        except Exception:
            return False

    def selecionar_club_com_espaco(self, limite: int = 300) -> None:
        """Na 'Área de Membros', le o nº de produtos de cada Club e clica no que
        tem MENOS que o limite (com espaço) — o Club cheio (300) fica de fora.
        Se houver varios com espaço, escolhe o de menor contagem (mais folga)."""
        import re
        labels = self.page.get_by_text(re.compile(r"\d+\s+produtos?", re.I))
        # espera os Clubs renderizarem (a lista carrega async) — nao depende de
        # um wait fixo antes de chamar; poll ate ~6s pelo 1o "N produtos".
        try:
            labels.first.wait_for(state="visible", timeout=6000)
        except Exception:
            pass
        total = labels.count()
        if total == 0:
            self.shot("erro_club")
            raise RoboError("Não achei os Clubs na tela de Área de Membros.")
        escolhido, menor = None, None
        for i in range(total):
            try:
                txt = labels.nth(i).inner_text()
            except Exception:
                continue
            m = re.search(r"(\d+)", txt)
            if not m:
                continue
            qtd = int(m.group(1))
            if qtd < limite and (menor is None or qtd < menor):
                menor, escolhido = qtd, labels.nth(i)
        if escolhido is None:
            self.shot("erro_club_cheio")
            raise RoboError(f"Todos os Clubs estão cheios (>= {limite} produtos).")
        # clica no CARD (sobe pro ancestral clicavel); fallback no proprio texto
        try:
            card = escolhido.locator(
                "xpath=ancestor::*[self::button or @role='button' "
                "or contains(@class,'card') or contains(@class,'club')][1]")
            card.click(timeout=3000)
        except Exception:
            escolhido.click()
        self.page.wait_for_timeout(600)
        self.job.log(f"Club escolhido: {menor} produtos (com espaço).")

    def clicar_por_texto(self, texto: str, timeout: int = 15000,
                         exato: bool = True) -> None:
        """Clica num botao/chip que tenha esse texto (ex.: categoria
        'Espiritualidade' ou 'Modelo de parceria de negócio' na coprodução).
        exato=False casa por CONTÉM — pra clicar no resultado da busca do
        checkout, cujo card tem o título no meio de mais texto.

        POLLING rápido: em vez de esperar 900ms bloqueando em CADA candidato (o
        que explodia pra dezenas de segundos varrendo os iframes — 43s num clique
        só!), faz varreduras INSTANTÂNEAS (is_visible) repetidas e clica assim que
        o elemento aparece. Mesma busca (página + iframes, 4 formas), sem o
        desperdício de esperar cada candidato falhar."""
        import re
        if exato:
            alvo = re.compile(rf"^\s*{re.escape(texto)}\s*$", re.I)
        else:
            alvo = re.compile(re.escape(texto), re.I)

        def fabricas(ctx):
            return [
                ctx.get_by_role("button", name=alvo),
                ctx.get_by_role("radio", name=alvo),
                ctx.locator("button, label").filter(has_text=alvo),
                ctx.get_by_text(alvo),
            ]

        fim = time.time() + timeout / 1000.0
        while True:
            for ctx in self._contextos():          # pagina + iframes
                for loc in fabricas(ctx):
                    try:
                        el = loc.first
                        if el.is_visible():         # checagem instantanea (nao bloqueia)
                            el.click(timeout=2500)   # curto: candidato ruim falha rapido
                            self.page.wait_for_timeout(300)
                            return
                    except Exception:
                        continue
            if time.time() >= fim:
                break
            self.page.wait_for_timeout(200)         # espera curta e re-varre
        self.shot(f"erro_botao_{texto}")
        raise RoboError(f"Não achei o botão/opção '{texto}'. Print salvo em data/publicacoes.")

    def ir_para_conteudo(self) -> None:
        """Vai pra tela de Conteúdo do Produto. Tenta o menu lateral; se ele
        estiver colapsado/não clicar (comum com 2 contas em janelas menores),
        clica no botão 'Configurar' do checklist."""
        try:
            self.clicar("menu_conteudo", timeout=6000)
            return
        except RoboError:
            self.job.log("Menu 'Conteúdo do Produto' não clicou — usando o 'Configurar' do checklist.", "aviso")
        self.clicar("btn_configurar_conteudo", timeout=8000)

    def ir_para_coproducao(self) -> None:
        """Vai pra tela de Coproduções. Tenta o menu lateral; se não achar,
        clica no lápis (expande o menu colapsado) e tenta de novo."""
        try:
            self.clicar("menu_coproducao", timeout=6000)
            return
        except RoboError:
            self.job.log("Menu 'Coproduções' não apareceu — clicando no lápis pra abrir o menu...", "aviso")
        try:
            self.clicar("btn_lapis_editar", timeout=6000)
            self.page.wait_for_timeout(1500)
        except RoboError:
            pass
        self.clicar("menu_coproducao", timeout=10000)

    def upload(self, chave: str, arquivos: str | list[str]) -> None:
        if isinstance(arquivos, str):
            arquivos = [arquivos]
        self.page.locator(hm.MAPA[chave][0]["css"]).first.set_input_files(arquivos)

    def upload_conteudo(self, itens: list[tuple[str, str]]) -> None:
        """Upload na tela de Conteúdo — UM ARQUIVO POR VEZ.

        Motivo: como o robô se conecta ao Chrome já aberto (CDP), o Playwright
        limita a transferencia a 50MB por chamada. Mandando 1 PDF de cada vez
        (cada um < 50MB) contornamos o limite, e cada clique no botao ADICIONA
        o arquivo na lista (nao substitui).

        `itens` = lista de (caminho, nome_cliente). O que o cliente ve na Hotmart
        e o NOME DO ARQUIVO, entao cada PDF e copiado pra uma pasta temporaria
        renomeado pro `nome_cliente` (titulo traduzido: do principal ou do bonus).
        O arquivo original no disco NAO e alterado. Se `nome_cliente` vier vazio,
        mantem o nome original. Nomes finais iguais ganham um numero pra nao
        colidir ('Titulo.pdf', 'Titulo 2.pdf')."""
        temp_dir = tempfile.mkdtemp(prefix="hmflow_up_")
        try:
            arquivos = self._preparar_uploads(itens, temp_dir)
            for n, arq in enumerate(arquivos, 1):
                nome = Path(arq).name
                self.job.log(f"Enviando arquivo {n}/{len(arquivos)}: {nome}...")
                with self.page.expect_file_chooser() as fc:
                    self.clicar("btn_selecione_arquivo")
                fc.value.set_files(arq)
                # espera esse arquivo aparecer na lista antes de mandar o proximo
                if not self.existe_texto(nome, timeout=300_000):
                    self.shot(f"erro_upload_{n}")
                    raise RoboError(f"O arquivo '{nome}' não terminou de subir em 5 min.")
                self.page.wait_for_timeout(1500)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _preparar_uploads(self, itens: list[tuple[str, str]], destino: str) -> list[str]:
        """Copia cada arquivo pra `destino` com o nome desejado (titulo traduzido),
        preservando a extensao e evitando nomes duplicados. Retorna os caminhos
        das copias, na ordem original."""
        copias: list[str] = []
        usados: set[str] = set()
        for caminho, nome_cliente in itens:
            ext = Path(caminho).suffix  # preserva .pdf/.epub/etc
            base = _nome_arquivo_seguro(nome_cliente) if (nome_cliente or "").strip() \
                else Path(caminho).stem
            final = f"{base}{ext}"
            n = 1
            while final.lower() in usados:  # nome repetido -> numera
                n += 1
                final = f"{base} {n}{ext}"
            usados.add(final.lower())
            alvo = str(Path(destino) / final)
            shutil.copy2(caminho, alvo)
            copias.append(alvo)
        return copias

    def _elemento_visivel(self, chave: str, timeout: int = 1500) -> bool:
        """True se ALGUM candidato da chave está visível agora (rápido, sem
        screenshot de erro). Usado pra saber, p.ex., se o botão 'Finalizar' ainda
        está na tela ou já sumiu (= cadastro finalizado)."""
        for c in hm.MAPA[chave]:
            for ctx in self._contextos():
                try:
                    self._loc_no_ctx(ctx, c).first.wait_for(state="visible", timeout=timeout)
                    return True
                except Exception:
                    continue
        return False

    def finalizar_cadastro(self, tentativas: int = 3) -> bool:
        """Clica em 'Finalizar Cadastro' e reconhece o sucesso por DOIS sinais:
          a) a mensagem 'Enviado para aprovação' aparece, OU
          b) o botão 'Finalizar' SUMIU depois do clique (= a Hotmart finalizou —
             o botão só existe enquanto o produto é rascunho).
        O sinal (b) é o confiável: a mensagem às vezes é um toast que some rápido
        ou vem noutro idioma. Escala o clique a cada tentativa (o botão às vezes
        não dispara de 1ª ou fica atrás do balão de chat): normal → forçado →
        dispatch. SÓ considera 'sumiu = sucesso' se a gente REALMENTE clicou."""
        clicou = False
        for n in range(1, tentativas + 1):
            if not self._elemento_visivel("btn_finalizar_cadastro", timeout=2000):
                if clicou:  # sumiu DEPOIS do nosso clique -> finalizou
                    self.job.log("Botão 'Finalizar' sumiu após o clique — finalizado ✔", "ok")
                    return True
                self.page.wait_for_timeout(1500)   # ainda carregando o painel
                continue
            try:
                btn = self._localizar("btn_finalizar_cadastro", timeout=8000)
                try:
                    btn.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
                if n == 1:
                    btn.click()
                elif n == 2:
                    btn.click(force=True)          # ignora checagem de "recebe o clique"
                else:
                    btn.dispatch_event("click")     # dispara direto no elemento (fura overlay)
                clicou = True
            except Exception:
                self.job.log(f"Finalizar: tentativa {n} não conseguiu clicar no botão.", "aviso")
                self.page.wait_for_timeout(1500)
                continue
            self.page.wait_for_timeout(1500)   # deixa o clique processar
            # sucesso b) PRIMEIRO (sinal confiável e rápido): o botão sumiu = finalizou
            if not self._elemento_visivel("btn_finalizar_cadastro", timeout=2500):
                self.job.log("Botão 'Finalizar' sumiu após o clique — finalizado ✔", "ok")
                return True
            # sucesso a): a mensagem de confirmação (fallback)
            if self.existe_texto("Enviado para aprovação", timeout=4000):
                return True
            self.job.log(f"Finalizar: tentativa {n} sem confirmação da Hotmart — repetindo.", "aviso")
            self.page.wait_for_timeout(1500)
        return False

    def criar_cupom_ui(self, codigo: str, desconto_pct: int) -> None:
        """Cria o cupom CLICANDO na tela de Cupons do produto (menu lateral) —
        a API oficial de cupom é bugada (200 sem criar), então vai pela UI mesmo.

        Fluxo: menu 'Cupons' -> 'Criar cupom' -> código + desconto -> salvar.
        Sucesso SÓ se o código aparecer na lista depois de salvar."""
        if not (codigo or "").strip():
            raise RoboError("Código do cupom vazio (Config > Cupom).")
        self.clicar("menu_cupons", timeout=8000)
        self.page.wait_for_timeout(1500)
        self.clicar("btn_criar_cupom", timeout=10000)
        self.page.wait_for_timeout(1000)
        self.preencher("campo_cupom_codigo", codigo.strip())
        # o campo de desconto (#percentage) e money-input direita->esquerda
        # ("0,00"): pra mostrar "25,00" digitamos os digitos de 25*100 = "2500"
        digitos_pct = str(int(round(float(desconto_pct) * 100)))
        self.preencher("campo_cupom_desconto", digitos_pct)
        self.shot("cupom_preenchido")
        self.clicar("btn_salvar_cupom", timeout=8000)
        self.page.wait_for_timeout(1500)
        # confere DE VERDADE: o codigo tem que aparecer na lista de cupons
        if not self.existe_texto(codigo.strip(), timeout=8000):
            self.shot("erro_cupom_nao_listado")
            raise RoboError(
                f"Salvei mas o cupom '{codigo}' não apareceu na lista — "
                "confira o print em data/publicacoes."
            )

    def capturar_link_pagamento(self, timeout: float = 15000) -> str:
        """Lê o link https://pay.hotmart.com/... do input da tela de sucesso do
        checkout ('Sua página foi publicada com sucesso!') — direto do value,
        sem depender do botão 'Copiar link' nem da área de transferência."""
        fim = time.time() + timeout / 1000.0
        while True:
            for ctx in self._contextos():
                try:
                    inputs = ctx.locator("input")
                    for i in range(min(inputs.count(), 40)):
                        try:
                            v = (inputs.nth(i).input_value() or "").strip()
                        except Exception:
                            continue
                        if v.startswith("https://pay.hotmart.com"):
                            return v
                except Exception:
                    continue
            if time.time() >= fim:
                return ""
            self.page.wait_for_timeout(500)

    def existe_texto(self, texto: str, timeout: float = 3000) -> bool:
        """Procura o texto na página E nos iframes, tentando ate 'timeout'."""
        import re
        alvo = re.compile(re.escape(texto), re.I)
        fim = time.time() + timeout / 1000.0
        while True:
            for ctx in self._contextos():
                try:
                    ctx.get_by_text(alvo).first.wait_for(state="visible", timeout=600)
                    return True
                except Exception:
                    continue
            if time.time() >= fim:
                return False



def _nome_arquivo_seguro(titulo: str) -> str:
    """Transforma o titulo traduzido num nome de arquivo valido no Windows.
    Remove os caracteres proibidos (\\ / : * ? \" < > |), colapsa espacos e
    apara pontos/espacos das pontas. Se sobrar vazio, usa 'ebook'."""
    import re
    limpo = re.sub(r'[\\/:*?"<>|]', " ", titulo or "")
    limpo = re.sub(r"\s+", " ", limpo).strip(" .")
    limpo = limpo[:120].strip(" .")  # nome de arquivo curto o bastante
    return limpo or "ebook"


def _chrome_exe() -> str | None:
    candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return None


def _cdp_ativo() -> bool:
    """A janela de controle do Chrome ja esta no ar (porta de depuracao respondendo)?"""
    import urllib.request
    try:
        with urllib.request.urlopen(_url_cdp() + "/json/version", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _matar_chrome_do_perfil() -> None:
    """Fecha um Chrome antigo que esteja usando o perfil do robo SEM a porta de
    depuracao (senao o novo launch vira 'singleton' sem porta e o connect falha)."""
    if os.name != "nt":
        return
    perfil_str = str(PASTA_PERFIL).replace("\\", "/").lower()
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' OR Name='msedge.exe'\" | "
        "Where-Object { $_.CommandLine -and "
        f"  $_.CommandLine.Replace('\\\\','/').ToLower().Contains('{perfil_str}') "
        "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        time.sleep(1.0)
    except Exception:
        pass


def garantir_chrome(url: str | None = None) -> None:
    """Garante que existe UMA janela do Chrome do robo aberta com a porta de
    controle (perfil proprio data/hotmart_profile). Se ja estiver aberta, reusa.
    O login feito nessa janela vale pra todas as publicacoes (mesma janela)."""
    if _cdp_ativo():
        return
    exe = _chrome_exe()
    if not exe:
        raise RoboError("Não encontrei o Chrome/Edge instalado.")
    _matar_chrome_do_perfil()
    PASTA_PERFIL.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--remote-debugging-port={_porta_cdp()}",
        f"--user-data-dir={PASTA_PERFIL}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--profile-directory=Default",
        # Mantém a janela 100% ativa mesmo ATRÁS de outras janelas (2º plano):
        # sem isso o Chrome "estrangula" janelas ocultas e trava clique/visibilidade.
        # (Não resolve janela MINIMIZADA — essa continua sem renderizar.)
        "--disable-backgrounding-occluded-windows",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
    ]
    if url:
        args.append(url)
    subprocess.Popen(args, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    # espera a porta de controle subir (ate ~15s)
    for _ in range(30):
        if _cdp_ativo():
            return
        time.sleep(0.5)
    raise RoboError("O Chrome do robô não subiu a tempo. Tente de novo.")


def _conectar(p):
    """Conecta na janela do Chrome ja aberta (CDP) e devolve (browser, page)."""
    if not _cdp_ativo():
        raise RoboError(
            "A janela do robô não está aberta. Clique em 'Abrir Hotmart (login)', "
            "faça o login e DEIXE a janela aberta — o robô usa ela pra publicar."
        )
    browser = p.chromium.connect_over_cdp(_url_cdp())
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return browser, page


def _obter_codigo_2fa(job: Job, settings: dict, *, desde_ts: float,
                      ignorar=None) -> str:
    """Lê o código 2FA no Gmail (se configurado e ligado); senão pausa pro humano.

    ignorar: códigos já usados nesta publicação (1º convite de coprodução) —
    evita reaproveitar o código antigo quando tem 2 coprodutores."""
    gm = settings.get("gmail", {})
    ligado = gm.get("auto") and (gm.get("email") or "").strip() and (gm.get("app_password") or "").strip()
    if ligado:
        job.log("Buscando o código de segurança no Gmail automaticamente...")
        try:
            codigo = gmail_code.buscar_codigo(
                gm["email"], gm["app_password"], desde_ts=desde_ts, timeout=90,
                ignorar=ignorar)
        except gmail_code.GmailError as e:
            job.log(f"Gmail: {e}", "aviso")
            codigo = None
        if codigo:
            job.log(f"Código lido do Gmail: {codigo[:2]}**** ✔", "ok")
            return codigo
        job.log("Não achei o código no Gmail a tempo — cole na tela, por favor.", "aviso")
    return job.aguardar_codigo()  # fallback: pausa humana (cola na UI)


def _executar_navegador(job: Job, produto: dict, item: dict) -> None:
    from playwright.sync_api import sync_playwright

    from core import config as cfg
    s = cfg.carregar_settings()
    ensaio = job.modo == "ensaio"

    pasta_shots = PASTA_PUBLICACOES / job.produto_id / job.codigo_idioma
    pasta_shots.mkdir(parents=True, exist_ok=True)

    job.estado = "rodando"
    with sync_playwright() as p:
        browser, page = _conectar(p)  # conecta na janela ja aberta e logada
        try:
            page.set_default_timeout(20000)
            delay_dig = int(s.get("robo", {}).get("delay_digitacao_ms", _DELAY_DIGITACAO))
            tela = Tela(page, job, pasta_shots, delay_digitacao=delay_dig)

            # ---- 1. abrir direto o formulario de eBook novo + checar login ----
            job.marcar_etapa("abrir", "Abrindo o formulário de eBook novo na Hotmart...")
            page.goto(hm.URL_CRIAR_EBOOK, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            # rede de seguranca: se caiu no login (com dados ja preenchidos), entra sozinho
            if any(m in page.url for m in hm.MARCADORES_LOGIN):
                job.log("Caiu na tela de login — tentando entrar (dados já preenchidos)...", "aviso")
                try:
                    tela.clicar("btn_entrar_login")
                    page.wait_for_timeout(4000)
                    page.goto(hm.URL_CRIAR_EBOOK, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                except RoboError:
                    pass
            if any(m in page.url for m in hm.MARCADORES_LOGIN):
                tela.shot("erro_login")
                raise RoboError(
                    "Ainda está na tela de login. Vá na janela do robô (já aberta), "
                    "faça o login na Hotmart e clique publicar de novo."
                )
            tela.shot("inicio")

            # ---- 2. informacoes basicas (ja estamos nela) ------------------
            job.marcar_etapa("informacoes_basicas", "Preenchendo informações básicas...")
            # espera a SPA terminar de carregar ANTES de digitar (senao a Hotmart
            # 'reseta' o form logo apos o 1o campo e apaga o Nome).
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            tela.preencher("campo_nome", item["titulo"])
            tela.preencher("campo_descricao", item["descricao"])
            idioma_txt = hm.idioma_hotmart(item["codigo"])
            if idioma_txt == hm.IDIOMA_FALLBACK and item["codigo"] not in hm.IDIOMA_HOTMART:
                job.log(f"Idioma '{item['pais']}' não existe no dropdown da Hotmart — usando English.", "aviso")
            tela.escolher_opcao("campo_idioma", idioma_txt)
            tela.escolher_opcao("campo_pais", hm.PAIS_HOTMART[item["codigo"]])
            # capa: o campo #cover aceita SO 1 imagem (a capa do produto).
            if item.get("capa") and Path(item["capa"]).is_file():
                tela.upload("input_capa", item["capa"])
                job.log("Capa enviada.")
                page.wait_for_timeout(2500)   # capa precisa anexar antes de seguir
            else:
                job.log("Sem capa pra esse idioma — imagem pulada.", "aviso")
            # imagens de bonus/extra NAO cabem no campo de capa (aceita 1 so)
            imgs_anexo = [a for a in item.get("anexos", [])
                          if a.get("capa") and Path(a["capa"]).is_file()]
            if imgs_anexo:
                job.log(f"{len(imgs_anexo)} imagem(ns) de bônus/extra não entram no campo "
                        "de capa (ele aceita 1 imagem só) — confira se precisam ir noutro lugar.", "aviso")
            tela.clicar_por_texto(s["hotmart"]["categoria"])  # categoria = chip/botao
            tela.shot("basico_preenchido")

            # ---- 2b. conferir se a Hotmart nao resetou nada (o Nome some as vezes) ----
            job.marcar_etapa("conferir", "Conferindo se a Hotmart não apagou nenhum campo...")
            tela.garantir_valor("campo_nome", item["titulo"])
            tela.garantir_valor("campo_descricao", item["descricao"])
            tela.shot("basico_conferido")

            if ensaio:
                job.log("ENSAIO: primeira tela preenchida e conferida. Parando aqui sem "
                        "avançar — confira os prints em data/publicacoes.", "ok")
                return

            tela.clicar("btn_avancar_basico")
            page.wait_for_timeout(2500)   # troca de tela (basico -> preco)

            # ---- 4. preco ---------------------------------------------------
            # Regra: todos em Dolar, SO o Brasil em Real.
            if item["codigo"] == "pt-br":
                moeda_txt, sigla = "Real Brasileiro", "BRL"
            else:
                moeda_txt, sigla = "Dólar Americano", "USD"
            job.marcar_etapa("preco", f"Definindo preço: {sigla} {item['preco']:.2f}...")
            tela.escolher_opcao("campo_moeda", moeda_txt)
            job.lap("preco: select moeda")
            # prazo de reembolso: a Hotmart JÁ VEM com o padrão selecionado — não
            # mexemos (evita ~25s e o erro de 'campo não encontrado').
            # forma de pagamento: sempre à vista
            tela.escolher_opcao("campo_forma_pagamento", "Pagamento à vista")
            job.lap("preco: select forma pagamento")
            valor = f"{item['preco']:.2f}".replace(".", ",")
            tela.preencher("campo_valor", valor)
            tela.shot("preco")
            tela.clicar("btn_salvar_continuar")
            job.lap("preco: digitar valor + salvar")
            page.wait_for_timeout(2500)   # salva o preco + troca pra area de membros

            # ---- 4b. area de membros: Club com espaco (<300) + Criar produto ----
            job.marcar_etapa("area_membros", "Área de Membros: escolhendo o Club com espaço...")
            page.wait_for_timeout(1500)
            tela.selecionar_club_com_espaco(limite=300)
            tela.shot("club_escolhido")
            tela.clicar("btn_criar_produto_final")
            job.log("Produto criado (rascunho). Indo pro painel...")
            page.wait_for_timeout(4000)   # cria o produto de fato + navega

            # ---- 4c. tela "Criado com sucesso" -> Painel do produto ----------
            try:
                tela.clicar("btn_ir_painel")
                page.wait_for_timeout(3500)   # navega pro painel (e captura o ID)
            except RoboError:
                job.log("Sem 'Ir para o painel' — seguindo (talvez já no painel).", "aviso")
            # captura o ID do produto na Hotmart (da URL /products/manage/NNNN)
            import re as _re
            m_id = _re.search(r"/products/manage/(\d+)", page.url)
            if m_id:
                job.hotmart_id = m_id.group(1)
                job.log(f"Produto na Hotmart: ID {job.hotmart_id}")

            # ---- 5. conteudo do produto: menu lateral -> upload dos PDFs ------
            # o cliente ve o NOME DO ARQUIVO: principal -> titulo traduzido do
            # produto; cada bonus -> titulo traduzido DELE (cai pro PT ou pro
            # titulo do principal se o bonus nao tiver titulo).
            titulo_cliente = item["titulo"] or produto["titulo_pt"]
            uploads = [(item["pdf"], titulo_cliente)]
            for a in item.get("anexos", []):
                if a.get("pdf") and Path(a["pdf"]).is_file():
                    nome_anexo = a.get("titulo") or a.get("titulo_pt") or titulo_cliente
                    uploads.append((a["pdf"], nome_anexo))
            n_anexos = len(uploads) - 1
            job.marcar_etapa("conteudo",
                             f"Subindo {len(uploads)} PDF(s): principal"
                             + (f" + {n_anexos} anexo(s)" if n_anexos else "") + "...")
            tela.ir_para_conteudo()
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            tela.upload_conteudo(uploads)  # sobe 1 por vez, renomeado, e espera cada um
            job.log(f"{len(uploads)} arquivo(s) enviado(s) ✔")
            tela.shot("pdf_enviado")

            # ---- 6. coproducao (1 ou 2 coprodutores, em SEQUENCIA) -----------
            coprodutores = [c for c in (s.get("coproducao", {}), s.get("coproducao2", {}))
                            if (c.get("email") or "").strip()]
            if not coprodutores:
                job.log("Sem coprodutor configurado — etapa pulada.")
            codigos_usados: set[str] = set()  # códigos 2FA já usados (não repetir no 2º)
            for n_cop, coprod in enumerate(coprodutores, 1):
                if n_cop > 1:
                    # intervalo entre convites: o código 2FA do 2º precisa chegar
                    # DEPOIS do 1º no Gmail — sem isso os códigos se misturam
                    job.log("Aguardando 40s antes do próximo convite (pra não misturar os códigos 2FA)...")
                    page.wait_for_timeout(40_000)
                job.marcar_etapa("coproducao",
                                 f"Coprodução {n_cop}/{len(coprodutores)}: {coprod['email']} ({coprod['percentual']}%)...")
                tela.ir_para_coproducao()
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)
                # a lista de coproducoes carrega async — espera o botao aparecer (ate 20s)
                if not tela.existe_texto("Convidar", timeout=20000):
                    job.log("A tela de Coproduções demorou a carregar — tentando mesmo assim...", "aviso")
                job.lap("coprod: abrir tela + carregar lista")
                if tela.existe_texto(coprod["email"]) and tela.existe_texto("Pendente"):
                    job.log(f"Já existe convite Pendente pra {coprod['email']} — pulando (evita duplicar).", "aviso")
                    continue
                tela.clicar("btn_convidar_coprodutor", timeout=15000)
                page.wait_for_timeout(1000)
                tela.preencher("campo_email_coprodutor", coprod["email"])
                job.lap("coprod: abrir form + email")
                tela.escolher_opcao("campo_atuacao", "Sócio do produto")
                job.lap("coprod: select 'Sócio do produto'")
                # o campo de % preenche da direita p/ esquerda (money): pra mostrar
                # "P,00" digitamos os digitos de P*100 (ex.: 10 -> "1000" -> "10,00").
                digitos_pct = str(int(round(float(coprod["percentual"]) * 100)))
                tela.preencher("campo_percentual", digitos_pct)
                job.lap("coprod: digitar percentual")
                # modelo de coproducao: "parceria de negocio"
                tela.clicar_por_texto("Modelo de parceria de negócio")
                job.lap("coprod: click 'Modelo parceria'")
                tela.clicar("check_termos")
                job.lap("coprod: click termos")
                tela.shot(f"coproducao_{n_cop}_preenchida")
                tela.clicar("btn_enviar_convite")  # "Continuar" -> tela de revisão
                job.lap("coprod: enviar (Continuar)")
                page.wait_for_timeout(2500)   # troca pra tela de revisao do convite
                # ---- tela de revisão: concordar -> digitar código 2FA -> enviar ----
                job.marcar_etapa("coproducao_revisao",
                                 f"Revisão do convite {n_cop} — vou pedir o código 2FA...")
                inicio_2fa = time.time()
                tela.clicar_por_texto("Li e concordo com as informações")
                tela.shot(f"coproducao_{n_cop}_revisao")
                job.lap("revisao: concordar")
                codigo = _obter_codigo_2fa(job, s, desde_ts=inicio_2fa, ignorar=codigos_usados)
                job.lap("revisao: ESPERAR o e-mail do 2FA")
                tela.preencher("campo_codigo_2fa", codigo)
                codigos_usados.add(codigo)
                tela.shot(f"codigo_{n_cop}_preenchido")
                tela.clicar("btn_enviar_convite_final", timeout=15000)  # envia com o código
                job.lap("revisao: enviar convite com código")
                page.wait_for_timeout(3000)   # submete o convite com o 2FA
                tela.shot(f"coproducao_{n_cop}_enviada")
                if tela.existe_texto("erro", timeout=2000):
                    job.log("A Hotmart acusou erro na verificação do convite — o convite pode ter "
                            "entrado como Pendente mesmo assim (confira depois). Seguindo em frente.", "aviso")

            # ---- 7. cupom no PRINCIPAL — ANTES de finalizar (depois de enviar
            # pra análise a tela pode travar a criação). Best-effort: se falhar,
            # vira aviso com print e o fluxo segue pro finalizar mesmo assim.
            c_cfg = s.get("cupom", {})
            if c_cfg.get("ativo") and produto.get("tipo") == "Principal":
                try:
                    job.marcar_etapa("cupom",
                                     f"Criando cupom '{c_cfg.get('codigo')}' ({c_cfg.get('desconto')}%) na tela de Cupons...")
                    tela.criar_cupom_ui(str(c_cfg.get("codigo") or ""),
                                        int(float(c_cfg.get("desconto", 10) or 10)))
                    job.log(f"Cupom '{c_cfg.get('codigo')}' criado e conferido na lista ✔", "ok")
                except Exception as e:
                    tela.shot("erro_cupom")
                    job.log(f"Cupom: não consegui criar clicando ({str(e)[:150]}) — "
                            "seguindo pro Finalizar mesmo assim; crie o cupom na mão e "
                            "me mande o print da tela pra eu calibrar.", "aviso")

            # ---- 8. finalizar (direto, sem pausa) ---------------------------
            job.marcar_etapa("finalizar", "Voltando ao Painel e finalizando o cadastro...")
            tela.clicar("menu_painel")
            page.wait_for_timeout(2000)
            tela.shot("painel_final")
            # SÓ segue como publicado se a Hotmart confirmar de verdade. Se nao
            # confirmar, levanta erro -> o produto fica como 'erro' (nao entra no
            # historico como publicado). Nunca mais "publicou" sem finalizar.
            if not tela.finalizar_cadastro():
                tela.shot("erro_finalizar")
                raise RoboError(
                    "Cliquei em 'Finalizar Cadastro' mas a Hotmart não confirmou "
                    "('Enviado para aprovação'). O produto NÃO foi finalizado — ficou "
                    "como rascunho. Veja o print em data/publicacoes e finalize na mão "
                    "(confira se o botão não está atrás do balão de chat)."
                )
            job.log("Cadastro finalizado — enviado para aprovação ✔", "ok")
            tela.shot("finalizado")

            # ---- medição: onde o tempo foi gasto (aparece no painel e em arquivo) ----
            resumo = job.resumo_tempos()
            if resumo:
                job.log(resumo, "ok")
                try:
                    (pasta_shots / "tempos.txt").write_text(resumo, encoding="utf-8")
                except OSError:
                    pass
        finally:
            # NAO fecha a janela — ela fica aberta e logada pra proxima publicacao.
            # O Chrome foi aberto por nos (subprocess), fora do Playwright; ao sair
            # do 'with sync_playwright' so o controle CDP e desconectado.
            pass


def _posicionar_imagem_topo(tela: Tela, page) -> None:
    """Depois do 'Inserir', o chip 'Imagem' fica GRUDADO no cursor (print do
    usuário) — não é drag&drop: é LEVAR o mouse até o slot do topo e CLICAR
    pra soltar. Move gradualmente (o chip segue o cursor) e clica no slot."""
    alvo = None
    try:
        el = tela._localizar("ck_slot_vazio", timeout=4000)
        alvo = el.bounding_box()
    except Exception:
        pass
    if alvo is None:
        raise RoboError("não achei o slot do topo pra soltar a imagem")
    tx = alvo["x"] + alvo["width"] / 2
    ty = alvo["y"] + alvo["height"] / 2
    # parte de baixo do canvas e sobe ate o slot, em passos (chip segue o mouse)
    sx, sy = tx, ty + 300
    page.mouse.move(sx, sy)
    page.wait_for_timeout(200)
    passos = 10
    for n in range(1, passos + 1):
        page.mouse.move(sx + (tx - sx) * n / passos, sy + (ty - sy) * n / passos)
        page.wait_for_timeout(50)
    page.wait_for_timeout(500)   # deixa o slot "acender"
    page.mouse.click(tx, ty)     # solta o componente no slot
    page.wait_for_timeout(1200)


def _clicar_aplicar_cor(tela: Tela, page, vezes: int = 3) -> None:
    """Clica os 'Aplicar' do Background na ORDEM CERTA: do ÚLTIMO do DOM pro
    primeiro. Com o picker aberto ha DOIS 'Aplicar' — o do picker é popup
    (fim do DOM); clicar o do painel primeiro NAO confirma a cor (era o bug)."""
    import re
    alvo = re.compile(r"^\s*Aplicar\s*$", re.I)
    for _ in range(vezes):
        clicado = False
        for ctx in tela._contextos():
            try:
                btns = ctx.get_by_role("button", name=alvo)
                for i in range(btns.count() - 1, -1, -1):   # ultimo -> primeiro
                    b = btns.nth(i)
                    try:
                        if b.is_visible():
                            b.click(timeout=2500)
                            clicado = True
                            break
                    except Exception:
                        continue
            except Exception:
                continue
            if clicado:
                break
        if not clicado:
            return
        page.wait_for_timeout(900)


# ---------------------------------------------------------------------------
# Executor de CHECKOUT (custom-checkout.hotmart.com) — monta a pagina de
# pagamento de um Principal publicado e captura o link pay.hotmart.com
# ---------------------------------------------------------------------------
def _executar_checkout(job: Job, produto: dict, item: dict) -> None:
    from playwright.sync_api import sync_playwright

    from core import config as cfg
    s = cfg.carregar_settings()

    pasta_shots = PASTA_PUBLICACOES / job.produto_id / f"checkout_{item['codigo']}"
    pasta_shots.mkdir(parents=True, exist_ok=True)

    bumps = _bumps_do_checkout(produto, item["codigo"])
    imagem = _imagem_checkout(produto.get("pasta", ""), item["codigo"])
    texto_cont = hm.texto_contagem(item["codigo"])
    # no builder nao tem o anti-bot do cadastro — digitacao rapida (descricoes longas)
    DELAY_CK = 8

    job.estado = "rodando"
    with sync_playwright() as p:
        browser, page = _conectar(p)
        try:
            page.set_default_timeout(20000)
            tela = Tela(page, job, pasta_shots,
                        delay_digitacao=int(s.get("robo", {}).get("delay_digitacao_ms", _DELAY_DIGITACAO)))

            # ---- 1. abrir o builder e achar o produto -----------------------
            job.marcar_etapa("ck_abrir", f"Abrindo o builder de checkout ({item['pais']})...")
            page.goto(hm.URL_CUSTOM_CHECKOUT, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if any(m in page.url for m in hm.MARCADORES_LOGIN):
                tela.shot("ck_erro_login")
                raise RoboError("Caiu na tela de login — entre na Hotmart na janela do robô e tente de novo.")
            tela.preencher("ck_busca", item["titulo"], delay=DELAY_CK)
            page.wait_for_timeout(2000)
            # clica no card do produto (o titulo aparece no resultado da busca)
            tela.clicar_por_texto(item["titulo"][:60], exato=False)
            page.wait_for_timeout(2000)
            tela.shot("ck_produto")

            # ---- 2. nova pagina em branco -----------------------------------
            job.marcar_etapa("ck_nova_pagina", "Criando nova página (Em Branco)...")
            tela.clicar("ck_btn_criar_pagina", timeout=10000)
            page.wait_for_timeout(1500)
            tela.clicar_por_texto("Em Branco")
            page.wait_for_timeout(2500)
            tela.shot("ck_editor")

            # ---- 3. order bumps (um componente por bump) --------------------
            for n_b, bump in enumerate(bumps, 1):
                job.marcar_etapa("ck_bump",
                                 f"Order Bump {n_b}/{len(bumps)}: {bump['titulo'][:45]}...")
                tela.clicar_por_texto("Order Bump")
                page.wait_for_timeout(800)
                tela.clicar("ck_btn_escolher_produto", timeout=10000)
                page.wait_for_timeout(800)
                tela.preencher("ck_busca", bump["titulo"], delay=DELAY_CK)
                page.wait_for_timeout(1500)
                # o resultado vem RECOLHIDO (accordion) — expande o card antes
                # do radio "Preço base" existir na tela
                try:
                    tela.clicar_por_texto(bump["titulo"][:60], exato=False, timeout=8000)
                except RoboError:
                    tela.clicar("ck_card_resultado", timeout=5000)  # fallback: 1o card
                page.wait_for_timeout(800)
                tela.clicar("ck_radio_preco_base", timeout=10000)  # oferta "Preço base"
                tela.clicar("ck_btn_selecionar", timeout=8000)
                page.wait_for_timeout(800)
                # preco "de" fixo 89,90 — money-input direita->esquerda: "8990"
                tela.preencher("ck_campo_preco_de", "8990")
                tela.preencher("ck_campo_descricao", bump["descricao"], delay=DELAY_CK)
                tela.shot(f"ck_bump_{n_b}")
                tela.clicar("ck_btn_inserir", timeout=8000)
                page.wait_for_timeout(1200)
            if not bumps:
                job.log("Nenhum Order Bump publicado nesse idioma — página sai sem bumps.", "aviso")

            # ---- 4. fundo preto ---------------------------------------------
            job.marcar_etapa("ck_background", "Background: cor de fundo preta (#000000)...")
            tela.clicar_por_texto("Background")
            page.wait_for_timeout(800)
            tela.clicar("ck_btn_color_trigger", timeout=8000)
            page.wait_for_timeout(500)
            tela.preencher("ck_campo_color_hex", "#000000", delay=DELAY_CK)
            # DOIS Aplicar obrigatorios (picker E painel) — na ordem certa:
            # o do picker (popup, fim do DOM) PRIMEIRO, depois o do painel
            _clicar_aplicar_cor(tela, page)
            page.wait_for_timeout(800)
            tela.shot("ck_fundo")

            # ---- 5. imagem do pais (pasta ZPAG DE CHECKOUT) -----------------
            if imagem:
                job.marcar_etapa("ck_imagem", f"Imagem do checkout: {Path(imagem).name}...")
                tela.clicar_por_texto("Imagem")
                page.wait_for_timeout(800)
                tela._localizar("ck_input_imagem", timeout=8000).set_input_files(imagem)
                page.wait_for_timeout(2000)
                tela.clicar("ck_btn_aplicar", timeout=10000)   # modal "Cortar imagem"
                page.wait_for_timeout(1000)
                tela.clicar("ck_btn_inserir", timeout=8000)
                page.wait_for_timeout(1500)
                # o chip 'Imagem' fica preso no cursor — leva ate o slot do
                # topo e CLICA pra soltar (best-effort, nunca derruba)
                try:
                    _posicionar_imagem_topo(tela, page)
                    tela.shot("ck_imagem_posicionada")
                except Exception as e:
                    tela.shot("ck_erro_drag")
                    job.log(f"Não consegui posicionar a imagem no topo ({str(e)[:100]}) — "
                            "posiciona na mão; me manda o print do momento do encaixe "
                            "que eu calibro.", "aviso")
            else:
                job.log(f"Sem imagem de checkout pra {item['pais']} na pasta da rede "
                        "(procurei subpasta com 'checkout' no nome) — página sai sem imagem.", "aviso")

            # ---- 6. contagem regressiva -------------------------------------
            job.marcar_etapa("ck_contagem", f"Contagem regressiva: \"{texto_cont}\"...")
            tela.clicar_por_texto("Contagem Regressiva")
            page.wait_for_timeout(800)
            tela.preencher("ck_campo_countdown_ativo", texto_cont, delay=DELAY_CK)
            tela.preencher("ck_campo_countdown_zerado", texto_cont, delay=DELAY_CK)
            tela.clicar("ck_btn_inserir", timeout=8000)
            page.wait_for_timeout(1200)
            tela.shot("ck_contagem")

            # ---- 7. copiar pro celular + salvar + publicar ------------------
            job.marcar_etapa("ck_publicar", "Copiando pro celular, salvando e publicando...")
            try:
                tela.clicar("ck_btn_visao_celular", timeout=5000)
                page.wait_for_timeout(1000)
            except RoboError:
                job.log("Botão da visão celular não achado — seguindo direto pro Copiar celular.", "aviso")
            tela.clicar("ck_btn_copiar_celular", timeout=8000)
            page.wait_for_timeout(1200)
            tela.clicar("ck_btn_salvar_pagina", timeout=10000)
            page.wait_for_timeout(2000)
            tela.clicar("ck_btn_publicar_pagina", timeout=10000)
            page.wait_for_timeout(1500)
            tela.clicar("ck_btn_atualizar_publicacao", timeout=10000)
            page.wait_for_timeout(2000)
            tela.shot("ck_publicado")

            # ---- 8. capturar o LINK (input da tela de sucesso) --------------
            link = tela.capturar_link_pagamento(timeout=15000)
            if link:
                job.link_checkout = link
                job.log(f"Link do checkout capturado: {link}", "ok")
            tela.shot("ck_final")

            resumo = job.resumo_tempos()
            if resumo:
                job.log(resumo, "ok")
                try:
                    (pasta_shots / "tempos.txt").write_text(resumo, encoding="utf-8")
                except OSError:
                    pass
        finally:
            pass  # janela fica aberta (mesma regra do publicador)


# ---------------------------------------------------------------------------
# Janela de login (primeira configuracao do perfil)
# ---------------------------------------------------------------------------
def abrir_login() -> None:
    """Abre (ou reusa) a janela do Chrome do robo na Hotmart pro operador logar.
    A janela FICA ABERTA — o robo se conecta nela na hora de publicar, entao o
    login vale pra todas as publicacoes (mesma janela, sem relogar)."""
    global _JOB
    with _TRAVA:
        if _JOB is not None and _JOB.estado in ESTADOS_ATIVOS:
            raise RoboError("Tem uma publicação em andamento — feche antes de abrir o login.")
    garantir_chrome(hm.URL_APP)
