"""
Matriz de permissoes de UI por perfil de usuario.

Centraliza as decisoes de "quem ve o que" no dashboard.
Usado pelas abas e componentes para ocultar/exibir
elementos conforme o perfil efetivo (considera
'visualizar como' do admin).

Elementos (keys):
    tab_produtos          Aba Produtos (visao agregada)
    tab_regioes           Aba Regioes
    tab_rankings_lojas    Rankings globais de lojas
    tab_rankings_cons     Rankings de consultores
    tab_analiticos        Analiticos (heatmap, distribuicao)
    tab_evolucao          Evolucao temporal
    tab_em_analise        Pipeline em analise
    tab_detalhes          Tabela detalhada
    tab_consultor         Dashboard individual do consultor
    cards_gerenciais      Cards agregados (num consultores,
                          ticket medio/consultor etc.)
    cards_consultor       Cards pessoais (meus pagos,
                          meus pontos, minha meta etc.)
    visualizar_como       Seletor 'Visualizar Como'
    gestao_usuarios       Pagina de gestao de usuarios
"""

from typing import Optional

# ── Matriz de visibilidade ───────────────────────────
# True  = perfil ve o elemento
# False = perfil NAO ve o elemento
MATRIZ: dict[str, dict[str, bool]] = {
    # Abas principais
    "tab_produtos":       {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": True,
        "consultor": False,
    },
    "tab_regioes":        {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": False,
        "consultor": False,
    },
    "tab_rankings_lojas": {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": False,
        "consultor": False,
    },
    "tab_rankings_cons":  {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": True,
        "consultor": True,
    },
    "tab_analiticos":     {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": True,
        "consultor": False,
    },
    "tab_evolucao":       {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": True,
        "consultor": True,
    },
    "tab_em_analise":     {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": True,
        "consultor": True,
    },
    "tab_detalhes":       {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": True,
        "consultor": True,
    },
    "tab_consultor":      {
        "admin": False, "gestor": False,
        "gerente_comercial": False, "supervisor": False,
        "consultor": True,
    },
    # Grupos de cards
    "cards_gerenciais":   {
        "admin": True, "gestor": True,
        "gerente_comercial": True, "supervisor": True,
        "consultor": False,
    },
    "cards_consultor":    {
        "admin": False, "gestor": False,
        "gerente_comercial": False, "supervisor": False,
        "consultor": True,
    },
    # Ferramentas
    "visualizar_como":    {
        "admin": True, "gestor": False,
        "gerente_comercial": False, "supervisor": False,
        "consultor": False,
    },
    "gestao_usuarios":    {
        "admin": True, "gestor": False,
        "gerente_comercial": False, "supervisor": False,
        "consultor": False,
    },
}


def pode_ver(elemento: str, perfil: Optional[str]) -> bool:
    """
    Retorna True se o perfil pode ver o elemento.

    Args:
        elemento: Chave em MATRIZ (ex: 'tab_regioes').
        perfil: Papel do usuario efetivo (admin, gestor,
            gerente_comercial, supervisor, consultor).
            None trata como sem acesso.

    Returns:
        True se autorizado. Se elemento nao existir em
        MATRIZ, retorna False (fail-closed).
    """
    if not perfil:
        return False
    return MATRIZ.get(elemento, {}).get(perfil, False)


def abas_visiveis(perfil: Optional[str]) -> list[str]:
    """
    Retorna lista de chaves de aba (tab_*) visiveis
    para o perfil, na ordem definida em MATRIZ.
    """
    return [
        chave for chave in MATRIZ
        if chave.startswith("tab_") and pode_ver(chave, perfil)
    ]
