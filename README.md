# MatVerse Verifier

**Verificador Independente Offline (100% Verificável)**

## Visão Geral

O **MatVerse Verifier** é um verificador independente que pode rodar **offline** e **sem confiança**. Qualquer pessoa pode usar este verificador para auditar o kernel MatVerse sem depender de terceiros.

O Verifier:
- **Verifica assinatura Ed25519** do kernel
- **Valida hash SHA3-256** do bundle
- **Reconstrói Merkle Tree** das regras
- **Roda offline** sem dependências externas
- **Não requer confiança** em autoridades
- **100% verificável** por qualquer um

> "Não confie. Verifique."

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                   VERIFIER INDEPENDENTE                 │
│                   (Roda offline)                        │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │ Entrada                                           │ │
│  │ - genesis-bundle.json                             │ │
│  │ - matverse-public-key.pem                         │ │
│  └───────────────────────────────────────────────────┘ │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 1. Verificar Assinatura                           │ │
│  │    - Carregar chave pública                        │ │
│  │    - Extrair assinatura do bundle                  │ │
│  │    - Verificar com Ed25519                         │ │
│  │    ✅ VALID / ❌ INVALID                           │ │
│  └───────────────────────────────────────────────────┘ │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 2. Validar Hash                                   │ │
│  │    - Recalcular hash SHA3-256                      │ │
│  │    - Comparar com hash do bundle                   │ │
│  │    ✅ VALID / ❌ INVALID                           │ │
│  └───────────────────────────────────────────────────┘ │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 3. Verificar Constituição                         │ │
│  │    - Validar 5 regras                              │ │
│  │    - Verificar estrutura                           │ │
│  │    ✅ 5/5 VALID / ❌ X/5 INVALID                   │ │
│  └───────────────────────────────────────────────────┘ │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 4. Verificar Merkle Tree                          │ │
│  │    - Recalcular raiz                               │ │
│  │    - Comparar com merkle_root do bundle            │ │
│  │    ✅ VALID / ❌ INVALID                           │ │
│  └───────────────────────────────────────────────────┘ │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐ │
│  │ 5. Verificar Anchors                              │ │
│  │    - GitHub (replicação)                           │ │
│  │    - Zenodo (DOI + preservação)                    │ │
│  │    - IPFS (redundância P2P)                        │ │
│  │    ✅ CONFIGURED / ⚠️  PENDING                     │ │
│  └───────────────────────────────────────────────────┘ │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐ │
│  │ Saída                                             │ │
│  │ - verification-report.json                        │ │
│  │ - Score: 0-100% VERIFIED                          │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Uso do Verifier

### Instalação

```bash
pip install cryptography
```

### Uso Básico

```python
from matverse_verifier import verify_kernel

# Verificar kernel completo
report = verify_kernel(
    bundle_path='../matverse-u-kernel/genesis-bundle.json',
    public_key_path='../matverse-u-kernel/matverse-public-key.pem'
)

print(f"Score: {report['score']}% VERIFIED")
print(f"Assinatura: {report['signature']}")
print(f"Hash: {report['hash']}")
print(f"Constituição: {report['constitution']}")
print(f"Merkle Tree: {report['merkle_tree']}")
```

### Uso via CLI

```bash
python matverse_verifier.py \
  --bundle ../matverse-u-kernel/genesis-bundle.json \
  --public-key ../matverse-u-kernel/matverse-public-key.pem \
  --output verification-report.json
```

## Relatório de Verificação

O verifier gera um relatório JSON completo:

```json
{
  "version": "1.0.0",
  "timestamp": "2026-02-13T12:00:00Z",
  "kernel_hash": "0xd9dcd0bb...",
  "merkle_root": "0xfef9a4e3...",
  "checks": {
    "signature": {
      "status": "VALID",
      "algorithm": "Ed25519",
      "verified_at": "2026-02-13T12:00:00Z"
    },
    "hash": {
      "status": "VALID",
      "algorithm": "SHA3-256",
      "expected": "0xd9dcd0bb...",
      "computed": "0xd9dcd0bb..."
    },
    "constitution": {
      "status": "VALID",
      "rules_total": 5,
      "rules_valid": 5,
      "rules": [
        {"id": "R1", "valid": true},
        {"id": "R2", "valid": true},
        {"id": "R3", "valid": true},
        {"id": "R4", "valid": true},
        {"id": "R5", "valid": true}
      ]
    },
    "merkle_tree": {
      "status": "VALID",
      "expected_root": "0xfef9a4e3...",
      "computed_root": "0xfef9a4e3..."
    },
    "anchors": {
      "status": "CONFIGURED",
      "github": "https://github.com/MatVerse-py/matverse-u-kernel",
      "zenodo": "PENDING",
      "ipfs": "PENDING"
    }
  },
  "score": 100,
  "verdict": "VERIFIED"
}
```

