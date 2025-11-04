"""Simple argumentation framework solver for computing grounded extension."""
from typing import List, Dict, Set, Tuple


class Argument:
    """Represents an argument in the argumentation framework."""
    
    def __init__(self, id: str, premises: List[str], conclusion: str):
        self.id = id
        self.premises = premises
        self.conclusion = conclusion
    
    def __repr__(self):
        return f"Argument({self.id}: {self.premises} => {self.conclusion})"
    
    def __eq__(self, other):
        return isinstance(other, Argument) and self.id == other.id
    
    def __hash__(self):
        return hash(self.id)


class Attack:
    """Represents an attack between arguments."""
    
    def __init__(self, attacker: str, target: str, attack_type: str = "rebut"):
        self.attacker = attacker
        self.target = target
        self.attack_type = attack_type  # 'rebut' or 'undercut'
    
    def __repr__(self):
        return f"Attack({self.attacker} --{self.attack_type}-> {self.target})"


class ArgumentationFramework:
    """Argumentation Framework (AF) with grounded extension computation."""
    
    def __init__(self, arguments: List[Argument], attacks: List[Attack]):
        self.arguments = {arg.id: arg for arg in arguments}
        self.attacks = attacks
        self._build_attack_relations()
    
    def _build_attack_relations(self):
        """Build attack relations for efficient lookup."""
        self.attackers = {}  # target -> list of attackers
        self.attacked_by = {}  # attacker -> list of targets
        
        for attack in self.attacks:
            if attack.target not in self.attackers:
                self.attackers[attack.target] = []
            self.attackers[attack.target].append(attack.attacker)
            
            if attack.attacker not in self.attacked_by:
                self.attacked_by[attack.attacker] = []
            self.attacked_by[attack.attacker].append(attack.target)
    
    def compute_grounded_extension(self) -> Tuple[Set[str], Dict[str, List[str]]]:
        """
        Compute the grounded extension using a fixed-point algorithm.
        Returns: (grounded_extension, support_sets)
        """
        # Start with empty set
        grounded = set()
        defeated = set()
        
        # Iterate until fixed point
        changed = True
        while changed:
            changed = False
            
            for arg_id in self.arguments.keys():
                if arg_id in grounded or arg_id in defeated:
                    continue
                
                # Check if all attackers are defeated
                attackers = self.attackers.get(arg_id, [])
                if all(attacker in defeated for attacker in attackers):
                    grounded.add(arg_id)
                    changed = True
                    
                    # Mark all arguments attacked by this one as defeated
                    for target in self.attacked_by.get(arg_id, []):
                        if target not in defeated:
                            defeated.add(target)
                            changed = True
        
        # Compute support sets (minimal explanations)
        support_sets = self._compute_support_sets(grounded)
        
        return grounded, support_sets
    
    def _compute_support_sets(self, grounded: Set[str]) -> Dict[str, List[str]]:
        """
        Compute minimal support sets for each justified argument.
        A support set is the minimal set of arguments needed to justify an argument.
        """
        support_sets = {}
        
        for arg_id in grounded:
            # For simplicity, the support set includes the argument itself
            # and any arguments it depends on (via premises)
            support = {arg_id}
            arg = self.arguments[arg_id]
            
            # Add arguments corresponding to premises
            for premise in arg.premises:
                # Find arguments that conclude this premise
                for other_id, other_arg in self.arguments.items():
                    if other_arg.conclusion == premise and other_id in grounded:
                        support.add(other_id)
            
            support_sets[arg_id] = list(support)
        
        return support_sets
    
    def get_justified_arguments(self) -> List[Argument]:
        """Get all justified (grounded) arguments."""
        grounded, _ = self.compute_grounded_extension()
        return [self.arguments[arg_id] for arg_id in grounded]
    
    def explain_justification(self, arg_id: str) -> Dict:
        """Explain why an argument is justified."""
        grounded, support_sets = self.compute_grounded_extension()
        
        if arg_id not in grounded:
            return {
                "justified": False,
                "reason": "Argument is defeated or not in grounded extension"
            }
        
        support = support_sets.get(arg_id, [])
        attackers = self.attackers.get(arg_id, [])
        defeated_attackers = [a for a in attackers if a not in grounded]
        
        return {
            "justified": True,
            "argument": self.arguments[arg_id],
            "support_set": [self.arguments[s] for s in support],
            "defeated_attackers": [self.arguments[a] for a in defeated_attackers]
        }
