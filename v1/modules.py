"""DSPy modules for the causal reasoning pipeline."""
import json
import dspy
from .signatures import (
    TextToFacts,
    FactsToRules,
    GenerateArgumentsAndAttacks,
    CausalJudgement
)


class CausalReasoningPipeline(dspy.Module):
    """Complete pipeline for causal reasoning in legal cases."""
    
    def __init__(self):
        super().__init__()
        self.text_to_facts = dspy.ChainOfThought(TextToFacts)
        self.facts_to_rules = dspy.ChainOfThought(FactsToRules)
        self.generate_arguments = dspy.ChainOfThought(GenerateArgumentsAndAttacks)
        self.causal_judgement = dspy.ChainOfThought(CausalJudgement)
    
    def forward(self, case_description: str, target_conclusion: str = "Dever_Reparo"):
        """
        Run the complete pipeline.
        
        Args:
            case_description: Text description of the consumer law case
            target_conclusion: The conclusion we want to evaluate (default: "Dever_Reparo")
        
        Returns:
            Dict with facts, rules, arguments, attacks, and final judgment
        """
        # Step 1: Extract facts
        facts_result = self.text_to_facts(case_description=case_description)
        structured_facts = facts_result.structured_facts
        
        # Step 2: Identify causal rules
        rules_result = self.facts_to_rules(structured_facts=structured_facts)
        causal_rules = rules_result.causal_rules
        
        # Step 3: Generate arguments and attacks
        args_result = self.generate_arguments(
            structured_facts=structured_facts,
            causal_rules=causal_rules,
            target_conclusion=target_conclusion
        )
        
        return {
            "structured_facts": structured_facts,
            "causal_rules": causal_rules,
            "arguments_and_attacks": args_result.arguments_and_attacks,
            "reasoning": {
                "facts_reasoning": getattr(facts_result, 'reasoning', None),
                "rules_reasoning": getattr(rules_result, 'reasoning', None),
                "args_reasoning": getattr(args_result, 'reasoning', None),
            }
        }
    
    def explain_causation(self, case_description: str, justified_argument: str, 
                         support_set: str, potential_cause: str):
        """
        Generate final causal explanation.
        
        Args:
            case_description: Original case text
            justified_argument: The justified argument from the solver
            support_set: Minimal support set for the argument
            potential_cause: The fact being evaluated as a cause
        
        Returns:
            Causal explanation
        """
        result = self.causal_judgement(
            justified_argument=justified_argument,
            support_set=support_set,
            potential_cause=potential_cause,
            case_description=case_description
        )
        return result.causal_explanation
