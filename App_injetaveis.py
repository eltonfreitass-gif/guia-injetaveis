import html
import logging
import os
import re
import unicodedata
import hashlib
import json
import tempfile
from copy import copy
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from deep_translator import GoogleTranslator
from openpyxl import load_workbook
from filelock import FileLock, Timeout
import gspread

VERSAO = "8.0"
PASTA_APP = Path(__file__).resolve().parent
ARQUIVO_DADOS = PASTA_APP / "dados_injetaveis.xlsx"
ARQUIVO_LOGO = PASTA_APP / "Logo_huufma.png"
ABA_DADOS = "Dadosrevisados"
ABA_GOOGLE = "Página1"
GOOGLE_SHEET_ID = "1NMg74orqu2KKLe1ug9PISZMBfgWZfdw2WEUO8-r9Tfg"
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title=f"HUUFMA — Guia de Injetáveis v{VERSAO}",
    layout="wide",
    page_icon="💉",
)

st.markdown(
    '''<style>
.block-container {padding-top:1.5rem;padding-bottom:2rem;max-width:1250px}
.header-container {display:flex;gap:12px;align-items:center;flex-wrap:wrap;border-bottom:3px solid #087f8c;padding-bottom:16px;margin:20px 0}
.med-title {font-size:1.8rem;line-height:1.3;overflow-wrap:anywhere;margin:0}
.badge-mav,.badge-ur {color:white;padding:5px 12px;border-radius:8px;font-weight:700;font-size:.8rem}
.badge-mav {background:#b42318}.badge-ur {background:#925400}
.secao-titulo {background:#edf4f8;color:#005A8D;border-left:4px solid #005A8D;padding:7px 10px;margin:10px 0 4px;font-weight:700}
.secao-neo {background:#edf8f8;color:#075c66;border-color:#087f8c}
.info-row {display:flex;gap:12px;padding:6px 0;border-bottom:1px solid #a0a0a040;align-items:flex-start}
.info-label {width:235px;min-width:235px;font-weight:600}
.info-value {flex:1;min-width:0;overflow-wrap:anywhere;line-height:1.65}
.texto-original {white-space:pre-wrap;overflow-wrap:anywhere}
.grupo-dados {font-weight:700;margin-bottom:8px}
.linha-dados {white-space:pre-wrap;border-left:3px solid #087f8c;padding:8px 12px;margin:5px 0;background:#8080800a}
.complemento {margin-left:18px;border-left-color:#9baab4}
.opcao-neo {border:1px solid #087f8c66;border-radius:8px;padding:12px 16px;margin:10px 0;white-space:pre-wrap;overflow-wrap:anywhere}
.estado-ausente {color:#805200;background:#fff4d6;padding:3px 8px;border-radius:5px}
.estado-na {color:#454b53;background:#eef0f2;padding:3px 8px;border-radius:5px}
.st-key-nav_preparo button,.st-key-nav_doses button,.st-key-nav_neo button {min-height:2.5rem;font-weight:650;white-space:normal}
.st-key-conteudo_ficha [data-testid="stVerticalBlock"] {gap:.35rem}
.footer-normal {text-align:center;padding:20px 8px;font-size:11px;border-top:1px solid #a0a0a040;margin-top:35px}
@media(max-width:768px){.block-container{padding:1rem}.info-row{flex-direction:column;gap:5px}.info-label{width:100%;min-width:0}.med-title{font-size:1.35rem}}
</style>''',
    unsafe_allow_html=True,
)

COMERCIAL = "NOME COMERCIAL — LABORATÓRIO"
VIAS = "VIA DE ADMINISTRAÇÃO — POR LABORATÓRIO"

GRUPOS = {
    "Identificação": [
        ("Medicamento / apresentação", "MEDICAMENTO"),
        ("Nomes comerciais e laboratórios", COMERCIAL),
        ("Vias por laboratório", VIAS),
    ],
    "Reconstituição": [
        ("Reconstituição", "RECONSTITUIÇÃO"),
        ("Volume expandido", "VOLUME EXPANDIDO"),
        ("Concentração", "CONCENTRAÇÃO"),
    ],
    "Diluição e administração": [
        ("Diluição", "DILUIÇÃO"),
        ("Concentração de infusão — adulto", "CONCENTRAÇÃO DE INFUSÃO (ADULTO)"),
        ("Concentração de infusão — pediatria", "CONCENTRAÇÃO DE INFUSÃO (PEDIATRIA)"),
        ("Tempo de infusão", "TEMPO DE INFUSÃO"),
    ],
    "Adultos": [
        ("Dose usual", "DOSE ADULTA (USUAL)"),
        ("Dose máxima", "DOSE ADULTA MÁXIMA"),
    ],
    "Pediatria": [
        ("Dose usual", "DOSE PEDIÁTRICA (USUAL)"),
        ("Dose máxima", "DOSE PEDIÁTRICA MÁXIMA"),
    ],
    "Ajustes": [
        ("Ajuste renal", "AJUSTE RENAL"),
        ("Ajuste hepático", "AJUSTE HEPÁTICO"),
    ],
    "Neonatologia": [
        ("Dose usual neonatal", "Neonatal — DOSE USUAL"),
        ("Dose máxima neonatal", "Neonatal — DOSE MÁXIMA"),
        ("Preparo padronizado neonatal", "Neonatal — PREPARO PADRONIZADO"),
    ],
    "Estabilidade do reconstituído": [
        (
            "Ambiente — 25 °C",
            "ESTABILIDADE DO RECONSTITUÍDO (TEMPERATURA AMBIENTE — 25 °C)",
        ),
        (
            "Refrigerado — 2 °C a 8 °C",
            "ESTABILIDADE DO RECONSTITUÍDO REFRIGERADO (2 °C A 8 °C)",
        ),
    ],
    "Estabilidade da diluição": [
        (
            "Ambiente — 25 °C",
            "ESTABILIDADE DA DILUIÇÃO (TEMPERATURA AMBIENTE — 25 °C)",
        ),
        (
            "Refrigerada — 2 °C a 8 °C",
            "ESTABILIDADE DA DILUIÇÃO REFRIGERADA (2 °C A 8 °C)",
        ),
    ],
    "Cuidados": [
        ("Incompatibilidades", "INCOMPATIBILIDADES"),
        ("Observações", "OBSERVAÇÕES"),
    ],
}

