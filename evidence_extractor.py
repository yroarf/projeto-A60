"""
Evidence Extractor — Extração precisa de evidências HTML por indicador.
Inclui filtragem de elementos administrativos (drag handles, portlet controls, etc.)
para reduzir falsos positivos em portais corporativos.
"""

import re
from typing import Optional
from bs4 import BeautifulSoup, Tag


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tag_str(tag, max_len: int = 200) -> str:
    """Serializa uma tag para string truncada."""
    s = str(tag)
    return s[:max_len] + ("…" if len(s) > max_len else "")


def _find_all_str(soup: BeautifulSoup, *tags, **attrs) -> list[str]:
    found = soup.find_all(*tags, **attrs)
    return [_tag_str(t) for t in found]


# ─────────────────────────────────────────────────────────────────────────────
# Filtro de Elementos Administrativos (NOVO)
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_CLASSES = {
    "dndHandle", "dragHandle", "portletDrag", "drag-icon",
    "adminOnly", "edit-mode", "wpAdmin", "control-bar"
}

def _is_administrative_element(tag: Tag) -> bool:
    """
    Detecta se o elemento pertence à interface administrativa do portal
    (ex: drag handles do WebSphere Portal, controles de edição, etc.).
    """
    if not tag:
        return False

    # 1. Verifica classes administrativas conhecidas
    classes = tag.get("class", [])
    if isinstance(classes, str):
        classes = classes.split()
    if any(cls in ADMIN_CLASSES for cls in classes):
        return True

    # 2. Verifica eventos de drag do WebSphere Portal
    ondragstart = tag.get("ondragstart", "")
    if "wpModules.dnd" in str(ondragstart):
        return True

    # 3. Verifica se está explicitamente escondido ou marcado como não interativo para usuários
    aria_hidden = tag.get("aria-hidden", "").lower()
    if aria_hidden == "true":
        return True

    # 4. Verifica se tem estilo que esconde o elemento (básico)
    style = tag.get("style", "").lower().replace(" ", "")
    if "display:none" in style or "visibility:hidden" in style:
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. ALT TEXT — Imagens sem atributo alt ou com alt vazio
# ─────────────────────────────────────────────────────────────────────────────

