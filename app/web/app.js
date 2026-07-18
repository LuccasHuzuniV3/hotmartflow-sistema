/* ============ HotmartFlow — UI ============ */
"use strict";

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------
const estado = {
  settings: null,
  produtos: [],
  scan: null,
  scanPasta: "",
  abertos: new Set(),      // ids de produtos com card expandido
  ocupados: new Set(),     // chaves "pid" ou "pid:codigo" com operacao em andamento
  publicandoFila: false,   // fila "Publicar todos" em andamento
  filaCancelada: false,    // pediram pra cancelar a fila
};

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function api(metodo, url, body) {
  const opts = { method: metodo, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

let toastTimer = null;
function toast(msg, tipo = "") {
  const t = $("toast");
  t.textContent = msg;
  t.className = `toast mostrar ${tipo}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 4200);
}

// ms -> "1h 23m 45s" / "12m 05s" / "45s" (rede pode levar horas)
function fmtDuracao(ms) {
  const s = Math.floor(Math.max(0, ms) / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const seg = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  if (h > 0) return `${h}h ${pad(m)}m ${pad(seg)}s`;
  if (m > 0) return `${m}m ${pad(seg)}s`;
  return `${seg}s`;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

const ROTULO_STATUS = {
  rascunho: "rascunho",
  textos_gerados: "textos gerados",
  revisado: "revisado ✓",
  publicando: "publicando…",
  publicado: "publicado ✓",
  erro: "erro",
};

// ---------------------------------------------------------------------------
// Abas
// ---------------------------------------------------------------------------
document.querySelectorAll(".aba").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".aba").forEach((b) => b.classList.remove("ativa"));
    btn.classList.add("ativa");
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("visivel"));
    $(`tab-${btn.dataset.aba}`).classList.add("visivel");
    if (btn.dataset.aba === "historico") carregarHistorico();
  });
});

// ---------------------------------------------------------------------------
// Histórico de publicações
// ---------------------------------------------------------------------------
const ORDEM_TIPO_HIST = { "Principal": 0, "Order Bump": 1, "Upsell": 2 };
// o tipo agora pode vir com numero ("Upsell 1"); separa base e numero pra ordenar
function ordemTipoHist(tipo) {
  const base = String(tipo || "").replace(/\s*\d+\s*$/, "").trim();
  return ORDEM_TIPO_HIST[base] ?? 9;
}
function numeroTipoHist(tipo) {
  const m = String(tipo || "").match(/(\d+)\s*$/);
  return m ? parseInt(m[1], 10) : 0;
}

async function carregarHistorico() {
  carregarCheckouts();  // roda em paralelo — não bloqueia o histórico
  let r;
  try { r = await api("GET", "/api/historico"); } catch (e) { toast(e.message, "erro"); return; }
  $("hist-resumo").textContent = r.total
    ? `${r.total} publicação(ões) registradas`
    : "Nada publicado ainda — o histórico é preenchido quando você publica de verdade.";
  const box = $("hist-arvore");
  const redes = Object.keys(r.arvore).sort();
  if (!redes.length) { box.innerHTML = ""; return; }
  box.innerHTML = redes.map((rede) => {
    const paises = r.arvore[rede];
    const totalRede = Object.values(paises).reduce((a, arr) => a + arr.length, 0);
    const nomesPaises = Object.keys(paises).sort();
    const corpo = nomesPaises.map((pais) => {
      const itens = [...paises[pais]].sort((a, b) =>
        (ordemTipoHist(a.tipo) - ordemTipoHist(b.tipo))
        || (numeroTipoHist(a.tipo) - numeroTipoHist(b.tipo))
        || String(a.titulo).localeCompare(b.titulo));
      const linhas = itens.map((it) => `
        <div class="hist-item">
          <span class="chip tipo">${esc(it.tipo)}</span>
          <span class="h-tit">${esc(it.titulo)}</span>
          ${it.hotmart_id ? `<span class="h-id"><a href="https://app.hotmart.com/products/manage/${esc(it.hotmart_id)}" target="_blank">#${esc(it.hotmart_id)}</a></span>` : ""}
          <span class="h-quando">${esc((it.quando || "").replace("T", " "))}</span>
          <button class="btn mini h-del" title="Excluir este registro"
            data-hist-del="${encodeURIComponent(JSON.stringify({ rede, pais, titulo: it.titulo, tipo: it.tipo, quando: it.quando }))}">🗑</button>
        </div>`).join("");
      return `<div class="hist-pais"><div class="pais-nome">${esc(pais)} <small>(${itens.length})</small></div>${linhas}</div>`;
    }).join("");
    return `<div class="hist-rede"><h3>${esc(rede)} <small>${totalRede} publicação(ões)</small></h3>${corpo}</div>`;
  }).join("");
}

async function carregarCheckouts() {
  const bloco = $("ck-bloco");
  let r;
  try { r = await api("GET", "/api/checkouts"); } catch (_) { bloco.classList.add("oculto"); return; }
  if (!r.total) { bloco.classList.add("oculto"); return; }
  bloco.classList.remove("oculto");
  const redes = Object.keys(r.arvore).sort();
  $("ck-arvore").innerHTML = redes.map((rede) => {
    const paises = r.arvore[rede];
    const corpo = Object.keys(paises).sort().map((pais) =>
      paises[pais].map((it) => `
        <div class="hist-item">
          <span class="chip tipo">${esc(pais)}</span>
          <span class="h-tit">${esc(it.titulo)}</span>
          <a class="ck-link" href="${esc(it.link)}" target="_blank">${esc(it.link)}</a>
          <button class="btn mini" data-ck-link="${esc(it.link)}" title="Copiar o link">📋</button>
          <span class="h-quando">${esc((it.quando || "").replace("T", " "))}</span>
          <button class="btn mini h-del" title="Excluir este link"
            data-ck-del="${encodeURIComponent(JSON.stringify({ link: it.link, quando: it.quando }))}">🗑</button>
        </div>`).join("")
    ).join("");
    const total = Object.values(paises).reduce((a, arr) => a + arr.length, 0);
    return `<div class="hist-rede"><h3>${esc(rede)} <small>${total} link(s)</small></h3>${corpo}</div>`;
  }).join("");
}

$("ck-arvore").addEventListener("click", async (e) => {
  const del = e.target.closest("[data-ck-del]");
  if (del) {
    const reg = JSON.parse(decodeURIComponent(del.dataset.ckDel));
    if (!confirm(`Excluir este link de checkout?\n${reg.link}`)) return;
    try {
      const r = await api("POST", "/api/checkouts/remover", reg);
      toast(r.ok ? "Link excluído ✓" : "Link não encontrado (já removido?).", r.ok ? "ok" : "erro");
      carregarCheckouts();
    } catch (err) { toast(err.message, "erro"); }
    return;
  }
  const btn = e.target.closest("[data-ck-link]");
  if (!btn) return;
  try {
    await navigator.clipboard.writeText(btn.dataset.ckLink);
    toast("Link copiado 📋", "ok");
  } catch (_) { toast("Não consegui copiar — copie manualmente.", "erro"); }
});

$("hist-arvore").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-hist-del]");
  if (!btn) return;
  const reg = JSON.parse(decodeURIComponent(btn.dataset.histDel));
  if (!confirm(`Excluir do histórico:\n${reg.tipo} — ${reg.pais}\n${reg.titulo}?`)) return;
  try {
    const r = await api("POST", "/api/historico/remover-registro", reg);
    toast(r.ok ? "Registro excluído ✓" : "Registro não encontrado (já removido?).", r.ok ? "ok" : "erro");
    carregarHistorico();
  } catch (err) { toast(err.message, "erro"); }
});

$("btn-hist-atualizar").addEventListener("click", carregarHistorico);
$("btn-hist-limpar").addEventListener("click", async () => {
  if (!confirm("Limpar TODO o histórico de publicações?\n(Vira um backup — dá pra voltar pelo botão ♻️ Recuperar. Nada muda na Hotmart.)")) return;
  try {
    const r = await api("DELETE", "/api/historico");
    toast(`${r.removidos} registro(s) movidos pro backup (♻️ Recuperar traz de volta).`, "ok");
    carregarHistorico();
  } catch (e) { toast(e.message, "erro"); }
});

$("btn-hist-recuperar").addEventListener("click", async () => {
  const btn = $("btn-hist-recuperar");
  btn.disabled = true;
  try {
    const r = await api("POST", "/api/historico/recuperar");
    const partes = [];
    if (r.do_backup) partes.push(`${r.do_backup} do backup`);
    if (r.reconstruidos) partes.push(`${r.reconstruidos} reconstruído(s) da fila`);
    toast(partes.length
      ? `Histórico recuperado: ${partes.join(" + ")} ✓ (total ${r.total})`
      : "Nada pra recuperar — sem backup e sem publicados na fila.",
      partes.length ? "ok" : "");
    carregarHistorico();
  } catch (e) { toast(e.message, "erro"); }
  finally { btn.disabled = false; }
});

// ---------------------------------------------------------------------------
// Status da API key
// ---------------------------------------------------------------------------
async function atualizarStatusKey() {
  try {
    const s = await api("GET", "/api/status");
    const box = $("status-key");
    box.className = `status-key ${s.pronto ? "ok" : "falta"}`;
    if (s.pronto) {
      $("status-key-texto").textContent = s.provider === "agy" ? `agy ok (${s.detalhe})` : "OpenAI ok";
    } else {
      $("status-key-texto").textContent = s.detalhe || "IA não configurada";
    }
  } catch (_) { /* servidor caindo — ignora */ }
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
function atualizarGruposProvider() {
  const prov = $("cfg-provider").value;
  $("grupo-agy").classList.toggle("oculto-cfg", prov !== "agy");
  $("grupo-openai").classList.toggle("oculto-cfg", prov !== "openai");
}

$("cfg-provider").addEventListener("change", atualizarGruposProvider);

async function carregarConfig() {
  estado.settings = await api("GET", "/api/settings");
  const s = estado.settings;
  $("cfg-provider").value = s.provider || "agy";
  $("cfg-agy-model").value = (s.agy && s.agy.model) || "";
  $("cfg-api-key").value = s.openai.api_key;
  $("cfg-model").value = s.openai.model;
  atualizarGruposProvider();
  $("cfg-tom").value = s.descricao.tom;
  $("cfg-tam-min").value = s.descricao.tamanho_min;
  $("cfg-tam-max").value = s.descricao.tamanho_max;
  $("cfg-traduzir-simultaneas").value = s.traduzir_simultaneas || 15;
  $("cfg-coprod-email").value = s.coproducao.email;
  $("cfg-coprod-pct").value = s.coproducao.percentual;
  $("cfg-coprod2-email").value = (s.coproducao2 && s.coproducao2.email) || "";
  $("cfg-coprod2-pct").value = (s.coproducao2 && s.coproducao2.percentual) || 45;
  $("cfg-cupom-ativo").checked = !!(s.cupom && s.cupom.ativo);
  $("cfg-cupom-codigo").value = (s.cupom && s.cupom.codigo) || "";
  $("cfg-cupom-desconto").value = (s.cupom && s.cupom.desconto) || 10;
  $("cfg-delay-digitacao").value = (s.robo && s.robo.delay_digitacao_ms != null) ? s.robo.delay_digitacao_ms : 45;
  $("cfg-cdp-port").value = (s.robo && s.robo.cdp_port) || 9222;
  $("cfg-gmail-auto").checked = !!(s.gmail && s.gmail.auto);
  $("cfg-gmail-email").value = (s.gmail && s.gmail.email) || "";
  $("cfg-gmail-senha").value = (s.gmail && s.gmail.app_password) || "";

  const grid = $("cfg-precos");
  grid.innerHTML = Object.entries(s.precos).map(([tipo, preco]) => `
    <div class="campo">
      <label>${esc(tipo)}</label>
      <input type="number" step="0.10" min="0" data-preco-tipo="${esc(tipo)}" value="${preco}">
    </div>`).join("");

  const gridBr = $("cfg-precos-brasil");
  gridBr.innerHTML = Object.entries(s.precos_brasil || {}).map(([tipo, preco]) => `
    <div class="campo">
      <label>${esc(tipo)}</label>
      <input type="number" step="0.10" min="0" data-preco-br-tipo="${esc(tipo)}" value="${preco}">
    </div>`).join("");

  // deixa o campo ja preenchido com a ultima pasta usada (sem lista de historico)
  const ultima = (s.pastas_recentes || [])[0];
  if (ultima && !$("scan-pasta").value) $("scan-pasta").value = ultima;
}

$("btn-salvar-config").addEventListener("click", async () => {
  const precos = {};
  document.querySelectorAll("[data-preco-tipo]").forEach((inp) => {
    precos[inp.dataset.precoTipo] = parseFloat(inp.value || "0");
  });
  const precos_brasil = {};
  document.querySelectorAll("[data-preco-br-tipo]").forEach((inp) => {
    precos_brasil[inp.dataset.precoBrTipo] = parseFloat(inp.value || "0");
  });
  const patch = {
    provider: $("cfg-provider").value,
    agy: { model: $("cfg-agy-model").value.trim() },
    openai: { api_key: $("cfg-api-key").value.trim(), model: $("cfg-model").value.trim() || "gpt-4o" },
    precos,
    precos_brasil,
    descricao: {
      tom: $("cfg-tom").value.trim(),
      tamanho_min: parseInt($("cfg-tam-min").value || "400", 10),
      tamanho_max: parseInt($("cfg-tam-max").value || "900", 10),
    },
    traduzir_simultaneas: parseInt($("cfg-traduzir-simultaneas").value || "15", 10),
    coproducao: {
      email: $("cfg-coprod-email").value.trim(),
      percentual: parseInt($("cfg-coprod-pct").value || "45", 10),
    },
    coproducao2: {
      email: $("cfg-coprod2-email").value.trim(),
      percentual: parseInt($("cfg-coprod2-pct").value || "45", 10),
    },
    cupom: {
      ativo: $("cfg-cupom-ativo").checked,
      codigo: $("cfg-cupom-codigo").value.trim(),
      desconto: parseInt($("cfg-cupom-desconto").value || "10", 10),
    },
    robo: {
      delay_digitacao_ms: parseInt($("cfg-delay-digitacao").value || "45", 10),
      cdp_port: parseInt($("cfg-cdp-port").value || "9222", 10),
    },
    gmail: {
      auto: $("cfg-gmail-auto").checked,
      email: $("cfg-gmail-email").value.trim(),
      app_password: $("cfg-gmail-senha").value.trim(),
    },
  };
  try {
    estado.settings = await api("POST", "/api/settings", patch);
    $("config-feedback").textContent = "Configurações salvas ✓";
    setTimeout(() => ($("config-feedback").textContent = ""), 3000);
    atualizarStatusKey();
  } catch (e) { toast(e.message, "erro"); }
});

// ---------------------------------------------------------------------------
// Scan / importação
// ---------------------------------------------------------------------------
$("btn-escanear").addEventListener("click", escanear);
$("scan-pasta").addEventListener("keydown", (e) => { if (e.key === "Enter") escanear(); });

$("btn-escolher-pasta").addEventListener("click", async () => {
  const btn = $("btn-escolher-pasta");
  btn.classList.add("ocupado"); btn.disabled = true;
  try {
    const r = await api("POST", "/api/escolher-pasta");
    if (r.pasta) {
      $("scan-pasta").value = r.pasta;
      await escanear(); // ja escaneia direto — um clique a menos
    }
  } catch (e) {
    toast(e.message, "erro");
  } finally {
    btn.classList.remove("ocupado"); btn.disabled = false;
  }
});

async function escanear() {
  const pasta = $("scan-pasta").value.trim();
  if (!pasta) { toast("Informe o caminho da pasta.", "erro"); return; }
  const btn = $("btn-escanear");
  btn.classList.add("ocupado"); btn.disabled = true;
  try {
    estado.scan = await api("POST", "/api/scan", { pasta });
    estado.scanPasta = pasta;
    renderScan();
  } catch (e) {
    toast(e.message, "erro");
  } finally {
    btn.classList.remove("ocupado"); btn.disabled = false;
  }
}

function renderScan() {
  const box = $("scan-resultado");
  const { grupos, ignorados } = estado.scan;
  if (!grupos.length && !ignorados.length) {
    box.innerHTML = `<div class="scan-ignorados">Nenhum PDF na convenção encontrado nessa pasta.</div>`;
    box.classList.remove("oculto");
    return;
  }
  const linhas = grupos.map((g, n) => `
    <div class="scan-grupo ${g.ja_importado ? "ja-importado" : ""}">
      <input type="checkbox" data-scan-idx="${n}" ${g.ja_importado ? "" : "checked"}>
      <span class="titulo">${esc(g.titulo)}</span>
      <span class="chip tipo">${esc(g.tipo)}</span>
      <span class="meta">${g.idiomas.length} idioma(s)
        · ${g.idiomas.filter((i) => i.capa).length} capa(s)
        ${g.ja_importado ? " · já importado" : ""}</span>
    </div>`).join("");
  const avisos = ignorados.length
    ? `<div class="scan-ignorados">⚠ ${ignorados.length} arquivo(s) ignorado(s): ${
        ignorados.map((i) => `${esc(i.arquivo)} (${esc(i.motivo)})`).join("; ")}</div>`
    : "";
  box.innerHTML = `${linhas}${avisos}
    <div class="scan-acoes">
      <button id="btn-importar" class="btn primario">Importar selecionados</button>
      <button id="btn-fechar-scan" class="btn">Fechar</button>
    </div>`;
  box.classList.remove("oculto");
  $("btn-importar").addEventListener("click", importarSelecionados);
  $("btn-fechar-scan").addEventListener("click", () => box.classList.add("oculto"));
}

async function importarSelecionados() {
  const marcados = [...document.querySelectorAll("[data-scan-idx]:checked")]
    .map((cb) => estado.scan.grupos[parseInt(cb.dataset.scanIdx, 10)])
    .map((g) => ({ titulo: g.titulo, tipo: g.tipo }));
  if (!marcados.length) { toast("Nenhum grupo selecionado.", "erro"); return; }
  const btn = $("btn-importar");
  btn.classList.add("ocupado"); btn.disabled = true;
  try {
    const r = await api("POST", "/api/produtos", { pasta: estado.scanPasta, grupos: marcados });
    toast(`${r.criados.length} produto(s) importado(s) ✓`, "ok");
    $("scan-resultado").classList.add("oculto");
    r.criados.forEach((p) => estado.abertos.add(p.id));
    await carregarProdutos();
  } catch (e) {
    toast(e.message, "erro");
    btn.classList.remove("ocupado"); btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Lista de produtos
// ---------------------------------------------------------------------------
async function carregarProdutos() {
  estado.produtos = await api("GET", "/api/produtos");
  renderProdutos();
}

function renderProdutos() {
  const box = $("lista-produtos");
  atualizarSelectPastas();
  renderResumoGeral();
  if (!estado.produtos.length) {
    box.innerHTML = `<div class="vazio">Nenhum produto na fila ainda.<br>
      <small>Escaneie uma pasta acima pra importar os ebooks.</small></div>`;
    return;
  }
  box.innerHTML = estado.produtos.map(renderCard).join("");
}

// Placar sempre visivel: quanto da fila inteira ja esta traduzido/revisado/publicado
// e o que ainda falta (texto, capa) ou deu erro.
function renderResumoGeral() {
  const box = $("resumo-geral");
  const prods = estado.produtos;
  if (!prods.length) { box.classList.add("oculto"); return; }
  let idiomas = 0, comTextos = 0, revisados = 0, publicados = 0, semCapa = 0, comErro = 0;
  for (const p of prods) {
    for (const i of p.idiomas) {
      idiomas++;
      if (i.titulo && i.descricao) comTextos++;
      if (i.status === "publicado") { publicados++; revisados++; }
      else if (i.status === "revisado") revisados++;
      if (!i.capa) semCapa++;
      if (i.status === "erro") comErro++;
    }
  }
  const faltaTexto = idiomas - comTextos;
  const pct = (n) => idiomas ? (n / idiomas * 100).toFixed(1) : 0;
  box.classList.remove("oculto");
  box.innerHTML = `
    <span class="rg-item"><b>${prods.length}</b> produtos · <b>${idiomas}</b> idiomas</span>
    <span class="rg-sep">·</span>
    <span class="rg-item ${faltaTexto ? "rg-alerta" : "rg-ok"}">${comTextos}/${idiomas} traduzidos${faltaTexto ? ` (faltam ${faltaTexto})` : " ✓"}</span>
    <span class="rg-sep">·</span>
    <span class="rg-item ${revisados < idiomas ? "" : "rg-ok"}">${revisados}/${idiomas} revisados</span>
    ${publicados ? `<span class="rg-sep">·</span><span class="rg-item rg-ok">${publicados} publicados ✓</span>` : ""}
    ${semCapa ? `<span class="rg-sep">·</span><span class="rg-item rg-alerta">${semCapa} sem capa</span>` : ""}
    ${comErro ? `<span class="rg-sep">·</span><span class="rg-item rg-erro">${comErro} com erro</span>` : ""}
    ${faltaTexto ? `<button class="rg-completar" data-acao="completar-faltantes" title="Gera/traduz só os ${faltaTexto} que ficaram faltando (os que deram erro). Não mexe no que já está pronto.">🔁 Completar faltantes (${faltaTexto})</button>` : ""}
    <button class="rg-limpar" data-acao="limpar-tudo" title="Remove todos os produtos da fila (não apaga os PDFs/capas do disco)">🗑 Apagar todos</button>
    <span class="rg-barra" title="azul = traduzido · verde = revisado · verde forte = publicado">
      <i class="b-trad" style="width:${pct(comTextos - revisados)}%"></i>
      <i class="b-rev" style="width:${pct(revisados - publicados)}%"></i>
      <i class="b-pub" style="width:${pct(publicados)}%"></i>
    </span>`;
}

$("resumo-geral").addEventListener("click", async (e) => {
  if (e.target.closest("[data-acao='completar-faltantes']")) {
    // processarTudo() ja pega SO os idiomas vazios (os que deram erro) + descricao faltando
    await processarTudo();
    return;
  }
  if (!e.target.closest("[data-acao='limpar-tudo']")) return;
  const total = estado.produtos.length;
  if (!confirm(`Apagar TODOS os ${total} produtos da fila?\n\nOs arquivos PDF/capas NÃO são apagados — só a fila daqui. Você pode reimportar a pasta depois.`)) return;
  try {
    const r = await api("DELETE", "/api/produtos");
    estado.abertos.clear();
    await carregarProdutos();
    toast(`${r.removidos} produto(s) removido(s) da fila.`, "ok");
  } catch (err) { toast(err.message, "erro"); }
});

function atualizarSelectPastas() {
  const sel = $("titulos-pasta");
  const atual = sel.value;
  const pastas = [...new Set(estado.produtos.map((p) => p.pasta))];
  sel.innerHTML = pastas.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
  if (pastas.includes(atual)) sel.value = atual;
}

function renderCard(p) {
  const aberto = estado.abertos.has(p.id);
  const n = p.idiomas.length;
  const traduzidos = p.idiomas.filter((i) => i.titulo && i.descricao).length;
  const revisados = p.idiomas.filter((i) => ["revisado", "publicado"].includes(i.status)).length;
  const semCapa = p.idiomas.filter((i) => !i.capa).length;
  const comErro = p.idiomas.filter((i) => i.status === "erro").length;
  const corpo = aberto ? renderCorpo(p) : "";
  return `
  <div class="card produto ${aberto ? "aberto" : ""}" data-pid="${p.id}">
    <div class="produto-cab" data-toggle="${p.id}">
      <span class="seta">▸</span>
      <span class="titulo-pt">${esc(p.titulo_pt)}</span>
      <span class="chip tipo">${esc(p.tipo)}</span>
      <span class="resumo">
        ${comErro ? `<span class="chip erro">${comErro} erro</span>` : ""}
        ${semCapa ? `<span class="chip sem-capa">${semCapa} sem capa</span>` : ""}
        <span class="${traduzidos < n ? "rg-alerta" : ""}">${traduzidos}/${n} traduzidos</span>
        <span>${revisados}/${n} revisados</span>
      </span>
    </div>
    <div class="produto-corpo">${corpo}</div>
  </div>`;
}

function renderCorpo(p) {
  const ocupadoDesc = estado.ocupados.has(`${p.id}:desc`);
  const ocupadoTodos = estado.ocupados.has(`${p.id}:todos`);
  const todosRevisados = p.idiomas.every((i) => i.status === "revisado");
  const semCapa = p.idiomas.filter((i) => !i.capa).length;
  const linhas = p.idiomas.map((i) => renderLinhaIdioma(p, i)).join("");
  return `
  <div class="bloco-pt">
    <div class="linha-acoes">
      <button class="btn mini primario ${ocupadoDesc ? "ocupado" : ""}"
              data-acao="gerar-desc" data-pid="${p.id}" ${ocupadoDesc ? "disabled" : ""}>
        ${p.descricao_pt ? "Regerar descrição (PT)" : "Gerar descrição (PT)"}</button>
      <button class="btn mini ${ocupadoTodos ? "ocupado" : ""}"
              data-acao="traduzir-todos" data-pid="${p.id}"
              ${ocupadoTodos || !p.descricao_pt ? "disabled" : ""}>Traduzir todos</button>
      <button class="btn mini" data-acao="revisar-todos" data-pid="${p.id}">
        ${todosRevisados ? "Desmarcar todos" : "Revisar todos ✓"}</button>
      ${semCapa ? `<button class="btn mini" data-acao="detectar-capas" data-pid="${p.id}"
        title="Reprocura imagens com o mesmo nome dos PDFs na pasta">Detectar capas (${semCapa} faltando)</button>` : ""}
      <button class="btn mini perigo" data-acao="excluir" data-pid="${p.id}">Excluir</button>
    </div>
    <label>Descrição de venda (PT) — base pras traduções, edite à vontade:</label>
    <textarea data-campo-produto="descricao_pt" data-pid="${p.id}"
      placeholder="Clique em 'Gerar descrição (PT)' ou escreva aqui...">${esc(p.descricao_pt)}</textarea>
  </div>
  <table class="tabela-idiomas">
    <thead><tr>
      <th>País</th><th>Título e descrição traduzidos</th><th>Preço</th>
      <th>Capa</th><th>Status</th><th></th>
    </tr></thead>
    <tbody>${linhas}</tbody>
  </table>`;
}

function renderLinhaIdioma(p, i) {
  const chave = `${p.id}:${i.codigo}`;
  const ocupado = estado.ocupados.has(chave);
  const revisado = i.status === "revisado";
  const anexos = i.anexos || [];
  return `
  <tr>
    <td class="td-pais">${esc(i.pais)}
      ${anexos.length ? `<div class="anexos-badge" title="Sobem junto:\n${esc(anexos.map(a => a.nome).join("\n"))}">+${anexos.length} anexo(s)</div>` : ""}</td>
    <td class="td-textos">
      <input type="text" placeholder="Título traduzido"
        data-campo-item="titulo" data-pid="${p.id}" data-codigo="${i.codigo}" value="${esc(i.titulo)}">
      <textarea placeholder="Descrição traduzida"
        data-campo-item="descricao" data-pid="${p.id}" data-codigo="${i.codigo}">${esc(i.descricao)}</textarea>
      ${i.erro ? `<div class="linha-erro">⚠ ${esc(i.erro)}</div>` : ""}
    </td>
    <td class="td-preco">
      <input type="number" step="0.10" min="0"
        data-campo-item="preco" data-pid="${p.id}" data-codigo="${i.codigo}" value="${i.preco}">
    </td>
    <td>${i.capa
      ? `<span class="chip com-capa" title="${esc(i.capa)}">✓</span>`
      : `<span class="chip sem-capa">falta</span>`}
      <button class="btn mini btn-capa" data-acao="escolher-capa" data-pid="${p.id}"
        data-codigo="${i.codigo}" title="${i.capa ? "Trocar a imagem da capa" : "Escolher a imagem da capa"}">📁</button></td>
    <td class="td-status"><span class="chip ${esc(i.status)}">${ROTULO_STATUS[i.status] || esc(i.status)}</span>
      ${i.erro ? `<div class="linha-erro" title="${esc(i.erro)}">⚠</div>` : ""}</td>
    <td class="td-acoes">
      ${i.status === "publicando" ? `<span class="chip publicando">robô em ação…</span>` : `
      <button class="btn mini ${ocupado ? "ocupado" : ""}" ${ocupado ? "disabled" : ""}
        data-acao="traduzir" data-pid="${p.id}" data-codigo="${i.codigo}">Traduzir</button>
      <button class="btn mini" data-acao="revisado" data-pid="${p.id}" data-codigo="${i.codigo}">
        ${revisado ? "Desmarcar" : "Revisado ✓"}</button>
      ${revisado || i.status === "erro" ? `
      <button class="btn mini primario" data-acao="publicar" data-pid="${p.id}" data-codigo="${i.codigo}">Publicar 🚀</button>` : ""}
      ${i.status === "publicado" && p.tipo === "Principal" ? `
      <button class="btn mini" data-acao="checkout" data-pid="${p.id}" data-codigo="${i.codigo}"
        title="Monta a página de checkout (bumps + fundo preto + imagem + contagem) e salva o link">🛒 Checkout</button>` : ""}`}
    </td>
  </tr>`;
}

// ---------------------------------------------------------------------------
// Ações (delegação de eventos)
// ---------------------------------------------------------------------------
$("lista-produtos").addEventListener("click", async (e) => {
  const toggle = e.target.closest("[data-toggle]");
  if (toggle) {
    const pid = toggle.dataset.toggle;
    estado.abertos.has(pid) ? estado.abertos.delete(pid) : estado.abertos.add(pid);
    renderProdutos();
    return;
  }
  const btn = e.target.closest("[data-acao]");
  if (!btn || btn.disabled) return;
  const { acao, pid, codigo } = btn.dataset;
  try {
    if (acao === "gerar-desc") await gerarDescricao(pid);
    else if (acao === "traduzir") await traduzirIdioma(pid, codigo);
    else if (acao === "traduzir-todos") await traduzirTodos(pid);
    else if (acao === "revisado") await alternarRevisado(pid, codigo);
    else if (acao === "revisar-todos") await revisarTodos(pid);
    else if (acao === "publicar") await publicarIdioma(pid, codigo);
    else if (acao === "checkout") await montarCheckout(pid, codigo);
    else if (acao === "escolher-capa") await escolherCapa(pid, codigo, btn);
    else if (acao === "detectar-capas") await detectarCapas(pid);
    else if (acao === "excluir") await excluirProduto(pid);
  } catch (err) { await tratarErroAcao(err); }
});

// Produto sumiu do disco (excluido em outra janela/sessao)? Recarrega a lista
// pra remover o card fantasma em vez de deixar o usuario preso no erro.
async function tratarErroAcao(err) {
  toast(err.message, "erro");
  if (/nao encontrado/i.test(err.message)) {
    await carregarProdutos();
  }
}

// edicao inline (dispara no blur/change)
$("lista-produtos").addEventListener("change", async (e) => {
  const alvo = e.target;
  try {
    if (alvo.dataset.campoProduto) {
      await api("PATCH", `/api/produtos/${alvo.dataset.pid}`,
        { [alvo.dataset.campoProduto]: alvo.value });
      await recarregarProduto(alvo.dataset.pid);
    } else if (alvo.dataset.campoItem) {
      const campo = alvo.dataset.campoItem;
      const valor = campo === "preco" ? parseFloat(alvo.value || "0") : alvo.value;
      await api("PATCH", `/api/produtos/${alvo.dataset.pid}/idiomas/${alvo.dataset.codigo}`,
        { [campo]: valor });
      await recarregarProduto(alvo.dataset.pid);
    }
  } catch (err) { await tratarErroAcao(err); }
});

async function recarregarProduto(pid) {
  let atualizado;
  try {
    atualizado = await api("GET", `/api/produtos/${pid}`);
  } catch (e) {
    if (/nao encontrado/i.test(e.message)) { await carregarProdutos(); return; }
    throw e;
  }
  const n = estado.produtos.findIndex((p) => p.id === pid);
  if (n >= 0) estado.produtos[n] = atualizado;
  renderProdutos();
}

async function gerarDescricao(pid) {
  estado.ocupados.add(`${pid}:desc`);
  renderProdutos();
  try {
    await api("POST", `/api/produtos/${pid}/descricao`);
    toast("Descrição gerada ✓", "ok");
  } finally {
    estado.ocupados.delete(`${pid}:desc`);
    await recarregarProduto(pid);
  }
}

async function traduzirIdioma(pid, codigo) {
  estado.ocupados.add(`${pid}:${codigo}`);
  renderProdutos();
  try {
    await api("POST", `/api/produtos/${pid}/traduzir/${codigo}`);
  } finally {
    estado.ocupados.delete(`${pid}:${codigo}`);
    await recarregarProduto(pid);
  }
}

// Quantas traduções/gerações rodam AO MESMO TEMPO (limite global). Cada chamada
// do agy abre um processo node — sem limite, 180 de uma vez travariam a máquina.
// Configurável na aba Config (padrão 15).
function limiteTraducoes() {
  const n = parseInt(estado.settings?.traduzir_simultaneas, 10);
  return (n && n > 0) ? n : 15;
}

// Chama a API tentando de novo em falha (soluço do agy/token se recupera sozinho).
async function apiComRetry(metodo, url, body, tentativas = 3) {
  let ultimo;
  for (let n = 0; n < tentativas; n++) {
    try { return await api(metodo, url, body); }
    catch (e) {
      ultimo = e;
      if (n < tentativas - 1) await new Promise((r) => setTimeout(r, 900 * (n + 1)));
    }
  }
  throw ultimo;
}

async function traduzirLote(pid, itens) {
  const fila = [...itens];
  let erros = 0;
  fila.forEach((i) => estado.ocupados.add(`${pid}:${i.codigo}`));
  renderProdutos();

  const trabalhador = async () => {
    while (fila.length) {
      const item = fila.shift();
      try {
        await apiComRetry("POST", `/api/produtos/${pid}/traduzir/${item.codigo}`);
      } catch (e) {
        erros++;
        toast(`${item.pais}: ${e.message}`, "erro");
      } finally {
        estado.ocupados.delete(`${pid}:${item.codigo}`);
        await recarregarProduto(pid);
      }
    }
  };
  await Promise.all(Array.from(
    { length: Math.min(limiteTraducoes(), fila.length) },
    () => trabalhador(),
  ));
  return erros;
}

async function traduzirTodos(pid) {
  const p = estado.produtos.find((x) => x.id === pid);
  if (!p || !p.descricao_pt) { toast("Gere a descrição em PT primeiro.", "erro"); return; }
  estado.ocupados.add(`${pid}:todos`);
  const erros = await traduzirLote(pid, [...p.idiomas]);
  estado.ocupados.delete(`${pid}:todos`);
  renderProdutos();
  toast(erros ? `Tradução concluída com ${erros} erro(s).` : "Todos os idiomas traduzidos ✓",
        erros ? "erro" : "ok");
}

// Semaforo simples: limita quantas chamadas ao agy rodam AO MESMO TEMPO no
// TOTAL (somando todos os produtos). Sem isso, N produtos x 5 idiomas estouraria.
function criarSemaforo(limite) {
  let ativos = 0;
  const fila = [];
  const proximo = () => { if (fila.length && ativos < limite) { ativos++; fila.shift()(); } };
  return {
    async run(tarefa) {
      await new Promise((res) => { fila.push(res); proximo(); });
      try { return await tarefa(); }
      finally { ativos--; proximo(); }
    },
  };
}

// Botao global: processa TODOS os produtos ao mesmo tempo (limitado pelo
// semaforo global). Pra cada produto: gera a descricao (se faltar) e traduz
// so os idiomas ainda vazios — nao mexe em texto ja traduzido/revisado.
async function processarTudo() {
  const btn = $("btn-processar-tudo");
  if (!estado.produtos.length) { toast("Nenhum produto na fila.", "erro"); return; }
  btn.classList.add("ocupado"); btn.disabled = true;

  const sem = criarSemaforo(limiteTraducoes());
  let erros = 0;

  // marca tudo que vai ser processado (spinner) numa render so
  for (const p of estado.produtos) {
    if (!p.descricao_pt) estado.ocupados.add(`${p.id}:desc`);
    for (const i of p.idiomas) {
      if (!i.titulo || !i.descricao) estado.ocupados.add(`${p.id}:${i.codigo}`);
    }
  }
  renderProdutos();

  const processarProduto = async (pid) => {
    let p = estado.produtos.find((x) => x.id === pid);
    if (!p) return;
    // 1) descricao PT primeiro (traducoes dependem dela)
    if (!p.descricao_pt) {
      try {
        await sem.run(() => apiComRetry("POST", `/api/produtos/${pid}/descricao`));
      } catch (e) { erros++; toast(`${p.titulo_pt}: ${e.message}`, "erro"); }
      finally { estado.ocupados.delete(`${pid}:desc`); await recarregarProduto(pid); }
      p = estado.produtos.find((x) => x.id === pid);
      if (!p || !p.descricao_pt) {
        // desc falhou: tira os spinners dos idiomas desse produto
        for (const i of (p ? p.idiomas : [])) estado.ocupados.delete(`${pid}:${i.codigo}`);
        renderProdutos();
        return;
      }
    }
    // 2) traduz os idiomas ainda vazios (cada um passa pelo semaforo global)
    const faltantes = p.idiomas.filter((i) => !i.titulo || !i.descricao);
    await Promise.all(faltantes.map((item) =>
      sem.run(() => apiComRetry("POST", `/api/produtos/${pid}/traduzir/${item.codigo}`))
        .catch((e) => { erros++; toast(`${item.pais}: ${e.message}`, "erro"); })
        .finally(async () => {
          estado.ocupados.delete(`${pid}:${item.codigo}`);
          await recarregarProduto(pid);
        })));
  };

  try {
    await Promise.all(estado.produtos.map((p) => processarProduto(p.id)));
  } finally {
    btn.classList.remove("ocupado"); btn.disabled = false;
    renderProdutos();
  }
  toast(erros ? `Processamento concluído com ${erros} erro(s).` : "Tudo gerado e traduzido ✓",
        erros ? "erro" : "ok");
}

$("btn-processar-tudo").addEventListener("click", processarTudo);

// Botao global: marca como revisado TODOS os idiomas (de todos os produtos)
// que ja tem titulo e descricao. Nao mexe em quem falta texto.
async function revisarTudoGeral() {
  const btn = $("btn-revisar-tudo");
  if (!estado.produtos.length) { toast("Nenhum produto na fila.", "erro"); return; }
  btn.classList.add("ocupado"); btn.disabled = true;
  let marcados = 0, semTexto = 0;
  try {
    for (const p of estado.produtos) {
      const prontos = p.idiomas.filter((i) =>
        i.titulo && i.descricao && i.status !== "revisado" && i.status !== "publicado");
      semTexto += p.idiomas.filter((i) => !i.titulo || !i.descricao).length;
      await Promise.all(prontos.map((i) =>
        api("PATCH", `/api/produtos/${p.id}/idiomas/${i.codigo}`, { status: "revisado" })
          .then(() => { marcados++; }).catch(() => {})));
      if (prontos.length) await recarregarProduto(p.id);
    }
  } finally {
    btn.classList.remove("ocupado"); btn.disabled = false; renderProdutos();
  }
  toast(`${marcados} idioma(s) revisados` + (semTexto ? ` · ${semTexto} sem texto ficaram de fora` : " ✓"),
        semTexto ? "" : "ok");
}
$("btn-revisar-tudo").addEventListener("click", revisarTudoGeral);

// Botao global: publica um a um todos os idiomas REVISADOS de todos os produtos.
// Cada publicacao passa pelo robo normal (com as pausas de código 2FA e
// confirmação); a fila só avança quando a atual termina.
async function publicarTodos() {
  if (estado.checkoutFila) { toast("A fila de checkouts está rodando — espere ou cancele.", "erro"); return; }
  if (!estado.produtos.length) { toast("Nenhum produto na fila.", "erro"); return; }
  const modo = $("chk-ensaio").checked ? "ensaio" : "real";
  const fila = [];
  for (const p of estado.produtos) {
    for (const i of p.idiomas) {
      if (i.status === "revisado") fila.push({
        pid: p.id, codigo: i.codigo, pais: i.pais, titulo: p.titulo_pt,
        tipo: p.tipo, numero: p.numero || 0, ordemIdioma: p.idiomas.indexOf(i),
      });
    }
  }
  if (!fila.length) { toast("Nenhum idioma revisado pra publicar.", "erro"); return; }
  // ordem SEMPRE: Principal -> Order Bump -> Upsell (depois nº e idioma)
  const ORDEM_TIPO = { "Principal": 0, "Order Bump": 1, "Upsell": 2 };
  fila.sort((a, b) =>
    (ORDEM_TIPO[a.tipo] ?? 9) - (ORDEM_TIPO[b.tipo] ?? 9)
    || a.numero - b.numero
    || a.ordemIdioma - b.ordemIdioma);
  const msg = modo === "real"
    ? `Publicar DE VERDADE ${fila.length} cadastro(s) na Hotmart, um a um?\n\nVocê ainda digita cada código e confirma cada finalização.`
    : `Rodar ENSAIO de ${fila.length} cadastro(s), um a um? (nada é enviado)`;
  if (!confirm(msg)) return;

  const btn = $("btn-publicar-tudo");
  estado.filaCancelada = false;
  estado.publicandoFila = true;
  btn.textContent = "⛔ Cancelar fila";
  let feitos = 0, pulados = 0;
  // cronômetro da rede: inicia agora, conta ao vivo, mostra o total no fim
  const inicioFila = Date.now();
  const cron = $("fila-cronometro");
  cron.classList.remove("oculto", "fim");
  const tickCron = () => {
    cron.textContent = `⏱ ${fmtDuracao(Date.now() - inicioFila)} · ${feitos}/${fila.length}`;
  };
  tickCron();
  const timerCron = setInterval(tickCron, 1000);
  try {
    for (let n = 0; n < fila.length; n++) {
      if (estado.filaCancelada) { toast("Fila cancelada.", "aviso"); break; }
      const item = fila[n];
      // re-checa: o item ainda está 'revisado'? (pode ter mudado)
      let prod = null;
      try { prod = await api("GET", `/api/produtos/${item.pid}`); } catch (_) {}
      const at = prod && prod.idiomas.find((i) => i.codigo === item.codigo);
      if (!at || at.status !== "revisado") { pulados++; continue; }

      toast(`Publicando ${n + 1} de ${fila.length}: ${item.titulo} — ${item.pais}`, "");
      try {
        await api("POST", `/api/produtos/${item.pid}/publicar/${item.codigo}`, { modo });
      } catch (e) { toast(`${item.pais}: ${e.message}`, "erro"); pulados++; continue; }

      iniciarPollPublicacao();
      const fim = await aguardarFimPublicacao();
      if (fim === "cancelado" || estado.filaCancelada) { toast("Fila cancelada.", "aviso"); break; }
      feitos++;
    }
  } finally {
    clearInterval(timerCron);
    estado.publicandoFila = false;
    btn.textContent = "📤 Publicar todos";
    await carregarProdutos();
  }
  const total = fmtDuracao(Date.now() - inicioFila);
  // deixa o total FIXO na tela (o toast some em 4s; a rede leva horas)
  cron.classList.remove("oculto");
  cron.classList.add("fim");
  cron.textContent = estado.filaCancelada
    ? `⏱ ${total} (cancelada) · ${feitos} publicado(s)`
    : `⏱ Rede publicada em ${total} · ${feitos} publicado(s)${pulados ? `, ${pulados} pulado(s)` : ""}`;
  toast(`Fila concluída em ${total}: ${feitos} processado(s)` + (pulados ? `, ${pulados} pulado(s)` : "") + " ✓", "ok");
  if (!estado.filaCancelada) tocarAlarme();  // 🔔 avisa que terminou tudo
}

// Fila de CHECKOUTS: monta a página de pagamento de todos os Principais
// publicados (todas as redes), um por vez. Pula países que já têm link.
function nomeRede(pasta) {
  return String(pasta || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || String(pasta || "");
}

async function checkoutTodos() {
  if (estado.publicandoFila || estado.checkoutFila) { toast("Já tem uma fila rodando.", "erro"); return; }
  if (!estado.produtos.length) { toast("Nenhum produto na fila.", "erro"); return; }

  // links já gerados (rede|país) — esses são pulados (pode rodar de novo à vontade)
  const existentes = new Set();
  try {
    const r = await api("GET", "/api/checkouts");
    for (const [rede, paises] of Object.entries(r.arvore || {})) {
      for (const pais of Object.keys(paises)) existentes.add(`${rede}|${pais}`);
    }
  } catch (_) {}

  const fila = [];
  for (const p of estado.produtos) {
    if (p.tipo !== "Principal") continue;
    const rede = nomeRede(p.pasta);
    for (const i of p.idiomas) {
      if (i.status !== "publicado") continue;
      if (existentes.has(`${rede}|${i.pais}`)) continue;
      fila.push({ pid: p.id, codigo: i.codigo, pais: i.pais,
                  titulo: p.titulo_pt, ordemIdioma: p.idiomas.indexOf(i) });
    }
  }
  fila.sort((a, b) => a.ordemIdioma - b.ordemIdioma);
  if (!fila.length) {
    toast("Nenhum checkout pendente — os países publicados já têm link (ou nada foi publicado).", "");
    return;
  }
  if (!confirm(`Montar ${fila.length} página(s) de checkout, uma a uma?\n\n`
    + "Países que já têm link no histórico foram pulados. Cada página leva uns minutos.")) return;

  const btn = $("btn-checkout-tudo");
  estado.filaCancelada = false;
  estado.checkoutFila = true;
  btn.textContent = "⛔ Cancelar fila";
  let feitos = 0, falhas = 0;
  const inicioFila = Date.now();
  const cron = $("fila-cronometro");
  cron.classList.remove("oculto", "fim");
  const tickCron = () => {
    cron.textContent = `🛒 ${fmtDuracao(Date.now() - inicioFila)} · ${feitos}/${fila.length}`;
  };
  tickCron();
  const timerCron = setInterval(tickCron, 1000);
  try {
    for (let n = 0; n < fila.length; n++) {
      if (estado.filaCancelada) { toast("Fila cancelada.", "aviso"); break; }
      const item = fila[n];
      toast(`Checkout ${n + 1} de ${fila.length}: ${item.titulo} — ${item.pais}`, "");
      try {
        await api("POST", `/api/produtos/${item.pid}/checkout/${item.codigo}`);
      } catch (e) { toast(`${item.pais}: ${e.message}`, "erro"); falhas++; continue; }
      iniciarPollPublicacao();
      const fim = await aguardarFimPublicacao();
      if (fim === "cancelado" || estado.filaCancelada) { toast("Fila cancelada.", "aviso"); break; }
      if (fim === "erro") falhas++;
      else feitos++;
    }
  } finally {
    clearInterval(timerCron);
    estado.checkoutFila = false;
    btn.textContent = "🛒 Checkouts em fila";
  }
  const total = fmtDuracao(Date.now() - inicioFila);
  cron.classList.add("fim");
  cron.textContent = estado.filaCancelada
    ? `🛒 ${total} (cancelada) · ${feitos} checkout(s)`
    : `🛒 Checkouts em ${total} · ${feitos} criado(s)${falhas ? `, ${falhas} falha(s)` : ""}`;
  toast(`Fila de checkouts concluída em ${total}: ${feitos} criado(s)`
    + (falhas ? `, ${falhas} falha(s)` : "") + " ✓", falhas ? "" : "ok");
  if (!estado.filaCancelada) tocarAlarme();  // 🔔 terminou tudo
}

$("btn-checkout-tudo").addEventListener("click", () => {
  if (estado.checkoutFila) cancelarFila();
  else checkoutTodos();
});

// Alarme sonoro (Web Audio — não precisa de arquivo). 3 rodadas de bipes.
function tocarAlarme() {
  if (!$("chk-alarme").checked) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    let t = ctx.currentTime + 0.05;
    for (let rodada = 0; rodada < 3; rodada++) {
      for (const freq of [660, 880, 1175]) {
        const osc = ctx.createOscillator();
        const g = ctx.createGain();
        osc.type = "sine"; osc.frequency.value = freq;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.35, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
        osc.connect(g); g.connect(ctx.destination);
        osc.start(t); osc.stop(t + 0.24);
        t += 0.2;
      }
      t += 0.18;
    }
    setTimeout(() => { try { ctx.close(); } catch (_) {} }, 5000);
  } catch (_) { /* sem áudio disponível — segue sem alarme */ }
}

// Alarme de ERRO — som GRAVE e DESCENDENTE (square/áspero), bem diferente do
// chime alegre de sucesso, pra você reconhecer "deu ruim" só pelo ouvido.
function tocarAlarmeErro() {
  if (!$("chk-alarme").checked) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    let t = ctx.currentTime + 0.05;
    for (let rodada = 0; rodada < 3; rodada++) {
      for (const freq of [330, 233]) {   // descendente e grave (uh-oh)
        const osc = ctx.createOscillator();
        const g = ctx.createGain();
        osc.type = "square"; osc.frequency.value = freq;   // square = mais áspero
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.28, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.30);
        osc.connect(g); g.connect(ctx.destination);
        osc.start(t); osc.stop(t + 0.32);
        t += 0.30;
      }
      t += 0.14;
    }
    setTimeout(() => { try { ctx.close(); } catch (_) {} }, 6000);
  } catch (_) { /* sem áudio disponível — segue sem alarme */ }
}

$("chk-alarme").addEventListener("change", async () => {
  try { await api("POST", "/api/settings", { robo: { alarme: $("chk-alarme").checked } }); }
  catch (_) {}
});

async function cancelarFila() {
  estado.filaCancelada = true;
  toast("Cancelando a fila (o item atual é interrompido)...", "aviso");
  try { await api("POST", "/api/publicacao/cancelar"); } catch (_) {}
}

$("btn-publicar-tudo").addEventListener("click", () => {
  if (estado.publicandoFila) cancelarFila();
  else publicarTodos();
});

// Espera a publicação atual chegar num estado terminal (fora das pausas humanas).
async function aguardarFimPublicacao() {
  while (true) {
    await new Promise((r) => setTimeout(r, 1000));
    let r;
    try { r = await api("GET", "/api/publicacao"); } catch (_) { continue; }
    if (!r.job) return "concluido";
    if (!r.ativo) return r.job.estado; // concluido | erro | cancelado
  }
}

async function revisarTodos(pid) {
  const p = estado.produtos.find((x) => x.id === pid);
  if (!p) return;

  const todosRevisados = p.idiomas.every((i) => i.status === "revisado");
  if (todosRevisados) {
    await Promise.all(p.idiomas.map((i) =>
      api("PATCH", `/api/produtos/${pid}/idiomas/${i.codigo}`, { status: "textos_gerados" })));
    await recarregarProduto(pid);
    toast("Todos desmarcados.", "ok");
    return;
  }

  const prontos = p.idiomas.filter((i) => i.titulo && i.descricao && i.status !== "revisado");
  const semTextos = p.idiomas.filter((i) => !i.titulo || !i.descricao).length;
  if (!prontos.length) {
    toast("Nenhum idioma com título e descrição prontos pra revisar.", "erro");
    return;
  }
  await Promise.all(prontos.map((i) =>
    api("PATCH", `/api/produtos/${pid}/idiomas/${i.codigo}`, { status: "revisado" })));
  await recarregarProduto(pid);
  toast(semTextos
    ? `${prontos.length} idioma(s) revisados ✓ — ${semTextos} sem textos ficaram de fora`
    : "Todos os idiomas revisados ✓", semTextos ? "" : "ok");
}

async function escolherCapa(pid, codigo, btn) {
  btn.classList.add("ocupado"); btn.disabled = true;
  try {
    const r = await api("POST", `/api/produtos/${pid}/idiomas/${codigo}/escolher-capa`);
    if (r.ok) toast("Capa vinculada ✓", "ok");
  } finally {
    btn.classList.remove("ocupado"); btn.disabled = false;
    await recarregarProduto(pid);
  }
}

async function detectarCapas(pid) {
  const r = await api("POST", `/api/produtos/${pid}/detectar-capas`);
  await recarregarProduto(pid);
  toast(r.achadas
    ? `${r.achadas} capa(s) encontrada(s) ✓`
    : "Nenhuma capa nova — a imagem precisa ter o mesmo nome do PDF (ou o começo dele).", r.achadas ? "ok" : "");
}

async function alternarRevisado(pid, codigo) {
  const p = estado.produtos.find((x) => x.id === pid);
  const item = p?.idiomas.find((i) => i.codigo === codigo);
  if (!item) return;
  const novo = item.status === "revisado" ? "textos_gerados" : "revisado";
  if (novo === "revisado" && (!item.titulo || !item.descricao)) {
    toast("Traduza (ou preencha) título e descrição antes de marcar como revisado.", "erro");
    return;
  }
  await api("PATCH", `/api/produtos/${pid}/idiomas/${codigo}`, { status: novo });
  await recarregarProduto(pid);
}

async function excluirProduto(pid) {
  const p = estado.produtos.find((x) => x.id === pid);
  if (!confirm(`Excluir "${p?.titulo_pt}" (${p?.tipo}) da fila?\nOs arquivos PDF/capas NÃO são apagados.`)) return;
  await api("DELETE", `/api/produtos/${pid}`);
  estado.abertos.delete(pid);
  await carregarProdutos();
  toast("Produto removido da fila.", "ok");
}

// ---------------------------------------------------------------------------
// Publicação (Fase B — robô)
// ---------------------------------------------------------------------------
const ROTULO_JOB = {
  iniciando: "iniciando…", rodando: "robô trabalhando…",
  aguardando_2fa: "⏸ esperando código", aguardando_confirmacao: "⏸ esperando você confirmar",
  concluido: "concluído ✓", erro: "erro", cancelado: "cancelado",
};
const CLASSE_JOB = {
  iniciando: "publicando", rodando: "publicando",
  aguardando_2fa: "sem-capa", aguardando_confirmacao: "sem-capa",
  concluido: "publicado", erro: "erro", cancelado: "rascunho",
};
let pollTimer = null;

async function publicarIdioma(pid, codigo) {
  const modo = $("chk-ensaio").checked ? "ensaio" : "real";
  if (modo === "real" && !confirm(
    "Publicar DE VERDADE na Hotmart?\n\nO robô vai criar o produto e só para nas pausas humanas (código e finalização).")) return;
  await api("POST", `/api/produtos/${pid}/publicar/${codigo}`, { modo });
  toast(modo === "ensaio"
    ? "Ensaio iniciado — o robô preenche a 1ª tela e para."
    : "Publicação iniciada 🚀", "ok");
  await recarregarProduto(pid);
  iniciarPollPublicacao();
}

async function montarCheckout(pid, codigo) {
  if (!confirm("Montar a página de CHECKOUT desse produto na Hotmart?\n\n"
    + "O robô cria a página (bumps + fundo preto + imagem do país + contagem), "
    + "publica e salva o link na aba Histórico.")) return;
  await api("POST", `/api/produtos/${pid}/checkout/${codigo}`);
  toast("Montagem do checkout iniciada 🛒", "ok");
  iniciarPollPublicacao();
}

function iniciarPollPublicacao() {
  if (pollTimer) return;
  pollTimer = setInterval(atualizarPainelPub, 1200);
  atualizarPainelPub();
}

async function atualizarPainelPub() {
  let r;
  try { r = await api("GET", "/api/publicacao"); } catch (_) { return; }
  if (!r.job) { pararPollPublicacao(true); return; }
  renderPainelPub(r.job, r.ativo);
  if (!r.ativo) {
    pararPollPublicacao(false);
    if (r.job.estado === "erro") tocarAlarmeErro();  // 🔔 avisa que deu erro
    await carregarProdutos(); // reflete status publicado/erro/revisado nas linhas
  }
}

function pararPollPublicacao(esconder) {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (esconder) $("painel-pub").classList.add("oculto");
}

function renderPainelPub(job, ativo) {
  $("painel-pub").classList.remove("oculto");
  $("pub-titulo").textContent = `${job.titulo} — ${job.pais}`;
  $("pub-modo").textContent = job.modo;
  const chip = $("pub-estado");
  chip.textContent = ROTULO_JOB[job.estado] || job.estado;
  chip.className = `chip ${CLASSE_JOB[job.estado] || "publicando"}`;
  const log = $("pub-log");
  log.innerHTML = job.mensagens.map((m) =>
    `<div class="lin-${esc(m.nivel)}"><span class="hora">${esc(m.hora)}</span>${esc(m.texto)}</div>`
  ).join("");
  log.scrollTop = log.scrollHeight;
  $("pub-acao-2fa").classList.toggle("oculto", job.estado !== "aguardando_2fa");
  $("pub-acao-confirmar").classList.toggle("oculto", job.estado !== "aguardando_confirmacao");
  $("btn-cancelar-pub").classList.toggle("oculto", !ativo);
  $("btn-fechar-pub").classList.toggle("oculto", ativo);
}

$("btn-enviar-codigo").addEventListener("click", async () => {
  const codigo = $("pub-codigo").value.trim();
  if (codigo.length < 6) { toast("Código precisa ter 6 dígitos.", "erro"); return; }
  try {
    await api("POST", "/api/publicacao/codigo", { codigo });
    $("pub-codigo").value = "";
    atualizarPainelPub();
  } catch (e) { toast(e.message, "erro"); }
});
$("pub-codigo").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("btn-enviar-codigo").click();
});

$("btn-confirmar-pub").addEventListener("click", async () => {
  try { await api("POST", "/api/publicacao/confirmar"); atualizarPainelPub(); }
  catch (e) { toast(e.message, "erro"); }
});

$("btn-cancelar-pub").addEventListener("click", async () => {
  if (!confirm("Cancelar a publicação em andamento?")) return;
  try { await api("POST", "/api/publicacao/cancelar"); atualizarPainelPub(); }
  catch (e) { toast(e.message, "erro"); }
});

$("btn-fechar-pub").addEventListener("click", () => pararPollPublicacao(true));

// ---------------------------------------------------------------------------
// Títulos em português (colar do Discord)
// ---------------------------------------------------------------------------
$("titulos-toggle").addEventListener("click", () => {
  $("titulos-corpo").classList.toggle("oculto");
  document.querySelector(".titulos-card").classList.toggle("aberto");
});

$("btn-aplicar-titulos").addEventListener("click", async () => {
  const texto = $("titulos-texto").value.trim();
  const pasta = $("titulos-pasta").value;
  if (!texto) { toast("Cole a lista de títulos primeiro.", "erro"); return; }
  if (!pasta) { toast("Importe os produtos da pasta antes de aplicar os títulos.", "erro"); return; }
  const btn = $("btn-aplicar-titulos");
  btn.classList.add("ocupado"); btn.disabled = true;
  try {
    const r = await api("POST", "/api/titulos/aplicar", { texto, pasta });
    await carregarProdutos();
    if (!r.aplicados.length) {
      toast("Nenhum título aplicado — confira o formato da lista e a pasta escolhida.", "erro");
    } else {
      const aviso = r.sem_match.length ? ` · ${r.sem_match.length} produto(s) sem título na lista` : "";
      const bonus = r.bonus_nomeados ? ` · ${r.bonus_nomeados} bônus nomeado(s)` : "";
      toast(`${r.aplicados.length} título(s) aplicado(s) ✓${aviso}${bonus}`, "ok");
    }
  } catch (e) {
    toast(e.message, "erro");
  } finally {
    btn.classList.remove("ocupado"); btn.disabled = false;
  }
});

$("btn-login-hotmart").addEventListener("click", async () => {
  try {
    const r = await api("POST", "/api/hotmart/login");
    toast(r.detalhe, "ok");
  } catch (e) { toast(e.message, "erro"); }
});

$("chk-ensaio").addEventListener("change", async () => {
  try { await api("POST", "/api/settings", { robo: { ensaio: $("chk-ensaio").checked } }); }
  catch (_) {}
});

// ---------------------------------------------------------------------------
// Atualização do sistema
// ---------------------------------------------------------------------------
let updateEstado = "checar"; // "checar" -> "atualizar"

async function checarVersao() {
  try {
    const r = await api("GET", "/api/versao");
    const st = $("update-status");
    const log = $("update-log");
    st.textContent = `Versão local: ${r.local}` + (r.latest != null ? ` · última publicada: ${r.latest}` : "");
    if (!r.configurado) {
      log.textContent = "Atualização automática ainda não configurada neste PC.";
      log.className = "feedback";
      $("btn-atualizar").disabled = true;
      return;
    }
    if (r.ha_atualizacao) {
      log.textContent = `Há uma atualização disponível (v${r.latest}). Clique em "Atualizar agora".`;
      log.className = "feedback tem-update";
      $("btn-atualizar").textContent = "Atualizar agora";
      updateEstado = "atualizar";
    } else if (r.latest != null) {
      log.textContent = "Você está com a versão mais recente ✓";
      log.className = "feedback";
      $("btn-atualizar").textContent = "Verificar atualizações";
      updateEstado = "checar";
    }
  } catch (_) { /* offline — ignora */ }
}

async function aplicarAtualizacao() {
  const btn = $("btn-atualizar");
  const log = $("update-log");
  btn.classList.add("ocupado"); btn.disabled = true;
  log.textContent = "Baixando atualização...";
  try {
    const r = await api("POST", "/api/atualizar");
    if (!r.ok) {
      log.textContent = "Não foi possível atualizar: " + (r.error || "erro desconhecido");
      log.className = "feedback";
      return;
    }
    let msg = `Atualizado para a versão ${r.version} ✓ (${r.updated.length} arquivo(s)).`;
    if (r.failed.length) msg += ` ${r.failed.length} falharam.`;
    if (r.restart) msg += "\n⚠ Feche e abra o app de novo (start.bat) pra aplicar.";
    log.textContent = msg;
    log.className = "feedback tem-update";
  } catch (e) {
    log.textContent = "Erro: " + e.message;
    log.className = "feedback";
  } finally {
    btn.classList.remove("ocupado"); btn.disabled = false;
    btn.textContent = "Verificar atualizações";
    updateEstado = "checar";
  }
}

$("btn-atualizar").addEventListener("click", () => {
  if (updateEstado === "atualizar") aplicarAtualizacao();
  else checarVersao();
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
(async function init() {
  await Promise.all([atualizarStatusKey(), carregarConfig(), carregarProdutos()]);
  checarVersao(); // mostra a versao e avisa se ha update (silencioso se offline)
  $("chk-ensaio").checked = estado.settings?.robo?.ensaio !== false;
  $("chk-alarme").checked = estado.settings?.robo?.alarme !== false;
  // se tinha publicação rolando (F5 no meio), retoma o painel
  const pub = await api("GET", "/api/publicacao").catch(() => null);
  if (pub?.job) iniciarPollPublicacao();
})();
