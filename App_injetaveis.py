import streamlit as st
import pandas as pd
import requests
import re
import os
from deep_translator import GoogleTranslator
from functools import lru_cache
import numpy as np

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="HUUFMA - Guia v5.7", layout="wide", page_icon="💉")

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    .main { background-color: #ffffff; }
    .med-header { font-size: 2rem; font-weight: bold; color: #005A8D; border-bottom: 2px solid #D0F0C0; padding-bottom: 5px; }
    .mav-badge { background-color: #ff4b4b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 10px; }
    .status-alert { padding: 12px; border-radius: 6px; margin: 15px 0; font-weight: bold; border-left: 8px solid; }
    .divergente { background-color: #fff4e6; color: #d9480f; border-color: #fd7e14; }
    .padronizado { background-color: #ebfbee; color: #2b8a3e; border-color: #40c057; }
    .secao-titulo { background-color: #f8f9fa; padding: 6px 12px; border-left: 5px solid #005A8D; font-weight: bold; margin-top: 15px; color: #005A8D; font-size: 1.1rem; }
    .info-row { border-bottom: 1px solid #f0f0f0; padding: 8px 0; display: flex; align-items: flex-start; }
    .info-label { font-weight: bold; color: #495057; width: 280px; min-width: 280px; font-size: 0.95rem; }
    .info-value { color: #212529; font-size: 0.95rem; line-height: 1.4; white-space: pre-wrap; }
    </style>
    """, unsafe_allow_html=True)

# --- USUÁRIOS ---
USUARIOS = {"admin": "123", "farmacia": "hu"}

# --- FUNÇÕES DE INTELIGÊNCIA (RxNorm + FDA + Tradutor) ---
@lru_cache(maxsize=1000)
def traduzir(texto):
    if not texto or str(texto).strip() in ['-', 'nan']: return "Não disponível"
    try: return GoogleTranslator(source='auto', target='pt').translate(str(texto)[:4500])
    except: return "Erro na tradução automática."

def limpar_termo_local(nome):
    """ Limpeza inicial para o RxNorm não confundir siglas com nomes químicos """
    t = str(nome).upper()
    t = re.sub(r'\(.*?\)', '', t) # Remove (MAV), (UR), etc.
    for s in ['MAV', 'UR', 'AMPOLA', 'INJETÁVEL', 'SOLUÇÃO', 'FRASCO']:
        t = t.replace(s, '')
    t = re.sub(r'\d+(\.\d+)?\s?(MG|G|ML|UI|MEQ).*', '', t)
    return t.strip()

def buscar_nome_cientifico_ingles(termo_limpo):
    """ Usa RxNorm para converter nome PT-BR/Comercial para Ingrediente Ativo em Inglês """
    try:
        url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={termo_limpo}&maxEntries=1"
        res = requests.get(url, timeout=10).json()
        candidates = res.get('approximateGroup', {}).get('candidate', [])
        if candidates:
            rxcui = candidates[0]['rxcui']
            # Busca o nome oficial do ingrediente (TTY=IN)
            res_name = requests.get(f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json?tty=IN", timeout=10).json()
            props = res_name.get('relatedGroup', {}).get('conceptGroup', [{}])[0].get('conceptProperties', [])
            if props: return props[0]['name'] # Nome em Inglês
        return termo_limpo.split(' ')[0]
    except: return termo_limpo.split(' ')[0]

def verificar_divergencia(df_med):
    colunas_criticas = ["DILUIÇÃO", "RECONSTITUIÇÃO", "ESTABILIDADE DO RECONSTITUÍDO (Temp. Ambiente (25°C)", "TEMPO DE INFUSÃO"]
    dif = []
    for c in colunas_criticas:
        if c in df_med.columns:
            if len(df_med[df_med[c] != '-'][c].unique()) > 1: dif.append(c)
    return dif

# --- INTERFACE PRINCIPAL ---
def main():
    if 'auth' not in st.session_state: st.session_state['auth'] = False

    if not st.session_state['auth']:
        st.title("🏥 Guia de Injetáveis HUUFMA")
        u, p = st.text_input("Usuário"), st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if u in USUARIOS and USUARIOS[u] == p:
                st.session_state['auth'], st.session_state['perf'] = True, u
                st.rerun()
        return

    # Sidebar
    with st.sidebar:
        if os.path.exists("Logo_huufma.jpg"): st.image("Logo_huufma.jpg")
        st.write(f"Perfil: **{st.session_state['perf'].upper()}**")
        st.divider()
        st.markdown("[📚 UpToDate](https://uptodate.ebserh.gov.br/) | [🔗 Bula ANVISA](https://consultas.anvisa.gov.br/#/bulario/)")
        if st.button("Sair"): st.session_state['auth'] = False; st.rerun()

    try:
        df = pd.read_excel('dados_injetaveis.xlsx').ffill()
        df = df.replace(['nan', 'NaN'], np.nan).fillna('-')
    except: st.error("Erro ao carregar banco de dados."); return

    med_list = sorted(df["MEDICAMENTO"].unique())
    escolha = st.selectbox("💉 Pesquisar Medicamento:", [""] + med_list)

    if escolha:
        subset = df[df["MEDICAMENTO"] == escolha]
        is_mav = "MAV" in escolha.upper()
        st.markdown(f'<div class="med-header">{escolha.upper()} {f"<span class=\'mav-badge\'>ALTA VIGILÂNCIA</span>" if is_mav else ""}</div>', unsafe_allow_html=True)
        
        # Inteligência de Comparação
        if len(subset) > 1:
            dif = verificar_divergencia(subset)
            if dif: st.markdown(f'<div class="status-alert divergente">⚠️ ATENÇÃO: Diferenças entre laboratórios em: {", ".join(dif)}. Confira a aba correta!</div>', unsafe_allow_html=True)
            else: st.markdown('<div class="status-alert padronizado">✅ PADRONIZADO: Informações idênticas para todos os laboratórios.</div>', unsafe_allow_html=True)
        
        abas = st.tabs([f"🏢 {r['VIA DE ADMINISTRAÇÃO']} - {r['LABORATÓRIO']}" for _, r in subset.iterrows()])

        for i, aba in enumerate(abas):
            with aba:
                row = subset.iloc[i]
                
                # SEÇÃO 1: PRESCRIÇÃO (14 COLUNAS)
                st.markdown('<div class="secao-titulo">💊 PRESCRIÇÃO E PREPARO</div>', unsafe_allow_html=True)
                campos = [
                    ("Dose Ped. Usual", "DOSE PEDIATRIA (Usual)"), ("Dose Ped. Máxima", "DOSE Máximaped"),
                    ("Dose Adulto Usual", "DOSE ADULTO (Usual)"), ("Dose Adulto Máxima", "DOSE Máxima adulto"),
                    ("Reconstituinte", "RECONSTITUIÇÃO"), ("Volume Expandido", "VOLUME EXPANDIDO"),
                    ("Diluente Compatível", "DILUIÇÃO"), ("Conc. Infusão (Adulto)", "CONCENTRAÇÃO DE INFUSÃO (Adulto)"),
                    ("Conc. Infusão (Ped)", "CONCENTRAÇÃO_ped INFUSÃO")
                ]
                for label, col in campos:
                    st.markdown(f'<div class="info-row"><div class="info-label">{label}</div><div class="info-value">{row.get(col, "-")}</div></div>', unsafe_allow_html=True)

                # SEÇÃO 2: ESTABILIDADE
                st.markdown('<div class="secao-titulo">⏳ ESTABILIDADE E ADMINISTRAÇÃO</div>', unsafe_allow_html=True)
                for label, col in [("Tempo de Infusão", "TEMPO DE INFUSÃO"), ("Ambiente (25°C)", "ESTABILIDADE DO RECONSTITUÍDO (Temp. Ambiente (25°C)"), ("Geladeira (2-8°C)", "ESTABILIDADE DO RECONSTITUÍDO Refrigerada (2º a 8ºC)"), ("Diluído", "ESTABILIDADE DA DILUIÇÃO (Temp. Ambiente (25°C)")]:
                    st.markdown(f'<div class="info-row"><div class="info-label">{label}</div><div class="info-value">{row.get(col, "-")}</div></div>', unsafe_allow_html=True)

                # SEÇÃO 3: ALERTAS
                st.markdown('<div class="secao-titulo">🚨 ALERTAS</div>', unsafe_allow_html=True)
                st.write(f"**Observações:** {row.get('OBSERVAÇÕES', '-')}")
                c1, c2 = st.columns(2)
                with c1: st.info(f"**Ajuste Renal:** {row.get('AJUSTE RENAL', '-')}")
                with c2: st.info(f"**Ajuste Hepático:** {row.get('AJUSTE HEPÁTICO', '-')}")

                # SEÇÃO 4: FDA (RESTAURADO COM RXNORM E TODAS AS SEÇÕES)
                with st.expander("🔎 Dados Farmacológicos Completos (FDA/EUA)"):
                    with st.spinner("Consultando RxNorm e base completa do FDA..."):
                        termo_limpo = limpar_termo_local(escolha)
                        nome_en = buscar_nome_cientifico_ingles(termo_limpo)
                        st.caption(f"Fármaco (Inglês): **{nome_en}**")
                        
                        try:
                            # Busca no FDA
                            res = requests.get(f'https://api.fda.gov/drug/label.json?search=openfda.generic_name:"{nome_en}"&limit=1', timeout=15).json()
                            d = res['results'][0]
                            
                            # Mapeamento de todas as seções importantes para o Farmacêutico
                            secoes_mapeadas = [
                                ("🔬 Mecanismo de Ação", "mechanism_of_action"),
                                ("⚠️ Contraindicações", "contraindications"),
                                ("💊 Interações Medicamentosas", "drug_interactions"),
                                ("🚫 Incompatibilidades", "incompatibilities"),
                                ("🤢 Reações Adversas", "adverse_reactions"),
                                ("👶 Uso Pediátrico", "pediatric_use"),
                                ("👵 Uso Geriátrico", "geriatric_use"),
                                ("🤰 Gravidez e Lactação", "pregnancy"),
                                ("🛡️ Avisos e Precauções", "warnings_and_precautions")
                            ]
                            
                            for titulo, chave in secoes_mapeadas:
                                if chave in d:
                                    conteudo = d.get(chave, ["-"])
                                    texto_bruto = conteudo[0] if isinstance(conteudo, list) else conteudo
                                    
                                    if texto_bruto and texto_bruto != "-":
                                        st.markdown(f"#### {titulo}")
                                        st.write(traduzir(texto_bruto))
                                        st.divider()
                                        
                        except Exception as e:
                            st.info("FDA: Dados detalhados não encontrados para este ingrediente ou erro na tradução.")

if __name__ == "__main__": main()