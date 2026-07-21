# ADR 002: Estratégia de Matching de Ingredientes (Cascata de Confiança)
> Última revisão: 2026-07-21 02:38 UTC

**Status**: Aceito
**Data**: 27/06/2026
**Contexto**: A maior dificuldade do projeto é associar nomes de produtos brutos (ex: "Leite Condensado Moça 395g") a ingredientes canônicos (ex: "Leite Condensado Integral").

## Decisão
Implementação de um pipeline de matching em cascata, onde cada estágio aumenta a complexidade e o custo computacional:

1. **Match Exato**: Verifica se o nome canônico ou um alias está presente literalmente. (Confiança: 1.0)
2. **Match por Subconjunto**: Verifica se todas as palavras do canônico estão no produto. (Confiança: 1.0)
3. **Match Fuzzy (RapidFuzz)**: Usa `token_set_ratio` para lidar com typos e inversões. Threshold $\ge 80\%$. (Confiança: 0.8 - 1.0)
4. **Semantic Blend (ONNX)**: Combina RapidFuzz (60%) com Cosseno de Embeddings (40%) usando MiniLM-L12. (Confiança: 0.6 - 0.8)
5. **LLM Classifier (Groq)**: Para a "zona cinzenta" (65%-80%), usa Llama-3 via Groq API para decisão final. (Confiança: 0.85+)
6. **Review Queue**: Se nenhum método atingir o threshold mínimo ($\ge 55\%$), o item vai para a fila de revisão humana.

## Rationale
- Evita falsos positivos (especialmente em categorias similares como "leite condensado" vs "doce de leite").
- Maximiza a automação sem sacrificar a precisão.
- Reduz custos de API (Groq) ao usá-lo apenas como último recurso.

## Consequências
- **Positivas**: Alta taxa de acerto automático, transparência no motivo do match (`match_reason`).
- **Negativas**: Complexidade na implementação do pipeline e dependência de modelos de ML (Sentence-Transformers).
