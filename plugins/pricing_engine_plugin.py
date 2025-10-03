"""
Pricing Engine Plugin - MOCK IMPLEMENTATION
This plugin provides kernel functions to interact with a mortgage pricing engine.
"""

import json
from typing import Annotated, Dict, Any
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from operations.pricing_engine_operations import pricing_engine_operations
from utils.logger import console_info, console_error

class PricingEnginePlugin:
    """
    A Semantic Kernel plugin that simulates fetching rate quotes from a pricing engine.
    """
    
    def __init__(self, debug: bool = False, session_id: str = None):
        self.debug = debug
        self.session_id = session_id
        self.agent_name = "PricingEnginePlugin"

    def _log_function_call(self, function_name: str, **kwargs):
        if self.debug:
            log_message = f"[{self.agent_name}] Function: {function_name}, Session: {self.session_id}, Params: {kwargs}"
            console_info(log_message, self.agent_name)

    def _send_friendly_notification(self, message: str):
        if self.debug:
            print(message)

    @kernel_function(
        description="""
        Generates multiple rate lock options from a pricing engine based on loan context.
        
        USE THIS WHEN:
        - You need to get interest rate quotes for a specific loan.
        - A borrower is ready to see their available rate options.
        - The loan context has been retrieved and validated.
        
        CAPABILITIES:
        - Connects to pricing systems (e.g., Optimal Blue).
        - Generates multiple rate/point combinations.
        - Calculates estimated monthly payments and APR.
        - Returns quotes with an expiration time due to market volatility.
        
        COMMON USE CASES:
        - "Get rate quotes for loan LA12345"
        - "Generate pricing options based on the provided loan context"
        - "Fetch available interest rates for a borrower with a 780 credit score"
        """
    )
    async def get_rate_options(self, loan_context_json: Annotated[str, "A JSON string containing the detailed loan context, including 'loan_id', 'borrower_credit_score', 'loan_to_value', and 'loan_amount'."]) -> Annotated[str, "A JSON string containing a list of rate quote options, or an error message."]:
        
        self._log_function_call("get_rate_options")
        
        try:
            loan_context = json.loads(loan_context_json)
            loan_id = loan_context.get('loan_id', 'Unknown Loan')
            self._send_friendly_notification(f"💰 Generating rate options for loan {loan_id}...")

            if not loan_context:
                return json.dumps({"success": False, "error": "loan_context_json is required and must be valid JSON."})

            quotes = await pricing_engine_operations.get_rate_quotes(loan_context)
            
            if quotes:
                self._send_friendly_notification(f"✅ Successfully generated {len(quotes)} rate options.")
                return json.dumps({"success": True, "data": quotes})
            else:
                self._send_friendly_notification(f"❌ Could not generate rate options.")
                return json.dumps({"success": False, "error": "Failed to generate rate quotes from the pricing engine."})

        except json.JSONDecodeError:
            return json.dumps({"success": False, "error": "Invalid JSON format for loan_context_json."})
        except Exception as e:
            console_error(f"Error getting rate options: {str(e)}", self.agent_name)
            self._send_friendly_notification(f"❌ An error occurred while generating rate options.")
            return json.dumps({"success": False, "error": str(e)})

    async def close(self):
        """Clean up resources."""
        try:
            await pricing_engine_operations.close()
            console_info("Pricing Engine Plugin resources cleaned up.", self.agent_name)
        except Exception as e:
            console_error(f"Error during Pricing Engine Plugin cleanup: {e}", self.agent_name)
