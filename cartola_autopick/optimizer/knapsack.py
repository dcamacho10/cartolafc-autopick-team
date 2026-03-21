import pulp

class TeamOptimizer:
    """Uses Integer Linear Programming (PuLP) to select the optimal team."""

    # Cartola Positions mapping:
    # 1: Goleiro (1)
    # 2: Lateral (2)
    # 3: Zagueiro (2)
    # 4: Meio-campo (Varies, e.g., 3 or 4)
    # 5: Atacante (Varies, e.g., 2 or 3)
    # 6: Técnico (1)
    
    FORMATIONS = {
        "4-3-3": {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 1},
        "4-4-2": {1: 1, 2: 2, 3: 2, 4: 4, 5: 2, 6: 1},
        "3-4-3": {1: 1, 2: 0, 3: 3, 4: 4, 5: 3, 6: 1},
        "3-5-2": {1: 1, 2: 0, 3: 3, 4: 5, 5: 2, 6: 1}
    }

    def __init__(self, budget, strategy="points", formation="4-3-3"):
        self.budget = budget
        self.strategy = strategy
        self.formation_reqs = self.FORMATIONS.get(formation, self.FORMATIONS["4-3-3"])
        
    def optimize(self, player_profiles):
        """
        player_profiles: List of dicts with:
          id, name, position_id, club_id, price, expected_points, status_id.
        """
        # Filter out players that are guaranteed out
        valid_players = [p for p in player_profiles if p['expected_points'] > 0 and p['price'] > 0]
        
        # Create problem
        prob = pulp.LpProblem("CartolaFCMaster", pulp.LpMaximize)
        
        # Decision variables: player_vars[id] is 1 if selected, 0 otherwise
        player_vars = {}
        for p in valid_players:
            player_vars[p['id']] = pulp.LpVariable(f"player_{p['id']}", cat='Binary')
            
        # Objective Function
        if self.strategy == "points":
            prob += pulp.lpSum([p['expected_points'] * player_vars[p['id']] for p in valid_players])
        else:
            # Cartoletas strategy: maximize appreciation probability.
            # Simplified for now: Pick players with very low expected points threshold vs price (Valuation).
            # A real valuation model requires minimum points to appreciate.
            # We'll approximate this by prioritizing players with high previous average and very low current price.
            # Objective: Maximize (Expected Points / Price) * 10
            prob += pulp.lpSum([(p['expected_points'] / p['price'] * 10) * player_vars[p['id']] for p in valid_players])

        # Budget Constraint
        prob += pulp.lpSum([p['price'] * player_vars[p['id']] for p in valid_players]) <= self.budget
        
        # Total Players Constraint (12 including coach)
        prob += pulp.lpSum([player_vars[p['id']] for p in valid_players]) == 12

        # Formation Constraints
        for pos_id, count in self.formation_reqs.items():
            prob += pulp.lpSum([player_vars[p['id']] for p in valid_players if p['position_id'] == pos_id]) == count

        # Solve
        prob.solve(pulp.PULP_CBC_CMD(msg=0))
        
        selected_players = []
        for p in valid_players:
            if player_vars[p['id']].value() == 1.0:
                selected_players.append(p)
                
        return selected_players
