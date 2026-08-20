# Metodologia

## Delineamento

O estudo acompanha cinco classes vegetadas do TerraClass Amazônia: Vegetação Natural Florestal Primária, Vegetação Natural Florestal Secundária, Silvicultura, Pastagem Arbustiva/Arbórea e Pastagem Herbácea. O TerraClass é adotado como referência temática para a estratificação.

Para a classe (c), a máscara de permanência foi definida por:

\[
P_c(s)=\prod_{y\in\{2016,2018,2020,2022,2024\}}\mathbf{1}\{L_y(s)=c\}.
\]

Um pixel permanece elegível somente quando ele e seus oito vizinhos pertencem à mesma classe permanente:

\[
K_c(s)=\min_{u\in\mathcal{N}_{3\times3}}P_c(s+u).
\]

## Amostra sistemática

Foram selecionados 1.000 pixels por classe por meio de malha sistemática com origem pseudoaleatória reproduzível, seed 13, em SIRGAS 2000/Brazil Polyconic (EPSG:5880). O espaçamento inicial foi:

\[
h_c=\sqrt{\widetilde{A}_c/1000},
\]

em que \(\widetilde{A}_c\) é a área operacional aproximada do núcleo da classe. Quando necessário, o espaçamento foi reduzido em 5% até produzir pelo menos 1.000 pontos válidos. Os pontos excedentes foram ordenados espacialmente por código Morton e reduzidos em intervalos regulares.

| Classe | Espaçamento final | Distância mínima observada |
|---|---:|---:|
| 01 | 55,132 km | 55,122 km |
| 02 | 9,409 km | 9,400 km |
| 09 | 1,928 km | 1,918 km |
| 10 | 1,933 km | 1,924 km |
| 11 | 15,573 km | 15,564 km |

Os 1.000 pontos constituem um limite operacional uniforme entre classes. Eles não representam um tamanho amostral inferencial nem eliminam a possibilidade de autocorrelação espacial.

## Séries Sentinel-2

As séries foram obtidas pelo Web Time Series Service do Brasil Data Cube para a coleção `S2-16D-2`, com 184 compostos entre 2017 e 2024 (Vinhas et al., 2017; Ferreira et al., 2020). Foram utilizadas as bandas B02, B03, B04, B05, B06, B07, B08, B8A, B11 e B12.

A observação \(i,t\) foi considerada válida quando:

\[
Q_{i,t}=\mathbf{1}(\mathrm{CLEAROB}>0)\mathbf{1}(\mathrm{SCL}\notin\{0,1,2,3,8,9,10,11\})\prod_b\mathbf{1}(\rho_{i,t,b}\text{ finita}).
\]

## Pixel Purity Index

O PPI foi executado separadamente para cada combinação `classe × data`. As reflectâncias foram centralizadas pela média, sem padronização pela variância:

\[
z_i=x_i-\bar{x}.
\]

Em cada projeção aleatória:

\[
r_k=\frac{g_k}{\lVert g_k\rVert},\qquad g_k\sim N(0,I),
\]

\[
p_{ik}=z_i^\mathsf{T}r_k.
\]

O escore PPI soma os votos recebidos por um pixel como máximo ou mínimo em 10.000 projeções:

\[
\operatorname{PPI}(i)=\sum_{k=1}^{10000}\left[\mathbf{1}\{i=\arg\max_jp_{jk}\}+\mathbf{1}\{i=\arg\min_jp_{jk}\}\right].
\]

Foram mantidos até quatro candidatos, ordenados pelo escore PPI. A separação espectral foi avaliada pelo Spectral Angle Mapper (Kruse et al., 1993):

\[
\operatorname{SAM}(x,y)=\cos^{-1}\left(\frac{x^\mathsf{T}y}{\lVert x\rVert\lVert y\rVert}\right)\frac{180}{\pi}.
\]

Um candidato somente foi acrescentado quando apresentou \(\operatorname{SAM}\geq2^\circ\) em relação a todos os candidatos já selecionados. Os parâmetros foram definidos a priori e mantidos constantes em todas as classes e datas: máximo de quatro candidatos, 1.000 pixels, 10.000 projeções, seed 13 e uma única execução determinística.

## Avaliação humana

O núcleo geométrico do PPI clássico identifica extremos espectrais por projeções em vetores unitários aleatórios e contagem de máximos e mínimos, sem atribuir famílias semânticas (Boardman, Kruse e Green, 1995). Nesta implementação, as reflectâncias foram apenas centralizadas pela média, sem transformação MNF. Os candidatos foram avaliados com base na absorção no visível, transição do red edge, resposta no NIR e comportamento no SWIR. Foi permitido validar nenhum, um ou vários candidatos na mesma data. Uma única semente assegura repetibilidade computacional, não estabilidade entre realizações.

Quando mais de um candidato foi validado, representou a data o candidato real com maior escore PPI. Empates foram resolvidos pelo menor valor da ordem sistemática e, persistindo o empate, pelo identificador do candidato. Se nenhum candidato foi validado, a observação permaneceu ausente.

## Referências

- Boardman, J. W.; Kruse, F. A.; Green, R. O. (1995). Mapping target signatures via partial unmixing of AVIRIS data. *Summaries of the Fifth Annual JPL Airborne Earth Science Workshop*, 23–26. Publicação sem DOI. https://ntrs.nasa.gov/citations/19950027316
- Ferreira, K. R. et al. (2020). Earth observation data cubes for Brazil. *Remote Sensing*, 12, 4033. https://doi.org/10.3390/rs12244033
- Kruse, F. A. et al. (1993). The spectral image processing system (SIPS). *Remote Sensing of Environment*, 44, 145–163. https://doi.org/10.1016/0034-4257(93)90013-N
- Vinhas, L.; Queiroz, G. R.; Ferreira, K. R.; Câmara, G. (2017). Web services for big earth observation data. https://doi.org/10.14393/rbcv69n5-44004
