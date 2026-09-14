"""
Presets da aba de Gestao — leitura E escrita.

Unico modulo do dashboard que ESCREVE no Supabase (insert/update/
delete em `gestao_presets`). Morava em `loaders.py`, que e a camada de
LEITURA: a revisao de 09/2026 apontou a mistura, e a Etapa 2 separou.
A fronteira aqui e leitura x escrita, nao consulta x regra — por isso a
feature inteira (cache, queries e writes) veio junta, em vez de virar
mais um par loader/dominio.

## Seguranca: o recorte e da aplicacao, nao do banco

A chave do dashboard e **service_role**, que tem BYPASSRLS: as policies
da migration 064 nao chegam a rodar. Elas sao rede de seguranca para um
acesso futuro com chave anon. Enquanto isso, quem impede ler ou apagar
preset alheio e o filtro por `usuario_id` dentro de cada query daqui —
e o `_uuid_valido` antes dela, que barra id malformado chegando ao
PostgREST. Ver docs/agents/rls.md.

As tres funcoes publicas seguem importaveis de `loaders` (re-export),
que e de onde `tabs/gestao_consultores.py` ja as importava.
"""

import logging
import uuid

import streamlit as st

from src.config.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def _sb():
    """Atalho para obter o cliente Supabase."""
    return get_supabase_client()


def _uuid_valido(valor: str) -> bool:
    """True quando ``valor`` e um UUID bem formado."""
    try:
        uuid.UUID(str(valor))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


@st.cache_data(ttl=300, show_spinner=False)
def carregar_presets_gestao(usuario_id: str) -> list[dict]:
    """Presets da aba de Gestao visiveis para ``usuario_id``.

    Traz os proprios mais os que outros marcaram como
    ``compartilhado``. O recorte por dono e feito AQUI, na
    aplicacao: a chave do dashboard e service_role (BYPASSRLS), entao
    as policies da migracao 064 nao chegam a rodar — sao rede de
    seguranca para acesso futuro com chave anon. Ver rls.md.

    Retorna lista de dicts ``[id, usuario_id, nome, compartilhado,
    config, proprio]``, ordenada pelos proprios primeiro. TTL 5min;
    mutacoes invalidam via :func:`_invalidar_cache_presets`.
    """
    if not _uuid_valido(usuario_id):
        return []
    resp = (
        _sb()
        .table("gestao_presets")
        .select("id, usuario_id, nome, compartilhado, config")
        # usuario_id vai interpolado no filtro do PostgREST — validado
        # como UUID acima, para que nenhum texto arbitrario da sessao
        # chegue a compor a expressao.
        .or_(f"usuario_id.eq.{usuario_id},compartilhado.is.true")
        .order("nome")
        .execute()
    )
    presets = []
    for row in resp.data or []:
        presets.append({**row, "proprio": row.get("usuario_id") == usuario_id})
    return sorted(presets, key=lambda p: (not p["proprio"], p["nome"]))


def salvar_preset_gestao(
    usuario_id: str,
    nome: str,
    config: dict,
    compartilhado: bool = False,
) -> tuple[bool, str]:
    """Cria ou sobrescreve um preset do proprio usuario.

    Sobrescreve pelo par (usuario_id, nome) — a constraint
    ``uq_gestao_presets_dono_nome``. Salvar com um nome que ja existe
    e uma ATUALIZACAO deliberada; quem chama deve confirmar antes.
    Nunca toca preset de outro dono.
    """
    nome = (nome or "").strip()
    if not _uuid_valido(usuario_id):
        return False, "Sessao sem usuario identificado."
    if not nome:
        return False, "Informe um nome para o preset."
    if len(nome) > 60:
        return False, "Nome muito longo (maximo 60 caracteres)."

    try:
        (
            _sb()
            .table("gestao_presets")
            .upsert(
                {
                    "usuario_id": usuario_id,
                    "nome": nome,
                    "config": config,
                    "compartilhado": bool(compartilhado),
                },
                on_conflict="usuario_id,nome",
            )
            .execute()
        )
    except Exception as exc:
        logger.exception("Falha ao salvar preset de Gestao")
        return False, f"Nao foi possivel salvar o preset: {exc}"

    _invalidar_cache_presets()
    return True, f"Preset '{nome}' salvo."


def excluir_preset_gestao(usuario_id: str, preset_id: str) -> tuple[bool, str]:
    """Apaga um preset, desde que pertenca ao proprio usuario.

    O filtro por ``usuario_id`` na propria query e o que impede apagar
    preset alheio — com service_role a policy de DELETE nao roda.
    """
    if not _uuid_valido(usuario_id) or not _uuid_valido(preset_id):
        return False, "Preset invalido."
    try:
        (
            _sb()
            .table("gestao_presets")
            .delete()
            .eq("id", preset_id)
            .eq("usuario_id", usuario_id)
            .execute()
        )
    except Exception as exc:
        logger.exception("Falha ao excluir preset de Gestao")
        return False, f"Nao foi possivel excluir o preset: {exc}"

    _invalidar_cache_presets()
    return True, "Preset excluido."


def _invalidar_cache_presets() -> None:
    """Invalida o cache de :func:`carregar_presets_gestao`."""
    try:
        carregar_presets_gestao.clear()
    except Exception:
        pass
