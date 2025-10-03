"""
Loan Origination System (LOS) Plugin - MOCK IMPLEMENTATION
This plugin provides kernel functions to interact with a Loan Origination System.
"""

import json
from typing import Annotated, Dict, Any
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from operations.los_operations import los_operations
from utils.logger import console_info, console_error

class LoanOriginationSystemPlugin:
    """
    A Semantic Kernel plugin that simulates interactions with a Loan Origination System.
    
    This plugin wraps the mock LOSOperations and exposes its functionality as kernel functions
    that can be used by AI agents.
    """
    
    def __init__(self, debug: bool = False, session_id: str = None):
        self.debug = debug
        self.session_id = session_id
        self.agent_name = "LoanOriginationSystemPlugin"

    def _log_function_call(self, function_name: str, **kwargs):
        """Logs the function call if debug is enabled."""
        if self.debug:
            log_message = f"[{self.agent_name}] Function: {function_name}, Session: {self.session_id}, Params: {kwargs}"
            console_info(log_message, self.agent_name)

    def _send_friendly_notification(self, message: str):
        """Sends a user-friendly notification (prints to console)."""
        if self.debug:
            print(message)

    @kernel_function(
        description="""
        Fetches comprehensive loan application data from the Loan Origination System (LOS).
        
        USE THIS WHEN:
        - You need to retrieve the full context of a loan application.
        - You need to validate a borrower's eligibility for a rate lock.
        - You are enriching a rate lock request with data from the core system.
        
        CAPABILITIES:
        - Retrieves borrower financial information (credit score, DTI).
        - Fetches property details and loan status.
        - Confirms if all required documentation is complete.
        - Returns a flag indicating if the loan is eligible for a rate lock.
        
        COMMON USE CASES:
        - "Get loan details for LA12345"
        - "Check if loan LA67890 is eligible for a rate lock"
        - "Retrieve the context for loan application LA12345"
        """
    )
    async def get_loan_context(self, loan_application_id: Annotated[str, "The unique identifier for the loan application (e.g., 'LA12345')."]) -> Annotated[str, "A JSON string containing the detailed loan context, or an error message."]:
        
        self._log_function_call("get_loan_context", loan_application_id=loan_application_id)
        self._send_friendly_notification(f"🏦 Fetching loan context for {loan_application_id} from the LOS...")
        
        if not loan_application_id:
            return json.dumps({"success": False, "error": "loan_application_id is required"})
            
        try:
            loan_details = await los_operations.get_loan_application_details(loan_application_id)
            
            if loan_details:
                self._send_friendly_notification(f"✅ Successfully retrieved context for {loan_application_id}")
                return json.dumps({"success": True, "data": loan_details})
            else:
                self._send_friendly_notification(f"❌ Loan application {loan_application_id} not found.")
                return json.dumps({"success": False, "error": f"Loan application '{loan_application_id}' not found."})
                
        except Exception as e:
            console_error(f"Error fetching loan context: {str(e)}", self.agent_name)
            self._send_friendly_notification(f"❌ An error occurred while fetching loan context.")
            return json.dumps({"success": False, "error": str(e)})

    async def close(self):
        """Clean up resources when the plugin is no longer needed."""
        try:
            await los_operations.close()
            console_info("LOS Plugin resources cleaned up.", self.agent_name)
        except Exception as e:
            console_error(f"Error during LOS Plugin cleanup: {e}", self.agent_name)
