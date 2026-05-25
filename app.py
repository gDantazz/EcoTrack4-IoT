import random
import time
from io import BytesIO

import cv2
import numpy as np
import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageOps

try:
    from pyzbar.pyzbar import decode as decode_barcode
except Exception:
    decode_barcode = None

try:
    import zxingcpp
except Exception:
    zxingcpp = None


st.set_page_config(
    page_title="EcoTrack - Protótipo IA",
    page_icon="EC",
    layout="centered",
)

COLUNAS_CSV = [
    "product_name",
    "packaging",
    "brands",
    "categories_tags",
    "ingredients_text",
    "nutriscore_grade",
    "ecoscore_grade",
]

OPEN_FOOD_FACTS_HEADERS = {
    "User-Agent": "EcoTrack-IoT/1.0 (Projeto academico; contato: ecotrack.local)",
    "Accept": "application/json",
}


def texto_limpo(valor, padrao="Não informado"):
    if valor is None:
        return padrao
    if pd.isna(valor):
        return padrao
    texto = str(valor).strip()
    return texto if texto and texto.lower() != "nan" else padrao


def produto_para_dict(produto):
    row = produto.iloc[0] if isinstance(produto, pd.DataFrame) else produto
    nutriscore = texto_limpo(row.get("nutriscore_grade")).upper()
    ecoscore = texto_limpo(row.get("ecoscore_grade")).upper()
    return {
        "codigo": texto_limpo(row.get("code"), ""),
        "nome": texto_limpo(row.get("product_name")),
        "marca": texto_limpo(row.get("brands")),
        "ingredientes": texto_limpo(row.get("ingredients_text")),
        "nutriscore": "N/A" if nutriscore in ["NÃO INFORMADO", "NAO INFORMADO", "NOT-APPLICABLE", "UNKNOWN"] else nutriscore,
        "ecoscore": "N/A" if ecoscore in ["NÃO INFORMADO", "NAO INFORMADO", "NOT-APPLICABLE", "UNKNOWN"] else ecoscore,
        "embalagem": texto_limpo(row.get("packaging")),
        "categorias": texto_limpo(row.get("categories_tags")),
    }


@st.cache_data(show_spinner=False)
def carregar_dados():
    try:
        df = pd.read_csv(
            "open-food-facts-sample.csv",
            sep="\t",
            usecols=COLUNAS_CSV,
            low_memory=False,
        )
        return df.dropna(subset=["product_name"])
    except Exception as exc:
        st.error(f"Erro ao carregar: {exc}")
        return pd.DataFrame()


def buscar_no_csv(df_produtos, termo):
    if df_produtos.empty or not termo:
        return pd.DataFrame()

    termo = termo.strip()
    por_nome = df_produtos["product_name"].str.contains(termo, case=False, na=False)
    por_marca = df_produtos["brands"].str.contains(termo, case=False, na=False)
    return df_produtos[por_nome | por_marca].head(1)


@st.cache_data(show_spinner=False, ttl=3600)
def buscar_open_food_facts(codigo_barras):
    fields = ",".join(
        [
            "code",
            "product_name",
            "brands",
            "ingredients_text",
            "nutriscore_grade",
            "ecoscore_grade",
            "packaging",
            "categories_tags",
        ]
    )
    url = f"https://world.openfoodfacts.org/api/v2/product/{codigo_barras}.json"

    resposta = requests.get(
        url,
        params={"fields": fields},
        headers=OPEN_FOOD_FACTS_HEADERS,
        timeout=12,
    )
    resposta.raise_for_status()
    payload = resposta.json()

    if payload.get("status") != 1:
        return pd.DataFrame()

    produto = payload.get("product", {})
    if isinstance(produto.get("packaging"), list):
        produto["packaging"] = ", ".join(
            item.get("material", "") or item.get("shape", "") for item in produto["packaging"]
        )
    if isinstance(produto.get("categories_tags"), list):
        produto["categories_tags"] = ", ".join(produto["categories_tags"])

    return pd.DataFrame([produto])