def extract_alt_text_issues(soup: BeautifulSoup) -> dict:
    """Identifica imagens sem alt text adequado (ignorando elementos administrativos)."""
    imgs = soup.find_all("img")
    issues = []

    for img in imgs:
        # === NOVO: Ignora elementos administrativos ===
        if _is_administrative_element(img):
            continue

        alt = img.get("alt")
        src = img.get("src", "")[:80]

        if alt is None:
            issues.append({
                "tipo": "img_sem_alt",
                "elemento": _tag_str(img),
                "detalhe": f"Imagem sem atributo alt: src='{src}'",
            })
        elif alt.strip() == "":
            issues.append({
                "tipo": "img_alt_vazio",
                "elemento": _tag_str(img),
                "detalhe": f"Imagem com alt vazio (decorativa?): src='{src}'",
            })

    return {
        "total_imgs": len(imgs),
        "total_sem_alt": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / max(len(imgs), 1)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. CONTRASTE — Detecção heurística de estilos inline suspeitos
# ─────────────────────────────────────────────────────────────────────────────

_LOW_CONTRAST_COLORS = {
    "color:white;background:white", "color:#fff;background:#fff",
    "color:gray;background:white", "color:#999", "color:#aaa",
    "color:#bbb", "color:#ccc", "color:#ddd", "color:#eee",
    "color:lightgray", "color:silver", "font-size:8px",
    "font-size:9px", "font-size:10px",
}

def extract_contrast_issues(soup: BeautifulSoup) -> dict:
    """Detecta estilos inline com potencial baixo contraste (ignorando admin)."""
    issues = []
    for tag in soup.find_all(style=True):
        # === NOVO: Ignora elementos administrativos ===
        if _is_administrative_element(tag):
            continue

        style = tag.get("style", "").lower().replace(" ", "")
        for suspect in _LOW_CONTRAST_COLORS:
            if suspect.replace(" ", "") in style:
                issues.append({
                    "tipo": "contraste_suspeito",
                    "elemento": _tag_str(tag),
                    "detalhe": f"Estilo suspeito detectado: '{suspect}'",
                })
                break

    return {
        "total_com_style": len(soup.find_all(style=True)),
        "total_suspeitos": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / 20),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. NAVEGABILIDADE POR TECLADO
# ─────────────────────────────────────────────────────────────────────────────

def extract_keyboard_issues(soup: BeautifulSoup) -> dict:
    """Detecta elementos que bloqueiam navegação por teclado."""
    issues = []

    for tag in soup.find_all(tabindex=True):
        if _is_administrative_element(tag):
            continue
        try:
            if int(tag.get("tabindex", 0)) < 0:
                issues.append({
                    "tipo": "tabindex_negativo",
                    "elemento": _tag_str(tag),
                    "detalhe": f"tabindex negativo bloqueia foco: tabindex={tag.get('tabindex')}",
                })
        except ValueError:
            pass

    for tag in soup.find_all(onclick=True):
        if _is_administrative_element(tag):
            continue
        if tag.name in ["div", "span"] and not tag.get("role") and not tag.get("tabindex"):
            issues.append({
                "tipo": "div_onclick_sem_role",
                "elemento": _tag_str(tag),
                "detalhe": "Elemento clicável sem role ou tabindex — inacessível por teclado",
            })

    return {
        "total_issues": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / 15),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. LABELS DE FORMULÁRIOS
# ─────────────────────────────────────────────────────────────────────────────

def extract_form_label_issues(soup: BeautifulSoup) -> dict:
    """Detecta campos de formulário sem label associado."""
    issues = []
    label_fors = {lbl.get("for") for lbl in soup.find_all("label") if lbl.get("for")}

    for inp in soup.find_all(["input", "select", "textarea"]):
        if _is_administrative_element(inp):
            continue

        inp_type = inp.get("type", "text").lower()
        if inp_type in ["hidden", "submit", "button", "reset", "image"]:
            continue

        inp_id = inp.get("id", "")
        has_label = (
            inp_id in label_fors
            or inp.get("aria-label")
            or inp.get("aria-labelledby")
            or inp.get("title")
            or inp.get("placeholder")
        )
        if not has_label:
            issues.append({
                "tipo": "input_sem_label",
                "elemento": _tag_str(inp),
                "detalhe": f"Campo '{inp.name}' (type={inp_type}) sem label acessível",
            })

    return {
        "total_inputs": len(soup.find_all(["input", "select", "textarea"])),
        "total_issues": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / 10),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. HEADINGS
# ─────────────────────────────────────────────────────────────────────────────

def extract_heading_issues(soup: BeautifulSoup) -> dict:
    """Detecta problemas na hierarquia de headings."""
    issues = []
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    levels = [int(h.name[1]) for h in headings]

    if not headings:
        issues.append({
            "tipo": "sem_headings",
            "elemento": "<body>",
            "detalhe": "Página sem nenhum heading (h1-h6) — sem estrutura semântica",
        })
    else:
        if levels.count(1) == 0:
            issues.append({
                "tipo": "sem_h1",
                "elemento": str(headings[0])[:100],
                "detalhe": "Página sem h1 — falta título principal",
            })
        if levels.count(1) > 1:
            issues.append({
                "tipo": "multiplos_h1",
                "elemento": str(headings[0])[:100],
                "detalhe": f"Múltiplos h1 encontrados: {levels.count(1)} ocorrências",
            })
        for i in range(1, len(levels)):
            if levels[i] - levels[i - 1] > 1:
                issues.append({
                    "tipo": "salto_hierarquia",
                    "elemento": _tag_str(headings[i]),
                    "detalhe": f"Salto de h{levels[i-1]} para h{levels[i]} — hierarquia quebrada",
                })

    return {
        "total_headings": len(headings),
        "sequencia": levels[:20],
        "total_issues": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / 5),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. LANG ATTRIBUTE
# ─────────────────────────────────────────────────────────────────────────────

def extract_lang_issues(soup: BeautifulSoup) -> dict:
    """Verifica atributo lang na tag html."""
    issues = []
    html_tag = soup.find("html")
    if not html_tag:
        issues.append({
            "tipo": "sem_tag_html",
            "elemento": "",
            "detalhe": "Tag <html> não encontrada",
        })
    else:
        lang = html_tag.get("lang", "").strip()
        if not lang:
            issues.append({
                "tipo": "lang_ausente",
                "elemento": _tag_str(html_tag)[:100],
                "detalhe": "Atributo lang ausente na tag <html>",
            })
        elif len(lang) < 2:
            issues.append({
                "tipo": "lang_invalido",
                "elemento": _tag_str(html_tag)[:100],
                "detalhe": f"Valor de lang inválido: '{lang}'",
            })

    return {
        "lang_detectado": html_tag.get("lang", "") if html_tag else "",
        "total_issues": len(issues),
        "issues": issues,
        "score_estimado": 0.0 if issues else 1.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. LANDMARKS
# ─────────────────────────────────────────────────────────────────────────────

_LANDMARK_TAGS = {"main", "nav", "header", "footer", "aside", "section", "article"}
_LANDMARK_ROLES = {"main", "navigation", "banner", "contentinfo", "complementary",
                   "search", "form", "region"}

def extract_landmark_issues(soup: BeautifulSoup) -> dict:
    """Detecta ausência de landmarks semânticos."""
    issues = []
    found_tags = {t.name for t in soup.find_all(_LANDMARK_TAGS)}
    found_roles = {t.get("role") for t in soup.find_all(role=True)
                   if t.get("role") in _LANDMARK_ROLES}
    all_landmarks = found_tags | found_roles

    critical = ["main", "nav", "header"]
    for lm in critical:
        if lm not in all_landmarks and lm not in found_roles:
            issues.append({
                "tipo": f"landmark_{lm}_ausente",
                "elemento": "<body>",
                "detalhe": f"Landmark <{lm}> ou role='{lm}' não encontrado",
            })

    return {
        "landmarks_encontrados": list(all_landmarks),
        "total_issues": len(issues),
        "issues": issues,
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. LEGENDAS DE VÍDEO
# ─────────────────────────────────────────────────────────────────────────────

def extract_video_caption_issues(soup: BeautifulSoup) -> dict:
    """Detecta vídeos sem legendas."""
    issues = []
    videos = soup.find_all("video")
    iframes = [f for f in soup.find_all("iframe")
               if any(p in f.get("src", "") for p in
                      ["youtube", "vimeo", "youtu.be", "dailymotion"])]

    for v in videos:
        if _is_administrative_element(v):
            continue
        tracks = v.find_all("track", kind=lambda k: k in ["captions", "subtitles"] if k else False)
        if not tracks:
            issues.append({
                "tipo": "video_sem_legenda",
                "elemento": _tag_str(v),
                "detalhe": "Elemento <video> sem <track kind='captions'> ou <track kind='subtitles'>",
            })

    for iframe in iframes:
        if _is_administrative_element(iframe):
            continue
        title = iframe.get("title", "")
        if not title:
            issues.append({
                "tipo": "iframe_video_sem_title",
                "elemento": _tag_str(iframe),
                "detalhe": f"Iframe de vídeo sem atributo title: src='{iframe.get('src','')[:60]}'",
            })

    return {
        "total_videos": len(videos) + len(iframes),
        "total_issues": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else 0.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. ZOOM / REFLOW
# ─────────────────────────────────────────────────────────────────────────────

def extract_zoom_issues(soup: BeautifulSoup) -> dict:
    """Detecta bloqueio de zoom no viewport."""
    issues = []
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"viewport", re.I)}):
        content = meta.get("content", "").lower()
        if "user-scalable=no" in content or "user-scalable=0" in content:
            issues.append({
                "tipo": "zoom_bloqueado",
                "elemento": _tag_str(meta),
                "detalhe": "viewport com user-scalable=no — bloqueia zoom para idosos",
            })
        if "maximum-scale=1" in content:
            issues.append({
                "tipo": "zoom_limitado",
                "elemento": _tag_str(meta),
                "detalhe": "viewport com maximum-scale=1 — limita zoom severamente",
            })

    return {
        "total_issues": len(issues),
        "issues": issues,
        "score_estimado": 0.0 if issues else 1.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. URGÊNCIA ARTIFICIAL
# ─────────────────────────────────────────────────────────────────────────────

_URGENCY_PATTERNS = [
    r"(últimas?\s+\d+\s+unidades?)",
    r"(oferta\s+expira)",
    r"(restam\s+apenas\s+\d+)",
    r"(só\s+hoje|somente\s+hoje)",
    r"(corra\s*[,!]|aproveite\s+agora)",
    r"(promoção\s+por\s+tempo\s+limitado)",
    r"(\d+\s+pessoas?\s+(estão?\s+vendo|visitando))",
    r"(compre\s+agora\s+antes\s+que\s+acabe)",
    r"(timer|countdown|contagem\s+regressiva)",
    r"(flash\s+sale|relâmpago)",
]

def extract_urgency_issues(soup: BeautifulSoup) -> dict:
    """Detecta padrões de urgência artificial no texto."""
    issues = []
    text = soup.get_text(separator=" ", strip=True).lower()

    for pattern in _URGENCY_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches[:2]:
                match_str = match if isinstance(match, str) else match[0]
                for tag in soup.find_all(string=re.compile(re.escape(match_str), re.I)):
                    parent = tag.parent
                    if parent and not _is_administrative_element(parent):
                        issues.append({
                            "tipo": "urgencia_artificial",
                            "elemento": _tag_str(parent),
                            "detalhe": f"Padrão de urgência detectado: '{match_str}'",
                        })
                        break

    return {
        "total_issues": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / 5),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. CONFIRMSHAMING
# ─────────────────────────────────────────────────────────────────────────────

_CONFIRMSHAMING_PATTERNS = [
    r"(não,?\s+prefiro\s+pagar\s+mais)",
    r"(não,?\s+prefiro\s+ficar\s+ignorante)",
    r"(não,?\s+não\s+quero\s+(economizar|desconto|oferta))",
    r"(obrigado,?\s+não\s+preciso\s+de)",
    r"(prefiro\s+(perder|desperdiçar|pagar\s+mais))",
    r"(não,?\s+estou\s+bem\s+sem)",
    r"(dispensar|recusar)\s+(essa\s+)?(oferta|vantagem|benefício)",
]

def extract_confirmshaming_issues(soup: BeautifulSoup) -> dict:
    """Detecta botões/links com linguagem de confirmshaming."""
    issues = []
    text_full = soup.get_text(separator=" ", strip=True)

    for pattern in _CONFIRMSHAMING_PATTERNS:
        matches = re.findall(pattern, text_full, re.IGNORECASE)
        if matches:
            for match in matches[:2]:
                match_str = match if isinstance(match, str) else match[0]
                for tag in soup.find_all(["button", "a", "span", "label"],
                                          string=re.compile(re.escape(match_str[:20]), re.I)):
                    if not _is_administrative_element(tag):
                        issues.append({
                            "tipo": "confirmshaming",
                            "elemento": _tag_str(tag),
                            "detalhe": f"Texto constrangedor detectado: '{match_str[:80]}'",
                        })
                        break

    return {
        "total_issues": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else 0.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 12. FONT SIZE
# ─────────────────────────────────────────────────────────────────────────────

_SMALL_FONT_RE = re.compile(
    r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)(px|pt|rem|em)", re.I
)

def extract_font_size_issues(soup: BeautifulSoup) -> dict:
    """Detecta fontes muito pequenas em estilos inline."""
    issues = []
    for tag in soup.find_all(style=True):
        if _is_administrative_element(tag):
            continue

        style = tag.get("style", "")
        for m in _SMALL_FONT_RE.finditer(style):
            size = float(m.group(1))
            unit = m.group(2).lower()
            px_approx = size
            if unit == "pt":
                px_approx = size * 1.333
            elif unit == "rem" or unit == "em":
                px_approx = size * 16

            if px_approx < 14:
                issues.append({
                    "tipo": "fonte_muito_pequena",
                    "elemento": _tag_str(tag),
                    "detalhe": f"Fonte de {size}{unit} (~{px_approx:.0f}px) — abaixo do mínimo recomendado (16px) para idosos",
                })

    return {
        "total_issues": len(issues),
        "issues": issues[:10],
        "score_estimado": 1.0 if not issues else max(0.0, 1 - len(issues) / 10),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL — Extrai TODAS as evidências
# ─────────────────────────────────────────────────────────────────────────────

def extract_all_evidence(url: str, html: str) -> dict:
    """
    Extrai evidências HTML precisas para todos os indicadores.
    Retorna dict com issues por indicador.
    """
    if not html or not html.strip():
        return {"erro": "HTML vazio ou não disponível"}

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        return {"erro": f"Erro ao parsear HTML: {e}"}

    evidence = {
        "url": url,
        "alt_text":               extract_alt_text_issues(soup),
        "contraste":              extract_contrast_issues(soup),
        "navegabilidade_teclado": extract_keyboard_issues(soup),
        "labels_formularios":     extract_form_label_issues(soup),
        "headings":               extract_heading_issues(soup),
        "lang_attr":              extract_lang_issues(soup),
        "landmarks":              extract_landmark_issues(soup),
        "legendas_video":         extract_video_caption_issues(soup),
        "zoom_reflow":            extract_zoom_issues(soup),
        "urgencia_artificial":    extract_urgency_issues(soup),
        "confirmshaming":         extract_confirmshaming_issues(soup),
        "font_size":              extract_font_size_issues(soup),
    }

    total_issues = sum(
        v.get("total_issues", 0)
        for k, v in evidence.items()
        if isinstance(v, dict) and k != "url"
    )
    evidence["total_issues_geral"] = total_issues

    return evidence