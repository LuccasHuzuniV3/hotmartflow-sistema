"""Mapa de telas da Hotmart — TODOS os seletores do robo vivem aqui.

Quando a Hotmart mudar um botao de lugar (ou um seletor estiver errado),
corrige NESTE arquivo — o robo (core/robo.py) nao conhece nenhum seletor.

Cada chave tem uma LISTA de candidatos, tentados em ordem. Tipos:
  {"tipo": "role",        "role": "button", "nome": "Criar produto"}  -> get_by_role (nome = regex, case-insensitive)
  {"tipo": "texto",       "texto": "eBook"}                           -> get_by_text (exato, ci)
  {"tipo": "label",       "texto": "Nome do produto"}                 -> get_by_label
  {"tipo": "placeholder", "texto": "Digite o nome"}                   -> get_by_placeholder
  {"tipo": "css",         "css": "input[type=file]"}                  -> locator css
"""
from __future__ import annotations

URL_APP = "https://app.hotmart.com"
URL_PRODUTOS = f"{URL_APP}/products"
# URL direta do formulario "Informacoes basicas" de um eBook novo (formato 4).
# Cai direto na tela de preencher — pula "Criar produto > eBook > Continuar".
URL_CRIAR_EBOOK = f"{URL_APP}/products/add/4/info"

# Se a URL cair em algum desses pedacos, o usuario NAO esta logado
MARCADORES_LOGIN = ("sso.hotmart.com", "/login", "signin")

# Nome do idioma como aparece no select "Idioma do produto" da Hotmart (UI em PT)
# Nome do idioma EXATAMENTE como aparece no dropdown "Idioma do produto" da
# Hotmart (nome na propria lingua). Só existem estes no dropdown; qualquer
# idioma fora daqui cai em "English" (ver IDIOMA_FALLBACK / idioma_hotmart()).
IDIOMA_HOTMART = {
    "pt-br": "Português (Brasil)",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
}
IDIOMA_FALLBACK = "English"  # idiomas que a Hotmart nao tem -> ingles


def idioma_hotmart(codigo: str) -> str:
    """Nome do idioma no dropdown da Hotmart; 'English' se nao existir lá."""
    return IDIOMA_HOTMART.get(codigo, IDIOMA_FALLBACK)

# Nome do pais como aparece em "Principal pais para vendas"
PAIS_HOTMART = {
    "pt-br": "Brasil",
    "en": "Estados Unidos",
    "es": "Espanha",
    "fr": "França",
    "de": "Alemanha",
    "it": "Itália",
    "nl": "Holanda",
    "sv": "Suécia",
    "fi": "Finlândia",
    "pl": "Polônia",
    "cs": "República Tcheca",
    "sk": "Eslováquia",
    "sl": "Eslovênia",
    "hu": "Hungria",
    "ro": "Romênia",
    "bg": "Bulgária",
    "hr": "Croácia",
    "sr": "Sérvia",
    "el": "Grécia",
    "fil": "Filipinas",
}

