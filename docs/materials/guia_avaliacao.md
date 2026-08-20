# Guia de avaliação dos candidatos PPI

## Objetivo da avaliação

Identificar, em cada data, todos os candidatos cuja assinatura seja compatível com vegetação fotossinteticamente ativa. O PPI localiza pixels espectralmente extremos, mas não atribui significado biofísico aos candidatos.

## Critério espectral

A decisão deve considerar conjuntamente:

- absorção no visível, especialmente no vermelho;
- elevação ao longo das bandas de red edge;
- reflectância no infravermelho próximo maior que no vermelho;
- comportamento coerente no infravermelho de ondas curtas;
- forma geral da assinatura, e não uma banda isolada.

Diferenças de magnitude podem representar mistura espacial, estrutura do dossel, conteúdo de água, fundo e condições de observação. Mais de um candidato da mesma data pode ser compatível com vegetação ativa.

## Como usar o painel

1. Mantenha **Reflectância** como visualização principal.
2. Compare o gráfico conjunto e os quatro gráficos individuais.
3. Use as curvas cinzas como contexto da distribuição espectral dos pixels válidos.
4. Use EVI, BSI e as barras de desvio-padrão apenas como apoio visual.
5. Marque `EM01`, `EM02`, `EM03` e/ou `EM04` quando forem compatíveis com vegetação ativa.
6. Use **Todos** quando todos os candidatos forem compatíveis.
7. Use **Nenhum** quando nenhum candidato for compatível.
8. Avance até concluir todas as datas disponíveis.
9. Exporte o CSV e salve-o na pasta da classe correspondente.

## Regras importantes

- Não é obrigatório selecionar somente um candidato.
- Não escolha um candidato apenas porque B08 ou B8A apresenta o maior valor.
- `EM01` a `EM04` são posições relativas dentro de cada data; não representam indivíduos persistentes no tempo.
- Não altere manualmente os identificadores do CSV exportado.
- Datas sem candidatos não aparecem no painel e não devem ser criadas manualmente.

## Atalhos

| Tecla | Ação |
|---|---|
| `←` / `→` | data anterior / próxima data |
| `1` a `4` | alternar o candidato correspondente |
| `A` | selecionar todos |
| `N` | selecionar nenhum |
| `R` | reflectância |
| `F` | forma normalizada |

## Saída

O painel exporta:

```text
class_code,date,active_vegetation_endmembers,candidate_ids,reviewed_at
```

Cada linha corresponde a uma decisão `classe × data`.