## Verificações Realizadas

### 1. Assinatura Ed25519
- **Objetivo**: Garantir que o kernel não foi adulterado
- **Método**: Verificar assinatura criptográfica com chave pública
- **Resultado**: VALID / INVALID

### 2. Hash SHA3-256
- **Objetivo**: Garantir integridade do bundle
- **Método**: Recalcular hash e comparar
- **Resultado**: VALID / INVALID

### 3. Constituição
- **Objetivo**: Validar estrutura das 5 regras
- **Método**: Verificar campos obrigatórios e tipos
- **Resultado**: X/5 VALID

### 4. Merkle Tree
- **Objetivo**: Garantir integridade das regras
- **Método**: Recalcular raiz da árvore de Merkle
- **Resultado**: VALID / INVALID

### 5. Anchors
- **Objetivo**: Verificar replicação em múltiplos locais
- **Método**: Checar existência em GitHub, Zenodo, IPFS
- **Resultado**: CONFIGURED / PENDING

## Score de Verificação

O score é calculado com base nas verificações:

| Verificação | Peso | Pontos |
|-------------|------|--------|
| Assinatura | 30% | 0-30 |
| Hash | 30% | 0-30 |
| Constituição | 20% | 0-20 |
| Merkle Tree | 15% | 0-15 |
| Anchors | 5% | 0-5 |
| **TOTAL** | **100%** | **0-100** |

**Interpretação:**
- **100%**: Totalmente verificado
- **90-99%**: Verificado (alguns anchors pendentes)
- **70-89%**: Parcialmente verificado
- **< 70%**: Não verificado

## Uso Offline

O verifier pode rodar **completamente offline**:

1. Baixe os arquivos necessários:
   - `genesis-bundle.json`
   - `matverse-public-key.pem`
   - `matverse_verifier.py`

2. Desconecte da internet

3. Execute a verificação:
   ```bash
   python matverse_verifier.py --bundle genesis-bundle.json --public-key matverse-public-key.pem
   ```

4. O verifier **não faz nenhuma chamada de rede**

## Segurança

### Sem Confiança
O verifier **não confia em ninguém**:
- Não depende de servidores
- Não faz chamadas de API
- Não requer autenticação
- Verifica tudo criptograficamente

### Verificação Independente
Qualquer pessoa pode:
- Baixar o código
- Auditar a implementação
- Executar offline
- Obter os mesmos resultados

### Código Aberto
O código do verifier é:
- Simples (~200 linhas)
- Bem documentado
- Auditável
- Sem dependências ocultas

## Exemplo Completo

```python
#!/usr/bin/env python3
"""
Exemplo completo de verificação do kernel
"""

from matverse_verifier import MatVerseVerifier

def main():
    # Criar verifier
    verifier = MatVerseVerifier(
        bundle_path='../matverse-u-kernel/genesis-bundle.json',
        public_key_path='../matverse-u-kernel/matverse-public-key.pem'
    )
    
    # Executar todas as verificações
    report = verifier.verify_all()
    
    # Exibir resultados
    print(f"✅ Score: {report['score']}% VERIFIED")
    print()
    
    print("Verificações:")
    for check, result in report['checks'].items():
        status = result['status']
        emoji = "✅" if status == "VALID" else "❌"
        print(f"  {emoji} {check.upper()}: {status}")
    
    print()
    print(f"Veredito: {report['verdict']}")
    
    # Salvar relatório
    verifier.save_report('verification-report.json')

if __name__ == "__main__":
    main()
```

## Estrutura do Repositório

```
matverse-u-verifier/
├── matverse_verifier.py        # Implementação do verifier
├── verification-report.json    # Relatório de exemplo
├── examples/                   # Exemplos de uso
│   ├── basic_verification.py
│   ├── offline_verification.py
│   └── batch_verification.py
├── tests/                      # Testes
│   ├── test_signature.py
│   ├── test_hash.py
│   └── test_merkle.py
├── docs/                       # Documentação
│   ├── architecture.md
│   ├── security.md
│   └── offline_usage.md
└── README.md                   # Este arquivo
```

## Referências

- [MatVerse Kernel](../matverse-u-kernel) - Bundle gênese congelado
- [MatVerse OS](../matverse-u-os) - Sistema Operacional Constitucional
- [MatVerse Docs](../matverse-u-docs) - Documentação consolidada
- [Ed25519](https://ed25519.cr.yp.to/) - Algoritmo de assinatura
- [SHA3-256](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf) - Função de hash
- [Merkle Tree](https://en.wikipedia.org/wiki/Merkle_tree) - Estrutura de dados

---

**MatVerse Verifier** - Não confie. Verifique.

*"A confiança é opcional. A verificação é matemática."*
