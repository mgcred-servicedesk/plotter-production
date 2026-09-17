# Arte das campanhas

Uma pasta por campanha, nomeada com o **slug** dela
(`src/dashboard/kpis/campanha.py` → `Campanha.slug`).

A página descobre os arquivos por **prefixo do nome** — não há nada a
configurar no código. Soltar o arquivo na pasta basta.

| Prefixo | Onde aparece na página |
|---|---|
| `hero*.*` | faixa do cabeçalho, abrindo a página |
| `rodape*.*` | faixa no fim da página |
| `lateral*.*` | coluna estreita à direita dos rankings |

Vários arquivos do mesmo prefixo convivem e entram **em colunas de
largura igual**, na ordem alfabética do nome — use `hero-1.png`,
`hero-2.png`, … para controlar a ordem.

Formatos aceitos: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.svg`.
Pasta ausente ou vazia = nenhuma arte renderizada, sem erro.

## Proporção: o que realmente importa

`width="stretch"` iguala a **largura**, não a altura. Duas peças de
proporções diferentes na mesma faixa saem com alturas diferentes — a
mais "quadrada" fica visivelmente maior.

Por isso as peças de uma mesma faixa devem **compartilhar a
proporção**. A convenção adotada na Semestral 2026-H2: moldura
transparente de **1078×422** (≈2,55:1, a proporção da arte do prêmio),
com o conteúdo escalado para caber e centralizado.

Para normalizar uma peça nova nesse padrão:

```python
from PIL import Image

CANVAS = (1078, 422)
im = Image.open("nova.png").convert("RGBA")
corte = im.crop(im.getchannel("A").getbbox())      # tira o vão transparente
escala = min(CANVAS[0] / corte.width, CANVAS[1] / corte.height)
novo = (round(corte.width * escala), round(corte.height * escala))
corte = corte.resize(novo, Image.LANCZOS)

moldura = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
moldura.paste(corte, ((CANVAS[0] - novo[0]) // 2,
                      (CANVAS[1] - novo[1]) // 2), corte)
moldura.save("hero-3.png", optimize=True)
```

O recorte pelo bbox do alpha é importante: as peças originais são
1080×1350 (formato de social) com o conteúdo ocupando só 31–42% da
altura. Sem cortar, cada figura carregaria ~60% de vão transparente.

## Fundo transparente

Mantenha PNG com alpha. O dashboard tem tema claro e escuro; peça com
fundo branco chapado fica com uma caixa branca no tema escuro.
