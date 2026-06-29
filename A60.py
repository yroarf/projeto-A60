"""
Simplificado — Análise de Acessibilidade Digital
Versão enxuta e funcional: Interface + Análise/Processamento + Resultados
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from analyzer import analyze_technical
from classifier import classify_score
from llm_analyzer import LLM_INDICATORS, analyze_ethical_regulatory
from scoring import INDICATORS, calculate_weighted_score
from evidence_extractor import extract_all_evidence

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=" A60 ",
    page_icon="👴🏻",
    layout="wide",
)

if "urls_to_analyze" not in st.session_state:
    st.session_state["urls_to_analyze"] = []
if "df_results" not in st.session_state:
    st.session_state["df_results"] = None

def _fix_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    return u

# ─────────────────────────────────────────────────────────────────────────────
# CABEÇALHO
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<div style="background: linear-gradient(90deg, #1a237e 0%, #3949ab 100%); 
            padding: 1.2rem; border-radius: 10px; color: white; text-align: center; margin-bottom: 1.5rem;">
    <h1 style="margin:0;"> A60 — Análise de Acessibilidade Digital</h1>
    <p style="margin:0.3rem 0 0; opacity:0.9;">Versão Simplificada • Heurística Técnica + LLM Ética</p>
</div>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — CONFIGURAÇÕES ESSENCIAIS
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configurações")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    use_llm = st.toggle(
        "Usar LLM (indicadores éticos e regulatórios)",
        value=bool(api_key),
        disabled=not bool(api_key),
        help="Requer OPENAI_API_KEY no arquivo .env",
    )
    llm_model = (
        st.selectbox("Modelo LLM", ["gpt-4o-mini", "gpt-4o", "gpt-4.1"], index=0)
        if use_llm
        else "gpt-4o-mini"
    )

    max_workers = st.slider("Requisições paralelas", min_value=1, max_value=5, value=3)

    st.markdown("---")
    st.caption("Análise técnica (DOM) sempre executada.\nLLM adiciona detecção de dark patterns e conformidade LBI/WCAG.")

# ─────────────────────────────────────────────────────────────────────────────
# 1. INTERFACE — CARREGAMENTO DE URLs
# ─────────────────────────────────────────────────────────────────────────────
st.header("1. Interface — Carregar URLs")

col1, col2 = st.columns([3, 2])

with col1:
    uploaded = st.file_uploader(
        "📤 Carregar CSV ou Excel com URLs",
        type=["csv", "xlsx", "xls"],
        help="O arquivo deve conter uma coluna com URLs (nome: url, link, site ou primeira coluna)",
    )
    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith((".xlsx", ".xls")):
                df_in = pd.read_excel(uploaded)
            else:
                df_in = pd.read_csv(uploaded)

            # Detectar coluna de URL de forma robusta
            cols_lower = {str(c).lower().strip(): c for c in df_in.columns}
            url_col = None
            for cand in ["url", "link", "site", "website", "endereco", "address"]:
                if cand in cols_lower:
                    url_col = cols_lower[cand]
                    break
            if url_col is None:
                url_col = df_in.columns[0]

            raw_urls = df_in[url_col].dropna().astype(str).str.strip().tolist()
            urls_fixed = [_fix_url(u) for u in raw_urls if len(u) > 5]
            urls_fixed = list(dict.fromkeys(urls_fixed))  # deduplicar mantendo ordem

            st.session_state["urls_to_analyze"] = urls_fixed
            st.success(f"✅ {len(urls_fixed)} URLs carregadas (coluna '{url_col}')")

        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {e}")

with col2:
    st.markdown("**Ou cole URLs manualmente (uma por linha):**")
    manual_text = st.text_area(
        "URLs",
        height=120,
        placeholder="https://www.gov.br\nhttps://www.ibge.gov.br\nhttps://www.bb.com.br",
        label_visibility="collapsed",
    )
    if st.button("➕ Adicionar URLs", use_container_width=True):
        if manual_text.strip():
            manual_list = [line.strip() for line in manual_text.splitlines() if line.strip()]
            manual_fixed = [_fix_url(u) for u in manual_list if len(u) > 5]
            current = st.session_state.get("urls_to_analyze", [])
            merged = list(dict.fromkeys(current + manual_fixed))
            st.session_state["urls_to_analyze"] = merged
            st.success(f"Total atualizado: {len(merged)} URLs")
            st.rerun()

# Lista atual (editável)
if st.session_state["urls_to_analyze"]:
    with st.expander(f"📋 Lista atual ({len(st.session_state['urls_to_analyze'])} URLs) — clique para editar", expanded=False):
        current_list = "\n".join(st.session_state["urls_to_analyze"])
        edited_text = st.text_area("Editar URLs (uma por linha)", value=current_list, height=180)
        if st.button("💾 Salvar alterações na lista"):
            new_list = [line.strip() for line in edited_text.splitlines() if line.strip()]
            new_list = [_fix_url(u) for u in new_list if len(u) > 5]
            st.session_state["urls_to_analyze"] = list(dict.fromkeys(new_list))
            st.success("Lista atualizada!")
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 2. ANÁLISE / PROCESSAMENTO
# ─────────────────────────────────────────────────────────────────────────────
st.header("2. Análise e Processamento")

urls_atuais = st.session_state.get("urls_to_analyze", [])
n = len(urls_atuais)

if n == 0:
    st.info("⬆️ Carregue URLs na seção acima para iniciar a análise.")
else:
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.metric("URLs a analisar", n)
    with col_info2:
        tempo_est = round(n * 1.2 / max_workers, 0)
        st.metric("Tempo estimado", f"~{tempo_est}s")

    if st.button("🚀 Iniciar Análise Híbrida", type="primary", use_container_width=True):
        progress = st.progress(0.0, text="Preparando análise...")
        status_box = st.empty()
        resultados = []
        t0 = time.time()

        def _analisar_um(url: str) -> dict:
            t_url = time.time()
            try:
                # 1. Análise técnica (heurística)
                tech = analyze_technical(url)
                html_raw = tech.get("html_raw", "") or ""
                # === Integração com evidence_extractor ===
                evidence = {}
                if html_raw:
                    try:
                        evidence = extract_all_evidence(url, html_raw)
                    except Exception:
                        evidence = {}
                fetch_error = tech.get("erro")

                # === CORREÇÃO: Falha de coleta → retorna imediatamente ===
                if fetch_error or not html_raw.strip():
                    return {
                        "url": url,
                        "score_total": None,
                        "classificacao": "Não avaliável",
                        "nivel_exclusao": "Falha na coleta",
                        "tempo_s": round(time.time() - t_url, 1),
                        "status": "falha_coleta",
                        "erro_msg": fetch_error or "HTML vazio ou inacessível",
                        "scores_indicadores": {},
                        "indicadores_nao_conformes": {},
                        "evidencia_nao_conforme": {},
                    }

                # Scores técnicos
                tech_keys = [k for k, v in INDICATORS.items() if v.get("modo") == "heuristica"]
                tech_scores = {k: float(tech.get(k, 0.5)) for k in tech_keys}

                # 2. Análise LLM (ética/regulatória) — se ativada
                if use_llm and api_key:
                    llm_res = analyze_ethical_regulatory(
                        url=url,
                        html_text=html_raw[:8000],
                        html_snippet=html_raw[:4000],
                        api_key=api_key,
                        model=llm_model,
                    )
                    llm_scores = {k: float(llm_res.get(k, 0.5)) for k in LLM_INDICATORS}
                else:
                    llm_scores = {k: 0.5 for k in LLM_INDICATORS}

                # 3. Pontuação ponderada + classificação
                all_scores = {**tech_scores, **llm_scores}
                weighted = calculate_weighted_score(all_scores)
                classificacao = classify_score(weighted["score_total"])

                # === Identifica indicadores não conformes + evidência ===
                THRESHOLD = 0.60
                indicadores_nao_conformes = {}
                evidencia_nao_conforme = {}

                for ind_key, score_val in all_scores.items():
                    if score_val < THRESHOLD:
                        indicadores_nao_conformes[ind_key] = round(score_val, 3)

                        evidencia = ""
                        if ind_key in tech_scores:
                            evidencia = html_raw[:1500] if html_raw else "HTML não disponível"
                        else:
                            if 'llm_res' in locals() and isinstance(llm_res, dict):
                                justificativas = llm_res.get("llm_justificativas", {})
                                evidencia = justificativas.get(ind_key, "Justificativa não disponível")

                        evidencia_nao_conforme[ind_key] = evidencia[:800]

                return {
                    "url": url,
                    "score_total": round(weighted["score_total"], 1),
                    "classificacao": classificacao.get("classificacao", "N/A"),
                    "nivel_exclusao": classificacao.get("nivel_exclusao", ""),
                    "tempo_s": round(time.time() - t_url, 1),
                    "status": "sucesso",
                    "evidence": evidence,
                    "scores_indicadores": all_scores,
                    "indicadores_nao_conformes": indicadores_nao_conformes,
                    "evidencia_nao_conforme": evidencia_nao_conforme,

                }

            except Exception as exc:
                return {
                    "url": url,
                    "score_total": 0.0,
                    "classificacao": "Erro",
                    "nivel_exclusao": "Falha",
                    "tempo_s": round(time.time() - t_url, 1),
                    "status": "erro",
                    "erro_msg": str(exc)[:120],
                }

        # Execução paralela
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_analisar_um, u): u for u in urls_atuais}
            concluidos = 0
            for future in as_completed(future_map):
                res = future.result()
                resultados.append(res)
                concluidos += 1
                pct = concluidos / n
                progress.progress(pct, text=f"Processando {concluidos}/{n} — {res['url'][:60]}")
                status_box.caption(
                    f"⏱️ Decorrido: {time.time() - t0:.0f}s | "
                    f"Sucessos: {sum(r.get('status') == 'sucesso' for r in resultados)} | "
                    f"Falhas de coleta: {sum(r.get('status') == 'falha_coleta' for r in resultados)} | "
                    f"Erros: {sum(r.get('status') == 'erro' for r in resultados)}"
                )

        df_final = pd.DataFrame(resultados)
        st.session_state["df_results"] = df_final
        st.session_state["analysis_time"] = round(time.time() - t0, 1)

        progress.progress(1.0, text="Análise concluída!")
        status_box.success(f"✅ {concluidos} URLs processadas em {st.session_state['analysis_time']}s")
        time.sleep(0.8)
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 3. APRESENTAÇÃO DE RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────
st.header("3. Apresentação de Resultados")

df_res = st.session_state.get("df_results")

if df_res is None or df_res.empty:
    st.info("Execute a análise na seção 2 para visualizar os resultados.")
else:
    # Resumo executivo
    st.subheader("Resumo Executivo")
    c1, c2, c3, c4 = st.columns(4)
    total = len(df_res)
    sucessos = len(df_res[df_res["status"] == "sucesso"]) if "status" in df_res.columns else 0
    falhas_coleta = len(df_res[df_res["status"] == "falha_coleta"]) if "status" in df_res.columns else 0
    erros = len(df_res[df_res["status"] == "erro"]) if "status" in df_res.columns else 0

    c1.metric("Total de URLs", total)
    c2.metric("Analisadas com sucesso", sucessos)
    c3.metric("Falhas de coleta", falhas_coleta)
    if sucessos > 0 and "score_total" in df_res.columns:
        media = df_res[df_res["status"] == "sucesso"]["score_total"].mean()
        c4.metric("Score médio (sucessos)", f"{media:.1f} / 100")
    else:
        c4.metric("Score médio (sucessos)", "—")

    # Tabela principal (essencial)
    st.subheader("Tabela de Resultados")
    cols_mostrar = ["url", "score_total", "classificacao", "nivel_exclusao", "status"]
    if "erro_msg" in df_res.columns:
        cols_mostrar.append("erro_msg")

    df_show = df_res[cols_mostrar].copy()

    # === CORREÇÃO: Tratamento visual de falhas de coleta ===
    if "status" in df_show.columns and "score_total" in df_show.columns:
        mask_falha = df_show["status"] == "falha_coleta"
        # df_show.loc[mask_falha, "score_total"] = "N/A"
        df_show.loc[mask_falha, "classificacao"] = "Não avaliável"
        df_show.loc[mask_falha, "nivel_exclusao"] = "Falha na coleta de HTML"

    if "score_total" in df_show.columns:
        # Ordena numericamente os que têm score, mantendo N/A no final
        df_show = df_show.sort_values(
            by="score_total",
            ascending=False,
            key=lambda x: pd.to_numeric(x, errors="coerce")
        )

    st.dataframe(df_show, use_container_width=True, hide_index=True)

    # Visualização essencial — apenas histograma (apenas sucessos)
    if sucessos > 0 and "score_total" in df_res.columns:
        st.subheader("📈 Distribuição dos Scores")
        df_ok = df_res[df_res["status"] == "sucesso"]
        fig = px.histogram(
            df_ok,
            x="score_total",
            nbins=min(12, max(5, len(df_ok) // 2)),
            title="Distribuição dos Scores Totais (apenas análises bem-sucedidas)",
            labels={"score_total": "Score Total (0–100)", "count": "Quantidade"},
            color_discrete_sequence=["#3949ab"],
        )
        fig.update_layout(bargap=0.15, showlegend=False, height=320)
        st.plotly_chart(fig, use_container_width=True)

    # Resumo por classificação (apenas sucessos)
    if "classificacao" in df_res.columns:
        st.subheader("Classificação dos Sites")
        df_class = df_res[df_res["status"] == "sucesso"]
        if not df_class.empty:
            resumo_class = (
                df_class.groupby("classificacao")
                .size()
                .reset_index(name="Quantidade")
                .sort_values("Quantidade", ascending=False)
            )
            st.dataframe(resumo_class, use_container_width=True, hide_index=True)

        # ═══════════════════════════════════════════════════════════════════════
        # RELATÓRIO DETALHADO COM EVIDÊNCIA HTML
        # ═══════════════════════════════════════════════════════════════════════
        st.subheader("📋 Relatório Detalhado por Indicador e Não Conformidades")

        with st.expander("📊 Ver scores de todos os 15 indicadores", expanded=False):
            score_data = []
            for _, row in df_res.iterrows():
                if row.get("status") == "sucesso" and isinstance(row.get("scores_indicadores"), dict):
                    item = {
                        "url": row["url"],
                        "score_total": row["score_total"],
                        "classificacao": row["classificacao"]
                    }
                    item.update({f"score_{k}": v for k, v in row["scores_indicadores"].items()})
                    score_data.append(item)

            if score_data:
                st.dataframe(pd.DataFrame(score_data), use_container_width=True, hide_index=True)

        # === Seção de Não Conformidades com Evidência ===
        st.markdown("### ⚠️ Indicadores identificados como não conformes (score < 0.60)")

        for _, row in df_res.iterrows():
            if row.get("status") != "sucesso":
                continue  # Ignora falhas de coleta e erros

            nao_conformes = row.get("indicadores_nao_conformes", {})
            evidencias = row.get("evidencia_nao_conforme", {})

            if isinstance(nao_conformes, dict) and nao_conformes:
                with st.expander(f"🔗 {row['url']} — {row['classificacao']} (Score: {row['score_total']})"):
                    for ind_key, score_val in nao_conformes.items():
                        nome_legivel = INDICATORS.get(ind_key, {}).get("nome", ind_key.replace("_", " ").title())
                        st.markdown(f"**{nome_legivel}** (`{ind_key}`) — Score: **{score_val}**")

                        # Tenta pegar evidência precisa do evidence_extractor primeiro
                        evidencia_html = ""
                        if "evidence" in row and isinstance(row["evidence"], dict):
                            ind_evidence = row["evidence"].get(ind_key, {})
                            if isinstance(ind_evidence, dict) and ind_evidence.get("issues"):
                                # Pega o primeiro issue encontrado
                                first_issue = ind_evidence["issues"][0]
                                evidencia_html = first_issue.get("elemento", "") or first_issue.get("detalhe", "")

                        # Fallback para justificativa do LLM
                        if not evidencia_html:
                            evidencia_html = evidencias.get(ind_key, "Evidência não disponível")

                        st.code(evidencia_html[:800] if len(evidencia_html) > 800 else evidencia_html, language="html")

    # Exportação
    st.subheader("Exportar")
    csv_bytes = df_res.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Baixar CSV completo com resultados",
        data=csv_bytes,
        file_name="scoreA60_resultados_simplificado.csv",
        mime="text/csv",
        use_container_width=True,
    )

# Rodapé
st.markdown("---")
st.caption(
    "Apenas o essencial para análise funcional de acessibilidade de sites. "
    "Técnica via HTML/DOM + LLM (quando ativado) para dark patterns. "
    "Falhas de coleta são consideradas apenas para estatística operacional."
)
