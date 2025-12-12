"""Dataset com casos que demonstram diferentes padrões de raciocínio causal."""

GOLDEN_DATASET = [
    {
        "id": 1,
        "name": "Caso da Leucemia (Omissão)",
        "case_text": """
        Uma criança com leucemia (ChLe) não recebeu quimioterapia (Chem) porque seus pais se recusaram a consentir (¬PaCo).
        Os médicos recomendaram fortemente a quimioterapia. A criança não foi tratada e morreu (ChDi).
        Fonte: Baseado em Cassazione penale (2023) 
        """,
        "expected_knowledge_base": {
            "premises": ["ChLe", "¬PaCo"],
            "potential_causes": ["¬PaCo"],
            "target_conclusion": "ChDi",
            "axioms": []
        },
        "expected_causal_model": {
            "defeasible_rules": [
                "r0: ChLe => ChDi",
                "r1: PaCo => Chem"
            ],
            "undercutter_rules": [
                "r2: Chem => ¬r0"
            ]
        },
        "expected_causal_result": {
            "is_cause": True,
            "explanation": "A omissão do consentimento (¬PaCo) é uma causa da morte (ChDi). " + 
                        "Se uma intervenção fosse feita adicionando 'PaCo'[cite: 343], " +
                        "um novo argumento justificado 'Chem' seria criado (via r1), " + 
                        "que por sua vez ativaria a regra 'r2' para derrotar 'r0'[cite: 344, 345]. " +
                        "Isso bloquearia a conclusão 'ChDi', provando que '¬PaCo' era causal."
        }
    },
    {
        "id": 2,
        "name": "Dlugash Case (Preemption)",
        "case_text": """
        Dlugash atirou em uma vítima (DlKi), mas Bush já havia atirado antes (BuKi) 
        e a vítima já estava morta (ViDe).
        """,
        "expected_knowledge_base": {
            "premises": ["DlKi", "BuKi", "ViDe"],
            "potential_causes": ["DlKi", "BuKi"],
            "target_conclusion": "ViDe"
        },
        "expected_causal_model": {
            "defeasible_rules": [
                "r1: DlKi => ViDe",  # Tiro de Dlugash causa morte
                "r2: BuKi => ViDe"   # Tiro de Bush causa morte
            ],
            "undercutter_rules": [
                "r3: BuKi => ¬r1"    # Tiro prévio de Bush impede causalidade de Dlugash
            ]
        },
        "expected_causal_result": {
            "BuKi": {
                "is_cause": True,
                "explanation": "O tiro de Bush (BuKi) é causa da morte pois foi o primeiro e efetivo."
            },
            "DlKi": {
                "is_cause": False,
                "explanation": "O tiro de Dlugash (DlKi) não é causa da morte pois a vítima já estava morta."
            }
        }
    },
    {
        "id": 3,
        "name": "Celular à Prova D'água (Consumer Law)",
        "case_text": """
        Um celular anunciado como à prova d'água (PhWp) caiu na piscina (PoFa) e parou de funcionar.
        A empresa alega mau uso (MiUs), mas cair na piscina é um uso normal para um celular à prova d'água (NoUs).
        """,
        "expected_knowledge_base": {
            "premises": ["PhWp", "PoFa", "MiUs", "NoUs"],
            "potential_causes": ["PhWp", "PoFa"],
            "target_conclusion": "PrLi"  # Product Liability
        },
        "expected_causal_model": {
            "defeasible_rules": [
                "r1: PhWp AND PoFa => PrLi",     # Falha do produto à prova d'água gera responsabilidade
                "r2: MiUs => ¬PrLi"              # Mau uso exclui responsabilidade
            ],
            "undercutter_rules": [
                "r3: NoUs => ¬r2"                # Uso normal impede alegação de mau uso
            ]
        },
        "expected_causal_result": {
            "PhWp": {
                "is_cause": True,
                "explanation": "A característica à prova d'água (PhWp) é causa da responsabilidade " +
                             "pois criou a expectativa de funcionamento na água."
            }
        }
    }
]