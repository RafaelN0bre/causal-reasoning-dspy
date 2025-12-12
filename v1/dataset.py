"""Golden dataset with synthetic consumer law cases for testing and evaluation."""

GOLDEN_DATASET = [
    {
        "id": 1,
        "name": "Celular à prova d'água (undercutting)",
        "case_text": """
        Comprei um celular online que dizia ser à prova d'água. 
        Ele caiu na piscina e parou de funcionar. A empresa se recusa 
        a consertar, alegando que a garantia não cobre 'mau uso'.
        """,
        "expected_facts": [
            "Produto_Anunciado_AprovaAgua",
            "Produto_Caiu_Piscina",
            "Produto_Parou_Funcionar",
            "Empresa_Alegou_Mau_Uso",
            "Empresa_Recusou_Conserto"
        ],
        "expected_rules": [
            "r1: Produto_Anunciado_AprovaAgua => Produto_Defeituoso",
            "r2: Produto_Defeituoso => Dever_Reparo",
            "r3: Empresa_Alegou_Mau_Uso => Nao_Aplica_Garantia (undercuts r2)"
        ],
        "expected_arguments": [
            "A1: [Produto_Anunciado_AprovaAgua, r1, r2] => Dever_Reparo",
            "A2: [Empresa_Alegou_Mau_Uso, r3] => Nao_Aplica_Garantia"
        ],
        "expected_attacks": [
            "A2 undercuts A1"
        ],
        "expected_justified": "Depends on whether A3 (defense: cair na piscina não é mau uso) is constructed",
        "expected_cause": "Produto_Anunciado_AprovaAgua is a cause if A1 is justified"
    },
    {
        "id": 2,
        "name": "Entrega atrasada - causa direta",
        "case_text": """
        Comprei um presente de aniversário com entrega garantida em 5 dias. 
        O produto chegou 2 semanas depois, após o aniversário. 
        Pedi reembolso mas a empresa ofereceu apenas um cupom de desconto.
        """,
        "expected_facts": [
            "Entrega_Garantida_5_Dias",
            "Produto_Chegou_2_Semanas",
            "Aniversario_Passou",
            "Consumidor_Pediu_Reembolso",
            "Empresa_Ofereceu_Cupom"
        ],
        "expected_rules": [
            "r1: Entrega_Garantida_5_Dias AND Produto_Chegou_2_Semanas => Descumprimento_Prazo",
            "r2: Descumprimento_Prazo => Direito_Reembolso"
        ],
        "expected_arguments": [
            "A1: [Entrega_Garantida_5_Dias, Produto_Chegou_2_Semanas, r1, r2] => Direito_Reembolso"
        ],
        "expected_attacks": [],
        "expected_justified": "A1 (no attacks)",
        "expected_cause": "Descumprimento_Prazo is a cause-in-fact of Direito_Reembolso"
    },
    {
        "id": 3,
        "name": "Produto com defeito oculto",
        "case_text": """
        Comprei uma geladeira nova que funcionou por 2 meses e depois parou de gelar. 
        O técnico da assistência disse que é defeito de fábrica no compressor. 
        A empresa alega que a garantia é de apenas 60 dias e já expirou.
        """,
        "expected_facts": [
            "Geladeira_Nova",
            "Funcionou_2_Meses",
            "Parou_Gelar",
            "Tecnico_Diagnosticou_Defeito_Fabrica",
            "Empresa_Alegou_Garantia_Expirada"
        ],
        "expected_rules": [
            "r1: Tecnico_Diagnosticou_Defeito_Fabrica => Defeito_Oculto",
            "r2: Defeito_Oculto => Garantia_Legal_60_Dias_Apos_Descoberta",
            "r3: Empresa_Alegou_Garantia_Expirada => Nao_Aplica_Garantia (undercuts r2)"
        ],
        "expected_arguments": [
            "A1: [Tecnico_Diagnosticou_Defeito_Fabrica, r1, r2] => Garantia_Legal_60_Dias_Apos_Descoberta",
            "A2: [Empresa_Alegou_Garantia_Expirada, r3] => Nao_Aplica_Garantia"
        ],
        "expected_attacks": [
            "A2 undercuts A1 (but should be defeated by CDC provisions)"
        ],
        "expected_justified": "A1 should win (CDC Art. 26, §3º - defeito oculto)",
        "expected_cause": "Defeito_Oculto is a cause-in-fact of Garantia_Legal_60_Dias_Apos_Descoberta"
    },
    {
        "id": 4,
        "name": "Preempção - duas causas concorrentes",
        "case_text": """
        Contratei um serviço de streaming que prometia 4K. 
        O serviço não funcionou porque: (1) minha internet era muito lenta E 
        (2) a plataforma teve problemas técnicos no servidor. 
        Reclamei e a empresa disse que a culpa é da minha internet.
        """,
        "expected_facts": [
            "Servico_Prometeu_4K",
            "Internet_Lenta",
            "Servidor_Com_Problemas",
            "Servico_Nao_Funcionou",
            "Empresa_Culpou_Internet"
        ],
        "expected_rules": [
            "r1: Internet_Lenta => Servico_Nao_Funciona",
            "r2: Servidor_Com_Problemas => Servico_Nao_Funciona",
            "r3: Empresa_Culpou_Internet => Culpa_Exclusiva_Consumidor (undercuts consumer claim)"
        ],
        "expected_arguments": [
            "A1: [Internet_Lenta, r1] => Servico_Nao_Funciona",
            "A2: [Servidor_Com_Problemas, r2] => Servico_Nao_Funciona",
            "A3: [Empresa_Culpou_Internet, r3] => Culpa_Exclusiva_Consumidor"
        ],
        "expected_attacks": [
            "A1 and A2 are independent causes (overdetermination)"
        ],
        "expected_justified": "Both A1 and A2 (concurrent causes)",
        "expected_cause": "Servidor_Com_Problemas is a cause even if Internet_Lenta is also present"
    },
    {
        "id": 5,
        "name": "Vício de informação - publicidade enganosa",
        "case_text": """
        Comprei um curso online anunciado como 'com certificado reconhecido pelo MEC'. 
        Após concluir, descobri que o certificado não tem reconhecimento oficial. 
        Pedi reembolso mas a empresa disse que eu deveria ter lido os termos de uso.
        """,
        "expected_facts": [
            "Curso_Anunciado_Com_Certificado_MEC",
            "Certificado_Sem_Reconhecimento",
            "Consumidor_Concluiu_Curso",
            "Consumidor_Pediu_Reembolso",
            "Empresa_Alegou_Termos_Uso"
        ],
        "expected_rules": [
            "r1: Curso_Anunciado_Com_Certificado_MEC AND Certificado_Sem_Reconhecimento => Publicidade_Enganosa",
            "r2: Publicidade_Enganosa => Direito_Reembolso",
            "r3: Empresa_Alegou_Termos_Uso => Consumidor_Aceitou_Termos (undercuts r2)"
        ],
        "expected_arguments": [
            "A1: [Curso_Anunciado_Com_Certificado_MEC, Certificado_Sem_Reconhecimento, r1, r2] => Direito_Reembolso",
            "A2: [Empresa_Alegou_Termos_Uso, r3] => Consumidor_Aceitou_Termos"
        ],
        "expected_attacks": [
            "A2 undercuts A1 (but should be defeated - publicidade enganosa prevalece)"
        ],
        "expected_justified": "A1 (CDC protects against misleading advertising regardless of terms)",
        "expected_cause": "Publicidade_Enganosa is a cause-in-fact of Direito_Reembolso"
    }
]


def get_case_by_id(case_id: int):
    """Get a case from the golden dataset by ID."""
    for case in GOLDEN_DATASET:
        if case["id"] == case_id:
            return case
    return None


def get_all_cases():
    """Get all cases from the golden dataset."""
    return GOLDEN_DATASET
