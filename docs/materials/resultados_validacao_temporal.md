# Resultados da validação e preparação temporal

## Consolidação das avaliações

Foram validadas 918 combinações `classe × data` que possuíam candidatos PPI. A origem de cada decisão pode ser auditada em `reviews/validated/review_provenance.parquet`.

## Espectros representativos

Quando mais de um candidato foi validado como vegetação fotossinteticamente ativa, foi escolhido o candidato real com maior escore PPI. Empates foram resolvidos pela ordem sistemática e pelo identificador. Não foram calculadas médias artificiais entre candidatos.

A grade final possui 920 combinações, correspondentes a cinco classes e 184 datas. Foram obtidos 796 espectros representativos:

| Classe | Espectros válidos | Fração válida | `NENHUM` | Sem candidato PPI | Elegível para STL |
|---|---:|---:|---:|---:|---:|
| 01 | 138 | 75,00% | 46 | 0 | Não |
| 02 | 160 | 86,96% | 24 | 0 | Sim |
| 09 | 173 | 94,02% | 10 | 1 | Sim |
| 10 | 165 | 89,67% | 18 | 1 | Sim |
| 11 | 160 | 86,96% | 24 | 0 | Sim |

O limiar de 80% havia sido definido antes da obtenção dos resultados. Por esse motivo, a classe 01 não foi submetida ao STL. O critério não foi reduzido após a observação da fração de 75%.

## Decomposição temporal

As dez bandas das classes 02, 09, 10 e 11 foram decompostas por STL robusto, com periodicidade de 23 compostos. Isso corresponde a 40 séries `classe × banda` e 7.360 registros de componentes temporais. A classe 01 permanece no arquivo de componentes com o estado `INSUFFICIENT_VALID_FRACTION` e valores de tendência, sazonalidade e resíduo ausentes.

Para as séries elegíveis, a interpolação foi aplicada somente à entrada do STL. Os valores originais permanecem ausentes no produto científico observado, e cada valor interpolado possui a marca `imputed_for_stl = True`. O maior erro numérico de reconstrução entre entrada, tendência, sazonalidade e resíduo foi inferior a `1,2 × 10⁻¹⁶`.

## Produtos

- `reviews/validated/reviews_consolidadas.parquet`: decisões finais do avaliador principal;
- `reviews/validated/review_provenance.parquet`: origem de cada decisão;
- `data/series/representative_spectra.parquet`: grade completa com dez bandas, NDVI, EVI e BSI;
- `data/series/series_completeness.parquet`: completude e elegibilidade por classe;
- `data/analysis/stl_components.parquet`: valores observados, entrada interpolada e componentes STL;
- `data/analysis/stl_summary.parquet`: diagnóstico das 50 combinações `classe × banda`.
