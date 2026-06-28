"""
Inconsistency Reporter — Gera CSV detalhado de inconsistências detectadas.
Cada linha representa uma inconsistência específica encontrada em uma URL.
"""

import io
import pandas as pd
from typing import Any

# Mapeamento: indicador → dimensão e descrição
INDICATOR_META = {
    "alt_text": {
        "dimensao": "Técnica",
        "nome": "Texto Alternativo (Alt Text)",
        "wcag": "WCAG 1.1.1 (Nível A)",
        "lbi": "Art. 63",
        "impacto_idoso": "Crítico — leitores de tela não descrevem imagens",
    },
    "contraste": {
        "dimensao": "Técnica",
        "nome": "Contraste de Cores",
        "wcag": "WCAG 1.4.3 (Nível AA)",
        "lbi": "Art. 63",
        "impacto_idoso": "Crítico — visão reduzida dificulta leitura",
    },
    "navegabilidade_teclado": {
        "dimensao": "Técnica",
        "nome": "Navegabilidade por Teclado",
        "wcag": "WCAG 2.1.1 (Nível A)",
        "lbi": "Art. 63",
        "impacto_idoso": "Alto — idosos com tremor dependem do teclado",
    },
    "labels_formularios": {
        "dimensao": "Técnica",
        "nome": "Labels de Formulários",
        "wcag": "WCAG 1.3.1 (Nível A)",
        "lbi": "Art. 63",
        "impacto_idoso": "Alto — confusão ao preencher formulários",
    },
    "headings": {
        "dimensao": "Técnica",
        "nome": "Hierarquia de Headings",
        "wcag": "WCAG 1.3.1 (Nível A)",
        "lbi": "Art. 63",
        "impacto_idoso": "Moderado — desorientação na navegação",
    },
    "lang_attr": {
        "dimensao": "Técnica",
        "nome": "Atributo Lang",
        "wcag": "WCAG 3.1.1 (Nível A)",
        "lbi": "Art. 63",
        "impacto_idoso": "Moderado — leitores de tela pronunciam errado",
    },
    "landmarks": {
        "dimensao": "Técnica",
        "nome": "Landmarks ARIA",
        "wcag": "WCAG 1.3.6 (Nível AAA)",
        "lbi": "Art. 63",
        "impacto_idoso": "Moderado — dificulta navegação por regiões",
    },
    "legendas_video": {
        "dimensao": "Técnica",
        "nome": "Legendas de Vídeo",
        "wcag": "WCAG 1.2.2 (Nível A)",
        "lbi": "Art. 67",
        "impacto_idoso": "Alto — perda auditiva comum em idosos",
    },
    "zoom_reflow": {
        "dimensao": "Técnica",
        "nome": "Zoom e Reflow",
        "wcag": "WCAG 1.4.4 (Nível AA)",
        "lbi": "Art. 63",
        "impacto_idoso": "Crítico — idosos dependem de zoom para leitura",
    },
    "urgencia_artificial": {
        "dimensao": "Ética",
        "nome": "Urgência Artificial (Dark Pattern)",
        "wcag": "N/A",
        "lbi": "Art. 8 (dignidade)",
        "impacto_idoso": "Crítico — manipula decisão de compra de idosos",
    },
    "confirmshaming": {
        "dimensao": "Ética",
        "nome": "Confirmshaming (Dark Pattern)",
        "wcag": "N/A",
        "lbi": "Art. 8 (dignidade)",
        "impacto_idoso": "Crítico — constrangimento emocional de idosos",
    },
    "font_size": {
        "dimensao": "Técnica",
        "nome": "Tamanho de Fonte",
        "wcag": "WCAG 1.4.4 (Nível AA)",
        "lbi": "Art. 63",
        "impacto_idoso": "Crítico — visão reduzida em idosos",
    },
}


def _severity(tipo: str, score: float) -> str:
    """Classifica severidade da inconsistência."""
    critical_types = {
        "zoom_bloqueado", "img_sem_alt", "video_sem_legenda",
        "urgencia_artificial", "confirmshaming", "fonte_muito_pequena",
    }
    high_types = {
        "tabindex_negativo", "div_onclick_sem_role", "input_sem_label",
        "zoom_limitado", "lang_ausente", "sem_h1",
    }
    if tipo in critical_types or score < 0.3:
        return "🔴 Crítico"
    elif tipo in high_types or score < 0.5:
        return "🟠 Alto"
    elif score < 0.7:
        return "🟡 Moderado"
    else:
        return "🟢 Baixo"


