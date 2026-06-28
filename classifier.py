"""
Classificação conforme Tabela 5 do MIAED.
"""


def classify_score(score: float) -> dict:
    """
    Classifica a pontuação conforme Tabela 5 — Escala de Classificação.

    Args:
        score: Pontuação de 0 a 100

    Returns:
        Dicionário com classificação, nível, interpretação e ação recomendada.
    """
    score = float(score)

    if score >= 90:
        return {
            "classificacao": "Excelente",
            "nivel_exclusao": "Mínimo",
            "faixa": "90 — 100",
            "interpretacao": (
                "Site altamente acessível; conformidade WCAG AA completa; "
                "ausência de dark patterns."
            ),
            "acao_recomendada": "Manutenção e monitoramento contínuo.",
            "cor": "#2E7D32",
            "emoji": "🟢",
        }
    elif score >= 75:
        return {
            "classificacao": "Bom",
            "nivel_exclusao": "Baixo",
            "faixa": "75 — 89",
            "interpretacao": (
                "Conformidade substancial; problemas pontuais de baixa severidade."
            ),
            "acao_recomendada": "Correção de itens residuais; auditoria anual.",
            "cor": "#558B2F",
            "emoji": "🟡",
        }
    elif score >= 50:
        return {
            "classificacao": "Regular",
            "nivel_exclusao": "Moderado",
            "faixa": "50 — 74",
            "interpretacao": (
                "Violações de nível AA; possíveis dark patterns; "
                "barreiras para grupos vulneráveis."
            ),
            "acao_recomendada": "Plano de remediação em 90 dias.",
            "cor": "#F57F17",
            "emoji": "🟠",
        }
    elif score >= 25:
        return {
            "classificacao": "Insuficiente",
            "nivel_exclusao": "Alto",
            "faixa": "25 — 49",
            "interpretacao": (
                "Múltiplas violações de nível A; dark patterns confirmados; "
                "exclusão sistemática de grupos vulneráveis."
            ),
            "acao_recomendada": "Redesign urgente; auditoria especializada.",
            "cor": "#E65100",
            "emoji": "🔴",
        }
    else:
        return {
            "classificacao": "Crítico",
            "nivel_exclusao": "Muito Alto",
            "faixa": "0 — 24",
            "interpretacao": (
                "Não conformidade grave; exclusão intencional por design; "
                "risco legal significativo."
            ),
            "acao_recomendada": (
                "Interdição do serviço digital; redesign completo."
            ),
            "cor": "#B71C1C",
            "emoji": "⛔",
        }