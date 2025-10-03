"""
Compliance Plugin - MOCK IMPLEMENTATION
This plugin provides kernel functions for running compliance and risk checks.
"""

import json
from typing import Annotated, Dict, Any
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from operations.compliance_operations import compliance_operations
from utils.logger import console_info, console_error

class CompliancePlugin:
    """
    A Semantic Kernel plugin that simulates running compliance checks on a loan.
    """
    
    def __init__(self, debug: bool = False, session_id: str = None):
        self.debug = debug
        self.session_id = session_id
        self.agent_name = "CompliancePlugin"

    def _log_function_call(self, function_name: str, **kwargs):
        if self.debug:
            log_message = f"[{self.agent_name}] Function: {function_name}, Session: {self.session_id}"
            console_info(log_message, self.agent_name)

    def _send_friendly_notification(self, message: str):
        if self.debug:
            print(message)

    @kernel_function(
        description="""
        Runs a comprehensive set of regulatory compliance and risk checks on a loan.
        
        USE THIS WHEN:
        - You need to verify if a loan meets all regulatory requirements before locking a rate.
        - Rate options have been presented and you are ready for the final pre-lock validation.
        - You need to check for TRID compliance, state-specific laws, and fee reasonableness.
        
        CAPABILITIES:
        - Simulates checks for TRID, state laws, fee tolerance, and disclosure accuracy.
        - Returns a detailed report of all checks performed.
        - Provides an overall pass/fail status.
        
        COMMON USE CASES:
        - "Run compliance check on loan LA12345"
        - "Verify regulatory compliance for the loan with the provided data"
        - "Perform the final risk and compliance assessment before locking the rate"
        """
    )
    async def run_compliance_assessment(self, loan_data_json: Annotated[str, "A JSON string containing the full loan lock record, including LOS data and rate options."]) -> Annotated[str, "A JSON string with the compliance assessment results."]:
        
        self._log_function_call("run_compliance_assessment")
        
        try:
            loan_data = json.loads(loan_data_json)
            loan_id = loan_data.get('loan_application_id', 'Unknown Loan')
            self._send_friendly_notification(f"⚖️ Running compliance assessment for loan {loan_id}...")

            if not loan_data:
                return json.dumps({"success": False, "error": "loan_data_json is required."})

            results = await compliance_operations.run_compliance_check(loan_data)
            
            self._send_friendly_notification(f"✅ Compliance assessment complete. Status: {results.get('overall_status')}")
            return json.dumps({"success": True, "data": results})

        except json.JSONDecodeError:
            return json.dumps({"success": False, "error": "Invalid JSON format for loan_data_json."})
        except Exception as e:
            console_error(f"Error running compliance assessment: {str(e)}", self.agent_name)
            self._send_friendly_notification(f"❌ An error occurred during compliance assessment.")
            return json.dumps({"success": False, "error": str(e)})

    async def close(self):
        """Clean up resources."""
        try:
            await compliance_operations.close()
            console_info("Compliance Plugin resources cleaned up.", self.agent_name)
        except Exception as e:
            console_error(f"Error during Compliance Plugin cleanup: {e}", self.agent_name)
