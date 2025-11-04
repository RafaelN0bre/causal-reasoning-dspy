"""Argumentation solver based on ASPIC+ for causal reasoning."""
import json
import logging

from itertools import product
from typing import Dict, List, Set, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ASPIC+")


class Literal:
    """A literal in the logical language, can be positive or negative."""
    def __init__(self, name: str):
        """Initialize a literal with its name (including ¬ if negative)."""
        self.name = name
        self.is_negative = name.startswith("¬")
        self.base_name = name[1:] if self.is_negative else name
    
    def negate(self) -> 'Literal':
        """Return the negation of this literal."""
        return Literal(f"¬{self.base_name}" if not self.is_negative else self.base_name)
    
    def __str__(self) -> str:
        return self.name
    
    def __eq__(self, other) -> bool:
        return isinstance(other, Literal) and self.name == other.name
    
    def __hash__(self) -> int:
        return hash(self.name)


class Rule:
    """A rule (strict or defeasible) in the argumentation system."""
    def __init__(self, id: str, antecedents: List[str], consequent: str, 
                 is_strict: bool = False, preference: float = 0.5):
        """
        Initialize a rule with its ID, antecedents, and consequent.
        
        Args:
            id: Rule identifier (e.g., "r0" or "rS0")
            antecedents: List of literal strings that must hold for rule to apply
            consequent: The conclusion that follows from the antecedents
            is_strict: True if this is a strict rule (->), False if defeasible (=>)
            preference: Value between 0 and 1 indicating rule strength/preference
        """
        self.id = id
        self.antecedents = antecedents
        self.consequent = consequent
        self.is_strict = is_strict
        self.is_undercutter = consequent.startswith("¬r")  # e.g., "¬r1"
        self.preference = preference  # Higher value = stronger rule
    
    def __str__(self) -> str:
        ant_str = " AND ".join(self.antecedents)
        arrow = "->" if self.is_strict else "=>"
        return f"{self.id}: {ant_str} {arrow} {self.consequent}"


class Argument:
    """An argument in the ASPIC+ framework."""
    def __init__(self, id: str, premises: List[str], 
                 strict_rules: List[str], defeasible_rules: List[str],
                 conclusion: str, sub_arguments: List['Argument'] = None,
                 strength: float = None):
        """
        Initialize an argument with its structure.
        
        Args:
            id: Unique identifier for the argument
            premises: List of literals used as premises
            strict_rules: List of strict rule IDs used in the argument
            defeasible_rules: List of defeasible rule IDs used
            conclusion: The final conclusion of the argument
            sub_arguments: List of supporting sub-arguments
            strength: Calculated strength of argument (based on rule preferences)
        """
        self.id = id
        self.premises = premises
        self.strict_rules = strict_rules
        self.defeasible_rules = defeasible_rules
        self.conclusion = conclusion
        self.sub_arguments = sub_arguments or []
        # Argument strength is the minimum preference value of its defeasible rules
        # Strict rules don't affect strength since they're uncontestable
        self.strength = strength
        self.sub_arguments = sub_arguments or []
    
    def __str__(self) -> str:
        return f"{self.id}: [{', '.join(self.premises)}] => {self.conclusion}"


class Attack:
    """Represents an attack between arguments."""
    def __init__(self, attacker_id: str, target_id: str, 
                 attack_type: str, rule_id: Optional[str] = None,
                 attacked_literal: Optional[str] = None):
        """
        Initialize an attack relationship.
        
        Args:
            attacker_id: ID of the attacking argument
            target_id: ID of the attacked argument
            attack_type: One of "rebut", "undercut", or "undermine"
            rule_id: ID of attacked rule (for undercut)
            attacked_literal: The literal being attacked (for rebut/undermine)
        """
        self.attacker_id = attacker_id
        self.target_id = target_id
        self.attack_type = attack_type
        self.rule_id = rule_id
        self.attacked_literal = attacked_literal
    
    def __str__(self) -> str:
        if self.attack_type == "undercut":
            return f"{self.attacker_id} undercuts {self.target_id} on rule {self.rule_id}"
        elif self.attack_type == "rebut":
            return f"{self.attacker_id} rebuts {self.target_id} on {self.attacked_literal}"
        else:  # undermine
            return f"{self.attacker_id} undermines {self.target_id} on {self.attacked_literal}"


