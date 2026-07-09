# HotmartFlow

Ferramenta pra quem sobe os ebooks na Hotmart: gera a descricao de venda,
traduz titulo+descricao pros idiomas dos PDFs e organiza a fila de publicacao.

**Fase A (atual):** textos + fila. **Fase B (futura):** robo que preenche a Hotmart.

## Como usar

1. Dois cliques em `start.bat` (primeira vez demora pra instalar dependencias).
2. O app abre numa janela do Chrome.
3. Aba **Config**: cole sua API key da OpenAI e ajuste os precos por tipo.
4. Aba **Produtos**: informe a pasta com os ebooks e clique **Escanear**.
   - Convencao de nomes (a mesma que o EbookFlow gera):
     `Titulo do Ebook - Pais.pdf` — sem tipo no nome, assume Principal.
     Com tipo explicito: `Titulo - Order Bump - Pais.pdf` (Principal, Order Bump, Upsell, Bonus).
   - Capas: imagem com o mesmo nome do PDF (`.jpg/.png/.webp`), na mesma pasta
     ou na subpasta `capas/`.
5. Importe os grupos detectados, clique **Gerar descricao (PT)** e depois
   **Traduzir todos**.
6. Revise/edite os textos de cada idioma e marque **Revisado**.

## Estrutura

```
HotmartFlow/
├── start.bat
├── requirements.txt
├── config/settings.json      (criado na primeira execucao)
├── app/
│   ├── launcher.py           (abre o Chrome em app mode)
│   ├── server.py             (API FastAPI)
│   └── web/                  (index.html, style.css, app.js)
├── core/
│   ├── idiomas.py            (catalogo de 20 idiomas/paises)
│   ├── scanner.py            (parser da convencao de nomes)
│   ├── produtos.py           (fila de publicacao em JSON)
│   ├── llm.py                (cliente OpenAI)
│   └── textos.py             (descricao de venda + traducao)
├── data/produtos/            (fila persistida — 1 JSON por produto)
└── tests/                    (pytest — rode com: .venv\Scripts\python -m pytest)
```

## Testes

```
.venv\Scripts\python.exe -m pytest tests/ -q
```

Nenhum teste bate na rede (o LLM e mockado).
