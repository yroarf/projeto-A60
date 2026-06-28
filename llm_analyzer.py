
"""
llm_analyzer_ud.py — Versão atualizada e otimizada
Estratégia: Chain-of-Thought + Exemplos Positivos/Negativos
"""

import logging
import re
import threading
import time
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential, before_sleep_log

logger = logging.getLogger(__name__)

LLM_INDICATORS = [
    "urgencia_artificial",
    "opt_out",
    "confirmshaming",
    "roach_motel",
    "clareza_linguagem",
    # "conformidade_lbi",
    # "conformidade_wcag",
]

_LLM_SEMAPHORE = threading.Semaphore(1)
_MIN_CALL_INTERVAL = 3.0
_last_call_time = 0.0
_call_lock = threading.Lock()

def _wait_rate_limit():
    global _last_call_time
    with _call_lock:
        elapsed = time.time() - _last_call_time
        if elapsed < _MIN_CALL_INTERVAL:
            time.sleep(_MIN_CALL_INTERVAL - elapsed)
        _last_call_time = time.time()


def _truncate_html(html_text: str, max_chars: int = 7000) -> str:
    html_text = re.sub(r"<script[^>]*>.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    html_text = re.sub(r"<style[^>]*>.*?</style>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    html_text = re.sub(r"<!--.*?-->", "", html_text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", html_text).strip()[:max_chars]


def _build_improved_prompt(url: str, html_snippet: str) -> str:
    return f"""Você é um especialista em acessibilidade digital, dark patterns e inclusão de idosos (60+).

Analise o HTML abaixo e avalie **cada um dos 5 indicadores** com um score de 0.0 a 1.0.

**REGRAS GERAIS DE PONTUAÇÃO (obrigatórias):**
- Score ALTO (próximo de 1.0) = situação BOA para acessibilidade de idosos.
- Score BAIXO (próximo de 0.0) = situação RUIM para acessibilidade de idosos.
- Seja rigoroso, mas justo. Use 0.5 apenas quando realmente não for possível avaliar.

---

### INDICADORES E CRITÉRIOS DE PONTUAÇÃO:

1. **urgencia_artificial** (Dark Pattern)
   - Score ALTO (≈ 1.0): Não há mensagens de urgência artificial, contagens regressivas, "restam X unidades", "oferta expira em...", "só hoje" ou pressão de tempo/escassez.
   - Score BAIXO (≈ 0.0): Existem frases ou elementos que criam sensação de urgência artificial para pressionar decisões rápidas.

2. **opt_out**
   - Score ALTO (≈ 1.0): O usuário consegue recusar cookies, cancelar serviços ou sair de assinaturas de forma clara e fácil.
   - Score BAIXO (≈ 0.0): O opt-out é difícil, escondido, exige muitos cliques ou está em texto muito pequeno.

3. **confirmshaming** (Dark Pattern)
   - Score ALTO (≈ 1.0): Os botões ou links de recusa usam linguagem neutra ("Não, obrigado", "Recusar").
   - Score BAIXO (≈ 0.0): Usa linguagem constrangedora ou manipuladora para quem recusa ("Não, prefiro pagar mais caro", "Não quero economizar").

4. **roach_motel** (Dark Pattern)
   - Score ALTO (≈ 1.0): É fácil entrar e fácil sair do serviço (cancelamento visível e simples).
   - Score BAIXO (≈ 0.0): É fácil entrar, mas difícil sair (cancelamento escondido, exige telefone, chat demorado ou processo complexo).

5. **clareza_linguagem**
   - Score ALTO (≈ 1.0): O texto é simples, direto, com frases curtas e vocabulário acessível para idosos.
   - Score BAIXO (≈ 0.0): O texto usa linguagem técnica, jurídica ou complexa, com frases longas e difíceis de entender.


---

**URL analisada:** {url}

**HTML (trecho limpo):**
{html_snippet}

**INSTRUÇÕES FINAIS:**
- Pense passo a passo antes de atribuir cada score.
- Após definir os scores, verifique se a justificativa está coerente com o valor atribuído.
- Se a justificativa indicar ausência do problema, o score deve ser alto. Se indicar presença do problema, o score deve ser baixo.
- Responda **APENAS** com JSON válido, sem texto fora do JSON.

Formato de resposta esperado:
{{
  "urgencia_artificial": <0.0-1.0>,
  "opt_out": <0.0-1.0>,
  "confirmshaming": <0.0-1.0>,
  "roach_motel": <0.0-1.0>,
  "clareza_linguagem": <0.0-1.0>,
  "conformidade_lbi": <0.0-1.0>,
  "conformidade_wcag": <0.0-1.0>,
  "justificativas": {{
    "urgencia_artificial": "explicação curta e objetiva",
    "opt_out": "...",
    "confirmshaming": "...",
    "roach_motel": "...",
    "clareza_linguagem": "...",
    "conformidade_lbi": "...",
    "conformidade_wcag": "..."
  }}
}}
"""

# 6. **conformidade_lbi**
#    - Score ALTO (≈ 1.0): O site menciona ou demonstra conformidade com a Lei Brasileira de Inclusão (Lei 13.146/2015).
#    - Score BAIXO (≈ 0.0): Não há qualquer menção ou evidência de conformidade com a LBI.
#
# 7. **conformidade_wcag**
#    - Score ALTO (≈ 1.0): O HTML apresenta boa estrutura semântica, com alt texts, labels acessíveis, landmarks e hierarquia correta.
#    - Score BAIXO (≈ 0.0): Existem problemas claros de acessibilidade no HTML (imagens sem alt, inputs sem label, ausência de landmarks, etc.).



def analyze_ethical_regulatory(
    url: str,
    html_text: str = "",
    html_snippet: str = "",
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> dict:
    if not api_key:
        return _neutral_result("API Key não configurada")

    content = html_text or html_snippet or ""
    clean_html = _truncate_html(content, max_chars=7000)

    if not clean_html.strip():
        return _neutral_result("HTML vazio ou não extraível")

    try:
        client = OpenAI(api_key=api_key)
        prompt = _build_improved_prompt(url, clean_html)

        with _LLM_SEMAPHORE:
            _wait_rate_limit()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Você é um avaliador especialista em acessibilidade e dark patterns. Sempre responda com JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=900,
                response_format={"type": "json_object"}
            )

        import json
        data = json.loads(response.choices[0].message.content)

        result = {}
        for key in LLM_INDICATORS:
            val = data.get(key, 0.5)
            result[key] = max(0.0, min(1.0, float(val)))

        result["llm_justificativas"] = data.get("justificativas", {})
        result["llm_status"] = "ok"
        result["llm_erro"] = None
        return result

    except Exception as exc:
        logger.error(f"Erro LLM para {url}: {exc}")
        return _neutral_result(f"Erro: {str(exc)[:120]}")


def _neutral_result(reason: str) -> dict:
    result = {k: 0.5 for k in LLM_INDICATORS}
    result["llm_justificativas"] = {k: reason for k in LLM_INDICATORS}
    result["llm_status"] = "neutro"
    result["llm_erro"] = reason
    return result