def detectar_codigo_barras(arquivo_imagem):
    if arquivo_imagem is None:
        return None

    try:
        imagem = ImageOps.exif_transpose(Image.open(BytesIO(arquivo_imagem.getvalue()))).convert("RGB")
        if max(imagem.size) > 2200:
            imagem.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
    except Exception:
        return None

    frame_rgb = np.array(imagem)

    def normalizar_codigo(valor):
        codigo = str(valor).strip()
        return codigo if codigo.isdigit() and 6 <= len(codigo) <= 18 else None

    def tentar_pyzbar(img_rgb):
        if decode_barcode is None:
            return None

        try:
            for item in decode_barcode(img_rgb):
                codigo = normalizar_codigo(item.data.decode("utf-8", errors="ignore"))
                if codigo:
                    return codigo
        except Exception:
            return None

        return None

    def tentar_zxing(img_rgb):
        if zxingcpp is None:
            return None

        try:
            for item in zxingcpp.read_barcodes(img_rgb):
                codigo = normalizar_codigo(item.text)
                if codigo:
                    return codigo
        except Exception:
            return None

        return None

    def rotacionar(img_rgb, angulo):
        if angulo == 90:
            return cv2.rotate(img_rgb, cv2.ROTATE_90_CLOCKWISE)
        if angulo == 180:
            return cv2.rotate(img_rgb, cv2.ROTATE_180)
        if angulo == 270:
            return cv2.rotate(img_rgb, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return img_rgb

    def cortes_importantes(img_rgb):
        altura, largura = img_rgb.shape[:2]
        cortes = [img_rgb]
        regioes = [
            (0.08, 0.08, 0.92, 0.92),
            (0.15, 0.15, 0.85, 0.85),
            (0.05, 0.25, 0.95, 0.75),
            (0.20, 0.05, 0.80, 0.95),
            (0.00, 0.15, 1.00, 0.85),
            (0.15, 0.00, 0.85, 1.00),
        ]

        for x1, y1, x2, y2 in regioes:
            esquerda = int(largura * x1)
            topo = int(altura * y1)
            direita = int(largura * x2)
            baixo = int(altura * y2)
            if direita - esquerda > 250 and baixo - topo > 120:
                cortes.append(img_rgb[topo:baixo, esquerda:direita])

        return cortes

    def variantes_visuais(img_rgb):
        variantes = [img_rgb]
        bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        cinza = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        equalizada = cv2.equalizeHist(cinza)
        blur_leve = cv2.GaussianBlur(equalizada, (0, 0), 1.0)
        nitida = cv2.addWeighted(equalizada, 1.7, blur_leve, -0.7, 0)
        _, otsu = cv2.threshold(nitida, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptativa = cv2.adaptiveThreshold(
            nitida,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )

        for escala in [1.35, 1.8]:
            if max(img_rgb.shape[:2]) * escala <= 2600:
                largura = int(img_rgb.shape[1] * escala)
                altura = int(img_rgb.shape[0] * escala)
                variantes.append(cv2.resize(img_rgb, (largura, altura), interpolation=cv2.INTER_CUBIC))

        variantes.extend(
            [
                cv2.cvtColor(cinza, cv2.COLOR_GRAY2RGB),
                cv2.cvtColor(equalizada, cv2.COLOR_GRAY2RGB),
                cv2.cvtColor(nitida, cv2.COLOR_GRAY2RGB),
                cv2.cvtColor(otsu, cv2.COLOR_GRAY2RGB),
                cv2.cvtColor(adaptativa, cv2.COLOR_GRAY2RGB),
                cv2.cvtColor(255 - otsu, cv2.COLOR_GRAY2RGB),
            ]
        )
        return variantes

    def tentar_opencv(img_bgr):
        if hasattr(cv2, "barcode_BarcodeDetector"):
            detector = cv2.barcode_BarcodeDetector()
            try:
                ok, decoded_info, _, _ = detector.detectAndDecode(img_bgr)
                if ok:
                    for codigo in decoded_info:
                        codigo = normalizar_codigo(codigo)
                        if codigo:
                            return codigo
            except Exception:
                pass

        qr_detector = cv2.QRCodeDetector()
        try:
            codigo_qr, _, _ = qr_detector.detectAndDecode(img_bgr)
            return normalizar_codigo(codigo_qr)
        except Exception:
            return None

    candidatos_rgb = []
    for angulo in [0, 90, 270, 180]:
        rotacionada = rotacionar(frame_rgb, angulo)
        for corte in cortes_importantes(rotacionada):
            candidatos_rgb.extend(variantes_visuais(corte))

    for candidato_rgb in candidatos_rgb:
        codigo = tentar_zxing(candidato_rgb)
        if codigo:
            return codigo

    for candidato_rgb in candidatos_rgb:
        codigo = tentar_pyzbar(candidato_rgb)
        if codigo:
            return codigo

    for candidato_rgb in candidatos_rgb:
        candidato_bgr = cv2.cvtColor(candidato_rgb, cv2.COLOR_RGB2BGR)
        codigo = tentar_opencv(candidato_bgr)
        if codigo:
            return codigo

    return None


def contem_qualquer(texto, termos):
    texto = texto.lower()
    return any(termo in texto for termo in termos)


def gerar_mock_ia(produto, perfil):
    time.sleep(1.2)
    dados = produto_para_dict(produto)
    ingredientes = dados["ingredientes"].lower()
    nutri = dados["nutriscore"]
    eco = dados["ecoscore"]
    embalagem = dados["embalagem"].lower()
    categorias = dados["categorias"].lower()

    nome = dados["nome"]
    marca = dados["marca"]
    origem = "código de barras" if dados["codigo"] else "base de dados"
    contexto_busca = " ".join([nome, categorias, ingredientes]).lower()
    produto_doce_ou_lanche = contem_qualquer(
        contexto_busca,
        [
            "biscuit",
            "biscuits",
            "cookie",
            "cookies",
            "bolacha",
            "biscoito",
            "snack",
            "snacks",
            "chocolate",
            "wafer",
            "recheado",
            "sweet",
            "sweets",
            "dessert",
            "desserts",
            "cake",
            "cakes",
            "refrigerante",
            "soda",
            "bebida",
            "drink",
            "drinks",
        ],
    )
    ingrediente_acucar = contem_qualquer(
        ingredientes,
        ["sugar", "sucre", "açúcar", "acucar", "syrup", "xarope", "glucose", "fructose", "dextrose", "maltose"],
    )
    sinal_acucar = ingrediente_acucar or (nutri in ["D", "E"] and produto_doce_ou_lanche)

    if nutri in ["A", "B"]:
        veredito = "boa escolha para entrar no carrinho, com um perfil nutricional favorável."
        saude = (
            f"O NutriScore {nutri} joga a favor do produto. Ainda assim, vale bater o olho "
            "nos ingredientes para confirmar se ele combina com a sua rotina."
        )
    elif nutri == "C":
        veredito = "opção aceitável, mas sem aquele brilho de compra inteligente."
        saude = (
            "O NutriScore C coloca o produto no meio do caminho: não parece o pior vilão, "
            "mas também não é a escolha mais leve para consumo frequente."
        )
    elif nutri in ["D", "E"]:
        veredito = "produto para pensar duas vezes antes de repetir no dia a dia."
        saude = (
            f"O NutriScore {nutri} acende um alerta. Em geral, esse nível costuma pedir "
            "moderação por possível excesso de açúcar, sódio, gorduras ou processamento."
        )
    else:
        veredito = "análise possível, mas com dados nutricionais incompletos."
        saude = (
            "O fabricante não trouxe NutriScore suficiente para uma leitura forte. Aqui, "
            "a lista de ingredientes vira a parte mais importante da decisão."
        )

    pistas_saude = []
    if ingrediente_acucar:
        pistas_saude.append("aparece indício de açúcares ou xaropes")
    elif sinal_acucar:
        pistas_saude.append("a combinação de categoria e NutriScore sugere atenção a açúcar, mesmo sem ingrediente detalhado")
    if contem_qualquer(ingredientes, ["salt", "sel", "sal", "sodium", "sódio", "sodio"]):
        pistas_saude.append("há sinal de sal/sódio na composição")
    if contem_qualquer(ingredientes, ["palm", "palme", "palma"]):
        pistas_saude.append("óleo de palma entra como ponto de atenção")
    if pistas_saude:
        saude += " Pistas encontradas: " + "; ".join(pistas_saude) + "."

    if eco in ["A", "B"]:
        ambiente = f"O EcoScore {eco} é um bom sinal ambiental: a pegada estimada tende a ser menor."
    elif eco in ["D", "E"]:
        ambiente = (
            f"O EcoScore {eco} sugere impacto ambiental alto. Pode envolver ingredientes intensivos, "
            "transporte, processamento ou embalagem menos favorável."
        )
    elif eco == "C":
        ambiente = "O EcoScore C fica na faixa intermediária: não é desastre, mas também não lidera em sustentabilidade."
    else:
        ambiente = "O impacto ambiental não veio bem preenchido, então a embalagem e a categoria ajudam a completar a leitura."

    if contem_qualquer(embalagem, ["plastic", "plastique", "plástico", "plastico"]):
        ambiente += " A embalagem parece envolver plástico, então descarte correto e refil/retorno fariam diferença."
    elif contem_qualquer(embalagem, ["glass", "verre", "vidro"]):
        ambiente += " Vidro costuma ser interessante quando há reciclagem ou reutilização por perto."
    elif contem_qualquer(embalagem, ["carton", "paper", "papier", "papel"]):
        ambiente += " Papel/cartão ajuda, desde que esteja limpo e tenha coleta seletiva disponível."

    if perfil == "Intolerante a Glúten" and contem_qualquer(
        ingredientes, ["glúten", "gluten", "wheat", "ble", "blé", "trigo", "cevada", "barley", "rye", "centeio"]
    ):
        perfil_txt = (
            "Alerta forte para seu perfil: encontrei termos associados a glúten/trigo. "
            "Para intolerância ou doença celíaca, melhor evitar sem confirmação do rótulo."
        )
    elif perfil == "Vegano" and contem_qualquer(
        ingredientes,
        ["milk", "lait", "leite", "egg", "eggs", "oeuf", "ovo", "beurre", "butter", "meat", "carne", "gelatin"],
    ):
        perfil_txt = (
            "Alerta para perfil vegano: a composição indica possíveis ingredientes de origem animal."
        )
    elif perfil == "Redução de Açúcar" and ingrediente_acucar:
        perfil_txt = "Para redução de açúcar, este produto merece cautela: há sinais de açúcar, xarope ou açúcares similares na lista."
    elif perfil == "Redução de Açúcar" and sinal_acucar:
        perfil_txt = (
            "Para redução de açúcar, eu evitaria como compra frequente. Mesmo sem açúcar explícito nos ingredientes, "
            f"o NutriScore {nutri} em um produto de lanche/doce é um sinal forte de cautela."
        )
    elif perfil == "Geral/Nenhum":
        perfil_txt = "Sem restrição selecionada: foque no equilíbrio entre frequência de consumo, NutriScore e descarte da embalagem."
    else:
        perfil_txt = "Não encontrei um alerta óbvio para o perfil selecionado com os dados disponíveis."

    trocas = [
        "procure uma versão com lista de ingredientes menor e embalagem reciclável.",
        "compare com uma marca local: costuma reduzir transporte e facilita rastrear origem.",
        "se for um item de consumo frequente, teste uma alternativa com NutriScore melhor antes de comprar em quantidade.",
        "quando existir, prefira refil, retornável ou compra a granel para reduzir embalagem.",
    ]
    if "beverages" in categorias or "drinks" in categorias or "refrigerantes" in categorias:
        trocas.append("para bebidas doces, água com gás e fruta espremida pode cumprir o papel sem tanto açúcar.")
    if "snacks" in categorias or "biscuits" in categorias:
        trocas.append("para lanche rápido, castanhas, frutas ou biscoitos integrais simples tendem a ser trocas melhores.")

    return f"""
**Análise EcoTrack IA para:** `{nome}`  
**Marca:** {marca} | **Origem dos dados:** {origem}

**Veredito:** {veredito.capitalize()}

**Saúde:** {saude}

**Ambiente:** {ambiente}

**Perfil ({perfil}):** {perfil_txt}

**Troca inteligente:** {random.choice(trocas)}
""".strip()


def exibir_produto(produto):
    dados = produto_para_dict(produto)
    st.success(f"Produto identificado: {dados['nome']} | {dados['marca']}")
    col1, col2, col3 = st.columns(3)
    col1.metric("NutriScore", dados["nutriscore"])
    col2.metric("EcoScore", dados["ecoscore"])
    col3.metric("Código", dados["codigo"] or "BD")

    with st.expander("Dados enviados para a IA"):
        st.json(
            {
                "produto": dados,
                "observacao": "Estes dados são usados como contexto do prompt da IA generativa.",
            }
        )


st.title("EcoTrack Scanner - Protótipo IA")
st.caption("Mock de IA generativa + leitura de imagem/câmera para código de barras.")

with st.spinner("Carregando base local Open Food Facts..."):
    df_produtos = carregar_dados()

with st.sidebar:
    st.header("Perfil")
    perfil_usuario = st.selectbox(
        "Restrição ou objetivo alimentar",
        ["Geral/Nenhum", "Intolerante a Glúten", "Vegano", "Redução de Açúcar"],
    )

    st.info(f"{len(df_produtos):,} produtos carregados.")

if "produto_atual" not in st.session_state:
    st.session_state.produto_atual = None
if "ultimo_codigo_auto" not in st.session_state:
    st.session_state.ultimo_codigo_auto = ""
if "ultima_foto_lida" not in st.session_state:
    st.session_state.ultima_foto_lida = ""

aba_camera, aba_busca = st.tabs(["Câmera / código de barras", "Busca manual"])

with aba_camera:
    st.subheader("Ler código de barras")
    st.write("No celular, prefira anexar uma imagem e escolher a câmera na hora do envio.")

    foto = st.file_uploader(
        "Imagem do código de barras",
        type=["png", "jpg", "jpeg", "webp"],
        help="No celular, toque em Browse files/Escolher arquivo e selecione Câmera ou Tirar foto.",
    )

    codigo_manual = st.text_input("Ou digite o código de barras", placeholder="Ex: 7891000100103")

    codigo_detectado = ""
    if foto:
        st.caption(
            "Lendo automaticamente. Deixe o código grande, mas sem cortar as bordas brancas laterais."
        )

        foto_id = f"{getattr(foto, 'name', '')}:{getattr(foto, 'size', 0)}"
        if st.session_state.ultima_foto_lida != foto_id:
            with st.spinner("Tentando ler o código de barras da imagem..."):
                codigo_detectado = detectar_codigo_barras(foto) or ""
            st.session_state.ultima_foto_lida = foto_id

            if codigo_detectado:
                st.success(f"Código detectado na imagem: {codigo_detectado}")
                st.session_state.ultimo_codigo_auto = codigo_detectado
            else:
                st.warning(
                    "Não consegui ler o código nessa imagem. Tente aproximar mais, deixar as barras na horizontal, "
                    "evitar reflexo e manter uma pequena margem branca nas laterais do código."
                )
        else:
            codigo_detectado = st.session_state.ultimo_codigo_auto

        if st.button("Tentar ler a foto novamente", use_container_width=True):
            st.session_state.ultima_foto_lida = ""
            st.rerun()

    codigo = codigo_detectado or st.session_state.ultimo_codigo_auto or codigo_manual.strip()

    if st.button("Buscar produto pelo código", use_container_width=True):
        if not codigo:
            st.error("Anexe uma imagem, use a câmera ou digite um código de barras primeiro.")
        else:
            try:
                with st.spinner("Consultando Open Food Facts pelo código de barras..."):
                    produto = buscar_open_food_facts(codigo)
                if produto.empty:
                    st.warning("Código não encontrado na Open Food Facts. Tente a busca manual por nome.")
                else:
                    st.session_state.produto_atual = produto
            except Exception as exc:
                st.error(f"Não consegui consultar a Open Food Facts agora: {exc}")

with aba_busca:
    st.subheader("Buscar na base de dados")
    termo_busca = st.text_input(
        "Nome ou marca do produto",
        placeholder="Ex: Pepsi, 7Up, Donuts",
    )

    if st.button("Buscar", use_container_width=True):
        produto = buscar_no_csv(df_produtos, termo_busca)
        if produto.empty:
            st.warning("Produto não encontrado na base de dados.")
        else:
            st.session_state.produto_atual = produto

produto_atual = st.session_state.produto_atual

if produto_atual is not None and not produto_atual.empty:
    st.divider()
    exibir_produto(produto_atual)

    if st.button("Gerar analise com IA", type="primary", use_container_width=True):
        st.markdown("### Análise da IA demonstrativa")
        with st.spinner("Processando contexto e montando relatório EcoTrack..."):
            analise = gerar_mock_ia(produto_atual, perfil_usuario)
        st.info(analise)
else:
    st.info("Escaneie um código de barras ou busque um produto pelo nome para começar.")
