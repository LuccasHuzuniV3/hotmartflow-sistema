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
IDIOMA_HOTMART = {
    "pt-br": "Português",
    "en": "Inglês",
    "es": "Espanhol",
    "fr": "Francês",
    "de": "Alemão",
    "it": "Italiano",
    "nl": "Holandês",
    "sv": "Sueco",
    "fi": "Finlandês",
    "pl": "Polonês",
    "cs": "Tcheco",
    "sk": "Eslovaco",
    "sl": "Esloveno",
    "hu": "Húngaro",
    "ro": "Romeno",
    "bg": "Búlgaro",
    "hr": "Croata",
    "sr": "Sérvio",
    "el": "Grego",
    "fil": "Filipino",
}

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
        {"tipo": "label", "texto": "Nome do produto"},
        {"tipo": "placeholder", "texto": "nome"},
        {"tipo": "css", "css": "input[name='name']"},
    ],
    "campo_descricao": [
        {"tipo": "label", "texto": "Descrição"},
        {"tipo": "css", "css": "textarea"},
    ],
    "campo_idioma": [
        {"tipo": "label", "texto": "Idioma do produto"},
        {"tipo": "texto", "texto": "Idioma do produto"},
    ],
    "campo_pais": [
        {"tipo": "label", "texto": "Principal país para vendas"},
        {"tipo": "texto", "texto": "Principal país"},
    ],
    "input_capa": [
        {"tipo": "css", "css": "input[type='file']"},
    ],
    "campo_categoria": [
        {"tipo": "label", "texto": "Categoria"},
        {"tipo": "texto", "texto": "Categoria"},
    ],
    "btn_avancar_basico": [
        {"tipo": "role", "role": "button", "nome": "Avançar"},
        {"tipo": "role", "role": "button", "nome": "Continuar"},
    ],

    # ---------- preco ----------
    "campo_moeda": [
        {"tipo": "label", "texto": "Moeda"},
        {"tipo": "texto", "texto": "Moeda"},
    ],
    "opcao_dolar": [
        {"tipo": "texto", "texto": "Dólar Americano"},
        {"tipo": "texto", "texto": "Dólar"},
    ],
    "campo_valor": [
        {"tipo": "label", "texto": "Valor"},
        {"tipo": "placeholder", "texto": "0,00"},
        {"tipo": "css", "css": "input[name='price']"},
    ],
    "btn_salvar_continuar": [
        {"tipo": "role", "role": "button", "nome": "Salvar e Continuar"},
        {"tipo": "role", "role": "button", "nome": "Salvar e continuar"},
        {"tipo": "role", "role": "button", "nome": "Avançar"},
    ],

    # ---------- conteudo ----------
    "menu_conteudo": [
        {"tipo": "role", "role": "link", "nome": "Conteúdo do Produto"},
        {"tipo": "texto", "texto": "Conteúdo do Produto"},
        {"tipo": "texto", "texto": "Conteúdo"},
    ],
    "input_pdf": [
        {"tipo": "css", "css": "input[type='file']"},
    ],

    # ---------- coproducao ----------
    "menu_coproducao": [
        {"tipo": "role", "role": "link", "nome": "Coproduções"},
        {"tipo": "texto", "texto": "Coproduções"},
        {"tipo": "texto", "texto": "Coprodução"},
    ],
    "btn_convidar_coprodutor": [
        {"tipo": "role", "role": "button", "nome": "Convidar Coprodutor"},
        {"tipo": "texto", "texto": "Convidar Coprodutor"},
    ],
    "campo_email_coprodutor": [
        {"tipo": "label", "texto": "E-mail"},
        {"tipo": "placeholder", "texto": "e-mail"},
        {"tipo": "css", "css": "input[type='email']"},
    ],
    "opcao_socio_produtor": [
        {"tipo": "texto", "texto": "Sócio do produtor"},
    ],
    "campo_percentual": [
        {"tipo": "label", "texto": "comissão"},
        {"tipo": "css", "css": "input[type='number']"},
    ],
    "check_termos": [
        {"tipo": "css", "css": "input[type='checkbox']"},
        {"tipo": "texto", "texto": "Li e concordo"},
    ],
    "btn_enviar_convite": [
        {"tipo": "role", "role": "button", "nome": "Enviar convite"},
    ],
    "campo_codigo_2fa": [
        {"tipo": "label", "texto": "código"},
        {"tipo": "css", "css": "input[autocomplete='one-time-code']"},
        {"tipo": "css", "css": "input[maxlength='6']"},
    ],
    "btn_enviar_codigo": [
        {"tipo": "role", "role": "button", "nome": "Enviar"},
        {"tipo": "role", "role": "button", "nome": "Confirmar"},
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
