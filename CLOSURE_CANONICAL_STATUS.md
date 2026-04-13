# MatVerse Canonical Closure Status

## Escopo

Este documento corrige a leitura semântica de fechamento no repositório `matverse-u-verifier`.

A expressão `Closure = 1` é substituída por uma classificação em dois níveis:

- **Fechamento operacional**: existência e materialização pública mínima dos artefatos.
- **Fechamento estrito**: cadeia probatória independente, não circular, temporalmente consistente e suficiente sob auditoria adversarial.

## Definições formais

Seja:

- `G3` = Genesis publicado em Zenodo
- `G6` = Canonical Map publicado em Zenodo
- `PR` = pull request merged no GitHub
- `SEPOLIA` = verificação independente da transação Sepolia
- `NC` = ausência de circularidade de evidência
- `TC` = consistência temporal entre alegação e publicação pública

Definimos:

```text
ClosureOperational = G3 ∧ G6 ∧ PR
ClosureStrict      = G3 ∧ G6 ∧ PR ∧ SEPOLIA ∧ NC ∧ TC
```

## Evidências externas

- **G3 (Zenodo Genesis)**: DOI `10.5281/zenodo.19505244`
- **G6 (Canonical Map)**: DOI `10.5281/zenodo.19543878`
- **PR #1**: merged no repositório `MatVerse-py/matverse-u-verifier`

## Estado conservador atual

```text
G3 = 1
G6 = 1
PR = 1
SEPOLIA = ?
NC = 0
TC = 0
```

Logo:

```text
ClosureOperational = 1
ClosureStrict      = 0
```

## Justificativa técnica

1. **Fechamento operacional = 1**
   - há DOI público para G3;
   - há DOI público para G6;
   - há PR merged no GitHub.

2. **Fechamento estrito = 0**
   - o arquivo `closure_proof.txt` sustenta G6 com evidência autorreferente (`closure_proof.txt`), o que viola `NC = 1`;
   - a alegação de fechamento antecede a publicação pública de G6, o que viola `TC = 1`;
   - a transação Sepolia ainda requer verificação independente, portanto `SEPOLIA = ?`.

## Regra canônica

Nenhuma afirmação futura deve colapsar `ClosureOperational` em `ClosureStrict`.

```text
ClosureOperational ≠ ClosureStrict
```

## Status canônico do repositório

- **CLOSURE_OPERATIONAL = 1**
- **CLOSURE_STRICT = 0**

## Próximos passos mínimos para atingir fechamento estrito

1. substituir a evidência de G6 por referência direta ao DOI `10.5281/zenodo.19543878`;
2. verificar a transação Sepolia por fonte independente;
3. emitir novo artefato/PR com cadeia temporal coerente e sem circularidade.
