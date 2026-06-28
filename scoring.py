"""
Cálculo de pontuação ponderada conforme Tabela 4 do MIAED.
Pesos extraídos diretamente do documento acadêmico.
"""

# ---------------------------------------------------------------------------
# Tabela 4 — Indicadores, dimensões e pesos
# ---------------------------------------------------------------------------
INDICATORS = {
    # ── Dimensão Técnica (heurística) ───────────────────────────────────────
    "alt_text": {
        "dimensao": "Técnica",
        "nome": "Presença de alt text em imagens",
        "peso": 0.08,
        "criterio": "WCAG 1.1.1 (Nível A)",
        "modo": "heuristica",
    },
    "contraste": {
        "dimensao": "Técnica",
        "nome": "Contraste de cores",
        "peso": 0.08,
        "criterio": "WCAG 1.4.3 (Nível AA)",
        "modo": "heuristica",
    },
    "navegabilidade_teclado": {
        "dimensao": "Técnica",
        "nome": "Navegabilidade por teclado",
        "peso": 0.07,
        "criterio": "WCAG 2.1.1 (Nível A)",
        "modo": "heuristica",
    },
    "labels_formularios": {
        "dimensao": "Técnica",
        "nome": "Labels e instruções em formulários",
        "peso": 0.07,
        "criterio": "WCAG 1.3.1 / 3.3.2 (Nível A)",
        "modo": "heuristica",
    },
    "headings": {
        "dimensao": "Técnica",
        "nome": "Estrutura hierárquica de headings",
        "peso": 0.06,
        "criterio": "WCAG 1.3.1 (Nível A)",
        "modo": "heuristica",
    },
    "lang_attr": {
        "dimensao": "Técnica",
        "nome": "Atributo de idioma (lang)",
        "peso": 0.05,
        "criterio": "WCAG 3.1.1 (Nível A)",
        "modo": "heuristica",
    },
    "landmarks": {
        "dimensao": "Técnica",
        "nome": "Landmarks e estrutura semântica",
        "peso": 0.05,
        "criterio": "WCAG 1.3.1 (Nível A)",
        "modo": "heuristica",
    },
    "legendas_video": {
        "dimensao": "Técnica",
        "nome": "Legendas em vídeos",
        "peso": 0.06,
        "criterio": "WCAG 1.2.2 (Nível A)",
        "modo": "heuristica",
    },
    "zoom_reflow": {
        "dimensao": "Técnica",
        "nome": "Zoom e reflow",
        "peso": 0.05,
        "criterio": "WCAG 1.4.4 / 1.4.10 (Nível AA)",
        "modo": "heuristica",
    },
    # ── Dimensão Ética (LLM) ────────────────────────────────────────────────
    "urgencia_artificial": {
        "dimensao": "Ética",
        "nome": "Urgência Artificial",
        "peso": 0.13,
        "criterio": "Dark Patterns (Brignull, 2010; Mathur et al., 2019)",
        "modo": "llm",
    },
    "opt_out": {
        "dimensao": "Ética",
        "nome": "Opt-out Pré-selecionado",
        "peso": 0.13,
        "criterio": "Dark Patterns + LGPD (Art. 7º e 9º)",
        "modo": "llm",
    },
    "confirmshaming": {
        "dimensao": "Ética",
        "nome": "Confirmshaming",
        "peso": 0.06,
        "criterio": "Dark Patterns (Brignull, 2010)",
        "modo": "llm",
    },
    "roach_motel": {
        "dimensao": "Ética",
        "nome": "Roach Motel",
        "peso": 0.06,
        "criterio": "Dark Patterns + CDC (Art. 49)",
        "modo": "llm",
    },
    "clareza_linguagem": {
        "dimensao": "Ética",
        "nome": "Clareza de linguagem",
        "peso": 0.05,
        "criterio": "WCAG 3.1.5 (Nível AAA)",
        "modo": "llm",
    },
    # ── Dimensão Regulatória (LLM) ──────────────────────────────────────────
    # "conformidade_lbi": {
    #     "dimensao": "Regulatória",
    #     "nome": "Conformidade com a LBI",
    #     "peso": 0.05,
    #     "criterio": "BRASIL (2015) – Lei Brasileira de Inclusão",
    #     "modo": "llm",
    # },
    # "conformidade_wcag": {
    #     "dimensao": "Regulatória",
    #     "nome": "Conformidade WCAG AA",
    #     "peso": 0.06,
    #     "criterio": "W3C WCAG 2.1 / 2.2",
    #     "modo": "llm",
    # },
}

# Verificação de integridade dos pesos
_total_peso = sum(v["peso"] for v in INDICATORS.values())
# assert abs(_total_peso - 1.0) < 1e-6, f"Pesos não somam 100%: {_total_peso:.4f}"


def calculate_weighted_score(raw_scores: dict) -> dict:
    """
    Calcula pontuação ponderada final (0–100).

    Args:
        raw_scores: {indicador: valor_0_a_1}

    Returns:
        Dicionário com score total, por dimensão e detalhamento.
    """
    total = 0.0
    detail = {}
    dim_scores = {"Técnica": 0.0, "Ética": 0.0, "Regulatória": 0.0}
    dim_pesos  = {"Técnica": 0.0, "Ética": 0.0, "Regulatória": 0.0}

    for key, meta in INDICATORS.items():
        raw = float(raw_scores.get(key, 0.0))
        raw = max(0.0, min(1.0, raw))
        weighted = raw * meta["peso"] * 100
        total += weighted

        detail[key] = {
            "nome":            meta["nome"],
            "dimensao":        meta["dimensao"],
            "modo":            meta["modo"],
            "peso_pct":        round(meta["peso"] * 100, 0),
            "valor_bruto":     round(raw * 100, 1),
            "valor_ponderado": round(weighted, 2),
            "criterio":        meta["criterio"],
        }

        dim_scores[meta["dimensao"]] += weighted
        dim_pesos[meta["dimensao"]]  += meta["peso"] * 100

    # Score normalizado por dimensão (0–100)
    dim_norm = {}
    for dim in dim_scores:
        if dim_pesos[dim] > 0:
            dim_norm[dim] = round(dim_scores[dim] / dim_pesos[dim] * 100, 1)
        else:
            dim_norm[dim] = 0.0

    return {
        "score_total":            round(total, 1),
        "score_tecnica":          round(dim_scores["Técnica"], 1),
        "score_etica":            round(dim_scores["Ética"], 1),
        "score_regulatoria":      round(dim_scores["Regulatória"], 1),
        "score_tecnica_norm":     dim_norm["Técnica"],
        "score_etica_norm":       dim_norm["Ética"],
        "score_regulatoria_norm": dim_norm["Regulatória"],
        "detalhamento":           detail,
    }