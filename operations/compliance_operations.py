"""
Compliance Operations - MOCK IMPLEMENTATION
This module simulates performing compliance and risk checks on a loan.
"""

import asyncio
import random
from typing import Dict, Any
from utils.logger import console_info

class ComplianceOperations:
    """
    A mock class that simulates running compliance checks.
    """
    
    def __init__(self):
        self.agent_name = "compliance_operations"

    async def run_compliance_check(self, loan_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulates running a series of compliance checks.
        
        Args:
            loan_data: A dictionary containing the full loan lock record.
            
        Returns:
            A dictionary with the compliance check results.
        """
        loan_id = loan_data.get('loan_application_id', 'Unknown')
        console_info(f"Running compliance checks for loan '{loan_id}'...", self.agent_name)
        
        # Simulate network delay/processing time
        await asyncio.sleep(1)
        
        checks = {
            "trid_3_day_rule": {"passed": True, "details": "Initial Loan Estimate sent on time."},
            "state_lending_laws": {"passed": True, "details": "Compliant with CA state laws."},
            "fee_reasonableness": {"passed": True, "details": "Origination fees are within tolerance."},
            "disclosure_accuracy": {"passed": True, "details": "APR and finance charges are accurate."}
        }
        
        # Randomly fail one check for demonstration purposes
        if loan_id == "LA67890": # Pre-determined failure case
            checks["trid_3_day_rule"] = {"passed": False, "details": "Initial Loan Estimate was delivered 1 day late."}
        elif random.random() < 0.1: # 10% chance of random failure
            check_to_fail = random.choice(list(checks.keys()))
            checks[check_to_fail] = {"passed": False, "details": "Randomly generated compliance failure for testing."}

        overall_passed = all(check["passed"] for check in checks.values())
        
        result = {
            "overall_status": "Passed" if overall_passed else "Failed",
            "checks": checks,
            "checked_at": asyncio.get_event_loop().time()
        }
        
        console_info(f"Compliance check for loan '{loan_id}' completed with status: {result['overall_status']}", self.agent_name)
        return result

    async def close(self):
        """Clean up resources (no-op for mock)."""
        console_info("Compliance Operations resources closed (mock).", self.agent_name)
        await asyncio.sleep(0)

# Singleton instance
compliance_operations = ComplianceOperations()
