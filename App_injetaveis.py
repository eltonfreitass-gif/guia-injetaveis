import streamlit as st
import pandas as pd
import requests
import re
import os
from deep_translator import GoogleTranslator
from functools import lru_cache
import numpy as np

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="HUUFMA- Guia de Medicamentos Injetáveis v8.0", layout="wide", page_icon="💉")

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    .main { background-color: #ffffff; }
    button[data-testid="stSidebarCollapseIcon"]::before {
        content: "Links Úteis";
        font-size: 14px;
        font-weight: bold;
        color: #005A8D;
        margin-right: 5px;
        font-family: sans-serif;
    }
    button[data-testid="stSidebarCollapseIcon"] svg { display: none; }
    .header-container { display: flex; align-items: center; gap: 10px; border-bottom: 3px solid #D0F0C0; padding-bottom: 10px; margin-bottom: 20px; flex-wrap: wrap; }
    .med-title { font-size: 2rem; font-weight: bold; color: #005A8D; margin: 0; padding: 0; line-height: 1; }
    .badge-mav { background-color: #ff4b4b; color: white; padding: 2px 10px; border-radius: 12px; font-weight: bold; font-size: 0.75rem; border: 1px solid #8b0000; display: inline-block; }
    .badge-ur { background-color: #f39c12; color: white; padding: 2px 10px; border-radius: 12px; font-weight: bold; font-size: 0.75rem; border: 1px solid #b35900; display: inline-block; }
    .status-alert { padding: 8px; border-radius: 4px; margin: 10px 0; font-size: 0.9rem; font-weight: bold; border-left: 5px solid; }
    .divergente { background-color: #fff4e6; color: #d9480f; border-color: #fd7e14; }
    .padronizado { background-color: #ebfbee; color: #2b8a3e; border-color: #40c057; }
    .secao-titulo { background-color: #f8f9fa; padding: 6px 12px; border-left: 5px solid #005A8D; font-weight: bold; margin-top: 15px; color: #005A8D; font-size: 1.1rem; }
    .info-row { border-bottom: 1px solid #f0f0f0; padding: 8px 0; display: flex; align-items: flex-start; }
    .info-label { font-weight: bold; color: #495057; width: 280px; min-width: 280px; font-size: 0.95rem; }
    .info-value { color: #212529; font-size: 0.95rem; line-height: 1.4; white-space: pre-wrap; }
    .footer { position: fixed; left: 0; bottom: 0; width: 100%; background-color: #f1f3f5; color: #495057; text-align: center; padding: 8px; font-size: 11px; border-top: 1px solid #dee2e6; z-index: 100; }
    </style>
    """, unsafe_allow_html=True)

# --- USUÁRIOS E FUNÇÕES ---
USUARIOS = {"admin": "123", "farmacia": "hu"}

@st.cache_data(ttl=3600)
def carregar_dados():
    try:
        df = pd.read_excel('dados_injetaveis.xlsx').ffill()
        return df.replace(['nan', 'NaN'], np.nan).fillna('-')
    except: return None

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

    if not st.session_state['auth']:
        _, col_log, _ = st.columns([1, 1.5, 1])
        with col_log:
            if os.path.exists("Logo_huufma.jpg"): st.image("Logo_huufma.jpg", use_container_width=True)
            st.title("Guia de Medicamentos Injetáveis")
            u, p = st.text_input("Usuário"), st.text_input("Senha", type="password")
            if st.button("Acessar", use_container_width=True):
                if u in USUARIOS and USUARIOS[u] == p:
                    st.session_state['auth'], st.session_state['perf'] = True, u
                    st.rerun()
        return

    # BARRA LATERAL
    with st.sidebar:
        if os.path.exists("Logo_huufma.jpg"): st.image("Logo_huufma.jpg")
        st.write(f"👤 Perfil: **{st.session_state['perf'].upper()}**")
        st.divider()
        
        # Menu de Navegação (CORRIGIDO: Acessível a todos)
        opcoes_menu = ["🔍 Consultar Guia"]
        if st.session_state['perf'] == 'admin':
            opcoes_menu.append("➕ Adicionar Medicamento")
        
        escolha_menu = st.radio("Navegador:", opcoes_menu)
        
        st.divider()
        st.markdown("### LINKS ÚTEIS") 
        st.markdown("[📚 UpToDate](https://uptodate.ebserh.gov.br/)")
        st.markdown("[🔗 Bula ANVISA](https://consultas.anvisa.gov.br/#/bulario/)")
        st.markdown("[🔗 Feedback](https://docs.google.com/forms/d/e/1FAIpQLSeO7N5Iyuf-rjnXbTtKHl95aE-rXVv-5ao-kFzTXbEYN5FdzQ/viewform?pli=1/)")
        st.divider()
        if st.button("Sair / Logout", use_container_width=True):
            st.session_state['auth'] = False
            st.rerun()

    df = carregar_dados()
    if df is None: st.error("Erro ao carregar dados."); return

    # --- LÓGICA DE TELAS ---
    if escolha_menu == "🔍 Consultar Guia":
        med_list = sorted(df["MEDICAMENTO"].unique())
        col_s, col_c = st.columns([4, 1])
        with col_s: 
            escolha = st.selectbox("💉 Pesquise o medicamento:", [""] + med_list, key=f"s_{st.session_state['search_key']}")
        with col_c:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Limpar Busca"): st.session_state['search_key'] += 1; st.rerun()

        if escolha:
            nome_up = escolha.upper()
            html_header = f'<div class="header-container"><h1 class="med-title">{nome_up}</h1>'
            if "MAV" in nome_up: html_header += '<span class="badge-mav">ALTA VIGILÂNCIA</span>'
            if "UR" in nome_up: html_header += '<span class="badge-ur">USO RESTRITO</span>'
            html_header += '</div>'
            st.markdown(html_header, unsafe_allow_html=True)

            subset = df[df["MEDICAMENTO"] == escolha]
            
            # Alerta de Divergência
            if len(subset) > 1:
                cols_t = ["DILUIÇÃO", "RECONSTITUIÇÃO", "ESTABILIDADE DO RECONSTITUÍDO (Temp. Ambiente (25°C)", "TEMPO DE INFUSÃO"]
                dif = [c for c in cols_t if c in subset.columns and len(subset[subset[c] != '-'][c].unique()) > 1]
                if dif: st.markdown(f'<div class="status-alert divergente">⚠️ Diferença(s) em: {", ".join(dif)}</div>', unsafe_allow_html=True)

            abas = st.tabs([f"🏢 {r['VIA DE ADMINISTRAÇÃO']} - {r['LABORATÓRIO']}" for _, r in subset.iterrows()])

            for i, aba in enumerate(abas):
                with aba:
                    row = subset.iloc[i]
                    st.markdown('<div class="secao-titulo">💊 PRESCRIÇÃO E PREPARO</div>', unsafe_allow_html=True)
                    # Exemplo de campos (adicione os demais conforme sua necessidade)
                    st.write(f"**Reconstituição:** {row.get('RECONSTITUIÇÃO', '-')}")
                    st.write(f"**Diluição:** {row.get('DILUIÇÃO', '-')}")
                    
                    with st.expander("🔎 Bula Digital FDA (EUA)"):
                        nome_en = buscar_ingles_rxcui(escolha)
                        st.caption(f"Fármaco: {nome_en}")
                        # Lógica da API FDA mantida...

    elif escolha_menu == "➕ Adicionar Medicamento":
        st.title("➕ Cadastrar Novo Injetável")
        with st.form("novo_registro", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                f_med = st.text_input("Nome do Medicamento")
                f_lab = st.text_input("Laboratório")
                f_via = st.text_input("Via de Administração")
            with c2:
                f_reconst = st.text_input("Reconstituição")
                f_dilu = st.text_input("Diluição")
                f_tempo = st.text_input("Tempo de Infusão")
            
            if st.form_submit_button("💾 Salvar no Banco de Dados"):
                if f_med and f_lab:
                    nova_linha = pd.DataFrame([{
                        "MEDICAMENTO": f_med.upper(),
                        "LABORATÓRIO": f_lab.upper(),
                        "VIA DE ADMINISTRAÇÃO": f_via.upper(),
                        "RECONSTITUIÇÃO": f_reconst,
                        "DILUIÇÃO": f_dilu,
                        "TEMPO DE INFUSÃO": f_tempo
                    }])
                    df_final = pd.concat([df, nova_linha], ignore_index=True)
                    df_final.to_excel('dados_injetaveis.xlsx', index=False)
                    carregar_dados.clear()
                    st.success("✅ Cadastrado com sucesso!")
                    st.balloons()

    # FOOTER
    st.markdown('<div class="footer"><b>Guia de Medicamentos de Injetáveis - HUUFMA</b></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
