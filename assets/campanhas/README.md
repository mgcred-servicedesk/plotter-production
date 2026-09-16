# Arte das campanhas

Uma pasta por campanha, nomeada com o **slug** dela
(`src/dashboard/kpis/campanha.py` → `Campanha.slug`).

A página descobre os arquivos por **prefixo do nome** — não há nada a
configurar no código. Soltar o arquivo na pasta basta.

| Prefixo | Onde aparece na página |
|---|---|
| `hero.*` | banner de largura total, abrindo a página |
| `lateral*.*` | coluna estreita à direita dos rankings |
| `rodape*.*` | faixa de figuras no fim da página |

Vários `lateral`/`rodape` convivem e entram em **ordem alfabética** —
use `rodape-1.png`, `rodape-2.png`, … para controlar a ordem.

Formatos aceitos: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.svg`.

Só o primeiro `hero.*` é usado. Pasta ausente ou vazia = nenhuma arte
renderizada, sem erro.

## Dimensões sugeridas

- **hero**: 1600×400 px (proporção ~4:1). A página é wide; o Streamlit
  reescala para a largura do container.
- **lateral**: 400 px de largura; altura livre.
- **rodape**: até 4 figuras lado a lado; ~400×300 px cada.
