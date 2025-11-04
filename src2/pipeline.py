"""Script principal do pipeline para análise causal de casos jurídicos."""
import json
import os
import logging
from typing import Optional, Dict, Any

import dspy
from dotenv import load_dotenv

from src2.modules import CausalReasoningPipeline
from src2.dataset import GOLDEN_DATASET

# Module logger
logger = logging.getLogger(__name__)


def analyze_case(pipeline: CausalReasoningPipeline, 
                case_data: Dict[str, Any],
                output_dir: str = "outputs") -> Dict[str, Any]:
    """
    Analyze a single case and compare with expected results.
    
    Args:
        pipeline: Configured CausalReasoningPipeline instance
        case_data: Case data from GOLDEN_DATASET
        output_dir: Directory to save results
    
    Returns:
        Dictionary with analysis results and validation
    """
    logger.info(f"📋 Analyzing case {case_data['id']}: {case_data['name']}...")

    # Run analysis (use module(...) instead of .forward(...) per dspy recommendation)
    logger.debug("Starting pipeline for case %s (text preview): %s",
                 case_data['id'],
                 (case_data['case_text'][:200] + '...') if len(case_data['case_text']) > 200 else case_data['case_text'])
    result = pipeline(case_data['case_text'])
    
    # Validate against expected results
    validation = {
        "knowledge_base": {
            "matches": result["knowledge_base"] == case_data["expected_knowledge_base"],
            "expected": case_data["expected_knowledge_base"],
            "got": result["knowledge_base"]
        },
        "causal_model": {
            "matches": result["causal_model"] == case_data["expected_causal_model"],
            "expected": case_data["expected_causal_model"],
            "got": result["causal_model"]
        },
            "causal_results": {
                # expected entries can be booleans or dicts like {"is_cause": bool}
                "matches": all(
                    result["causal_results"].get(cause, {}).get("is_cause") == (
                        expected["is_cause"] if isinstance(expected, dict) else expected
                    )
                    for cause, expected in case_data["expected_causal_result"].items()
                ),
                "expected": case_data["expected_causal_result"],
                "got": result["causal_results"]
            }
    }
    
    # Save detailed results
    output_path = os.path.join(output_dir, f"case_{case_data['id']}_results.json")
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "case": case_data,
            "analysis": result,
            "validation": validation
        }, f, ensure_ascii=False, indent=2)
    
    # Print summary
    logger.info("🔍 Validation Results:")
    for aspect, check in validation.items():
        status = "✅" if check["matches"] else "❌"
        logger.info("%s %s", status, aspect)

    logger.info("💾 Detailed results saved to: %s", output_path)
    
    return {
        "case_id": case_data["id"],
        "name": case_data["name"],
        "validation": validation,
        "output_path": output_path
    }


def main():
    """Main entry point."""
    # Load environment
    load_dotenv()

    # Configure logging early so other modules pick it up
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        log_level = getattr(logging, log_level_name)
    except Exception:
        log_level = logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting pipeline (log level=%s)", log_level_name)

    # Configure DSPy
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️  GEMINI_API_KEY not found in environment")
        print("Example .env file:")
        print("GEMINI_API_KEY=your-api-key-here")
        return
    
    lm = dspy.LM('gemini/gemini-2.5-flash', api_key=api_key, max_tokens=8000)
    dspy.configure(lm=lm)
    
    # Initialize pipeline
    pipeline = CausalReasoningPipeline()
    
    # Lista casos disponíveis
    logger.info("📚 Available cases:")
    for case in GOLDEN_DATASET:
        logger.info("%s. %s", case['id'], case['name'])
    
    # Get user input
    case_id = input("\nEnter case ID to analyze (or press Enter for all): ").strip()
    
    results = []
    if case_id:
        # Analisa um único caso
        case = next((c for c in GOLDEN_DATASET if str(c["id"]) == case_id), None)
        if not case:
            print(f"⚠️  Caso {case_id} não encontrado")
            return
        
        results.append(analyze_case(pipeline, case))
    else:
        # Analisa todos os casos
        for case in GOLDEN_DATASET:
            results.append(analyze_case(pipeline, case))
    
    # Imprime resumo final
    logger.info("📊 Resultados Gerais:")
    successful = sum(1 for r in results 
                    if all(v["matches"] for v in r["validation"].values()))
    logger.info("✅ %s/%s casos passaram em todas as validações", successful, len(results))
    
    # Salva resumo
    summary_path = os.path.join("outputs", "analysis_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_cases": len(results),
            "successful_cases": successful,
            "case_results": results
        }, f, ensure_ascii=False, indent=2)
    
    logger.info("💾 Resumo salvo em: %s", summary_path)


if __name__ == "__main__":
    main()