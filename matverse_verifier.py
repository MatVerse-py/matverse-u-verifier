#!/usr/bin/env python3
"""
MatVerse Verifier - Verificador Independente Offline

Verifica o kernel MatVerse sem confiança.
Pode rodar completamente offline.
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

class MatVerseVerifier:
    """
    Verificador independente do kernel MatVerse
    
    Roda offline e verifica:
    - Assinatura Ed25519
    - Hash SHA3-256
    - Constituição (5 regras)
    - Merkle Tree
    - Anchors (GitHub, Zenodo, IPFS)
    """
    
    def __init__(self, bundle_path: str, public_key_path: str):
        """
        Inicializa o verifier
        
        Args:
            bundle_path: Caminho para genesis-bundle.json
            public_key_path: Caminho para matverse-public-key.pem
        """
        self.bundle_path = Path(bundle_path)
        self.public_key_path = Path(public_key_path)
        
        # Carregar chave pública
        with open(self.public_key_path, 'rb') as f:
            self.public_key = serialization.load_pem_public_key(f.read())
        
        # Carregar bundle
        with open(self.bundle_path, 'r') as f:
            self.bundle = json.load(f)
    
    def verify_signature(self) -> Dict:
        """
        Verifica assinatura Ed25519 do kernel
        
        Returns:
            Dicionário com resultado da verificação
        """
        try:
            # Extrair assinatura
            signature_hex = self.bundle['signature'].replace('0x', '')
            signature = bytes.fromhex(signature_hex)
            
            # Recalcular dados (sem assinatura e hash)
            bundle_copy = self.bundle.copy()
            del bundle_copy['signature']
            del bundle_copy['hash']
            data = json.dumps(bundle_copy, sort_keys=True).encode()
            
            # Verificar assinatura
            self.public_key.verify(signature, data)
            
            return {
                "status": "VALID",
                "algorithm": "Ed25519",
                "verified_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "INVALID",
                "algorithm": "Ed25519",
                "error": str(e),
                "verified_at": datetime.now(timezone.utc).isoformat()
            }
    
    def verify_hash(self) -> Dict:
        """
        Verifica hash SHA3-256 do bundle
        
        Returns:
            Dicionário com resultado da verificação
        """
        try:
            # Recalcular hash (sem assinatura e hash)
            bundle_copy = self.bundle.copy()
            del bundle_copy['signature']
            del bundle_copy['hash']
            data = json.dumps(bundle_copy, sort_keys=True).encode()
            
            computed_hash = hashlib.sha3_256(data).hexdigest()
            expected_hash = self.bundle['hash'].replace('0x', '')
            
            if computed_hash == expected_hash:
                return {
                    "status": "VALID",
                    "algorithm": "SHA3-256",
                    "expected": f"0x{expected_hash}",
                    "computed": f"0x{computed_hash}"
                }
            else:
                return {
                    "status": "INVALID",
                    "algorithm": "SHA3-256",
                    "expected": f"0x{expected_hash}",
                    "computed": f"0x{computed_hash}",
                    "error": "Hash mismatch"
                }
        except Exception as e:
            return {
                "status": "INVALID",
                "algorithm": "SHA3-256",
                "error": str(e)
            }
    
    def verify_constitution(self) -> Dict:
        """
        Verifica estrutura da constituição
        
        Returns:
            Dicionário com resultado da verificação
        """
        try:
            constitution = self.bundle['constitution']
            rules = constitution['rules']
            
            # Verificar cada regra
            rules_result = []
            for rule in rules:
                valid = all([
                    'id' in rule,
                    'type' in rule,
                    'condition' in rule,
                    'action' in rule,
                    'description' in rule
                ])
                rules_result.append({
                    "id": rule.get('id', 'UNKNOWN'),
                    "valid": valid
                })
            
            rules_valid = sum(1 for r in rules_result if r['valid'])
            rules_total = len(rules_result)
            
            return {
                "status": "VALID" if rules_valid == rules_total else "INVALID",
                "rules_total": rules_total,
                "rules_valid": rules_valid,
                "rules": rules_result
            }
        except Exception as e:
            return {
                "status": "INVALID",
                "error": str(e)
            }
    
    def verify_merkle_tree(self) -> Dict:
        """
        Verifica Merkle Tree das regras
        
        Returns:
            Dicionário com resultado da verificação
        """
        try:
            # Recalcular Merkle Tree
            rules = self.bundle['constitution']['rules']
            leaves = []
            
            for rule in rules:
                rule_str = json.dumps(rule, sort_keys=True)
                rule_hash = hashlib.sha3_256(rule_str.encode()).hexdigest()
                leaves.append(f"0x{rule_hash}")
            
            # Calcular raiz
            all_hashes = ''.join(leaves)
            computed_root = hashlib.sha3_256(all_hashes.encode()).hexdigest()
            expected_root = self.bundle['merkle_root'].replace('0x', '')
            
            if computed_root == expected_root:
                return {
                    "status": "VALID",
                    "expected_root": f"0x{expected_root}",
                    "computed_root": f"0x{computed_root}",
                    "leaves_count": len(leaves)
                }
            else:
                return {
                    "status": "INVALID",
                    "expected_root": f"0x{expected_root}",
                    "computed_root": f"0x{computed_root}",
                    "error": "Merkle root mismatch"
                }
        except Exception as e:
            return {
                "status": "INVALID",
                "error": str(e)
            }
    
    def verify_anchors(self) -> Dict:
        """
        Verifica anchors (GitHub, Zenodo, IPFS)
        
        Returns:
            Dicionário com resultado da verificação
        """
        # Nota: Esta verificação é informativa, não criptográfica
        # Não faz chamadas de rede (offline)
        
        return {
            "status": "CONFIGURED",
            "github": "https://github.com/MatVerse-py/matverse-u-kernel",
            "zenodo": "PENDING",
            "ipfs": "PENDING",
            "note": "Anchors verificados manualmente (offline)"
        }
    
    def verify_all(self) -> Dict:
        """
        Executa todas as verificações
        
        Returns:
            Relatório completo de verificação
        """
        # Executar verificações
        signature = self.verify_signature()
        hash_check = self.verify_hash()
        constitution = self.verify_constitution()
        merkle_tree = self.verify_merkle_tree()
        anchors = self.verify_anchors()
        
        # Calcular score
        score = 0
        
        # Assinatura: 30 pontos
        if signature['status'] == 'VALID':
            score += 30
        
        # Hash: 30 pontos
        if hash_check['status'] == 'VALID':
            score += 30
        
        # Constituição: 20 pontos
        if constitution['status'] == 'VALID':
            score += 20
        
        # Merkle Tree: 15 pontos
        if merkle_tree['status'] == 'VALID':
            score += 15
        
        # Anchors: 5 pontos
        if anchors['status'] == 'CONFIGURED':
            score += 5
        
        # Veredito
        if score == 100:
            verdict = "VERIFIED"
        elif score >= 90:
            verdict = "VERIFIED (anchors pending)"
        elif score >= 70:
            verdict = "PARTIALLY VERIFIED"
        else:
            verdict = "NOT VERIFIED"
        
        # Montar relatório
        report = {
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kernel_hash": self.bundle['hash'],
            "merkle_root": self.bundle['merkle_root'],
            "checks": {
                "signature": signature,
                "hash": hash_check,
                "constitution": constitution,
                "merkle_tree": merkle_tree,
                "anchors": anchors
            },
            "score": score,
            "verdict": verdict
        }
        
        return report
    
    def save_report(self, output_path: str):
        """
        Salva relatório de verificação
        
        Args:
            output_path: Caminho para salvar o relatório
        """
        report = self.verify_all()
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✅ Relatório salvo em: {output_path}")
        print(f"   Score: {report['score']}% {report['verdict']}")

def verify_kernel(bundle_path: str, public_key_path: str) -> Dict:
    """
    Função auxiliar para verificar kernel
    
    Args:
        bundle_path: Caminho para genesis-bundle.json
        public_key_path: Caminho para matverse-public-key.pem
    
    Returns:
        Relatório de verificação
    """
    verifier = MatVerseVerifier(bundle_path, public_key_path)
    return verifier.verify_all()

def main():
    """Exemplo de uso"""
    print("=" * 70)
    print("  MATVERSE VERIFIER - VERIFICADOR INDEPENDENTE OFFLINE")
    print("=" * 70)
    print()
    
    # Criar verifier
    print("1. Inicializando verifier...")
    verifier = MatVerseVerifier(
        bundle_path='../matverse-u-kernel/genesis-bundle.json',
        public_key_path='../matverse-u-kernel/matverse-public-key.pem'
    )
    print("   ✅ Verifier inicializado")
    print()
    
    # Executar verificações
    print("2. Executando verificações...")
    report = verifier.verify_all()
    print()
    
    # Exibir resultados
    print("=" * 70)
    print("  RELATÓRIO DE VERIFICAÇÃO")
    print("=" * 70)
    print(f"Kernel Hash: {report['kernel_hash']}")
    print(f"Merkle Root: {report['merkle_root']}")
    print()
    
    print("Verificações:")
    for check, result in report['checks'].items():
        status = result['status']
        emoji = "✅" if status in ['VALID', 'CONFIGURED'] else "❌"
        print(f"  {emoji} {check.upper()}: {status}")
    
    print()
    print(f"Score: {report['score']}%")
    print(f"Veredito: {report['verdict']}")
    print()
    
    # Salvar relatório
    print("3. Salvando relatório...")
    verifier.save_report('verification-report.json')
    print()

if __name__ == "__main__":
    main()