COLUNAS = [
    coluna
    for campos in GRUPOS.values()
    for _, coluna in campos
]

TITULOS_CONSOLIDADOS = {
    "DADOS POR VIA:",
    "DADOS POR LABORATÓRIO:",
    "DADOS POR VIA E LABORATÓRIO:",
    "DADOS GERAIS E POR LABORATÓRIO:",
    "DETALHAMENTO:",
}


def texto_campo(valor):
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip()


def normalizar_busca(valor):
    texto = unicodedata.normalize(
        "NFKD",
        texto_campo(valor).casefold(),
    )
    return re.sub(
        r"\s+",
        " ",
        "".join(
            c for c in texto
            if not unicodedata.combining(c)
        ),
    ).strip()


def contem_marcador(nome, marcador):
    return bool(
        re.search(
            rf"\b{re.escape(marcador)}\b",
            nome,
            re.IGNORECASE,
        )
    )


def possui_conteudo(valor):
    return normalizar_busca(valor) not in {
        "",
        "-",
        "_",
        "nao informado na base",
        "nao se aplica",
    }


def formatar_conteudo(valor):
    texto = texto_campo(valor) or "Não informado na base"
    estado = normalizar_busca(texto)

    if estado in {"nao informado na base", "nao se aplica"}:
        classe = (
            "estado-ausente"
            if estado == "nao informado na base"
            else "estado-na"
        )
        return (
            f'<span class="{classe}">'
            f"{html.escape(texto)}"
            "</span>"
        )

    linhas = texto.splitlines()

    if linhas and linhas[0].strip() in TITULOS_CONSOLIDADOS:
        partes = [
            '<div class="grupo-dados">'
            + html.escape(linhas[0])
            + "</div>"
        ]

        for linha in linhas[1:]:
            classe = (
                "linha-dados"
                if linha.lstrip().startswith("•")
                else "texto-original"
            )

            if linha.lstrip().startswith("↳"):
                classe = "linha-dados complemento"

            partes.append(
                f'<div class="{classe}">'
                f"{html.escape(linha)}"
                "</div>"
            )

        return "".join(partes)

    return (
        '<div class="texto-original">'
        + html.escape(texto)
        + "</div>"
    )


def html_campo(rotulo, valor):
    return (
        '<div class="info-row">'
        '<div class="info-label">'
        + html.escape(rotulo)
        + "</div>"
        '<div class="info-value">'
        + formatar_conteudo(valor)
        + "</div></div>"
    )


def exibir_campo(rotulo, valor):
    st.markdown(
        html_campo(rotulo, valor),
        unsafe_allow_html=True,
    )


def titulo_secao(texto, neonatal=False):
    classe = (
        "secao-titulo secao-neo"
        if neonatal
        else "secao-titulo"
    )
    st.markdown(
        f'<div class="{classe}">'
        f"{html.escape(texto)}"
        "</div>",
        unsafe_allow_html=True,
    )


def exibir_grupo(registro, grupo):
    corpo = "".join(
        html_campo(rotulo, registro.get(coluna))
        for rotulo, coluna in GRUPOS[grupo]
    )
    st.markdown(
        f'<div class="secao-titulo">'
        f"{html.escape(grupo)}"
        f"</div>{corpo}",
        unsafe_allow_html=True,
    )


def validar_base(df):
    if df.columns.duplicated().any():
        raise ValueError(
            "Existem cabeçalhos duplicados na aba de dados."
        )

    faltantes = [
        coluna
        for coluna in COLUNAS
        if coluna not in df.columns
    ]

    if faltantes:
        raise ValueError(
            "Colunas ausentes: " + "; ".join(faltantes)
        )

    if df.empty:
        raise ValueError(
            "A aba de dados não contém registros."
        )

    sem_nome = df["MEDICAMENTO"].map(texto_campo).eq("")

    if sem_nome.any():
        raise ValueError(
            "Há registros sem nome de medicamento."
        )

    duplicados = (
        df["MEDICAMENTO"]
        .map(normalizar_busca)
        .duplicated(keep=False)
    )

    if duplicados.any():
        nomes = df.loc[
            duplicados,
            "MEDICAMENTO",
        ].unique()[:8]
        raise ValueError(
            "Revise os nomes duplicados: "
            + "; ".join(nomes)
        )


def usar_google():
    try:
        credenciais = st.secrets.get("gcp_service_account")
        identificador = st.secrets.get("google_sheet_id")
    except FileNotFoundError:
        return False

    if identificador and not credenciais:
        raise ValueError(
            "Configure gcp_service_account nos Secrets "
            "para acessar a planilha online."
        )

    return bool(credenciais)


def planilha_google():
    credenciais = dict(
        st.secrets["gcp_service_account"]
    )
    cliente = gspread.service_account_from_dict(
        credenciais
    )
    identificador = st.secrets.get(
        "google_sheet_id",
        GOOGLE_SHEET_ID,
    )
    aba = st.secrets.get(
        "google_sheet_aba",
        ABA_GOOGLE,
    )

    return (
        cliente
        .open_by_key(identificador)
        .worksheet(aba)
    )


