"""
Loan Origination System (LOS) Operations - MOCK IMPLEMENTATION
This module simulates interactions with a Loan Origination System like Encompass or Blend.
In a real-world scenario, this would involve API calls to the LOS.
"""

import asyncio
from typing import Dict, Any, Optional
from utils.logger import console_info, console_error

class LOSOperations:
    """
    A mock class that simulates fetching data from a Loan Origination System.
    """
    
    def __init__(self):
        self.agent_name = "los_operations"
        # Mock database of loan applications
        self._mock_loan_data = {
            "LA12345": {
                "loan_id": "LA12345",
                "borrower_name": "John Doe",
                "borrower_credit_score": 780,
                "property_value": 500000,
                "loan_amount": 400000,
                "loan_to_value": 80.0,
                "debt_to_income": 35.0,
                "loan_status": "Pre-Approved",
                "documentation_status": "Complete",
                "is_eligible_for_lock": True
            },
            "LA67890": {
                "loan_id": "LA67890",
                "borrower_name": "Jane Smith",
                "borrower_credit_score": 650,
                "property_value": 300000,
                "loan_amount": 280000,
                "loan_to_value": 93.3,
                "debt_to_income": 48.0,
                "loan_status": "Application",
                "documentation_status": "Incomplete",
                "is_eligible_for_lock": False,
                "reason_for_ineligibility": "Debt-to-income ratio too high; missing income verification documents."
            }
        }

    async def get_loan_application_details(self, loan_application_id: str) -> Optional[Dict[str, Any]]:
        """
        Simulates fetching detailed loan application data from an LOS.
        
        Args:
            loan_application_id: The ID of the loan application to fetch.
            
        Returns:
            A dictionary with loan details or None if not found.
        """
        console_info(f"Fetching details for loan application '{loan_application_id}' from LOS...", self.agent_name)
        
        # Simulate network delay
        await asyncio.sleep(1)
        
        # Check if it's in our static mock data
        if loan_application_id in self._mock_loan_data:
            console_info(f"Successfully fetched details for loan '{loan_application_id}'", self.agent_name)
            return self._mock_loan_data[loan_application_id]
        
        # For APP-* pattern loans (from email intake), generate dynamic mock data
        if loan_application_id.startswith("APP-"):
            console_info(f"Generating dynamic mock data for loan '{loan_application_id}'", self.agent_name)
            # Extract numeric portion for pseudo-random variation
            try:
                loan_num = int(loan_application_id.split("-")[1])
                
                # Use modulo to create variation in data
                credit_score = 650 + (loan_num % 15) * 10  # Range: 650-790
                ltv = 70 + (loan_num % 25)  # Range: 70-95
                dti = 28 + (loan_num % 25)  # Range: 28-53
                is_eligible = (credit_score >= 680 and ltv <= 90 and dti <= 45)
                
                return {
                    "loan_id": loan_application_id,
                    "borrower_name": f"Borrower for {loan_application_id}",
                    "borrower_credit_score": credit_score,
                    "property_value": 500000,
                    "loan_amount": 400000,
                    "loan_to_value": ltv,
                    "debt_to_income": dti,
                    "loan_status": "Pre-Approved" if is_eligible else "Application",
                    "documentation_status": "Complete" if is_eligible else "Incomplete",
                    "is_eligible_for_lock": is_eligible,
                    "reason_for_ineligibility": None if is_eligible else "Credit score, LTV, or DTI requirements not met."
                }
            except (ValueError, IndexError):
                console_error(f"Invalid APP-* loan ID format: '{loan_application_id}'", self.agent_name)
                return None
        
        # Not found in static data and doesn't match APP-* pattern
        console_error(f"Loan application '{loan_application_id}' not found in LOS.", self.agent_name)
        return None

    async def close(self):
        """Clean up resources (no-op for mock)."""
        console_info("LOS Operations resources closed (mock).", self.agent_name)
        await asyncio.sleep(0)

# Singleton instance
los_operations = LOSOperations()
