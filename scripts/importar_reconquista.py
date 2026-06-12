"""
Importa o arquivo de Reconquista (v2) para o Supabase.

Le a planilha de export (aba `Export`), monta o payload e chama
a RPC `fn_importar_reconquista`, que TRUNCA a tabela `reconquista`
e a realimenta numa unica transacao (resolvendo loja_id e
consultor_id no banco).

Uso:
    python scripts/importar_reconquista.py [caminho/para/reconquista.xlsx]

Requer SUPABASE_URL e SUPABASE_KEY (role service_role) no .env e
as migracoes 028/029/030 aplicadas no Supabase.

NOTA LGPD: a coluna nu_matricula NAO e enviada ao banco.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.supabase_client import get_supabase_client

ARQUIVO_PADRAO = Path(__file__).parent.parent / "reconquista.xlsx"
ABA = "Export"

STATUS_VALIDOS = {"EFETIVADA", "PROMESSA", "SEM RECONQUISTA"}


def _str(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _date(v) -> str | None:
    """Converte para 'AAAA-MM-DD' ou None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    ts = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(ts) else ts.date().isoformat()


def _int(v) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cod_bmg(no_franquia: str | None) -> int | None:
    """Extrai o prefixo numerico de no_franquia ('49925 - HELP! ...')."""
    if not no_franquia:
        return None
    prefixo = no_franquia.split(" - ")[0].strip()
    return int(prefixo) if prefixo.isdigit() else None


def montar_rows(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    vistos: set[int] = set()
    for r in df.itertuples(index=False):
        status = _str(r.de_status_reconquista)
        co_adesao = _int(r.co_adesao)
        if status not in STATUS_VALIDOS or co_adesao is None:
            continue  # rodape / linha invalida
        if co_adesao in vistos:
            continue  # dedup defensivo (mantem a 1a ocorrencia)
        vistos.add(co_adesao)

        no_franquia = _str(r.no_franquia)
        rows.append({
            "co_adesao": co_adesao,
            "status": status,
            "dt_fim_relacionamento": _date(r.dt_fim_relacionamento),
            "dt_macica": _date(r.dt_macica),
            "dt_dna": _date(r.dt_dna),
            "dt_producao": _date(r.dt_producao),
            "subproduto": _str(r.de_subproduto),
            "no_franquia": no_franquia,
            "cod_bmg": _cod_bmg(no_franquia),
            "consultor_nome": _str(r.no_consultor),
            "gerente_regional": _str(r.no_gerente_regional),
            "gerente_loja": _str(r.no_gerente_loja),
            "coordenador_loja": _str(r.no_coordenador_loja),
            "banco_origem": _str(r.de_banco_origem),
            "banco_destino": _str(r.de_banco_destino),
            "saldo_contabil": _num(r.vl_saldo_contabil),
            "dias_atraso": _int(r.qt_dias_atraso),
            "faixa_atraso": _str(r.de_faixa_atraso),
            "tipo_pagamento": _str(r.de_tipo_pagamento),
            "qt_fim_relacionamento": _int(r.qt_fim_relacionamento),
            "link_aceite": _str(r.de_link_aceite),
        })
    return rows


def resumo_mensal(rows: list[dict]) -> pd.DataFrame:
    """Quebra por mes de dt_fim_relacionamento x status (conferencia)."""
    df = pd.DataFrame(rows)
    df["ref"] = df["dt_fim_relacionamento"].str.slice(0, 7)
    piv = pd.crosstab(df["ref"], df["status"], margins=True, margins_name="TOTAL")
    cols = [c for c in ["EFETIVADA", "PROMESSA", "SEM RECONQUISTA", "TOTAL"]
            if c in piv.columns]
    return piv[cols]


def importar(caminho: Path) -> None:
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho}")

    df = pd.read_excel(caminho, sheet_name=ABA)
    rows = montar_rows(df)
    if not rows:
        raise SystemExit("Nenhuma linha valida encontrada no arquivo.")

    print(f"Arquivo: {caminho}")
    print(f"Linhas validas: {len(rows)}\n")
    print("Quebra por mes de dt_fim_relacionamento (conferencia):")
    print(resumo_mensal(rows).to_string(), "\n")

    sb = get_supabase_client()
    resp = sb.rpc("fn_importar_reconquista", {"p_rows": rows}).execute()
    res = resp.data[0] if resp.data else {}

    print("Import concluido (TRUNCATE + carga):")
    print(f"  inseridos     : {res.get('inseridos')}")
    print(f"  sem_loja      : {res.get('sem_loja')}")
    print(f"  sem_consultor : {res.get('sem_consultor')}")
    if res.get("sem_loja") or res.get("sem_consultor"):
        print("  ATENCAO: revisar cod_bmg das lojas / nomes de consultores.")


if __name__ == "__main__":
    arq = Path(sys.argv[1]) if len(sys.argv) > 1 else ARQUIVO_PADRAO
    importar(arq)