def build_inconsistency_dataframe(
    all_evidence: list[dict],
    score_threshold: float = 0.7,
) -> pd.DataFrame:
    """
    Constrói DataFrame com todas as inconsistências detectadas.

    Parâmetros:
        all_evidence: Lista de dicts retornados por extract_all_evidence()
        score_threshold: Só inclui indicadores com score abaixo deste valor

    Retorna:
        DataFrame com uma linha por inconsistência específica
    """
    rows = []

    for ev in all_evidence:
        if not isinstance(ev, dict) or "url" not in ev:
            continue

        url = ev.get("url", "")

        for indicator_key, meta in INDICATOR_META.items():
            ind_data = ev.get(indicator_key, {})
            if not isinstance(ind_data, dict):
                continue

            score = ind_data.get("score_estimado", 1.0)
            issues = ind_data.get("issues", [])
            total_issues = ind_data.get("total_issues", len(issues))

            # Só reporta se há issues OU score abaixo do threshold
            if not issues and score >= score_threshold:
                continue

            if issues:
                # Uma linha por issue específico
                for issue in issues:
                    rows.append({
                        # Identificação
                        "url":                  url,
                        "indicador_chave":      indicator_key,
                        "indicador_nome":       meta["nome"],
                        "dimensao":             meta["dimensao"],
                        # Conformidade
                        "wcag_criterio":        meta["wcag"],
                        "lbi_referencia":       meta["lbi"],
                        "impacto_idoso":        meta["impacto_idoso"],
                        # Issue específico
                        "tipo_inconsistencia":  issue.get("tipo", "N/A"),
                        "severidade":           _severity(
                                                    issue.get("tipo", ""),
                                                    score
                                                ),
                        "score_indicador":      round(score * 100, 1),
                        "total_issues_indicador": total_issues,
                        # Evidência HTML
                        "elemento_html":        issue.get("elemento", ""),
                        "detalhe_inconsistencia": issue.get("detalhe", ""),
                        # Dados extras do indicador
                        "info_adicional":       _format_extra(indicator_key, ind_data),
                    })
            else:
                # Score baixo mas sem issues específicos capturados
                rows.append({
                    "url":                  url,
                    "indicador_chave":      indicator_key,
                    "indicador_nome":       meta["nome"],
                    "dimensao":             meta["dimensao"],
                    "wcag_criterio":        meta["wcag"],
                    "lbi_referencia":       meta["lbi"],
                    "impacto_idoso":        meta["impacto_idoso"],
                    "tipo_inconsistencia":  "score_baixo",
                    "severidade":           _severity("score_baixo", score),
                    "score_indicador":      round(score * 100, 1),
                    "total_issues_indicador": 0,
                    "elemento_html":        "N/A",
                    "detalhe_inconsistencia": f"Score baixo ({score*100:.0f}%) — análise LLM indicou problemas",
                    "info_adicional":       "",
                })

    if not rows:
        return pd.DataFrame(columns=[
            "url", "indicador_chave", "indicador_nome", "dimensao",
            "wcag_criterio", "lbi_referencia", "impacto_idoso",
            "tipo_inconsistencia", "severidade", "score_indicador",
            "total_issues_indicador", "elemento_html",
            "detalhe_inconsistencia", "info_adicional",
        ])

    df = pd.DataFrame(rows)

    # Ordena: URL → severidade → indicador
    severity_order = {
        "🔴 Crítico": 0, "🟠 Alto": 1, "🟡 Moderado": 2, "🟢 Baixo": 3
    }
    df["_sev_order"] = df["severidade"].map(severity_order).fillna(4)
    df = df.sort_values(["url", "_sev_order", "indicador_nome"])
    df = df.drop(columns=["_sev_order"])
    df = df.reset_index(drop=True)

    return df


def _format_extra(indicator_key: str, ind_data: dict) -> str:
    """Formata informações adicionais específicas por indicador."""
    extras = {
        "alt_text": lambda d: f"Total imagens: {d.get('total_imgs',0)} | Sem alt: {d.get('total_sem_alt',0)}",
        "headings": lambda d: f"Total headings: {d.get('total_headings',0)} | Sequência: {d.get('sequencia',[])}",
        "labels_formularios": lambda d: f"Total inputs: {d.get('total_inputs',0)}",
        "landmarks": lambda d: f"Landmarks encontrados: {d.get('landmarks_encontrados',[])}",
        "legendas_video": lambda d: f"Total vídeos/iframes: {d.get('total_videos',0)}",
        "lang_attr": lambda d: f"Lang detectado: '{d.get('lang_detectado','')}'",
        "contraste": lambda d: f"Total elementos com style: {d.get('total_com_style',0)}",
    }
    fn = extras.get(indicator_key)
    return fn(ind_data) if fn else ""


def generate_csv_bytes(df: pd.DataFrame) -> bytes:
    """Converte DataFrame para bytes CSV (UTF-8 com BOM para Excel)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue().encode("utf-8-sig")


def generate_summary_dataframe(df_inconsistencies: pd.DataFrame) -> pd.DataFrame:
    """
    Gera DataFrame resumo: uma linha por URL com contagem de issues por severidade.
    """
    if df_inconsistencies.empty:
        return pd.DataFrame()

    summary = (
        df_inconsistencies
        .groupby("url")
        .agg(
            total_inconsistencias=("tipo_inconsistencia", "count"),
            criticos=("severidade", lambda x: (x == "🔴 Crítico").sum()),
            altos=("severidade", lambda x: (x == "🟠 Alto").sum()),
            moderados=("severidade", lambda x: (x == "🟡 Moderado").sum()),
            baixos=("severidade", lambda x: (x == "🟢 Baixo").sum()),
            indicadores_afetados=("indicador_nome", lambda x: ", ".join(sorted(x.unique()))),
            dimensoes_afetadas=("dimensao", lambda x: ", ".join(sorted(x.unique()))),
        )
        .reset_index()
        .sort_values("criticos", ascending=False)
    )
    return summary