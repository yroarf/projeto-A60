"""
analyzer.py — Análise técnica de acessibilidade e dark patterns
Extrai métricas do HTML e retorna resultado estruturado incluindo html_raw.
"""

import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Configurações de requisição ───────────────────────────────────────────────
REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─────────────────────────────────────────────────────────────────────────────
# Fetch — Baixa o HTML da URL
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_html(url: str) -> tuple[str, int, str]:
    """
    Faz a requisição HTTP e retorna (html, status_code, erro).
    Retorna html="" e erro descritivo em caso de falha.
    """
    try:
        resp = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text, resp.status_code, ""
    except requests.exceptions.Timeout:
        return "", 0, f"Timeout após {REQUEST_TIMEOUT}s"
    except requests.exceptions.ConnectionError as e:
        return "", 0, f"Erro de conexão: {str(e)[:80]}"
    except requests.exceptions.HTTPError as e:
        return "", getattr(e.response, "status_code", 0), f"HTTP {e}"
    except Exception as e:
        return "", 0, f"Erro inesperado: {str(e)[:80]}"


# ─────────────────────────────────────────────────────────────────────────────
# Extratores individuais — cada um recebe soup e retorna métricas
# ─────────────────────────────────────────────────────────────────────────────

def _check_lang(soup: BeautifulSoup) -> float:
    """Verifica atributo lang na tag <html>."""
    html_tag = soup.find("html")
    if not html_tag:
        return 0.0
    lang = html_tag.get("lang", "").strip()
    return 1.0 if len(lang) >= 2 else 0.0


def _check_alt_text(soup: BeautifulSoup) -> float:
    """Proporção de imagens com alt text adequado."""
    imgs = soup.find_all("img")
    if not imgs:
        return 1.0  # Sem imagens = sem problema
    with_alt = sum(
        1 for img in imgs
        if img.get("alt") is not None and img.get("alt", "").strip() != ""
    )
    return round(with_alt / len(imgs), 3)


def _check_headings(soup: BeautifulSoup) -> float:
    """Avalia estrutura de headings."""
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if not headings:
        return 0.0

    levels = [int(h.name[1]) for h in headings]
    score = 1.0

    # Penaliza ausência de h1
    if 1 not in levels:
        score -= 0.4

    # Penaliza múltiplos h1
    if levels.count(1) > 1:
        score -= 0.2

    # Penaliza saltos de hierarquia
    jumps = sum(
        1 for i in range(1, len(levels))
        if levels[i] - levels[i - 1] > 1
    )
    score -= min(0.4, jumps * 0.1)

    return max(0.0, round(score, 3))


def _check_form_labels(soup: BeautifulSoup) -> float:
    """Proporção de inputs com label acessível."""
    inputs = [
        inp for inp in soup.find_all(["input", "select", "textarea"])
        if inp.get("type", "text").lower()
        not in ["hidden", "submit", "button", "reset", "image"]
    ]
    if not inputs:
        return 1.0

    label_fors = {
        lbl.get("for") for lbl in soup.find_all("label")
        if lbl.get("for")
    }

    accessible = sum(
        1 for inp in inputs
        if (
            inp.get("id", "") in label_fors
            or inp.get("aria-label")
            or inp.get("aria-labelledby")
            or inp.get("title")
        )
    )
    return round(accessible / len(inputs), 3)


def _check_landmarks(soup: BeautifulSoup) -> float:
    """Verifica presença de landmarks semânticos."""
    landmark_tags  = {"main", "nav", "header", "footer"}
    landmark_roles = {"main", "navigation", "banner", "contentinfo"}

    found_tags  = {t.name for t in soup.find_all(landmark_tags)}
    found_roles = {
        t.get("role") for t in soup.find_all(role=True)
        if t.get("role") in landmark_roles
    }
    found = found_tags | found_roles

    critical = {"main", "nav", "header"}
    present  = len(critical & found)
    return round(present / len(critical), 3)


def _check_zoom(soup: BeautifulSoup) -> float:
    """Verifica se o viewport bloqueia zoom."""
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"viewport", re.I)}):
        content = meta.get("content", "").lower()
        if "user-scalable=no" in content or "user-scalable=0" in content:
            return 0.0
        if "maximum-scale=1" in content:
            return 0.3
    return 1.0


def _check_keyboard_nav(soup: BeautifulSoup) -> float:
    """Detecta barreiras à navegação por teclado."""
    issues = 0

    # tabindex negativos em elementos interativos
    for tag in soup.find_all(tabindex=True):
        try:
            if int(tag.get("tabindex", 0)) < 0:
                issues += 1
        except ValueError:
            pass

    # Divs clicáveis sem role ou tabindex
    for tag in soup.find_all(onclick=True):
        if tag.name in ["div", "span"]:
            if not tag.get("role") and not tag.get("tabindex"):
                issues += 1

    return max(0.0, round(1 - issues / max(issues + 5, 10), 3))


