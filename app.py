import json
import time
import pandas as pd
from google import genai
import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Gestão de Produção & Histórico", layout="wide", page_icon="🏭")

st.title("🏭 Gestão de Produção - Leitor & Histórico Acumulado")

# Conexão com o Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception:
    conn = None

tab1, tab2 = st.tabs(["📋 Processar Relatório Diário", "📈 Dashboard de Histórico"])

# ==========================================================
# TAB 1: PROCESSAR NOVO RELATÓRIO DO WHATSAPP
# ==========================================================
with tab1:
    st.write("Copie o texto do relatório do WhatsApp e cole na caixa abaixo.")
    texto_whatsapp = st.text_area("📋 Cole o relatório aqui:", height=250)

    if st.button("🚀 Processar e Salvar no Histórico", type="primary"):
        if not texto_whatsapp.strip():
            st.warning("⚠️ Por favor, cole o texto do relatório antes de processar.")
        else:
            with st.spinner("Lendo dados e atualizando histórico..."):
                try:
                    if "GEMINI_API_KEY" not in st.secrets:
                        st.error("❌ A chave GEMINI_API_KEY não foi encontrada nos Secrets do Streamlit.")
                        st.stop()

                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                    prompt = f"""
                    Você é um assistente especialista em Controle de Produção Industrial (PCP).
                    Analise o texto do relatório abaixo e extraia todas as informações no formato JSON rigorosamente estruturado.

                    Retorne APENAS o JSON puro, sem marcações adicionais ou textos antes/depois:

                    {{
                      "data": "DD/MM/AAAA",
                      "turno": "1º ou 2º",
                      "mo_total": 0,
                      "efetivos": 0,
                      "temporarios": 0,
                      "ausencias": "Descrição das ausências, atestados e alterações de pessoal",
                      "producao": [
                        {{
                          "equipamento": "Nome do equipamento",
                          "produto": "Nome do produto ou projeto",
                          "programado": 0,
                          "realizado": 0,
                          "mo_necessaria": 0,
                          "status": "Detalhes de falhas, paradas e observações"
                        }}
                      ]
                    }}

                    Texto do relatório:
                    {texto_whatsapp}
                    """

                    # Sistema com retry para contornar oscilações e erro 503
                    response = None
                    modelos = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
                    
                    for mod in modelos:
                        for tentativa in range(3):
                            try:
                                res = client.models.generate_content(
                                    model=mod,
                                    contents=prompt,
                                )
                                if res and res.text:
                                    response = res
                                    break
                            except Exception as err:
                                if "503" in str(err) or "UNAVAILABLE" in str(err):
                                    time.sleep(2)  # Aguarda 2 segundos se o servidor do Google estiver ocupado
                                    continue
                                else:
                                    break
                        if response and response.text:
                            break

                    if not response or not response.text:
                        st.error("⚠️ Os servidores do Google Gemini estão em alta demanda no momento. Aguarde alguns segundos e clique no botão novamente.")
                        st.stop()

                    texto_resposta = response.text.strip()
                    if texto_resposta.startswith("```json"):
                        texto_resposta = texto_resposta[7:-3].strip()
                    elif texto_resposta.startswith("```"):
                        texto_resposta = texto_resposta[3:-3].strip()

                    dados = json.loads(texto_resposta)

                    st.success("✅ Relatório Processado com Sucesso!")

                    # Exibição do resumo
                    st.subheader("📊 Resumo do Turno Processado")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Data", dados.get("data", "N/A"))
                    c2.metric("Turno", dados.get("turno", "N/A"))
                    c3.metric("M.O Total", dados.get("mo_total", 0))
                    c4.metric("Efetivos / Temp", f"{dados.get('efetivos', 0)} / {dados.get('temporarios', 0)}")

                    st.info(f"**Ocorrências de Pessoal:** {dados.get('ausencias', 'Nenhuma')}")

                    # Tabela de produção do turno
                    lista_prod = dados.get("producao", [])
                    if lista_prod:
                        df_turno = pd.DataFrame(lista_prod)
                        df_turno["data"] = dados.get("data")
                        df_turno["turno"] = dados.get("turno")
                        
                        if "programado" in df_turno.columns and "realizado" in df_turno.columns:
                            df_turno["eficiencia_%"] = df_turno.apply(
                                lambda r: round((r["realizado"] / r["programado"] * 100), 1) if r["programado"] > 0 else 0.0,
                                axis=1
                            )

                        st.dataframe(df_turno, width="stretch")

                        # Gravação automática no Google Sheets (se configurado)
                        if conn:
                            try:
                                df_save_prod = df_turno[["data", "turno", "equipamento", "produto", "programado", "realizado", "eficiencia_%", "status"]]
                                df_existente_prod = conn.read(worksheet="Producao", ttl=0)
                                df_final_prod = pd.concat([df_existente_prod, df_save_prod], ignore_index=True)
                                conn.update(worksheet="Producao", data=df_final_prod)

                                df_save_mo = pd.DataFrame([{
                                    "data": dados.get("data"),
                                    "turno": dados.get("turno"),
                                    "mo_total": dados.get("mo_total"),
                                    "efetivos": dados.get("efetivos"),
                                    "temporarios": dados.get("temporarios"),
                                    "ocorrencias": dados.get("ausencias")
                                }])
                                df_existente_mo = conn.read(worksheet="Absenteismo", ttl=0)
                                df_final_mo = pd.concat([df_existente_mo, df_save_mo], ignore_index=True)
                                conn.update(worksheet="Absenteismo", data=df_final_mo)

                                st.success("💾 Dados gravados com sucesso na planilha do Google Sheets!")
                            except Exception:
                                st.info("Relatório processado! Para gravar automaticamente, certifique-se de configurar a URL da planilha no Secrets.")

                except Exception as e:
                    st.error(f"Erro ao processar o relatório: {e}")

# ==========================================================
# TAB 2: DASHBOARD DE MÉTRICAS E HISTÓRICO ACUMULADO
# ==========================================================
with tab2:
    st.header("📈 Histórico Acumulado e Gráficos")
    
    if conn:
        try:
            df_hist_prod = conn.read(worksheet="Producao", ttl=0)
            df_hist_mo = conn.read(worksheet="Absenteismo", ttl=0)

            if not df_hist_prod.empty:
                st.subheader("⚙️ Média de Eficiência por Equipamento (%)")
                df_grafico = df_hist_prod.groupby("equipamento")["eficiencia_%"].mean().reset_index()
                st.bar_chart(df_grafico.set_index("equipamento"))

                st.subheader("📦 Produção Total: Programado vs Realizado por Equipamento")
                df_totais = df_hist_prod.groupby("equipamento")[["programado", "realizado"]].sum()
                st.bar_chart(df_totais)

                st.subheader("📜 Histórico Geral de Produção")
                st.dataframe(df_hist_prod, width="stretch")
            else:
                st.info("Nenhum registro de produção encontrado na planilha ainda.")

            if not df_hist_mo.empty:
                st.subheader("👥 Histórico de Mão de Obra e Absenteísmo")
                st.dataframe(df_hist_mo, width="stretch")

        except Exception:
            st.info("Cole e processe o primeiro relatório na Tab 1 para iniciar o histórico!")
    else:
        st.info("Para visualizar os gráficos e o histórico acumulado, configure o link da planilha no Secrets.")
