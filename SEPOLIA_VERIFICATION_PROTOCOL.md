# Sepolia Verification Protocol

## Objective

Converter `SEPOLIA = ?` em `SEPOLIA = 1` ou `SEPOLIA = 0` por verificação independente.

## Canonical transaction

- **Transaction hash**: `0x4143cd92dba24ac5dbbbf44086ff6d94cb5024fcd6dcf6615a434ae40e0eb3c4`
- **Expected Merkle root**: `de64429cb1c1c79e580455e4ce5e890d1e954273ec2e33b825a5d8e548b3b07a`

## Fail-closed rule

Nenhuma alegação de `CLOSURE_STRICT = 1` é válida enquanto `SEPOLIA` permanecer indeterminado.

## Verification methods

### Method A: JSON-RPC

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "method":"eth_getTransactionByHash",
    "params":["0x4143cd92dba24ac5dbbbf44086ff6d94cb5024fcd6dcf6615a434ae40e0eb3c4"],
    "id":1
  }' \
  https://rpc.sepolia.org
```

### Method B: Receipt verification

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "method":"eth_getTransactionReceipt",
    "params":["0x4143cd92dba24ac5dbbbf44086ff6d94cb5024fcd6dcf6615a434ae40e0eb3c4"],
    "id":1
  }' \
  https://rpc.sepolia.org
```

## Success criteria

Set `SEPOLIA = 1` only if all of the following hold:

1. transaction exists;
2. receipt exists and indicates success;
3. the transaction data or emitted record is consistent with the expected Merkle root;
4. the verification source is independent of the original artifact authoring path.

Otherwise:

- set `SEPOLIA = 0` if contradiction is proven;
- keep `SEPOLIA = ?` if evidence remains unavailable.
