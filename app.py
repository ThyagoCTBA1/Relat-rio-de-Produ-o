import json
import time
import pandas as pd
from google import genai
import streamlit as st

st.set_page_config(page_title="Gestão de Produção", layout="wide", page_icon="🏭")

st.title("🏭 Leitor e Agrupador de Relatórios de Produção")
st.write("Copie o texto do relatório do WhatsApp e cole na caixa abaixo.")

texto_whatsapp = st.text_area("📋 Cole o relatório aqui:", height=280)

if st.button("🚀 Processar e Agrupar Dados", type="primary"):
    if not texto_whatsapp.strip():
        st.warning("⚠️ Por favor, cole o texto do relatório antes de processar.")
    else:
        with st.spinner("Lendo e organizando dados com o Google Gemini..."):
            try:
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

                # Lista com apenas modelos válidos e suportados
                modelos = ["gemini-3.8-flash", "gemini-1.5-flash"]
                response = None

                for modelo in modelos:
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
                            msg_erro = str(err)
                            # Se o modelo for 404 (inexistente), pula direto para o próximo modelo da lista
                            if "404" in msg_erro or "NOT_FOUND" in msg_erro:
                                break
                            # Se for instabilidade (503), espera 2 segundos e tenta novamente o mesmo modelo
                            elif "503" in msg_erro or "UNAVAILABLE" in msg_erro:
                                time.sleep(2)
                                continue
                            else:
                                break
                    if response and response.text:
                        break

                if not response or not response.text:
                    raise Exception("Não foi possível conectar aos servidores no momento. Por favor, tente novamente em instantes.")

                # Limpeza e conversão do JSON recebido
                texto_resposta = response.text.strip()
                if texto_resposta.startswith("```json"):
                    texto_resposta = texto_resposta[7:-3].strip()
                elif texto_resposta.startswith("```"):
                    texto_resposta = texto_resposta[3:-3].strip()

                dados = json.loads(texto_resposta)

                st.success("✅ Relatório Processado com Sucesso!")

                # Exibição do resumo de pessoal
                st.subheader("📊 Mão de Obra e Ocorrências")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Data", dados.get("data", "N/A"))
                c2.metric("Turno", dados.get("turno", "N/A"))
                c3.metric("M.O Total", dados.get("mo_total", 0))
                c4.metric("Efetivos / Temp", f"{dados.get('efetivos', 0)} / {dados.get('temporarios', 0)}")

                st.info(f"**Ocorrências de Pessoal:** {dados.get('ausencias', 'Nenhuma ocorrência relatada.')}")

                # Exibição do resumo de produção
                st.subheader("⚙️ Produção Detalhada por Equipamento")
                lista_prod = dados.get("producao", [])

                if lista_prod:
                    df = pd.DataFrame(lista_prod)

                    if "programado" in df.columns and "realizado" in df.columns:
                        df["eficiencia_%"] = df.apply(
                            lambda row: round((row["realizado"] / row["programado"] * 100), 1) if row["programado"] > 0 else 0.0,
                            axis=1
                        )

                    cols = ["equipamento", "produto", "programado", "realizado", "eficiencia_%", "mo_necessaria", "status"]
                    cols_existentes = [c for c in cols if c in df.columns]
                    df = df[cols_existentes]

                    st.dataframe(df, use_container_width=True)

                    st.subheader("⚠️ Resumo de Problemas e Paradas do Turno")
                    problemas = df[df["status"].str.len() > 3]
                    
                    if not problemas.empty:
                        for _, row in problemas.iterrows():
                            st.warning(f"**{row['equipamento']}** ({row['produto']}): {row['status']}")
                    else:
                        st.success("Nenhuma parada ou problema reportado neste turno.")

            except Exception as e:
                st.error(f"Erro ao processar o relatório: {e}")