def assinatura_linhas(linhas):
    texto = json.dumps(
        linhas,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()


@st.cache_data(ttl=30, show_spinner=False)
def obter_linhas_google():
    return planilha_google().get_all_values()


def assinatura_arquivo():
    if usar_google():
        return assinatura_linhas(
            obter_linhas_google()
        )

    return hashlib.sha256(
        ARQUIVO_DADOS.read_bytes()
    ).hexdigest()


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_dados(assinatura):
    if usar_google():
        linhas = obter_linhas_google()

        if assinatura_linhas(linhas) != assinatura:
            raise ValueError(
                "A planilha mudou durante a leitura. "
                "Atualize a página."
            )

        if not linhas:
            raise ValueError(
                "A aba da planilha Google está vazia."
            )

        cabecalhos = [
            str(c).strip()
            for c in linhas[0]
        ]

        dados = [
            linha[:len(cabecalhos)]
            + [""] * (
                len(cabecalhos) - len(linha)
            )
            for linha in linhas[1:]
        ]

        df = pd.DataFrame(
            dados,
            columns=cabecalhos,
            dtype=object,
        )

    else:
        bruto = ARQUIVO_DADOS.read_bytes()

        if hashlib.sha256(
            bruto
        ).hexdigest() != assinatura:
            raise ValueError(
                "O arquivo mudou durante a leitura. "
                "Atualize a página."
            )

        with pd.ExcelFile(
            BytesIO(bruto),
            engine="openpyxl",
        ) as excel:
            if ABA_DADOS not in excel.sheet_names:
                raise ValueError(
                    "Aba Dadosrevisados não encontrada. "
                    "Abas disponíveis: "
                    + ", ".join(excel.sheet_names)
                )

            df = pd.read_excel(
                excel,
                sheet_name=ABA_DADOS,
                dtype=object,
                keep_default_na=False,
            )

    df.columns = [
        str(c).strip()
        for c in df.columns
    ]

    preenchidas = df.apply(
        lambda linha: any(
            texto_campo(valor)
            for valor in linha
        ),
        axis=1,
    )

    df = df.loc[preenchidas].copy()

    linhas_planilha = [
        int(indice) + 2
        for indice in df.index
    ]

    validar_base(df)

    for coluna in df.columns:
        df[coluna] = df[coluna].map(
            texto_campo
        )

    df = df.reset_index(drop=True)
    df.attrs["linhas_excel"] = linhas_planilha

    return df


def gravar_registro(
    dados,
    assinatura_original,
    linha_excel=None,
):
    if usar_google():
        gravar_registro_google(
            dados,
            assinatura_original,
            linha_excel,
        )
        return

    temporario = None
    wb = None

    try:
        with FileLock(
            str(ARQUIVO_DADOS) + ".lock",
            timeout=8,
        ):
            if assinatura_arquivo() != assinatura_original:
                raise ValueError(
                    "A base mudou desde a abertura do "
                    "formulário. Recarregue e revise "
                    "sua alteração."
                )

            bruto = ARQUIVO_DADOS.read_bytes()
            wb = load_workbook(BytesIO(bruto))
            ws = wb[ABA_DADOS]

            cabecalhos = [
                str(c.value).strip()
                for c in ws[1]
            ]

            if set(dados) != set(cabecalhos):
                raise ValueError(
                    "Os campos do formulário não "
                    "correspondem aos cabeçalhos."
                )

            nome = normalizar_busca(
                dados.get("MEDICAMENTO")
            )

            if not nome:
                raise ValueError(
                    "Preencha o nome do medicamento."
                )

            col_nome = (
                cabecalhos.index("MEDICAMENTO") + 1
            )

            for linha in range(
                2,
                ws.max_row + 1,
            ):
                existente = normalizar_busca(
                    ws.cell(
                        linha,
                        col_nome,
                    ).value
                )

                if (
                    linha != linha_excel
                    and existente == nome
                ):
                    raise ValueError(
                        "Já existe uma ficha com esse "
                        "nome. Edite a ficha existente."
                    )

            destino = (
                linha_excel
                if linha_excel is not None
                else ws.max_row + 1
            )

            if (
                linha_excel is not None
                and not 2 <= destino <= ws.max_row
            ):
                raise ValueError(
                    "A linha selecionada não existe "
                    "mais. Recarregue o formulário."
                )

            for coluna, nome_coluna in enumerate(
                cabecalhos,
                1,
            ):
                celula = ws.cell(
                    destino,
                    coluna,
                )
                valor = str(
                    dados[nome_coluna]
                )

                if (
                    linha_excel is None
                    and destino > 2
                ):
                    celula._style = copy(
                        ws.cell(
                            destino - 1,
                            coluna,
                        )._style
                    )

                if texto_campo(
                    celula.value
                ) != valor:
                    celula.value = valor
                    celula.data_type = "s"

            if linha_excel is None:
                if ws.auto_filter.ref:
                    from openpyxl.utils.cell import (
                        range_boundaries,
                        get_column_letter,
                    )

                    a, b, c, d = (
                        range_boundaries(
                            ws.auto_filter.ref
                        )
                    )

                    ws.auto_filter.ref = (
                        f"{get_column_letter(a)}{b}:"
                        f"{get_column_letter(c)}"
                        f"{destino}"
                    )

                for tabela in ws.tables.values():
                    from openpyxl.utils.cell import (
                        range_boundaries,
                        get_column_letter,
                    )

                    a, b, c, d = (
                        range_boundaries(
                            tabela.ref
                        )
                    )

                    tabela.ref = (
                        f"{get_column_letter(a)}{b}:"
                        f"{get_column_letter(c)}"
                        f"{destino}"
                    )

            backup = PASTA_APP / "backups"
            backup.mkdir(exist_ok=True)

            caminho_backup = backup / (
                "dados_injetaveis_"
                f"{assinatura_original}.xlsx"
            )

            if not caminho_backup.exists():
                caminho_backup.write_bytes(
                    bruto
                )

            with tempfile.NamedTemporaryFile(
                dir=PASTA_APP,
                suffix=".xlsx",
                delete=False,
            ) as arquivo:
                temporario = Path(
                    arquivo.name
                )

            wb.save(temporario)
            wb.close()
            wb = None

            if assinatura_arquivo() != assinatura_original:
                raise ValueError(
                    "O arquivo foi alterado durante "
                    "a gravação. Nada foi aplicado."
                )

            os.replace(
                temporario,
                ARQUIVO_DADOS,
            )
            carregar_dados.clear()

    finally:
        if wb is not None:
            wb.close()

        if temporario is not None:
            temporario.unlink(
                missing_ok=True
            )


def gravar_registro_google(
    dados,
    assinatura_original,
    linha_excel=None,
):
    folha = planilha_google()
    linhas = folha.get_all_values()

    if assinatura_linhas(
        linhas
    ) != assinatura_original:
        raise ValueError(
            "A planilha online mudou. "
            "Recarregue o formulário antes de salvar."
        )

    if not linhas:
        raise ValueError(
            "A aba online está vazia."
        )

    cabecalhos = [
        str(c).strip()
        for c in linhas[0]
    ]

    if (
        set(cabecalhos) != set(dados)
        or len(cabecalhos) != len(set(cabecalhos))
    ):
        raise ValueError(
            "Os cabeçalhos online não correspondem "
            "aos campos do formulário."
        )

    coluna_nome = cabecalhos.index(
        "MEDICAMENTO"
    )
    nome = normalizar_busca(
        dados.get("MEDICAMENTO")
    )

    if not nome:
        raise ValueError(
            "Preencha o nome do medicamento."
        )

    for numero, linha in enumerate(
        linhas[1:],
        start=2,
    ):
        existente = (
            linha[coluna_nome]
            if coluna_nome < len(linha)
            else ""
        )

        if (
            numero != linha_excel
            and normalizar_busca(
                existente
            ) == nome
        ):
            raise ValueError(
                "Já existe uma ficha com esse nome. "
                "Edite a ficha existente."
            )

    valores = [
        str(dados[c])
        for c in cabecalhos
    ]

    if linha_excel is None:
        folha.append_row(
            valores,
            value_input_option="RAW",
        )

    else:
        if not 2 <= linha_excel <= len(linhas):
            raise ValueError(
                "A linha mudou. "
                "Recarregue o formulário."
            )

        atual = linhas[
            linha_excel - 1
        ]

        antigo = (
            atual[:len(cabecalhos)]
            + [""] * (
                len(cabecalhos)
                - len(atual)
            )
        )

        if antigo == valores:
            return

        from openpyxl.utils.cell import (
            get_column_letter,
        )

        alteracoes = [
            {
                "range": (
                    f"{get_column_letter(i)}"
                    f"{linha_excel}"
                ),
                "values": [[valor]],
            }
            for i, valor in enumerate(
                valores,
                1,
            )
            if antigo[i - 1] != valor
        ]

        folha.batch_update(
            alteracoes,
            value_input_option="RAW",
        )

    obter_linhas_google.clear()
    carregar_dados.clear()


def salvar_formulario(
    dados,
    assinatura,
    linha=None,
):
    if not st.session_state.get(
        "auth"
    ):
        st.error(
            "Entre no acesso administrativo "
            "antes de salvar."
        )
        return

    try:
        gravar_registro(
            dados,
            assinatura,
            linha,
        )

    except (
        ValueError,
        PermissionError,
        Timeout,
    ) as erro:
        dica = (
            " Confira o acesso à planilha online."
            if usar_google()
            else (
                " Se o arquivo estiver aberto "
                "no Excel, feche-o e tente novamente."
            )
        )
        st.error(
            f"Não foi possível salvar: "
            f"{erro}.{dica}"
        )
        return

    except Exception:
        logger.exception(
            "Falha na gravação"
        )
        st.error(
            "Não foi possível salvar. "
            "Consulte o terminal do aplicativo."
        )
        return

    st.session_state.pop(
        "admin_snapshot",
        None,
    )
    st.session_state["admin_epoch"] = (
        st.session_state.get(
            "admin_epoch",
            0,
        )
        + 1
    )

    if usar_google():
        aba = st.secrets.get(
            "google_sheet_aba",
            ABA_GOOGLE,
        )
        mensagem = (
            f"Registro salvo na aba {aba} "
            "do Google Sheets."
        )
    else:
        mensagem = (
            "Registro salvo na aba local "
            "Dadosrevisados. Backup criado."
        )

    st.session_state[
        "mensagem_admin"
    ] = mensagem
    st.rerun()


def recarregar_formulario():
    st.session_state.pop(
        "admin_snapshot",
        None,
    )
    st.session_state["admin_epoch"] = (
        st.session_state.get(
            "admin_epoch",
            0,
        )
        + 1
    )


def tela_administrativa(
    df,
    menu,
    assinatura,
):
    if usar_google():
        aba = st.secrets.get(
            "google_sheet_aba",
            ABA_GOOGLE,
        )
        st.caption(
            f"Edição da aba {aba} "
            "no Google Sheets. Se outra pessoa "
            "alterar a planilha, recarregue "
            "o formulário antes de salvar."
        )
    else:
        st.warning(
            "Fonte local em uso. Configure o "
            "Google Sheets nos Secrets para "
            "manter as edições na hospedagem."
        )

    novo = menu == "Adicionar Novo"

    st.header(
        "Cadastrar medicamento / apresentação"
        if novo
        else "Editar ficha consolidada"
    )

    nome = ""

    if not novo:
        opcoes = sorted(
            df["MEDICAMENTO"],
            key=normalizar_busca,
        )

        if (
            st.session_state.get(
                "editar_medicamento"
            )
            not in opcoes
        ):
            st.session_state[
                "editar_medicamento"
            ] = opcoes[0]

        nome = st.selectbox(
            "Medicamento",
            opcoes,
            key="editar_medicamento",
        )

    token = (
        menu,
        nome,
    )

    snapshot = st.session_state.get(
        "admin_snapshot"
    )

    if (
        snapshot is None
        or snapshot["token"] != token
    ):
        indice = (
            None
            if novo
            else df.index[
                df["MEDICAMENTO"].eq(
                    nome
                )
            ][0]
        )

        snapshot = {
            "token": token,
            "assinatura": assinatura,
            "linha": (
                None
                if novo
                else df.attrs[
                    "linhas_excel"
                ][indice]
            ),
            "dados": (
                {
                    c: ""
                    for c in df.columns
                }
                if novo
                else df.loc[
                    indice
                ].to_dict()
            ),
        }

        st.session_state[
            "admin_snapshot"
        ] = snapshot

    if (
        snapshot["assinatura"]
        != assinatura
    ):
        st.warning(
            "A base mudou depois que o "
            "formulário foi aberto. Copie "
            "suas alterações antes de recarregar."
        )

    st.button(
        "Recarregar formulário",
        on_click=recarregar_formulario,
    )

    prefixo = hashlib.sha256(
        repr(
            (
                token,
                snapshot["assinatura"],
                st.session_state.get(
                    "admin_epoch",
                    0,
                ),
            )
        ).encode()
    ).hexdigest()[:20]

    with st.form(
        "form_" + prefixo
    ):
        dados = {}

        for grupo, campos in (
            GRUPOS.items()
        ):
            st.subheader(
                grupo
            )

            for rotulo, coluna in campos:
                dados[coluna] = st.text_area(
                    rotulo,
                    value=snapshot[
                        "dados"
                    ].get(
                        coluna,
                        "",
                    ),
                    height=(
                        130
                        if (
                            "PREPARO PADRONIZADO"
                            in coluna
                        )
                        else 100
                    ),
                    key=(
                        f"editar_{prefixo}_"
                        f"{coluna}"
                    ),
                )

        extras = [
            c
            for c in snapshot["dados"]
            if c not in dados
        ]

        if extras:
            st.subheader(
                "Outros campos da base"
            )

            for coluna in extras:
                dados[
                    coluna
                ] = st.text_area(
                    coluna,
                    value=snapshot[
                        "dados"
                    ][coluna],
                    key=(
                        f"editar_{prefixo}_"
                        f"{coluna}"
                    ),
                )

        salvar = st.form_submit_button(
            "Salvar registro",
            use_container_width=True,
        )

    if salvar:
        salvar_formulario(
            dados,
            snapshot["assinatura"],
            snapshot["linha"],
        )


def exibir_neonatologia(
    registro
):
    titulo_secao(
        "Doses e preparo neonatal",
        neonatal=True,
    )

    campos = GRUPOS[
        "Neonatologia"
    ]

    for rotulo, coluna in (
        campos[:2]
    ):
        exibir_campo(
            rotulo,
            registro.get(coluna),
        )

    preparo = texto_campo(
        registro.get(
            campos[2][1]
        )
    )

    titulo_secao(
        "Preparo padronizado",
        neonatal=True,
    )

    blocos = re.split(
        (
            r"(?m)(?=^OPÇÃO\s+\d+\s*[—–:-]"
            r"|^TEMPO DE INFUSÃO\s*"
            r"\(todas as opções\))"
        ),
        preparo,
    )

    if any(
        re.match(
            r"OPÇÃO\s+\d+",
            bloco,
        )
        for bloco in blocos
    ):
        for bloco in blocos:
            if bloco:
                st.markdown(
                    '<div class="opcao-neo">'
                    + html.escape(
                        bloco
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
    else:
        exibir_campo(
            "Orientação de preparo",
            preparo,
        )

    st.caption(
        "Conteúdo apresentado conforme a "
        "base, sem cálculo automático de "
        "dose ou volume. Confira as "
        "condições específicas do preparo."
    )


def exibir_ficha(
    registro
):
    st.markdown(
        html_campo(
            "Nomes comerciais e laboratórios",
            registro[COMERCIAL],
        )
        + html_campo(
            "Vias por laboratório",
            registro[VIAS],
        ),
        unsafe_allow_html=True,
    )

    tem_neonatologia = any(
        possui_conteudo(
            registro.get(
                coluna
            )
        )
        for _, coluna in (
            GRUPOS[
                "Neonatologia"
            ]
        )
    )

    secoes = [
        "💉 Preparo e administração",
        "📏 Doses e ajustes",
    ]

    if tem_neonatologia:
        secoes.append(
            "👶 Neonatologia"
        )

    if (
        st.session_state.get(
            "secao_ficha"
        )
        not in secoes
    ):
        st.session_state[
            "secao_ficha"
        ] = secoes[0]

    colunas = st.columns(
        len(secoes)
    )

    chaves = [
        "nav_preparo",
        "nav_doses",
        "nav_neo",
    ]

    for coluna, rotulo, chave in zip(
        colunas,
        secoes,
        chaves,
    ):
        with coluna:
            clicado = st.button(
                rotulo,
                key=chave,
                type=(
                    "primary"
                    if (
                        st.session_state[
                            "secao_ficha"
                        ]
                        == rotulo
                    )
                    else "secondary"
                ),
                use_container_width=True,
            )

            if clicado:
                st.session_state[
                    "secao_ficha"
                ] = rotulo

    secao = st.session_state[
        "secao_ficha"
    ]

    with st.container(
        key="conteudo_ficha"
    ):
        if secao == secoes[0]:
            cuidados = [
                rotulo.lower()
                for rotulo, coluna in (
                    GRUPOS[
                        "Cuidados"
                    ]
                )
                if possui_conteudo(
                    registro.get(
                        coluna
                    )
                )
            ]

            if cuidados:
                st.warning(
                    "Esta ficha contém "
                    + " e ".join(
                        cuidados
                    )
                    + ". Confira a seção "
                    "Cuidados antes do preparo."
                )

            exibir_grupo(
                registro,
                "Reconstituição",
            )
            exibir_grupo(
                registro,
                "Estabilidade do reconstituído",
            )
            exibir_grupo(
                registro,
                "Diluição e administração",
            )
            exibir_grupo(
                registro,
                "Estabilidade da diluição",
            )
            exibir_grupo(
                registro,
                "Cuidados",
            )

        elif secao == secoes[1]:
            for grupo in [
                "Adultos",
                "Pediatria",
                "Ajustes",
            ]:
                exibir_grupo(
                    registro,
                    grupo,
                )

        else:
            exibir_neonatologia(
                registro
            )

        extras = [
            c
            for c in registro.index
            if c not in COLUNAS
        ]

        if extras:
            titulo_secao(
                "Outras informações da base"
            )

            for coluna in extras:
                exibir_campo(
                    coluna,
                    registro[coluna],
                )


def limpar_busca():
    st.session_state[
        "texto_busca"
    ] = ""
    st.session_state.pop(
        "medicamento_pesquisa",
        None,
    )


def tela_pesquisa(
    df
):
    st.title(
        "Guia de Medicamentos Injetáveis"
    )
    st.caption(
        "HU-UFMA • Consulta por "
        "medicamento e apresentação"
    )

    busca, limpar = st.columns(
        [4, 1]
    )

    with busca:
        termo = st.text_input(
            "Pesquisar por medicamento, "
            "nome comercial ou laboratório",
            key="texto_busca",
            placeholder=(
                "Digite parte do nome"
            ),
        )

    with limpar:
        st.button(
            "Limpar busca",
            on_click=limpar_busca,
            use_container_width=True,
        )

    termo = normalizar_busca(
        termo
    )

    mascara = (
        df["MEDICAMENTO"]
        .map(normalizar_busca)
        .str.contains(
            termo,
            regex=False,
        )
    )

    mascara |= (
        df[COMERCIAL]
        .map(normalizar_busca)
        .str.contains(
            termo,
            regex=False,
        )
    )

    opcoes = [""] + sorted(
        df.loc[
            mascara,
            "MEDICAMENTO",
        ],
        key=normalizar_busca,
    )

    if (
        st.session_state.get(
            "medicamento_pesquisa"
        )
        not in opcoes
    ):
        st.session_state[
            "medicamento_pesquisa"
        ] = ""

    if len(opcoes) == 1:
        st.info(
            "Nenhum medicamento encontrado."
        )
        return

    escolha = st.selectbox(
        "Selecione o medicamento "
        "/ apresentação",
        opcoes,
        format_func=lambda valor: (
            valor or "Selecione..."
        ),
        key="medicamento_pesquisa",
    )

    if not escolha:
        st.info(
            "Selecione um medicamento "
            "para consultar a ficha."
        )
        return

    cabecalho = (
        '<div class="header-container">'
        '<h2 class="med-title">'
        f"{html.escape(escolha)}"
        "</h2>"
    )

    if contem_marcador(
        escolha,
        "MAV",
    ):
        cabecalho += (
            '<span class="badge-mav">'
            "ALTA VIGILÂNCIA — MAV"
            "</span>"
        )

    if contem_marcador(
        escolha,
        "UR",
    ):
        cabecalho += (
            '<span class="badge-ur">'
            "USO RESTRITO — UR"
            "</span>"
        )

    st.markdown(
        cabecalho + "</div>",
        unsafe_allow_html=True,
    )

    registro = df.loc[
        df["MEDICAMENTO"].eq(
            escolha
        )
    ].iloc[0]

    exibir_ficha(
        registro
    )
    exibir_fda(
        escolha
    )


def exibir_rodape():
    st.markdown(
        f"""
        <div class="footer-normal">
            <b>Guia de Medicamentos Injetáveis — HUUFMA</b><br>
            Versão {VERSAO}<br>
            Desenvolvimento: Elton Jonh Freitas Santos<br>
            Colaboradores: Vinicius Brito Pereira |
            Carolayne Silva Amorim
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(
    ttl=86400,
    max_entries=200,
    show_spinner=False,
)
def buscar_ingles_rxcui(
    nome
):
    termo = re.sub(
        r"\([^)]*\)",
        " ",
        str(nome),
    )

    termo = re.sub(
        (
            r"\b(?:MAV|UR|AMPOLA|"
            r"INJETÁVEL|INJETAVEL)\b"
        ),
        " ",
        termo,
        flags=re.IGNORECASE,
    )

    termo = re.sub(
        (
            r"\d+(?:[.,]\d+)?\s*"
            r"(?:MG|MCG|G|ML|UI|MEQ)"
            r"\b.*"
        ),
        "",
        termo,
        flags=re.IGNORECASE,
    )

    termo = re.sub(
        r"\s+",
        " ",
        termo,
    ).strip()

    if not termo:
        return None

    resposta = requests.get(
        "https://rxnav.nlm.nih.gov/REST/approximateTerm.json",
        params={
            "term": termo,
            "maxEntries": 1,
        },
        timeout=8,
    )
    resposta.raise_for_status()

    candidatos = (
        resposta.json()
        .get(
            "approximateGroup",
            {},
        )
        .get(
            "candidate",
            [],
        )
    )

    if not candidatos:
        return None

    rxcui = candidatos[0].get(
        "rxcui"
    )

    if not rxcui:
        return None

    resposta_nome = requests.get(
        (
            "https://rxnav.nlm.nih.gov/"
            f"REST/rxcui/{rxcui}/"
            "related.json"
        ),
        params={
            "tty": "IN",
        },
        timeout=8,
    )
    resposta_nome.raise_for_status()

    grupos = (
        resposta_nome.json()
        .get(
            "relatedGroup",
            {},
        )
        .get(
            "conceptGroup",
            [],
        )
    )

    nomes = set()

    for grupo in grupos:
        for conceito in grupo.get(
            "conceptProperties",
            [],
        ):
            nome_en = conceito.get(
                "name"
            )

            if nome_en:
                nomes.add(
                    nome_en
                )

    if len(nomes) != 1:
        return None

    return next(
        iter(nomes)
    )


@st.cache_data(
    ttl=3600,
    max_entries=200,
    show_spinner=False,
)
def consultar_fda(
    nome_ingles
):
    termo = (
        str(nome_ingles)
        .strip()
        .replace('"', "")
    )

    if not termo:
        return []

    resposta = requests.get(
        "https://api.fda.gov/drug/label.json",
        params={
            "search": (
                'openfda.generic_name:'
                f'"{termo}"'
            ),
            "limit": 10,
        },
        timeout=12,
    )

    if resposta.status_code == 404:
        return []

    resposta.raise_for_status()

    return (
        resposta.json()
        .get(
            "results",
            [],
        )
    )


def dividir_texto(
    texto,
    limite=3500,
):
    restante = str(
        texto
    ).strip()

    partes = []

    while restante:
        if len(restante) <= limite:
            partes.append(
                restante
            )
            break

        corte = restante.rfind(
            " ",
            0,
            limite + 1,
        )

        if corte < limite // 2:
            corte = limite

        partes.append(
            restante[:corte]
        )

        restante = (
            restante[corte:]
            .lstrip()
        )

    return partes


@st.cache_data(
    ttl=86400,
    max_entries=300,
    show_spinner=False,
)
def traduzir_texto(
    texto
):
    tradutor = GoogleTranslator(
        source="en",
        target="pt",
    )

    traducoes = []

    for parte in dividir_texto(
        texto
    ):
        traducao = (
            tradutor.translate(
                parte
            )
        )

        if not traducao:
            raise ValueError(
                "Resposta vazia do serviço "
                "de tradução."
            )

        traducoes.append(
            traducao
        )

    return "\n\n".join(
        traducoes
    )


def metadado_fda(
    registro,
    campo,
):
    valor = (
        registro.get(
            "openfda",
            {},
        )
        .get(
            campo,
            [],
        )
    )

    if isinstance(
        valor,
        list,
    ):
        return ", ".join(
            str(item)
            for item in valor
        )

    return (
        str(valor)
        if valor
        else ""
    )


def rotulo_fda(
    registro,
    indice,
):
    marca = (
        metadado_fda(
            registro,
            "brand_name",
        )
        or "Marca não informada"
    )

    fabricante = (
        metadado_fda(
            registro,
            "manufacturer_name",
        )
        or "Fabricante não informado"
    )

    via = (
        metadado_fda(
            registro,
            "route",
        )
        or "Via não informada"
    )

    return (
        f"{indice + 1}. "
        f"{marca} | "
        f"{fabricante} | "
        f"{via}"
    )


def exibir_fda(
    medicamento
):
    with st.expander(
        "🔎 Referência complementar — FDA (EUA)"
    ):
        st.caption(
            "Consulta externa independente da "
            "ficha institucional. O resultado "
            "pode corresponder a outro produto, "
            "via ou apresentação. Confira a "
            "identificação da bula."
        )

        if (
            st.session_state.get(
                "fda_medicamento"
            )
            != medicamento
        ):
            st.session_state[
                "fda_medicamento"
            ] = medicamento
            st.session_state[
                "fda_termo"
            ] = ""
            st.session_state[
                "fda_resultados"
            ] = []
            st.session_state[
                "fda_consultado"
            ] = False
            st.session_state.pop(
                "fda_resultado_selecionado",
                None,
            )

        if st.button(
            "Sugerir nome em inglês",
            key="sugerir_rxnorm",
        ):
            try:
                with st.spinner(
                    "Consultando o RxNorm..."
                ):
                    sugestao = (
                        buscar_ingles_rxcui(
                            medicamento
                        )
                    )

                if sugestao:
                    st.session_state[
                        "fda_termo"
                    ] = sugestao
                    st.info(
                        "Sugestão aproximada. "
                        "Confira o princípio ativo "
                        "antes de pesquisar."
                    )
                else:
                    st.warning(
                        "Não foi encontrada uma "
                        "sugestão única. Informe "
                        "o princípio ativo em inglês."
                    )

            except Exception:
                logger.exception(
                    "Falha na consulta RxNorm"
                )
                st.warning(
                    "O RxNorm não respondeu. "
                    "Você pode informar o nome "
                    "em inglês manualmente."
                )

        termo = st.text_input(
            "Princípio ativo em inglês:",
            key="fda_termo",
        )

        if st.button(
            "Pesquisar na FDA",
            key="consultar_fda",
        ):
            if not termo.strip():
                st.warning(
                    "Informe o princípio ativo "
                    "em inglês."
                )
            else:
                try:
                    with st.spinner(
                        "Consultando a FDA..."
                    ):
                        resultados = consultar_fda(
                            termo
                        )

                    st.session_state[
                        "fda_resultados"
                    ] = resultados
                    st.session_state[
                        "fda_consultado"
                    ] = True
                    st.session_state[
                        "fda_termo_consultado"
                    ] = termo
                    st.session_state.pop(
                        "fda_resultado_selecionado",
                        None,
                    )

                except Exception:
                    logger.exception(
                        "Falha na consulta FDA"
                    )
                    st.session_state[
                        "fda_resultados"
                    ] = []
                    st.session_state[
                        "fda_consultado"
                    ] = False
                    st.error(
                        "Não foi possível consultar "
                        "a FDA. A ficha institucional "
                        "permanece disponível."
                    )

        resultados = (
            st.session_state.get(
                "fda_resultados",
                [],
            )
        )

        if not resultados:
            if st.session_state.get(
                "fda_consultado"
            ):
                st.info(
                    "Nenhum resultado encontrado."
                )
            return

        st.caption(
            "Resultados para: "
            + st.session_state.get(
                "fda_termo_consultado",
                "",
            )
            + ". São apresentados até "
            "10 resultados."
        )

        selecionado = st.selectbox(
            "Selecione e confira o produto:",
            options=list(
                range(
                    len(resultados)
                )
            ),
            format_func=lambda indice: (
                rotulo_fda(
                    resultados[indice],
                    indice,
                )
            ),
            key="fda_resultado_selecionado",
        )

        registro = resultados[
            selecionado
        ]

        st.write(
            "**Princípio ativo:**",
            metadado_fda(
                registro,
                "generic_name",
            )
            or "Não informado",
        )

        st.write(
            "**Via:**",
            metadado_fda(
                registro,
                "route",
            )
            or "Não informada",
        )

        st.write(
            "**Fabricante:**",
            metadado_fda(
                registro,
                "manufacturer_name",
            )
            or "Não informado",
        )

        st.write(
            "**Data informada pela fonte:**",
            registro.get(
                "effective_time",
                "Não informada",
            ),
        )

        identificador = registro.get(
            "set_id",
            "",
        )

        if re.fullmatch(
            r"[0-9a-fA-F-]{36}",
            identificador,
        ):
            st.markdown(
                "[Abrir documento no DailyMed]"
                "(https://dailymed.nlm.nih.gov/"
                "dailymed/drugInfo.cfm?"
                f"setid={identificador})"
            )

        st.markdown(
            "[Sobre os dados do openFDA]"
            "(https://open.fda.gov/apis/"
            "drug/label/)"
        )

        secoes = [
            (
                "Mecanismo de ação",
                "mechanism_of_action",
            ),
            (
                "Contraindicações",
                "contraindications",
            ),
            (
                "Interações",
                "drug_interactions",
            ),
            (
                "Reações adversas",
                "adverse_reactions",
            ),
            (
                "Uso pediátrico",
                "pediatric_use",
            ),
            (
                "Uso geriátrico",
                "geriatric_use",
            ),
            (
                "Gravidez",
                "pregnancy",
            ),
            (
                "Avisos e precauções",
                "warnings_and_precautions",
            ),
            (
                "Avisos",
                "warnings",
            ),
        ]

        encontrou_secao = False

        for titulo, campo in secoes:
            conteudo = registro.get(
                campo
            )

            if not conteudo:
                continue

            encontrou_secao = True

            if isinstance(
                conteudo,
                list,
            ):
                original = "\n\n".join(
                    str(parte)
                    for parte in conteudo
                )
            else:
                original = str(
                    conteudo
                )

            st.markdown(
                f"**{titulo} — original**"
            )
            st.write(
                original
            )

            chave = (
                "traducao_"
                f"{registro.get('id', selecionado)}"
                f"_{campo}"
            )

            if st.button(
                f"Traduzir: {titulo}",
                key=chave,
            ):
                try:
                    with st.spinner(
                        "Traduzindo..."
                    ):
                        traducao = traduzir_texto(
                            original
                        )

                    st.caption(
                        "Tradução automática; "
                        "não validada pela equipe "
                        "da farmácia."
                    )
                    st.write(
                        traducao
                    )

                except Exception:
                    logger.exception(
                        "Falha na tradução"
                    )
                    st.warning(
                        "Tradução indisponível. "
                        "O texto original está "
                        "preservado acima."
                    )

            st.divider()

        if not encontrou_secao:
            st.info(
                "As seções previstas nesta tela "
                "não estão disponíveis no "
                "resultado selecionado."
            )


def sair():
    for chave in list(
        st.session_state.keys()
    ):
        if chave.startswith(
            (
                "novo_",
                "editar_",
            )
        ):
            del st.session_state[
                chave
            ]

    st.session_state[
        "auth"
    ] = False
    st.session_state.pop(
        "admin_snapshot",
        None,
    )
    st.session_state.pop(
        "perf",
        None,
    )
    st.session_state.pop(
        "menu_admin",
        None,
    )
    st.session_state.pop(
        "user_login",
        None,
    )
    st.session_state.pop(
        "pass_login",
        None,
    )


def barra_lateral():
    menu = "Pesquisar"

    with st.sidebar:
        if not st.session_state[
            "auth"
        ]:
            with st.expander(
                "🔐 Acesso administrativo"
            ):
                with st.form(
                    "form_login",
                    clear_on_submit=True,
                ):
                    usuario = st.text_input(
                        "Usuário",
                        key="user_login",
                    )
                    senha = st.text_input(
                        "Senha",
                        type="password",
                        key="pass_login",
                    )

                    acessar = (
                        st.form_submit_button(
                            "Acessar",
                            use_container_width=True,
                        )
                    )

                if acessar:
                    try:
                        usuarios = st.secrets[
                            "usuarios"
                        ]
                        usuario = (
                            usuario.strip()
                        )

                        if (
                            usuario in usuarios
                            and str(
                                usuarios[
                                    usuario
                                ]
                            )
                            == senha
                        ):
                            st.session_state[
                                "auth"
                            ] = True
                            st.session_state[
                                "perf"
                            ] = usuario
                            st.rerun()
                        else:
                            st.error(
                                "Usuário ou senha "
                                "incorretos."
                            )

                    except Exception:
                        st.error(
                            "Acesso administrativo "
                            "indisponível. Confira "
                            "a configuração dos "
                            "Secrets."
                        )

        else:
            st.success(
                "Logado como: "
                + st.session_state.get(
                    "perf",
                    "",
                ).upper()
            )

            menu = st.radio(
                "Painel administrativo:",
                [
                    "Pesquisar",
                    "Adicionar Novo",
                    "Editar/Corrigir",
                ],
                key="menu_admin",
            )

            st.button(
                "Sair",
                on_click=sair,
                use_container_width=True,
            )

        st.divider()
        st.markdown(
            "### Links úteis"
        )

        st.markdown(
            "[📚 UpToDate]"
            "(https://uptodate.ebserh.gov.br/)"
        )

        st.markdown(
            "[🔗 Bulário ANVISA]"
            "(https://consultas.anvisa.gov.br/"
            "#/bulario/)"
        )

        st.markdown(
            "[💬 Solicitar ajustes / Feedback]"
            "(https://docs.google.com/forms/d/e/"
            "1FAIpQLSeO7N5Iyuf-rjnXbTtKHl95aE-rXVv-"
            "5ao-kFzTXbEYN5FdzQ/viewform)"
        )

        st.caption(
            f"Versão {VERSAO}"
        )

    return menu


def main():
    st.session_state.setdefault(
        "auth",
        False,
    )

    mensagem = (
        st.session_state.pop(
            "mensagem_admin",
            None,
        )
    )

    if mensagem:
        st.success(
            mensagem
        )

    menu = barra_lateral()

    try:
        assinatura = assinatura_arquivo()
        df = carregar_dados(
            assinatura
        )

    except FileNotFoundError:
        st.error(
            "Base indisponível. Configure "
            "[gcp_service_account] nos Secrets "
            "para usar a planilha Google ou "
            "coloque dados_injetaveis.xlsx na "
            "pasta do aplicativo para testar "
            "localmente."
        )
        exibir_rodape()
        return

    except Exception as erro:
        logger.exception(
            "Falha ao ler a base"
        )
        st.error(
            "Não foi possível carregar o banco "
            f"de dados: {erro}"
        )
        exibir_rodape()
        return

    if ARQUIVO_LOGO.exists():
        st.image(
            str(ARQUIVO_LOGO),
            use_container_width=True
        )

    if (
        st.session_state[
            "auth"
        ]
        and menu != "Pesquisar"
    ):
        tela_administrativa(
            df,
            menu,
            assinatura,
        )
    else:
        st.session_state.pop(
            "admin_snapshot",
            None,
        )
        tela_pesquisa(
            df
        )

    exibir_rodape()


if __name__ == "__main__":
    main()
