"""
Pricing Engine Operations - MOCK IMPLEMENTATION
This module simulates interactions with a mortgage pricing engine like Optimal Blue.
"""

import asyncio
import random
from typing import Dict, Any, List
from datetime import datetime, timedelta
from utils.logger import console_info, console_error

class PricingEngineOperations:
    """
    A mock class that simulates fetching rate quotes from a pricing engine.
    """
    
    def __init__(self):
        self.agent_name = "pricing_engine_operations"

    async def get_rate_quotes(self, loan_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Simulates fetching rate quotes based on loan context.
        
        Args:
            loan_context: A dictionary containing loan details like amount, LTV, credit score.
            
        Returns:
            A list of dictionaries, each representing a rate quote option.
        """
        console_info(f"Fetching rate quotes for loan '{loan_context.get('loan_id')}'...", self.agent_name)
        
        # Simulate network delay
        await asyncio.sleep(1.5)
        
        try:
            credit_score = loan_context.get("borrower_credit_score", 700)
            ltv = loan_context.get("loan_to_value", 80.0)
            
            # Simulate rate adjustments based on risk
            base_rate = 6.5
            rate_adjustment = (780 - credit_score) / 100 + (ltv - 80) / 20
            final_base_rate = base_rate + rate_adjustment
            
            quotes = []
            for i in range(3):
                rate = final_base_rate + (i * 0.125)
                points = 1.5 - (i * 0.5) - (rate_adjustment / 4)
                
                quotes.append({
                    "quote_id": f"Q-{random.randint(10000, 99999)}",
                    "interest_rate": round(rate, 3),
                    "points": round(points, 3),
                    "lock_period_days": loan_context.get("requested_lock_period", 30),
                    "monthly_payment": self._calculate_monthly_payment(loan_context.get("loan_amount", 0), rate),
                    "apr": round(rate + (points / 5), 3), # Simplified APR calculation
                    "expires_at": (datetime.utcnow() + timedelta(hours=4)).isoformat()
                })
            
            console_info(f"Generated {len(quotes)} rate quotes.", self.agent_name)
            return quotes
            
        except Exception as e:
            console_error(f"Failed to generate rate quotes: {e}", self.agent_name)
            return []

    def _calculate_monthly_payment(self, principal: float, annual_rate: float) -> float:
        """Calculates the monthly mortgage payment."""
        if principal <= 0 or annual_rate <= 0:
            return 0.0
            
        monthly_rate = (annual_rate / 100) / 12
        term_in_months = 360 # Assuming 30-year fixed
        
        if monthly_rate == 0:
            return principal / term_in_months
            
        payment = principal * (monthly_rate * (1 + monthly_rate)**term_in_months) / ((1 + monthly_rate)**term_in_months - 1)
        return round(payment, 2)

    async def close(self):
        """Clean up resources (no-op for mock)."""
        console_info("Pricing Engine Operations resources closed (mock).", self.agent_name)
        await asyncio.sleep(0)

# Singleton instance
pricing_engine_operations = PricingEngineOperations()
