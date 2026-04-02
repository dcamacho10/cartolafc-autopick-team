class MatchAnalyzer:
    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    """Uses the official Cartola API match data (table positions) to compute Team Strength (1-5)
    and evaluate match equilibrium. Includes mandante/visitante last-five form (v/e/d) from the API."""

    @staticmethod
    def format_form_sequence(aproveitamento):
        """Pretty-print last 5 as V/E/D for UI; aproveitamento is newest-first or oldest-first from API."""
        if not aproveitamento:
            return "—"
        letter = {"v": "V", "e": "E", "d": "D"}
        return "".join(letter.get((x or "").lower()[:1], "?") for x in aproveitamento[:5])

    def compute_strength_from_position(self, position):
        """Calculates a 1-5 score for each team based on their official Cartola ranking position."""
        if not position or position <= 0:
            return 3 # Default to average if unknown
            
        if position <= 4:
            return 5
        elif position <= 8:
            return 4
        elif position <= 12:
            return 3
        elif position <= 16:
            return 2
        else:
            return 1

    def parse_recent_form(self, aproveitamento):
        """Converts an array like ['v', 'e', 'd', 'd', 'v'] into a momentum modifier (-1.0 to +1.0)."""
        if not aproveitamento:
            return 0.0
        score = 0
        for res in aproveitamento:
            if res == 'v': score += 3
            elif res == 'e': score += 1
        # Max score is 15. We map 0 to -1.0, 7.5 to 0.0, 15 to +1.0.
        return ((score / 15.0) * 2.0) - 1.0

    def analyze_match(self, match_dict):
        """
        Analyzes a single match using the team tabletop positions and their recent Home/Away specific form.
        Returns the match difficulty classification.
        """
        home_pos = match_dict.get('clube_casa_posicao', 10)
        away_pos = match_dict.get('clube_visitante_posicao', 10)
        
        home_base = self.compute_strength_from_position(home_pos)
        away_base = self.compute_strength_from_position(away_pos)

        home_form_mod = self.parse_recent_form(match_dict.get('aproveitamento_mandante', []))
        away_form_mod = self.parse_recent_form(match_dict.get('aproveitamento_visitante', []))

        # Add form modifiers to the base position strength
        home_score = round(home_base + home_form_mod, 1)
        away_score = round(away_base + away_form_mod, 1)

        diff = home_score - away_score

        # Generic home advantage plus contextual strength differential.
        adjusted_diff = diff + 0.5

        # Build continuous multipliers so matchup quality has stronger effect on final projection.
        home_multiplier = self._clamp(1.0 + (adjusted_diff * 0.09), 0.75, 1.25)
        away_multiplier = self._clamp(1.0 - (adjusted_diff * 0.09), 0.75, 1.25)

        if abs(adjusted_diff) <= 1.0:
            classification = "equilibrium"
        elif adjusted_diff > 1.0:
            classification = "home_favorite"
        else:
            classification = "away_favorite"

        home_form = match_dict.get("aproveitamento_mandante") or []
        away_form = match_dict.get("aproveitamento_visitante") or []

        return {
            "home_score": home_score,
            "away_score": away_score,
            "classification": classification,
            "home_multiplier": home_multiplier,
            "away_multiplier": away_multiplier,
            "home_form_last5": self.format_form_sequence(home_form),
            "away_form_last5": self.format_form_sequence(away_form),
            "strength_diff": round(diff, 2),
            "adjusted_diff": round(adjusted_diff, 2),
        }
