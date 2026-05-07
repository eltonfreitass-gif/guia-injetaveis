import streamlit as st
import pandas as pd
import requests
import re
import os
from deep_translator import GoogleTranslator
from functools import lru_cache
import numpy as np

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="HUUFMA - Guia de Injetáveis v7.18", layout="wide", page_icon="💉")

# --- ESTILIZAÇÃO CSS (FIDELIDADE v7.17) ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem !important; padding-bottom: 5rem; }
    .main { background-color: #ffffff; }
    .logo-box { display: flex; justify-content: center; align-items: center; width: 100%; margin-bottom: 20px; }
    button[data-testid="stSidebarCollapseIcon"]::before { content: "Links Úteis"; font-size: 14px; font-weight: bold; color: #005A8D; margin-right: 5px; }
    button[data-testid="stSidebarCollapseIcon"] svg { display: none; }
    .header-container { display: flex; align-items: center; gap: 10px; border-bottom: 3px solid #D0F0C0; padding-bottom: 10px; margin-bottom: 20px; flex-wrap: wrap; }
    .med-title { font-size: 2.2rem; font-weight: bold; color: #005A8D; margin: 0; line-height: 1.1; }
    .badge-mav { background-color: #ff4b4b; color: white; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 0.75rem; border: 1px solid #8b0000; display: inline-block; }
    .badge-ur { background-color: #f39c12; color: white; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 0.75rem; border: 1px solid #b35900; display: inline-block; }
    .secao-titulo { background-color: #f8f9fa; padding: 6px 12px; border-left: 5px solid #005A8D; font-weight: bold; margin-top: 15px; color: #005A8D; font-size: 1.1rem; }
    .info-row { border-bottom: 1px solid #f0f0f0; padding: 8px 0; display: flex; align-items: flex-start; }
    .info-label { font-weight: bold; color: #495057; width: 300px; min-width: 300px; font-size: 0.95rem; }
    .info-value { color: #212529; font-size: 0.95rem; line-height: 1.4; white-space: pre-wrap; }
    
    /* Alertas do Detector */
    .status-alert { padding: 10px; border-radius: 4px; margin: 10px 0; font-size: 0.9rem; font-weight: bold; border-left: 5px solid; }
    .divergente { background-color: #fff4e6; color: #d9480f; border-color: #fd7e14; }
    .padronizado { background-color: #ebfbee; color: #2b8a3e; border-color: #40c057; }

    .footer-fixed { position: fixed; left: 0; bottom: 0; width: 100%; background-color: #f1f3f5; color: #495057; text-align: center; padding: 8px; font-size: 11px; border-top: 1px solid #dee2e6; z-index: 100; }
    .footer-normal { width: 100%; background-color: #f1f3f5; color: #495057; text-align: center; padding: 20px 8px; font-size: 11px; border-top: 1px solid #dee2e6; margin-top: 30px; }
    .term-highlight { background-color: #f0f2f6; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #e91e63; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE DADOS ---
USUARIOS = {"admin": "123", "farmacia": "hu"}

@st.cache_data(ttl=3600)
def carregar_dados():
    try:
        df = pd.read_excel('dados_injetaveis.xlsx').ffill()
        return df.replace(['nan', 'NaN'], np.nan).fillna('-')
    except: return None

def salvar_dados_excel(df):
    try:
        df.to_excel('dados_injetaveis.xlsx', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}"); return False

@lru_cache(maxsize=500)
def traduzir_fast(texto):
    if not texto or str(texto).strip() in ['-', 'nan']: return "Não disponível"
    try: return GoogleTranslator(source='auto', target='pt').translate(str(texto)[:4500])
    except: return "Tradução indisponível."

def buscar_ingles_rxcui(nome):
    t = re.sub(r'\(.*?\)', '', str(nome).upper())
    for s in ['MAV', 'UR', 'AMPOLA', 'INJETÁVEL', 'CLORIDRATO DE', 'SULFATO DE']: t = t.replace(s, '')
    t = re.sub(r'\d+(\.\d+)?\s?(MG|G|ML|UI|MEQ).*', '', t).strip()
    try:
        res = requests.get(f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={t}&maxEntries=1", timeout=5).json()
        rxcui = res['approximateGroup']['candidate'][0]['rxcui']
        res_n = requests.get(f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json?tty=IN", timeout=5).json()
        return res_n['relatedGroup']['conceptGroup'][0]['conceptProperties'][0]['name']
    except: return t.capitalize()

# --- INTERFACE ---
def main():
    if 'auth' not in st.session_state: st.session_state['auth'] = False
    if 'search_key' not in st.session_state: st.session_state['search_key'] = 0

    with st.sidebar:
        if not st.session_state['auth']:
            with st.expander("🔐 Acesso Administrativo"):
                u = st.text_input("Usuário", key="user_login")
                p = st.text_input("Senha", type="password", key="pass_login")
                if st.button("Acessar", use_container_width=True):
                    if u in USUARIOS and USUARIOS[u] == p:
                        st.session_state['auth'], st.session_state['perf'] = True, u
                        st.rerun()
                    else: st.error("Dados incorretos")
        else:
            st.success(f"Logado como: {st.session_state['perf'].upper()}")
            menu_admin = st.radio("Painel Admin:", ["Pesquisar", "Adicionar Novo", "Editar/Corrigir"])
            if st.button("Sair / Logout", use_container_width=True):
                st.session_state['auth'] = False; st.rerun()

        st.divider()
        st.markdown("### LINKS ÚTEIS") 
        st.markdown("[📚 UpToDate](https://uptodate.ebserh.gov.br/)")
        st.markdown("[🔗 Bula ANVISA](https://consultas.anvisa.gov.br/#/bulario/)")
        st.markdown("[🔗 Solicitar ajustes/ Feedback](https://docs.google.com/forms/d/e/1FAIpQLSeO7N5Iyuf-rjnXbTtKHl95aE-rXVv-5ao-kFzTXbEYN5FdzQ/viewform?pli=1/)")

    df = carregar_dados()
    if df is None: st.error("Erro ao carregar banco de dados."); return

    _, col_logo, _ = st.columns([1, 1.5, 1])
    with col_logo:
        if os.path.exists("Logo_huufma.jpg"): 
            st.image("Logo_huufma.jpg", use_container_width=True)

    # --- TELAS ADMIN ---
    if st.session_state['auth'] and menu_admin != "Pesquisar":
        # (Lógica de Adicionar e Editar idêntica à v7.17)
        if menu_admin == "Adicionar Novo":
            st.header("➕ Cadastrar Novo Laboratório/Medicamento")
            with st.form("form_add"):
                dados_novos = {}
                col1, col2 = st.columns(2)
                for i, col in enumerate(df.columns):
                    with col1 if i % 2 == 0 else col2:
                        dados_novos[col] = st.text_area(col, "", height=68)
                if st.form_submit_button("Salvar no Banco de Dados"):
                    df_final = pd.concat([df, pd.DataFrame([dados_novos])], ignore_index=True)
                    if salvar_dados_excel(df_final):
                        st.success("Medicamento adicionado com sucesso!"); st.rerun()
        
        elif menu_admin == "Editar/Corrigir":
            st.header("📝 Corrigir Dados Existentes")
            med_sel = st.selectbox("Selecione o medicamento:", sorted(df["MEDICAMENTO"].unique()))
            sub = df[df["MEDICAMENTO"] == med_sel]
            lab_sel = st.selectbox("Selecione Laboratório/Via:", sub.apply(lambda r: f"{r['LABORATÓRIO']} ({r['VIA DE ADMINISTRAÇÃO']})", axis=1))
            idx = sub.index[sub.apply(lambda r: f"{r['LABORATÓRIO']} ({r['VIA DE ADMINISTRAÇÃO']})", axis=1) == lab_sel][0]
            with st.form("form_edit"):
                dados_edit = {}
                col1, col2 = st.columns(2)
                for i, col in enumerate(df.columns):
                    with col1 if i % 2 == 0 else col2:
                        dados_edit[col] = st.text_area(col, value=str(df.at[idx, col]), height=68)
                if st.form_submit_button("Atualizar Registro"):
                    for c, v in dados_edit.items(): df.at[idx, c] = v
                    if salvar_dados_excel(df): st.success("Dados atualizados!"); st.rerun()
        st.markdown('<div class="footer-normal"><b>Guia HUUFMA</b></div>', unsafe_allow_html=True)

    # --- TELA PESQUISA ---
    else:
        st.markdown('<h1 style="color: #005A8D; text-align: center; margin-bottom: 20px;">Guia de Medicamentos Injetáveis</h1>', unsafe_allow_html=True)
        med_list = sorted(df["MEDICAMENTO"].unique())
        col_s, col_c = st.columns([4, 1])
        with col_s: escolha = st.selectbox("💉 Pesquise o medicamento:", [""] + med_list, key=f"s_{st.session_state['search_key']}")
        with col_c:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Limpar Busca"): st.session_state['search_key'] += 1; st.rerun()

        if escolha:
            nome_up = escolha.upper()
            subset = df[df["MEDICAMENTO"] == escolha]
            
            html_header = f'<div class="header-container"><h1 class="med-title">{nome_up}</h1>'
            if "MAV" in nome_up: html_header += '<span class="badge-mav">ALTA VIGILÂNCIA - Cuidado na utilização</span>'
            if "UR" in nome_up: html_header += '<span class="badge-ur">USO RESTRITO - Solicitar UR após prescrever</span>'
            html_header += '</div>'
            st.markdown(html_header, unsafe_allow_html=True)

            # --- RESTAURAÇÃO: DETECTOR DE DIVERGÊNCIA ---
            if len(subset) > 1:
                colunas_comparar = [
                    "DILUIÇÃO", "RECONSTITUIÇÃO", "TEMPO DE INFUSÃO",
                    "ESTABILIDADE DO RECONSTITUÍDO (Temp. Ambiente (25°C)",
                    "ESTABILIDADE DA DILUIÇÃO (Temp. Ambiente (25°C)"
                ]
                # Filtra colunas que realmente existem no DF
                colunas_validas = [c for c in colunas_comparar if c in subset.columns]
                divergencias = [c for c in colunas_validas if len(subset[subset[c] != '-'][c].unique()) > 1]
                
                if divergencias:
                    st.markdown(f'<div class="status-alert divergente">⚠️ Confirme o laboratório do Medicamento. Diferença(s) detectada(s) em: {", ".join(divergencias)}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="status-alert padronizado">✅ Informações idênticas para todos os laboratórios cadastrados.</div>', unsafe_allow_html=True)

            abas = st.tabs([f"🏢 {r['VIA DE ADMINISTRAÇÃO']} - {r['LABORATÓRIO']}" for _, r in subset.iterrows()])

            for i, aba in enumerate(abas):
                with aba:
                    row = subset.iloc[i]
                    
                    st.markdown('<div class="secao-titulo">📋 INFORMAÇÕES GERAIS</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="info-row"><div class="info-label">Nome Comercial</div><div class="info-value">{row.get("NOME COMERCIAL", "-")}</div></div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="info-row"><div class="info-label">Via de Administração</div><div class="info-value">{row.get("VIA DE ADMINISTRAÇÃO", "-")}</div></div>', unsafe_allow_html=True)

                    st.markdown('<div class="secao-titulo">💊 PRESCRIÇÃO E PREPARO</div>', unsafe_allow_html=True)
                    c_prep = [
                        ("Dose Pediatria (Usual)", "DOSE PEDIATRIA (Usual)"), ("Dose Máxima Pediátrica", "DOSE Máximaped"),
                        ("Dose Adulto (Usual)", "DOSE ADULTO (Usual)"), ("Dose Máxima Adulto", "DOSE Máxima adulto"),
                        ("Reconstituição", "RECONSTITUIÇÃO"), ("Volume Expandido", "VOLUME EXPANDIDO"),
                        ("Diluição", "DILUIÇÃO"), ("Concentração)", "CONCENTRAÇÃO"), 
                        ("Conc. Infusão (Adulto)", "CONCENTRAÇÃO DE INFUSÃO (Adulto)"),
                        ("Conc. Infusão (Pediátrico)", "CONCENTRAÇÃO_ped INFUSÃO")
                    ]
                    for label, col in c_prep: st.markdown(f'<div class="info-row"><div class="info-label">{label}</div><div class="info-value">{row.get(col, "-")}</div></div>', unsafe_allow_html=True)

                    st.markdown('<div class="secao-titulo">⏳ ADMINISTRAÇÃO E ESTABILIDADE</div>', unsafe_allow_html=True)
                    c_estab = [
                        ("Tempo de Infusão", "TEMPO DE INFUSÃO"), 
                        ("Reconstituído: Ambiente (25°C)", "ESTABILIDADE DO RECONSTITUÍDO (Temp. Ambiente (25°C)"), 
                        ("Reconstituído: Geladeira (2-8°C)", "ESTABILIDADE DO RECONSTITUÍDO Refrigerada (2º a 8ºC)"), 
                        ("Diluído: Ambiente (25°C)", "ESTABILIDADE DA DILUIÇÃO (Temp. Ambiente (25°C)"),
                        ("Diluído: Geladeira (2-8°C)", "ESTABILIDADE DA DILUIÇÃO (Refrigerada 2º a 8ºC)")
                    ]
                    for label, col in c_estab: st.markdown(f'<div class="info-row"><div class="info-label">{label}</div><div class="info-value">{row.get(col, "-")}</div></div>', unsafe_allow_html=True)

                    st.markdown('<div class="secao-titulo">🚨 ALERTAS E AJUSTES</div>', unsafe_allow_html=True)
                    col_obs_list = [c for c in subset.columns if "OBS" in str(c).upper()]
                    val_obs = row.get(col_obs_list[0], "-") if col_obs_list else row.get("OBSERVAÇÕES", "-")
                    st.markdown(f'<div class="info-row"><div class="info-label">Observações</div><div class="info-value">{val_obs}</div></div>', unsafe_allow_html=True)
                    
                    c1, c2 = st.columns(2)
                    with c1: st.info(f"**Ajuste Renal:** {row.get('AJUSTE RENAL', '-')}")
                    with c2: st.info(f"**Ajuste Hepático:** {row.get('AJUSTE HEPÁTICO', '-')}")

                    with st.expander("🔎 Bula Digital FDA (EUA)"):
                        nome_en = buscar_ingles_rxcui(escolha)
                        st.markdown(f"Fármaco identificado para consulta: <span class='term-highlight'>{nome_en}</span>", unsafe_allow_html=True)
                        st.markdown("<br>", unsafe_allow_html=True)
                        try:
                            res = requests.get(f'https://api.fda.gov/drug/label.json?search=openfda.generic_name:"{nome_en}"&limit=1', timeout=10).json()
                            d = res['results'][0]
                            sec_fda = [
                                ("🚫 Incompatibilidades", "incompatibilities"), ("🔬 Mecanismo de Ação", "mechanism_of_action"), 
                                ("⚠️ Contraindicações", "contraindications"), ("💊 Interações", "drug_interactions"), 
                                ("🤢 Reações Adversas", "adverse_reactions"), ("👶 Pediátrico", "pediatric_use"), 
                                ("👵 Geriátrico", "geriatric_use"), ("🤰 Gravidez", "pregnancy"), 
                                ("🛡️ Avisos", "warnings_and_precautions")
                            ]
                            for t, ch in sec_fda:
                                if ch in d:
                                    st.markdown(f"**{t}**")
                                    st.write(traduzir_fast(d[ch][0] if isinstance(d[ch], list) else d[ch]))
                                    st.divider()
                        except: st.info("Dados do FDA não localizados.")
        
        st.markdown('<div class="footer-fixed"><b>Guia de Medicamentos de Injetáveis - HUUFMA</b><br>Desenvolvimento: Elton Jonh Freitas Santos | Colaboradores: Vinicius Brito Pereira | Carolayne Silva Amorim</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