def _check_font_size(soup: BeautifulSoup) -> float:
    """Detecta fontes muito pequenas em estilos inline."""
    _re = re.compile(r"font-size\s*:\s*([0-9.]+)(px|pt|rem|em)", re.I)
    small_count = 0
    total_count = 0

    for tag in soup.find_all(style=True):
        for m in _re.finditer(tag.get("style", "")):
            total_count += 1
            size, unit = float(m.group(1)), m.group(2).lower()
            px = size * {"px": 1, "pt": 1.333, "rem": 16, "em": 16}.get(unit, 1)
            if px < 14:
                small_count += 1

    if total_count == 0:
        return 1.0
    return round(1 - small_count / total_count, 3)


def _check_video_captions(soup: BeautifulSoup) -> float:
    """Verifica legendas em elementos de vídeo."""
    videos = soup.find_all("video")
    iframes = [
        f for f in soup.find_all("iframe")
        if any(p in f.get("src", "")
               for p in ["youtube", "vimeo", "youtu.be"])
    ]
    total = len(videos) + len(iframes)
    if total == 0:
        return 1.0

    ok = 0
    for v in videos:
        tracks = v.find_all(
            "track",
            kind=lambda k: k in ["captions", "subtitles"] if k else False
        )
        if tracks:
            ok += 1
    # Iframes de vídeo com title são parcialmente acessíveis
    for iframe in iframes:
        if iframe.get("title"):
            ok += 1

    return round(ok / total, 3)


def _check_contrast_heuristic(soup: BeautifulSoup) -> float:
    """Heurística de baixo contraste via estilos inline."""
    _suspect = {
        "#999", "#aaa", "#bbb", "#ccc", "#ddd", "#eee",
        "lightgray", "silver", "gray",
    }
    issues = 0
    for tag in soup.find_all(style=True):
        style = tag.get("style", "").lower()
        if any(c in style for c in _suspect):
            issues += 1

    return max(0.0, round(1 - issues / max(issues + 10, 20), 3))


# ─────────────────────────────────────────────────────────────────────────────
# Função principal — analyze_technical
# ─────────────────────────────────────────────────────────────────────────────

def analyze_technical(url: str) -> dict:
    """
    Analisa indicadores técnicos de acessibilidade de uma URL.

    Retorna dict com:
      - Scores por indicador (0.0 a 1.0)
      - Metadados da requisição
      - html_raw: HTML bruto completo (usado pelo evidence_extractor)
      - html_snippet: trecho resumido (usado pelo llm_analyzer)
      - erro: descrição do erro, se houver
    """
    start = time.time()

    # ── 1. Fetch do HTML ──────────────────────────────────────────────────────
    html, status_code, fetch_error = _fetch_html(url)

    # ── 2. Resultado base — preenchido mesmo em caso de erro ──────────────────
    result = {
        # Metadados
        "url":          url,
        "status_code":  status_code,
        "tempo_coleta": round(time.time() - start, 2),
        "erro":         fetch_error or None,

        # HTML — disponível para outros módulos
        "html_raw":     html,           # ← HTML completo para evidence_extractor
        "html_snippet": html[:15_000],  # ← Trecho para llm_analyzer

        # Scores técnicos — default 0.5 (neutro) se não foi possível analisar
        "lang_attr":              0.5,
        "alt_text":               0.5,
        "headings":               0.5,
        "labels_formularios":     0.5,
        "landmarks":              0.5,
        "zoom_reflow":            0.5,
        "navegabilidade_teclado": 0.5,
        "font_size":              0.5,
        "legendas_video":         0.5,
        "contraste":              0.5,
    }

    # ── 3. Se fetch falhou, retorna resultado com scores neutros ──────────────
    if not html:
        logger.warning(f"HTML vazio para {url}: {fetch_error}")
        return result

    # ── 4. Parsing do HTML ────────────────────────────────────────────────────
    try:
        # soup = BeautifulSoup(html, "html.parser")
        soup = BeautifulSoup(html, "lxml")

    except Exception as e:
        logger.error(f"Erro ao parsear HTML de {url}: {e}")
        result["erro"] = f"Erro de parsing: {e}"
        return result

    # ── 5. Executa todos os extratores e atualiza os scores ───────────────────
    #
    # Cada extrator é independente — um erro em um não afeta os outros.
    # Os scores substituem os valores neutros (0.5) definidos acima.
    #
    extractors = {
        "lang_attr":              _check_lang,
        "alt_text":               _check_alt_text,
        "headings":               _check_headings,
        "labels_formularios":     _check_form_labels,
        "landmarks":              _check_landmarks,
        "zoom_reflow":            _check_zoom,
        "navegabilidade_teclado": _check_keyboard_nav,
        "font_size":              _check_font_size,
        "legendas_video":         _check_video_captions,
        "contraste":              _check_contrast_heuristic,
    }

    for key, extractor_fn in extractors.items():
        try:
            result[key] = extractor_fn(soup)
        except Exception as e:
            logger.warning(f"Extrator '{key}' falhou para {url}: {e}")
            # Mantém o valor neutro (0.5) já definido no result base

    # ── 6. Tempo total ────────────────────────────────────────────────────────
    result["tempo_coleta"] = round(time.time() - start, 2)

    return result