class SecondaryOptimizer:
    """Handles Captain selection and Bench selection."""

    def select_captain(self, selected_team):
        """
        Selects the captain. Usually the player with highest expected points.
        Returns the updated team (one item gets 'is_captain': True).
        """
        if not selected_team:
            return None
            
        # Exclude coach from captaincy (position_id == 6)
        field_players = [p for p in selected_team if p['position_id'] != 6]
        
        if not field_players:
            return None
            
        best_candidate = max(field_players, key=lambda x: x['expected_points'])
        
        for p in selected_team:
            if p['id'] == best_candidate['id']:
                p['is_captain'] = True
            else:
                p['is_captain'] = False
                
        return selected_team

    def select_bench(self, all_profiles, selected_team, remaining_budget, formation="4-3-3"):
        """
        Selects 1 substitute per position based on the cheapest viable option under remaining budget.
        Cartola rule: Bench player must be cheaper than ALL selected players in that position.
        """
        from .knapsack import TeamOptimizer
        formation_reqs = TeamOptimizer.FORMATIONS.get(formation, TeamOptimizer.FORMATIONS["4-3-3"])
        
        selected_ids = {p['id'] for p in selected_team}
        available = [p for p in all_profiles if p['id'] not in selected_ids and p['expected_points'] > 0]
        
        bench = []
        current_budget = remaining_budget
        
        for pos_id, count in formation_reqs.items():
            if count == 0 or pos_id == 6: # No bench for coach or empty positions
                continue
                
            # Find cheapest player in starting 11 for this position
            starters_pos = [p for p in selected_team if p['position_id'] == pos_id]
            if not starters_pos: continue
            min_starter_price = min([p['price'] for p in starters_pos])
            
            # Find candidate bench players
            candidates = [p for p in available if p['position_id'] == pos_id and p['price'] < min_starter_price and p['price'] <= current_budget]
            
            if candidates:
                # Pick the highest expected points among valid candidates
                best_sub = max(candidates, key=lambda x: x['expected_points'])
                bench.append(best_sub)
                current_budget -= best_sub['price']
                
        return bench
