"""
csv_loader.py — Leitura robusta de arquivos CSV ou JSON exportados por planilhas.
Suporta:
  - CSV padrão (url,nome_site,tipo,cidade)
  - JSON no formato Sheet Export: [{"s":..., "k":[cols], "d":[[rows]]}]
  - JSON simples: [{"url": "...", ...}]
  - Excel (.xlsx) — bônus
"""

import io
import json
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Detectores de formato
# ─────────────────────────────────────────────────────────────────────────────

def _is_sheet_export_json(content: str) -> bool:
    """Detecta o formato [{"s":..., "k":[...], "d":[[...]]}]."""
    stripped = content.strip()
    return (
        stripped.startswith("[")
        and '"k"' in stripped
        and '"d"' in stripped
    )


def _is_json_array(content: str) -> bool:
    """Detecta JSON array simples de objetos."""
    stripped = content.strip()
    return stripped.startswith("[{") or stripped.startswith("[ {")


# ─────────────────────────────────────────────────────────────────────────────
# Parsers por formato
# ─────────────────────────────────────────────────────────────────────────────

def _parse_sheet_export(content: str) -> pd.DataFrame:
    """
    Parseia o formato exportado por planilhas:
    [{"s": "Sheet1", "k": ["col1","col2",...], "d": [["val1","val2",...], ...]}]
    """
    data = json.loads(content)

    if not isinstance(data, list) or not data:
        raise ValueError("JSON vazio ou formato inesperado.")

    sheet = data[0]  # Usa a primeira aba
    columns = sheet.get("k", [])
    rows    = sheet.get("d", [])

    if not columns:
        raise ValueError("Nenhuma coluna encontrada em 'k'.")
    if not rows:
        raise ValueError("Nenhuma linha encontrada em 'd'.")

    df = pd.DataFrame(rows, columns=columns)
    logger.info(f"Sheet Export JSON: {len(df)} linhas, colunas: {list(df.columns)}")
    return df


def _parse_json_array(content: str) -> pd.DataFrame:
    """Parseia JSON array simples: [{"url": "...", "nome_site": "..."}, ...]"""
    data = json.loads(content)
    df = pd.DataFrame(data)
    logger.info(f"JSON Array: {len(df)} linhas, colunas: {list(df.columns)}")
    return df


def _parse_csv(content: str, filename: str = "") -> pd.DataFrame:
    """Parseia CSV padrão com detecção automática de separador."""
    # Tenta detectar separador
    separators = [",", ";", "\t", "|"]
    first_line = content.split("\n")[0] if content else ""

    sep = ","
    for s in separators:
        if s in first_line:
            sep = s
            break

    df = pd.read_csv(io.StringIO(content), sep=sep)
    logger.info(f"CSV ({sep!r}): {len(df)} linhas, colunas: {list(df.columns)}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Validação e normalização do DataFrame
# ─────────────────────────────────────────────────────────────────────────────

# Possíveis nomes para a coluna de URL
_URL_COLUMN_ALIASES = ["url", "URL", "link", "Link", "endereco", "endereço", "site"]

# Possíveis nomes para colunas opcionais
_NAME_ALIASES   = ["nome_site", "nome", "name", "site", "título", "titulo"]
_TYPE_ALIASES   = ["tipo", "type", "categoria", "category"]
_CITY_ALIASES   = ["cidade", "city", "municipio", "município", "local"]


def _find_column(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    """Retorna o primeiro nome de coluna que bate com os aliases."""
    for alias in aliases:
        if alias in df.columns:
            return alias
    return None


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza o DataFrame:
    - Renomeia colunas para nomes padrão
    - Remove linhas sem URL válida
    - Preenche colunas opcionais ausentes com ""
    - Limpa espaços extras
    """
    # ── Coluna URL (obrigatória) ──────────────────────────────────────────────
    url_col = _find_column(df, _URL_COLUMN_ALIASES)
    if url_col is None:
        raise ValueError(
            f"Coluna de URL não encontrada. "
            f"Colunas disponíveis: {list(df.columns)}. "
            f"Nomes aceitos: {_URL_COLUMN_ALIASES}"
        )
    if url_col != "url":
        df = df.rename(columns={url_col: "url"})

    # ── Colunas opcionais ─────────────────────────────────────────────────────
    for target, aliases in [
        ("nome_site", _NAME_ALIASES),
        ("tipo",      _TYPE_ALIASES),
        ("cidade",    _CITY_ALIASES),
    ]:
        col = _find_column(df, aliases)
        if col and col != target:
            df = df.rename(columns={col: target})
        if target not in df.columns:
            df[target] = ""

    # ── Limpeza ───────────────────────────────────────────────────────────────
    df["url"] = df["url"].astype(str).str.strip()

    # Remove linhas sem URL ou com URL inválida
    df = df[
        df["url"].notna()
        & (df["url"] != "")
        & (df["url"] != "nan")
        & df["url"].str.startswith("http")
    ].copy()

    # Preenche NaN nas colunas opcionais
    for col in ["nome_site", "tipo", "cidade"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    df = df.reset_index(drop=True)
    logger.info(f"DataFrame normalizado: {len(df)} URLs válidas.")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Função pública principal
# ─────────────────────────────────────────────────────────────────────────────

def load_urls_from_file(uploaded_file) -> tuple[pd.DataFrame, str]:
    """
    Carrega URLs de um arquivo enviado pelo Streamlit (UploadedFile).

    Suporta: CSV padrão, JSON Sheet Export, JSON Array, Excel.

    Retorna:
        (DataFrame normalizado, mensagem de status)

    Lança:
        ValueError com mensagem amigável em caso de erro.
    """
    filename = getattr(uploaded_file, "name", "arquivo")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    try:
        # ── Excel ─────────────────────────────────────────────────────────────
        if extension in ("xlsx", "xls"):
            df_raw = pd.read_excel(uploaded_file)
            msg = f"Excel lido: {len(df_raw)} linhas."

        else:
            # Lê como texto
            raw_bytes = uploaded_file.read()
            content = raw_bytes.decode("utf-8", errors="replace")

            # ── JSON Sheet Export ─────────────────────────────────────────────
            if _is_sheet_export_json(content):
                df_raw = _parse_sheet_export(content)
                msg = f"Formato JSON (Sheet Export) detectado: {len(df_raw)} linhas."

            # ── JSON Array simples ────────────────────────────────────────────
            elif _is_json_array(content):
                df_raw = _parse_json_array(content)
                msg = f"Formato JSON Array detectado: {len(df_raw)} linhas."

            # ── CSV padrão ────────────────────────────────────────────────────
            else:
                df_raw = _parse_csv(content, filename)
                msg = f"Formato CSV detectado: {len(df_raw)} linhas."

        # ── Normalização ──────────────────────────────────────────────────────
        df = _normalize_dataframe(df_raw)

        if df.empty:
            raise ValueError(
                "Nenhuma URL válida encontrada após leitura. "
                "Verifique se a coluna 'url' contém endereços começando com 'http'."
            )

        return df, f"✅ {msg} → {len(df)} URLs válidas carregadas."

    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Erro ao decodificar arquivo '{filename}': {e}") from e
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Erro inesperado ao ler '{filename}': {e}") from e