class Defeat:
    """Represents a successful attack that becomes a defeat based on preferences."""
    def __init__(self, attack: Attack, attacker_strength: float, 
                 target_strength: float):
        """
        Initialize a defeat relationship.
        
        Args:
            attack: The underlying attack that becomes a defeat
            attacker_strength: Preference value of attacking argument
            target_strength: Preference value of target argument
        """
        self.attack = attack
        self.attacker_strength = attacker_strength
        self.target_strength = target_strength
    
    def get_explanation(self) -> str:
        """
        Generate a human-readable explanation of why the attack succeeds as a defeat,
        following ASPIC+ semantics for each attack type.
        """
        base = str(self.attack)
        
        if self.attack.attack_type == "undercut":
            return (f"{base} (succeeds by definition as it challenges "
                   f"rule applicability, strengths: {self.attacker_strength:.2f} vs {self.target_strength:.2f})")
            
        elif self.attack.attack_type == "rebut":
            return (f"{base} (succeeds due to strictly stronger argument: "
                   f"{self.attacker_strength:.2f} > {self.target_strength:.2f})")
            
        else:  # undermine
            return (f"{base} (succeeds by definition as ordinary premises "
                   f"cannot defend against attacks)")


class ArgumentationFramework:
    """Main class implementing argument construction and defeat computation."""

    def __init__(self, knowledge_base: Dict, causal_model: Dict):
        """
        Initialize with knowledge, rules and preferences.
        
        Args:
            knowledge_base: Dictionary with premises, axioms, etc.
            causal_model: Dictionary with strict rules, defeasible rules, 
                         undercutter rules, and preference values
        """
        logger.info("Initializing ArgumentationFramework...")
        
        # Initialize knowledge base (K)
        self.premises = {Literal(p) for p in knowledge_base.get("premises", [])}  # Kp
        self.axioms = {Literal(a) for a in knowledge_base.get("axioms", [])}      # Kn
        logger.info(f"Loaded knowledge base: {len(self.premises)} premises, {len(self.axioms)} axioms")
        
        # Initialize rule sets (R = Rs ∪ Rd)
        self.rules: Dict[str, Rule] = {}
        self.strict_rules: Dict[str, Rule] = {}     # Rs
        self.defeasible_rules: Dict[str, Rule] = {} # Rd
        self.undercutter_rules: Dict[str, Rule] = {} # Ru ⊆ Rd
        
        # Initialize preference handling
        self.rule_preferences = knowledge_base.get("preferences", {})
        self.strength_aggregation = knowledge_base.get("aggregation", "min")
        if self.strength_aggregation not in ["min", "last"]:
            raise ValueError("Strength aggregation must be either 'min' (weakest link) or 'last' (last link)")
        
        # Arguments and attacks
        self.arguments: Dict[str, Argument] = {}
        self.attacks: List[Attack] = []
        self.defeats: List[Defeat] = []
        self._argument_signatures: Set[Tuple] = set()  # Cache for unique arguments
        
        # Process all rules and construct framework
        self._parse_rules(knowledge_base, causal_model)
        self._construct_arguments()
        self._identify_attacks()
        self._compute_defeats()
    
    def _parse_rule(self, rule_str: str) -> Tuple[List[str], str]:
        """
        Parse a rule string into antecedents and consequent.
        
        Args:
            rule_str: String in format "id: ant1 AND ant2 => cons"
            
        Returns:
            Tuple of (list of antecedent literals, consequent literal)
        """
        # Remove rule ID from start
        rule_body = rule_str.split(":", 1)[1].strip()
        
        # Split on arrow (handles both -> and =>)
        parts = rule_body.split("=>")
        if len(parts) == 1:  # Try strict arrow
            parts = rule_body.split("->")
            
        if len(parts) != 2:
            raise ValueError(f"Invalid rule format: {rule_str}")
            
        # Get antecedents (split on AND) and consequent
        antecedents = [ant.strip() for ant in parts[0].split("AND")]
        consequent = parts[1].strip()
        
        return antecedents, consequent

    def _parse_rules(self, knowledge_base: Dict, causal_model: Dict):
        logger.info("Parsing rules from causal model...")
        
        # Parse defeasible rules
        defeasible_rules = causal_model.get("defeasible_rules", [])
        logger.info(f"Found {len(defeasible_rules)} defeasible rules")
        for r_str in defeasible_rules:
            rule_id = r_str.split(":")[0].strip()
            ants, cons = self._parse_rule(r_str)
            self.defeasible_rules[rule_id] = Rule(rule_id, ants, cons, is_strict=False)
            logger.debug(f"Parsed defeasible rule: {r_str}")

        # Parse undercutter rules
        undercutter_rules = causal_model.get("undercutter_rules", [])
        logger.info(f"Found {len(undercutter_rules)} undercutter rules")
        for r_str in undercutter_rules:
            rule_id = r_str.split(":")[0].strip()
            ants, cons = self._parse_rule(r_str)
            self.undercutter_rules[rule_id] = Rule(rule_id, ants, cons, is_strict=False)
            logger.debug(f"Parsed undercutter rule: {r_str}")
    
    def _construct_arguments(self):
        """Construct all possible arguments from the knowledge base and rules."""
        logger.info("Starting argument construction...")

        # Create atomic arguments from premises
        logger.info(f"Creating atomic arguments from {len(self.premises)} premises")
        for i, premise in enumerate(self.premises):
            arg_id = f"A{i}"
            self.arguments[arg_id] = Argument(
                id=arg_id,
                premises=[premise.name],
                strict_rules=[],
                defeasible_rules=[],
                conclusion=premise.name
            )
            # Add signature for atomic argument
            sig = (frozenset([premise.name]), premise.name, tuple(), tuple())
            self._argument_signatures.add(sig)
            logger.debug(f"Created atomic argument {arg_id} from premise: {premise.name}")

        # Get all rules
        all_rules = [*self.strict_rules.values(),
                    *self.defeasible_rules.values(),
                    *self.undercutter_rules.values()]
        logger.info(f"Loaded {len(all_rules)} rules total")

        # Safety controls
        MAX_ITER = 1000
        changed = True
        iteration = 0

        while changed and iteration < MAX_ITER:
            iteration += 1
            changed = False
            logger.info(f"Starting iteration {iteration}, current arguments: {len(self.arguments)}")

            # Track conclusions before this iteration
            previous_conclusions = {a.conclusion for a in self.arguments.values()}

            # Try to apply each rule
            for rule in all_rules:
                logger.debug(f"Trying to apply rule: {rule}")
                try:
                    new_args_created = self._apply_rule(rule)
                    if new_args_created:
                        changed = True
                        logger.debug(f"Applied rule {rule.id}, new arguments created")
                except Exception as e:
                    logger.error(f"Error applying rule {rule.id}: {e}")

            # Check if we've reached a fixed point in terms of conclusions
            new_conclusions = {a.conclusion for a in self.arguments.values()}
            if new_conclusions == previous_conclusions:
                logger.info("No new conclusions generated, stopping construction")
                break

        if iteration >= MAX_ITER:
            logger.warning("⚠️ Argument construction stopped after reaching MAX_ITER limit")

    def _apply_rule(self, rule: Rule) -> bool:
        antecedent_args = []
        for ant in rule.antecedents:
            ant_args = [arg for arg in self.arguments.values() if arg.conclusion == ant]
            if not ant_args:
                return False
            antecedent_args.append(ant_args)

        created = False
        for combo in product(*antecedent_args):
            premises = []
            strict_rules, defeasible_rules = [], []
            for a in combo:
                premises.extend(a.premises)
                strict_rules.extend(a.strict_rules)
                defeasible_rules.extend(a.defeasible_rules)

            premises = list(set(premises))  # remove duplicatas
            conclusion = rule.consequent

            # Check argument signature to avoid duplicates
            signature = (frozenset(premises), conclusion,
                        tuple(sorted(defeasible_rules)), tuple(sorted(strict_rules)))
            if signature in self._argument_signatures:
                continue  # Skip if we've seen this argument pattern before

            # Add to signature cache before creating argument
            self._argument_signatures.add(signature)
            
            new_id = f"A{len(self.arguments)}"
            new_arg = Argument(
                id=new_id,
                premises=list(set(premises)),
                strict_rules=strict_rules if rule.is_strict else [],
                defeasible_rules=defeasible_rules + [rule.id] if not rule.is_strict else [],
                conclusion=conclusion,
                sub_arguments=list(combo)
            )
            self.arguments[new_id] = new_arg
            created = True
            logger.debug(f"Created new argument {new_id}: {new_arg}")

        return created
    
    def _identify_attacks(self):
        """
        Identify all attacks between arguments following ASPIC+ attack types:
        - Undermine: Attack on an ordinary premise
        - Undercut: Attack on the applicability of a defeasible rule
        - Rebut: Attack on the conclusion of a defeasible inference
        """
        for attacker in self.arguments.values():
            for target in self.arguments.values():
                # Skip if same argument
                if attacker.id == target.id:
                    continue
                    
                # Check for undermining (attacks on ordinary premises)
                for premise in target.premises:
                    if attacker.conclusion == self._negate_str(premise):
                        self.attacks.append(Attack(
                            attacker.id, target.id, 
                            "undermine", 
                            attacked_literal=premise
                        ))
                
                # Check for undercutting (attacks on rule applicability)
                if attacker.conclusion.startswith("¬r"):
                    target_rule = attacker.conclusion[1:]  # Remove ¬
                    if target_rule in target.defeasible_rules:
                        self.attacks.append(Attack(
                            attacker.id, target.id,
                            "undercut",
                            rule_id=target_rule
                        ))
                
                # Check for rebutting (attacks on conclusions)
                # Only allow rebut on conclusions derived from defeasible rules
                if target.defeasible_rules and \
                   attacker.conclusion == self._negate_str(target.conclusion):
                    self.attacks.append(Attack(
                        attacker.id, target.id,
                        "rebut",
                        attacked_literal=target.conclusion
                    ))
    
    def _negate_str(self, literal: str) -> str:
        """Negate a literal string."""
        return literal[1:] if literal.startswith("¬") else f"¬{literal}"
    
    def _compute_defeats(self):
        """
        Compute which attacks become defeats following ASPIC+ semantics:
        
        1. Undermining: Always succeeds as ordinary premises are attackable by definition
        2. Undercutting: Succeeds regardless of strength as it challenges rule applicability
        3. Rebutting: Succeeds only if attacker is strictly stronger (prevents cycles)
        
        This implementation follows the principle that:
        - Attacks on premises (undermine) are fundamental
        - Attacks on rule applicability (undercut) are structural
        - Attacks on conclusions (rebut) require clear preference
        """
        self.defeats.clear()
        for attack in self.attacks:
            attacker = self.arguments[attack.attacker_id]
            target = self.arguments[attack.target_id]
            
            # Compute argument strengths if not already set
            if attacker.strength is None:
                attacker.strength = self._compute_argument_strength(attacker)
            if target.strength is None:
                target.strength = self._compute_argument_strength(target)
            
            # Apply ASPIC+ defeat conditions
            succeeds = False
            
            if attack.attack_type == "undermine":
                # Undermining always succeeds as ordinary premises can't defend
                succeeds = True
                
            elif attack.attack_type == "undercut":
                # Undercutting succeeds as it challenges rule applicability
                # This follows ASPIC+'s treatment of rule exceptions
                succeeds = True
                
            else:  # rebut
                # Rebutting requires strictly stronger argument
                # Using > instead of >= prevents problematic cycles
                succeeds = attacker.strength > target.strength
            
            if succeeds:
                self.defeats.append(Defeat(attack, attacker.strength, target.strength))
    
    def _compute_argument_strength(self, arg: Argument) -> float:
        """
        Compute argument strength based on its rules' preferences using either
        the weakest link (min) or last link principle.
        
        The weakest link principle (min):
            - Takes the minimum preference value of all defeasible rules
            - Represents that an argument is as strong as its weakest component
        
        The last link principle (last):
            - Uses only the last defeasible rule in the argument's construction
            - Based on the idea that the final step is most critical
            - If no defeasible rules, falls back to strict rule preference
        
        For both:
            - Strict rules have preference 1.0 (indefeasible)
            - Pure premises/axioms have preference 1.0
            - Default preference for unspecified rules is 0.5
        """
        # Handle atomic arguments (just premises/axioms)
        if not (arg.strict_rules or arg.defeasible_rules):
            return 1.0
            
        if self.strength_aggregation == "min":
            # Weakest link principle
            preferences = []
            
            # Strict rules have max preference
            if arg.strict_rules:
                preferences.append(1.0)
            
            # Get all defeasible rule preferences
            for rule_id in arg.defeasible_rules:
                pref = self.rule_preferences.get(rule_id, 0.5)
                preferences.append(pref)
                
            return min(preferences) if preferences else 1.0
            
        else:  # last link principle
            # If there are defeasible rules, use the last one
            if arg.defeasible_rules:
                last_rule = arg.defeasible_rules[-1]
                return self.rule_preferences.get(last_rule, 0.5)
            
            # If only strict rules, use 1.0
            if arg.strict_rules:
                return 1.0
                
            # Fallback (shouldn't happen given previous checks)
            return 1.0

    def compute_grounded_extension(self) -> Tuple[Set[str], Dict[str, List[str]], List[Defeat]]:
        """
        Compute the grounded extension following Dung's definition:
        - The grounded extension is the least fixed point of the defense function
        - It's computed by iteratively applying defense until no new arguments are added
        - This is guaranteed to terminate and produce the unique minimal complete extension
        
        Returns:
            Tuple containing:
            - Set of argument IDs in the grounded extension (minimal complete extension)
            - Dict mapping argument IDs to their supporting arguments
            - List of all defeats (used to explain the extension computation)
        """
        # Ensure defeats are computed
        if not self.defeats:
            self._compute_defeats()
        
        # Start with empty extension
        extension = set()
        explanations = {}
        
        # Compute least fixed point
        while True:
            # Find all arguments defended by current extension
            defended = {
                arg.id for arg in self.arguments.values()
                if self._is_defended(arg.id, extension)
            }
            
            # Try to expand the extension
            new_extension = extension | defended
            
            # Fixed point check
            if new_extension == extension:
                break
                
            extension = new_extension
        
        # Generate explanations for accepted arguments
        for arg_id in extension:
            arg = self.arguments[arg_id]
            explanations[arg_id] = self._get_explanation(arg)
        
        return extension, explanations, self.defeats
    
    def _is_defended(self, arg_id: str, defenders: Set[str]) -> bool:
        """
        Check if an argument is defended by a set of arguments.
        In ASPIC+, this means all its defeaters are defeated by the defenders.
        """
        # Get all defeats against this argument
        defeats_against = [d for d in self.defeats if d.attack.target_id == arg_id]
        
        # For each defeat, check if the attacker is defeated by a defender
        for defeat in defeats_against:
            attacker_defeated = False
            for defender_id in defenders:
                # Check if defender successfully defeats the attacker
                if any(d.attack.attacker_id == defender_id and 
                      d.attack.target_id == defeat.attack.attacker_id 
                      for d in self.defeats):
                    attacker_defeated = True
                    break
            if not attacker_defeated:
                return False
        return True
    
    def _get_attackers(self, arg_id: str) -> List[Argument]:
        """Get all arguments that defeat the given argument."""
        return [
            self.arguments[d.attack.attacker_id]
            for d in self.defeats
            if d.attack.target_id == arg_id
        ]
    
    def _get_explanation(self, arg: Argument) -> List[str]:
        """Get the minimal set of support for an argument."""
        support = set()
        
        def add_support(a: Argument):
            support.add(a.id)
            for sub in (a.sub_arguments or []):
                add_support(sub)
        
        add_support(arg)
        return list(support)
    
    def to_json(self) -> str:
        """Convert the framework to JSON format."""
        return json.dumps({
            "knowledge": {
                "axioms": [ax.name for ax in self.axioms],
                "premises": [p.name for p in self.premises],
                "rules": {
                    "defeasible": [str(r) for r in self.defeasible_rules],
                    "undercutters": [str(r) for r in self.undercutter_rules]
                }
            },
            "arguments": [
                {
                    "id": arg.id,
                    "premises": arg.premises,
                    "rules": arg.rules,
                    "conclusion": arg.conclusion
                }
                for arg in self.arguments.values()
            ],
            "attacks": [
                {
                    "attacker": att.attacker_id,
                    "target": att.target_id,
                    "type": att.attack_type,
                    "rule": att.rule_id
                }
                for att in self.attacks
            ],
            "defeats": [
                {
                    "defeater": d.attack.attacker_id,
                    "defeated": d.attack.target_id,
                    "type": d.attack.attack_type,
                    "explanation": d.get_explanation()
                }
                for d in self.defeats
            ]
        }, indent=2)