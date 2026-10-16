import json
import time
import pandas as pd
from google import genai
import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Gestão de Produção & Histórico", layout="wide", page_icon="🏭")

st.title("🏭 Gestão de Produção - Leitor & Histórico Acumulado")

# Tratamento para evitar erros de formatação na chave privada
if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
    if "private_key" in st.secrets["connections"]["gsheets"]:
        pk = st.secrets["connections"]["gsheets"]["private_key"]
        if "\\n" in pk:
            st.secrets["connections"]["gsheets"]["private_key"] = pk.replace("\\n", "\n")

# Conexão com o Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e_conn:
    conn = None
    st.error(f"Erro ao inicializar conexão com Google Sheets: {e_conn}")

tab1, tab2, tab3 = st.tabs(["📋 Processar Relatório Diário", "📈 Dashboard de Histórico", "🔍 Teste de Conexão Sheets"])

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

                    # Tentativas automáticas (Retry)
                    response = None
                    modelos_tentativa = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
                    
                    for modelo in modelos_tentativa:
                        for tentativa in range(3):
                            try:
                                res = client.models.generate_content(
                                    model=modelo,
                                    contents=prompt,
                                )
                                if res and res.text:
                                    response = res
                                    break
                            except Exception as err:
                                if "503" in str(err) or "UNAVAILABLE" in str(err):
                                    time.sleep(1.5)
                                    continue
                                else:
                                    break
                        if response and response.text:
                            break

                    if not response or not response.text:
                        st.warning("⏳ Os servidores do Gemini estão com alta demanda no momento. Aguarde 5 segundos e tente novamente.")
                        st.stop()

                    texto_resposta = response.text.strip()
                    if texto_resposta.startswith("```json"):
                        texto_resposta = texto_resposta[7:-3].strip()
                    elif texto_resposta.startswith("```"):
                        texto_resposta = texto_resposta[3:-3].strip()

                    dados = json.loads(texto_resposta)

                    st.success("✅ Relatório Processado com Sucesso!")

                    # Exibição do resumo do turno
                    st.subheader("📊 Resumo do Turno Processado")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Data", dados.get("data", "N/A"))
                    c2.metric("Turno", dados.get("turno", "N/A"))
                    c3.metric("M.O Total", dados.get("mo_total", 0))
                    c4.metric("Efetivos / Temp", f"{dados.get('efetivos', 0)} / {dados.get('temporarios', 0)}")

                    st.info(f"**Ocorrências de Pessoal:** {dados.get('ausencias', 'Nenhuma')}")

                    # Tabela de produção
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

                        # Gravação no Google Sheets
                        if conn:
                            try:
                                df_save_prod = df_turno[["data", "turno", "equipamento", "produto", "programado", "realizado", "eficiencia_%", "status"]]
                                try:
                                    df_existente_prod = conn.read(worksheet="Producao", ttl=0)
                                    df_final_prod = pd.concat([df_existente_prod, df_save_prod], ignore_index=True)
                                except Exception:
                                    df_final_prod = df_save_prod

                                conn.update(worksheet="Producao", data=df_final_prod)

                                df_save_mo = pd.DataFrame([{
                                    "data": dados.get("data"),
                                    "turno": dados.get("turno"),
                                    "mo_total": dados.get("mo_total"),
                                    "efetivos": dados.get("efetivos"),
                                    "temporarios": dados.get("temporarios"),
                                    "ocorrencias": dados.get("ausencias")
                                }])
                                try:
                                    df_existente_mo = conn.read(worksheet="Absenteismo", ttl=0)
                                    df_final_mo = pd.concat([df_existente_mo, df_save_mo], ignore_index=True)
                                except Exception:
                                    df_final_mo = df_save_mo

                                conn.update(worksheet="Absenteismo", data=df_final_mo)

                                st.success("💾 Dados gravados com sucesso na planilha do Google Sheets!")
                            except Exception as err_sheet:
                                st.error(f"❌ Falha ao gravar no Google Sheets: {err_sheet}")
                        else:
                            st.warning("⚠️ Conexão com Google Sheets não configurada no Secrets.")

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

            if df_hist_prod is not None and not df_hist_prod.empty:
                st.subheader("⚙️ Média de Eficiência por Equipamento (%)")
                if "eficiencia_%" in df_hist_prod.columns and "equipamento" in df_hist_prod.columns:
                    df_grafico = df_hist_prod.groupby("equipamento")["eficiencia_%"].mean().reset_index()
                    st.bar_chart(df_grafico.set_index("equipamento"))

                st.subheader("📦 Produção Total: Programado vs Realizado por Equipamento")
                if "programado" in df_hist_prod.columns and "realizado" in df_hist_prod.columns:
                    df_totais = df_hist_prod.groupby("equipamento")[["programado", "realizado"]].sum()
                    st.bar_chart(df_totais)

                st.subheader("📜 Histórico Geral de Produção")
                st.dataframe(df_hist_prod, width="stretch")
            else:
                st.info("Nenhum registro de produção encontrado na planilha ainda.")

            if df_hist_mo is not None and not df_hist_mo.empty:
                st.subheader("👥 Histórico de Mão de Obra e Absenteísmo")
                st.dataframe(df_hist_mo, width="stretch")

        except Exception as err_dash:
            st.info("Cole e processe o primeiro relatório na Tab 1 para iniciar o histórico!")
    else:
        st.info("Para visualizar os gráficos e o histórico acumulado, configure a conexão da planilha no Secrets.")

# ==========================================================
# TAB 3: TESTE DIRETO DE CONEXÃO E GRAVAÇÃO
# ==========================================================
with tab3:
    st.header("🔍 Diagnóstico da Planilha")
    if st.button("🧪 Fazer Teste de Leitura/Gravação na Planilha"):
        if not conn:
            st.error("Conexão com Sheets indisponível no Secrets.")
        else:
            try:
                # Teste 1: Leitura da aba Producao
                df_test = conn.read(worksheet="Producao", ttl=0)
                st.success("✅ Leitura da aba 'Producao' realizada com sucesso!")
                st.write("Dados atuais na aba 'Producao':", df_test)

                # Teste 2: Gravação de linha de teste
                teste_data = pd.DataFrame([{
                    "data": "01/01/2026",
                    "turno": "1º",
                    "equipamento": "Teste_Conexao",
                    "produto": "Teste",
                    "programado": 100,
                    "realizado": 100,
                    "eficiencia_%": 100.0,
                    "status": "Teste automatizado"
                }])
                
                df_novo = pd.concat([df_test, teste_data], ignore_index=True)
                conn.update(worksheet="Producao", data=df_novo)
                st.success("🎉 TESTE DE ESCRITA CONCLUÍDO! Uma linha de teste foi gravada no seu Google Sheets com sucesso!")
            except Exception as e_teste:
                st.error(f"❌ Falha no teste de conexão: {e_teste}")
