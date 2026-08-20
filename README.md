# Decomposição espectro-temporal de extremos do Pixel Purity Index — WORCAP 2026

Repositório do artigo submetido ao WORCAP 2026 sobre extremos do Pixel Purity Index (PPI)
compatíveis com vegetação fotossinteticamente ativa em quatro classes permanentes do
TerraClass Amazônia.

Artigo: [`manuscript/artigo.pdf`](manuscript/artigo.pdf)

## Verificar os resultados

Um comando reproduz e confere todos os números do artigo. Não precisa de rede.

```bash
python -m pip install -r requirements.txt
python verificar.py
```

A saída lista cada afirmação do artigo com `OK` ou `FALHA` e termina com código 0 se tudo
confere:

```text
2. Completude — o artigo afirma 658 de 736 combinações classe–data
  [OK   ] combinações com extremo retido = 658
  [OK   ] classe 02 (Vegetação Secundária): 160 datas
3. Força sazonal — rederivada dos componentes STL, não relida das métricas
  [OK   ] classe 02: F_S = 0.046, 0.435, 0.494, 0.143
4. Rotatividade espacial — o artigo afirma distâncias medianas de 222 a 774 km
  [OK   ] faixa observada = 222 a 774 km

RESULTADO: as 13 verificações conferem com o artigo
```

São conferidos: a integridade SHA-256 dos dados, as 736 combinações e os 658 extremos retidos,
as datas por classe, as 16 medianas de força sazonal — recalculadas a partir dos componentes
STL brutos — a faixa de rotatividade espacial, e a regeneração da Figura 1.

O caderno [`notebooks/02_verificar_resultados_do_artigo.ipynb`](notebooks/02_verificar_resultados_do_artigo.ipynb)
faz as mesmas conferências com o código visível célula a célula.

## Delineamento

- máscaras de permanência TerraClass de 2016, 2018, 2020, 2022 e 2024, com núcleo 3 × 3;
- 1.000 pixels sistemáticos por classe em EPSG:5880, semente 13;
- 184 compostos de 16 dias da coleção BDC `S2-16D-2`, 2017–2024, dez bandas;
- PPI por `classe × data`, 10.000 projeções, até quatro candidatos separados por SAM ≥ 2°;
- inspeção da forma espectral para identificar vegetação fotossinteticamente ativa;
- decomposição STL robusta por banda, período 23.

Os parâmetros estão congelados em [`config/study.yaml`](config/study.yaml). São decisões
operacionais, não parâmetros universais nem tamanho amostral inferencial. Uma única semente
assegura repetibilidade, não estabilidade entre realizações.

## Estrutura

```text
verificar.py                 verificação dos resultados em um comando
config/                      configuração congelada
data/points/                 amostra sistemática
data/wtss/                   séries Sentinel-2 do WTSS
data/candidates/             candidatos e manifestos PPI
data/series/                 espectros representativos
data/analysis/spectrotemporal/  componentes STL, métricas e robustez
manuscript/                  artigo em PDF, figura e referências
notebooks/                   verificação e reprodução passo a passo
scripts/                     análise e geração dos produtos
src/worcap_endmembers/       pacote com PPI, painéis e revisão
reviews/                     avaliações espectrais
docs/                        metodologia, materiais e painel de exemplo
tests/                       testes automatizados
metadata/                    manifesto e checksums
```

## Reproduzir a análise a partir dos dados brutos

```bash
python scripts/analyze_spectrotemporal.py
python scripts/build_spectrotemporal_outputs.py --output-dir manuscript/figures
python -m pytest
```

Os dados WTSS e os candidatos usados no estudo acompanham o repositório; não é preciso
consultar serviços remotos. Para percorrer o método com o código exposto em cada etapa, use
[`notebooks/standalone/`](notebooks/standalone/README.md).

## Totais da cadeia

| Indicador | Total |
|---|---:|
| Combinações classe–data | 736 |
| Candidatos automáticos | 2.935 |
| Combinações com candidatos | 734 |
| Datas sem candidato de vegetação ativa | 76 |
| Espectros representativos | 658 |

## Ambiente

`environment.yml` e `requirements.txt` fixam `python=3.12` e `pyarrow==22.0.0`. Os dados estão
em Parquet escrito com essa versão; leitores anteriores falham com
`Repetition level histogram size mismatch`, e `verificar.py` avisa com essa instrução em vez de
quebrar. Instale as dependências declaradas antes de executar.

```bash
conda env create -f environment.yml && conda activate worcap-endmembers
```

## Limites

Os resultados são preliminares e condicionais aos pixels válidos de cada composto. Os rótulos
TerraClass não foram validados de forma independente. A posição dos extremos não é mantida
entre datas, de modo que as trajetórias concatenam localizações distintas. Sem calibração
biofísica, as bandas não estimam clorofila, LAI, biomassa, produtividade ou conteúdo hídrico;
a STL separa componentes temporais, mas não determina suas causas.

## Licença e citação

Conteúdo distribuído sob [Creative Commons Attribution 4.0 International](LICENSE) (CC BY 4.0).
Os dados de terceiros mantêm as condições de origem: TerraClass Amazônia e Brazil Data Cube são
do INPE.

Para citar, use [`CITATION.cff`](CITATION.cff) ou o botão *Cite this repository*.
