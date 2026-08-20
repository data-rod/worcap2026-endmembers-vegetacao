# Colaboração

## Avaliadores

- Trabalhe somente na classe atribuída.
- Não altere os identificadores de classe, data ou candidato.
- Exporte o CSV diretamente pelo painel.
- Coloque o arquivo em `reviews/incoming/class_XX/`.
- Não edite manualmente as escolhas após a exportação.

## Coautores

- Preserve a configuração congelada em `config/study.yaml`.
- Para examinar ou reproduzir o método com o código integralmente exposto, execute os cadernos de `notebooks/standalone/` na ordem indicada no respectivo README.
- Novas análises devem ser escritas em `outputs/`, que não é versionado.
- Alterações metodológicas devem ser acompanhadas de teste e atualização da documentação.
- Não substitua dados publicados sem atualizar `metadata/checksums.sha256` e `metadata/manifest.json`.
- Antes de incorporar revisões, execute `python -m worcap_endmembers validate-reviews`.

A mesma validação, com todas as funções apresentadas nas células, está disponível em `notebooks/standalone/04_validar_e_consolidar_revisoes.ipynb`.

## Convenção para arquivos de revisão

```text
reviews/incoming/class_01/wtss1000_active_vegetation_class_01.csv
```

O CSV deve conter:

```text
class_code,date,active_vegetation_endmembers,candidate_ids,reviewed_at
```

## Verificação antes de compartilhar alterações

```bash
python -m pytest
python -m worcap_endmembers verify
python -m worcap_endmembers validate-all-reviews
```
