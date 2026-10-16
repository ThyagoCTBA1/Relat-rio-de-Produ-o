import json
import pandas as pd
from openai import OpenAI
import streamlit as st

st.set_page_config(page_title="Gestão de Produção", layout="wide", page_icon="🏭")

st.title("🏭 Leitor e Agrupador de Relatórios de Produção")
st.write("Copie o texto do relatório do WhatsApp e cole na caixa abaixo.")

# Caixa para colar o texto do WhatsApp
texto_whatsapp = st.text_area("📋 Cole o relatório aqui:", height=280)

if st.button("🚀 Processar e Agrupar Dados", type="primary"):
    if not texto_whatsapp.strip():
        st.warning("⚠️ Por favor, cole o texto do relatório antes de clicar em processar.")
    else:
        with st.spinner("Lendo e organizando dados com Inteligência Artificial..."):
            try:
                # Conexão com a chave de API da OpenAI
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

                prompt = f"""
                Você é um assistente especialista em Controle de Produção Industrial (PCP).
                Analise o texto do relatório enviado pelo usuário e extraia todas as informações em formato JSON rigorosamente estruturado:

                Regras para extração:
                1. Extraia Data, Turno, Mão de Obra Total, Efetivos, Temporários e Ausências/Faltas/Atestados.
                2. Extraia todos os equipamentos informados na lista de produção.
                3. Para cada equipamento, extraia: nome, produto/projeto, quantidade programada, quantidade realizada, M.O necessária e observações/status.
                4. Converta números em formato texto (ex: 10.000 ou 10000) em inteiros (ex: 10000). Se for nulo ou sem produção, coloque 0.

                Formato esperado de saída (JSON puro):
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

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )

                dados = json.loads(response.choices[0].message.content)

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

                    # Cálculo da eficiência %
                    if "programado" in df.columns and "realizado" in df.columns:
                        df["eficiencia_%"] = df.apply(
                            lambda row: round((row["realizado"] / row["programado"] * 100), 1) if row["programado"] > 0 else 0.0,
                            axis=1
                        )

                    # Reorganização das colunas
                    cols = ["equipamento", "produto", "programado", "realizado", "eficiencia_%", "mo_necessaria", "status"]
                    cols_existentes = [c for c in cols if c in df.columns]
                    df = df[cols_existentes]

                    st.dataframe(df, use_container_width=True)

                    # Destaque para equipamentos com problemas/observações
                    st.subheader("⚠️ Resumo de Problemas e Paradas do Turno")
                    problemas = df[df["status"].str.len() > 3]
                    
                    if not problemas.empty:
                        for _, row in problemas.iterrows():
                            st.warning(f"**{row['equipamento']}** ({row['produto']}): {row['status']}")
                    else:
                        st.success("Nenhuma parada ou problema reportado neste turno.")

            except Exception as e:
                st.error(f"Erro ao processar o relatório: {e}")