MAPA = {
    # ---------- login (rede de seguranca) ----------
    "btn_entrar_login": [
        {"tipo": "role", "role": "button", "nome": "Entrar"},
        {"tipo": "role", "role": "button", "nome": "Acessar"},
        {"tipo": "role", "role": "button", "nome": "Login"},
        {"tipo": "css", "css": "button[type='submit']"},
    ],

    # ---------- criacao ----------
    "btn_criar_produto": [
        {"tipo": "role", "role": "button", "nome": "Criar produto"},
        {"tipo": "role", "role": "link", "nome": "Criar produto"},
        {"tipo": "texto", "texto": "Criar produto"},
    ],
    "opcao_ebook": [
        {"tipo": "role", "role": "button", "nome": "eBook"},
        {"tipo": "texto", "texto": "eBook"},
    ],
    "btn_continuar_tipo": [
        {"tipo": "role", "role": "button", "nome": "Continuar"},
        {"tipo": "role", "role": "button", "nome": "Avançar"},
    ],

    # ---------- informacoes basicas ----------
    "campo_nome": [
        {"tipo": "css", "css": "#name"},
        {"tipo": "label", "texto": "Nome do produto"},
        {"tipo": "css", "css": "input.hot-form__input[name='name']"},
    ],
    "campo_descricao": [
        {"tipo": "css", "css": "#description"},
        {"tipo": "label", "texto": "Descrição"},
        {"tipo": "css", "css": "textarea.hot-form__input"},
    ],
    # Idioma/Pais sao COMBOBOX de busca (input#dropdown-input). O id NAO e unico
    # entre os dois — distingue pelo nome acessivel (o texto de dentro do campo).
    "campo_idioma": [
        {"tipo": "label", "texto": "Qual o idioma do seu produto"},
        {"tipo": "placeholder", "texto": "Qual o idioma do seu produto"},
        {"tipo": "role", "role": "textbox", "nome": "Qual o idioma do seu produto"},
    ],
    "campo_pais": [
        {"tipo": "label", "texto": "Em qual país você quer vender"},
        {"tipo": "placeholder", "texto": "Em qual país você quer vender"},
        {"tipo": "role", "role": "textbox", "nome": "Em qual país você quer vender"},
    ],
    # Campo de capa: input#cover — aceita SO 1 imagem (nao e multiple).
    "input_capa": [
        {"tipo": "css", "css": "#cover"},
        {"tipo": "css", "css": "input[type='file'][accept*='image']"},
    ],
    # Categoria = BOTOES/chips (nao dropdown). O robo clica no chip com o texto
    # da categoria (ex.: "Espiritualidade") direto — ver clicar_por_texto.
    "btn_avancar_basico": [
        {"tipo": "role", "role": "button", "nome": "Avançar"},
        {"tipo": "role", "role": "button", "nome": "Continuar"},
    ],

    # ---------- preco ----------
    # Moeda tambem e combobox de busca (input#dropdown-input, name "Selecione uma moeda").
    "campo_moeda": [
        {"tipo": "label", "texto": "Selecione uma moeda"},
        {"tipo": "placeholder", "texto": "Selecione uma moeda"},
        {"tipo": "role", "role": "textbox", "nome": "Selecione uma moeda"},
    ],
    # Prazo de reembolso — combobox (label "Prazo para solicitação de reembolso").
    # Ja costuma vir "7 dias" por padrao; setar e best-effort.
    "campo_reembolso": [
        {"tipo": "label", "texto": "Prazo para solicitação de reembolso"},
        {"tipo": "placeholder", "texto": "Prazo para solicitação"},
    ],
    # Forma de pagamento — combobox (name "Selecione uma forma de pagamento").
    "campo_forma_pagamento": [
        {"tipo": "label", "texto": "Selecione uma forma de pagamento"},
        {"tipo": "placeholder", "texto": "Selecione uma forma de pagamento"},
        {"tipo": "role", "role": "textbox", "nome": "Selecione uma forma de pagamento"},
    ],
    "campo_valor": [
        {"tipo": "css", "css": "#value"},
        {"tipo": "role", "role": "textbox", "nome": "Valor"},
        {"tipo": "label", "texto": "Valor"},
        {"tipo": "placeholder", "texto": "0,00"},
    ],
    "btn_salvar_continuar": [
        {"tipo": "role", "role": "button", "nome": "Salvar e Continuar"},
        {"tipo": "role", "role": "button", "nome": "Salvar e continuar"},
        {"tipo": "role", "role": "button", "nome": "Avançar"},
    ],

    # ---------- area de membros (passo 4) ----------
    # "Criar produto" (NAO confundir com "Criar Hotmart Club"). exact evita o outro.
    "btn_criar_produto_final": [
        {"tipo": "role", "role": "button", "nome": "^Criar produto$"},
        {"tipo": "texto", "texto": "^Criar produto$"},
    ],
    # Tela "Criado com sucesso" -> vai pro painel do produto.
    "btn_ir_painel": [
        {"tipo": "role", "role": "button", "nome": "Ir para o painel"},
        {"tipo": "role", "role": "link", "nome": "Ir para o painel"},
        {"tipo": "texto", "texto": "Ir para o painel"},
    ],

    # ---------- conteudo ----------
    # Menu lateral "Conteúdo do Produto" é um BUTTON (nao link).
    "menu_conteudo": [
        {"tipo": "role", "role": "button", "nome": "Conteúdo do Produto"},
        {"tipo": "role", "role": "link", "nome": "Conteúdo do Produto"},
        {"tipo": "texto", "texto": "Conteúdo do Produto"},
    ],
    "input_pdf": [
        {"tipo": "css", "css": "input[type='file']"},
    ],
    # Botao "Selecione um arquivo" (abre a janela de arquivo).
    "btn_selecione_arquivo": [
        {"tipo": "role", "role": "button", "nome": "Selecione um arquivo"},
        {"tipo": "texto", "texto": "Selecione um arquivo"},
    ],
    # Fallback: botao "Configurar" do checklist (o 1o e o de Conteudo do Produto),
    # usado quando o menu lateral esta colapsado/nao clicavel.
    "btn_configurar_conteudo": [
        {"tipo": "role", "role": "button", "nome": "^Configurar$"},
        {"tipo": "texto", "texto": "^Configurar$"},
    ],
    # Lapis de edicao (svg fa-pencil) — expande/abre o menu quando colapsado.
    "btn_lapis_editar": [
        {"tipo": "css", "css": "svg.fa-pencil"},
        {"tipo": "css", "css": ".fa-pencil"},
        {"tipo": "css", "css": "[class*='pencil']"},
    ],

    # ---------- coproducao ----------
    # Menu lateral "Coproduções" tambem e BUTTON.
    "menu_coproducao": [
        {"tipo": "role", "role": "button", "nome": "Coproduções"},
        {"tipo": "role", "role": "link", "nome": "Coproduções"},
        {"tipo": "texto", "texto": "Coproduções"},
    ],
    "btn_convidar_coprodutor": [
        {"tipo": "role", "role": "button", "nome": "Convidar Coprodutor"},
        {"tipo": "role", "role": "button", "nome": "Convidar"},
        {"tipo": "texto", "texto": "Convidar Coprodutor"},
        {"tipo": "css", "css": "button.hot-btn--primary"},
    ],
    # E-mail do coprodutor: input com name "Email do Coprodutor" / class js-input-email.
    "campo_email_coprodutor": [
        {"tipo": "label", "texto": "Email do Coprodutor"},
        {"tipo": "css", "css": "input.js-input-email"},
        {"tipo": "placeholder", "texto": "email@example.com"},
        {"tipo": "css", "css": "input[type='email']"},
    ],
    # "Como o(a) coprodutor(a) irá atuar?" -> escolher "Sócio do produtor".
    "campo_atuacao": [
        {"tipo": "label", "texto": "Como o(a) coprodutor(a) irá atuar"},
        {"tipo": "placeholder", "texto": "Escolha a atuação do Coprodutor"},
        {"tipo": "role", "role": "textbox", "nome": "Escolha a atuação do Coprodutor"},
    ],
    # Porcentagem das comissoes: input#proposedPercentage.
    "campo_percentual": [
        {"tipo": "css", "css": "#proposedPercentage"},
        {"tipo": "css", "css": "input.js-proposed-percentage"},
        {"tipo": "role", "role": "textbox", "nome": "Porcentagem das comissões"},
        {"tipo": "label", "texto": "Porcentagem das comissões"},
    ],
    # Checkbox custom "Li e aceito os termos e condições da coprodução".
    "check_termos": [
        {"tipo": "texto", "texto": "Li e aceito os termos e condições da coprodução"},
        {"tipo": "texto", "texto": "Li e aceito os termos"},
        {"tipo": "css", "css": "input[type='checkbox']"},
    ],
    # Botao do formulario: "Continuar" (leva pra tela de revisao).
    "btn_enviar_convite": [
        {"tipo": "role", "role": "button", "nome": "^Continuar$"},
        {"tipo": "role", "role": "button", "nome": "Enviar convite"},
        {"tipo": "role", "role": "button", "nome": "^Enviar$"},
    ],
    # Tela de REVISAO do convite: botao final "Enviar convite de coprodução".
    "btn_enviar_convite_final": [
        {"tipo": "role", "role": "button", "nome": "Enviar convite de coprodução"},
        {"tipo": "role", "role": "button", "nome": "Enviar convite"},
        {"tipo": "texto", "texto": "Enviar convite de coprodução"},
    ],
    # Chave de seguranca (2FA) — input.js-safety-key, name "Chave de segurança enviada por email".
    "campo_codigo_2fa": [
        {"tipo": "css", "css": "input.js-safety-key"},
        {"tipo": "label", "texto": "Chave de segurança enviada por email"},
        {"tipo": "placeholder", "texto": "Digite a chave de segurança"},
        {"tipo": "css", "css": "input[autocomplete='one-time-code']"},
    ],
    "marcador_convite_pendente": [
        {"tipo": "texto", "texto": "Pendente"},
    ],

    # ---------- finalizacao ----------
    "menu_painel": [
        {"tipo": "role", "role": "link", "nome": "Painel"},
        {"tipo": "texto", "texto": "Painel"},
    ],
    "btn_finalizar_cadastro": [
        {"tipo": "role", "role": "button", "nome": "Finalizar Cadastro"},
        {"tipo": "texto", "texto": "Finalizar Cadastro"},
    ],
    "marcador_sucesso": [
        {"tipo": "texto", "texto": "Enviado para aprovação"},
    ],
}
