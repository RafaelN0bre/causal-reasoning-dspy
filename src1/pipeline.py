"""Main pipeline script that orchestrates the complete causal reasoning process."""
import json
import os
from typing import Dict, Any
import dspy
from dotenv import load_dotenv

from src1.modules import CausalReasoningPipeline
from src1.solver import Argument, Attack, ArgumentationFramework
from src1.dataset import GOLDEN_DATASET


def parse_arguments_and_attacks(json_str: str) -> tuple[list[Argument], list[Attack]]:
    """Parse JSON string into Argument and Attack objects."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback: create a simple default structure
        print("Warning: Could not parse arguments JSON, using fallback")
        return [], []
    
    arguments = []
    for arg_data in data.get("arguments", []):
        arg = Argument(
            id=arg_data["id"],
            premises=arg_data.get("premises", []),
            conclusion=arg_data["conclusion"]
        )
        arguments.append(arg)
    
    attacks = []
    for attack_data in data.get("attacks", []):
        attack = Attack(
            attacker=attack_data["attacker"],
            target=attack_data["target"],
            attack_type=attack_data.get("type", "rebut")
        )
        attacks.append(attack)
    
    return arguments, attacks


def run_causal_reasoning_pipeline(case_text: str, potential_cause: str = None, 
                                  target_conclusion: str = "Dever_Reparo") -> Dict[str, Any]:
    """
    Run the complete causal reasoning pipeline.
    
    Args:
        case_text: Description of the consumer law case
        potential_cause: The fact to evaluate as a cause (if None, will be inferred)
        target_conclusion: The conclusion to evaluate (default: "Dever_Reparo")
    
    Returns:
        Dictionary with complete analysis results
    """
    # Initialize pipeline
    pipeline = CausalReasoningPipeline()
    
    print("=" * 80)
    print("CAUSAL REASONING PIPELINE")
    print("=" * 80)
    print(f"\n📋 Case: {case_text[:100]}...\n")
    
    # Step 1-3: Extract facts, rules, and generate arguments (DSPy)
    print("🔍 Step 1-3: Extracting facts, rules, and generating arguments...")
    result = pipeline.forward(case_description=case_text, target_conclusion=target_conclusion)
    
    print(f"\n✅ Facts: {result['structured_facts']}")
    print(f"\n✅ Rules:\n{result['causal_rules']}")
    print(f"\n✅ Arguments & Attacks:\n{result['arguments_and_attacks']}")
    
    # Step 4: Parse and solve with argumentation framework
    print("\n⚖️  Step 4: Computing grounded extension (justified arguments)...")
    arguments, attacks = parse_arguments_and_attacks(result['arguments_and_attacks'])
    
    if not arguments:
        print("⚠️  No arguments generated. Creating fallback analysis...")
        return {
            "case_text": case_text,
            "structured_facts": result['structured_facts'],
            "causal_rules": result['causal_rules'],
            "arguments": [],
            "justified_arguments": [],
            "causal_explanation": "Não foi possível gerar argumentos para este caso."
        }
    
    af = ArgumentationFramework(arguments, attacks)
    grounded, support_sets = af.compute_grounded_extension()
    
    print(f"\n✅ Justified arguments: {list(grounded)}")
    
    # Step 5: Generate causal explanation
    print("\n📝 Step 5: Generating causal explanation...")
    
    if not grounded:
        explanation = "Nenhum argumento foi justificado. Não há causa-em-fato estabelecida."
    else:
        # Pick the first justified argument
        justified_arg_id = list(grounded)[0]
        justified_arg = af.arguments[justified_arg_id]
        support = support_sets.get(justified_arg_id, [])
        
        # Infer potential cause if not provided
        if not potential_cause and justified_arg.premises:
            potential_cause = justified_arg.premises[0]
        
        support_str = ", ".join([af.arguments[s].id for s in support])
        
        explanation = pipeline.explain_causation(
            case_description=case_text,
            justified_argument=str(justified_arg),
            support_set=support_str,
            potential_cause=potential_cause or "Unknown"
        )
    
    print(f"\n✅ Causal Explanation:\n{explanation}")
    
    print("\n" + "=" * 80)
    
    return {
        "case_text": case_text,
        "structured_facts": result['structured_facts'],
        "causal_rules": result['causal_rules'],
        "arguments": [str(arg) for arg in arguments],
        "attacks": [str(att) for att in attacks],
        "justified_arguments": list(grounded),
        "support_sets": {k: [str(af.arguments[s]) for s in v] for k, v in support_sets.items()},
        "causal_explanation": explanation
    }


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Configure DSPy with Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️  GEMINI_API_KEY not found in environment. Please set it in .env file.")
        print("Example .env file:")
        print("GEMINI_API_KEY=your-api-key-here")
        return
    
    lm = dspy.LM('gemini/gemini-2.5-flash', api_key=api_key)
    dspy.configure(lm=lm)
    
    # Let user choose a case from the dataset
    print("\n📚 Available cases in the dataset:")
    for case in GOLDEN_DATASET:
        print(f"{case['id']}. {case['name']}")
    
    case_id = input("\nEnter case ID to analyze (or press Enter for all cases): ").strip()
    
    if case_id:
        # Run single case
        case = next((c for c in GOLDEN_DATASET if str(c['id']) == case_id), None)
        if not case:
            print(f"⚠️  Case ID {case_id} not found in dataset")
            return
        
        result = run_causal_reasoning_pipeline(
            case_text=case['case_text'],
            potential_cause=case['expected_facts'][0]  # Use first expected fact as potential cause
        )
        
        # Save result
        output_file = f"src1/output_analysis_case_{case_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Results saved to {output_file}")
        
        # Compare with expected results
        print("\n🔍 Comparing with expected results:")
        print(f"Expected facts: {case['expected_facts']}")
        print(f"Found facts: {result['structured_facts']}")
        print(f"\nExpected rules: {case['expected_rules']}")
        print(f"Generated rules: {result['causal_rules']}")
        
    else:
        # Run all cases
        all_results = {}
        for case in GOLDEN_DATASET:
            print(f"\n📋 Analyzing case {case['id']}: {case['name']}...")
            
            result = run_causal_reasoning_pipeline(
                case_text=case['case_text'],
                potential_cause=case['expected_facts'][0]
            )
            
            all_results[case['id']] = result
        
        # Save all results
        with open("output_analysis_all_cases.json", "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        
        print("\n💾 Results for all cases saved to output_analysis_all_cases.json")


if __name__ == "__main__":
    main()
