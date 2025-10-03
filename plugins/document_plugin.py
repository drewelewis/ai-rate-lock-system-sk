"""
Document Plugin - MOCK IMPLEMENTATION
This plugin provides kernel functions for generating documents.
"""

import json
from typing import Annotated, Dict, Any
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from operations.document_operations import document_operations
from utils.logger import console_info, console_error

class DocumentPlugin:
    """
    A Semantic Kernel plugin that simulates generating documents.
    """
    
    def __init__(self, debug: bool = False, session_id: str = None):
        self.debug = debug
        self.session_id = session_id
        self.agent_name = "DocumentPlugin"

    def _log_function_call(self, function_name: str, **kwargs):
        if self.debug:
            log_message = f"[{self.agent_name}] Function: {function_name}, Session: {self.session_id}"
            console_info(log_message, self.agent_name)

    def _send_friendly_notification(self, message: str):
        if self.debug:
            print(message)

    @kernel_function(
        description="""
        Generates a formal rate lock confirmation document.
        
        USE THIS WHEN:
        - A rate lock has been successfully executed and you need to create the official confirmation document.
        - You need to provide a document to be sent as an attachment in a confirmation email.
        
        CAPABILITIES:
        - Creates a formatted text document containing all essential lock details.
        - Returns a document object with content, ID, and metadata.
        
        COMMON USE CASES:
        - "Generate the lock confirmation document for the loan."
        - "Create the official confirmation PDF for the rate lock."
        """
    )
    async def generate_lock_confirmation(
        self, 
        loan_data_json: Annotated[str, "A JSON string of the full loan record."],
        lock_details_json: Annotated[str, "A JSON string of the confirmed lock details."]
    ) -> Annotated[str, "A JSON string representing the generated document object."]:
        
        self._log_function_call("generate_lock_confirmation")
        
        try:
            loan_data = json.loads(loan_data_json)
            lock_details = json.loads(lock_details_json)
            loan_id = loan_data.get('loan_application_id', 'Unknown')
            
            self._send_friendly_notification(f"📄 Generating lock confirmation document for loan {loan_id}...")

            document = await document_operations.generate_lock_confirmation_document(loan_data, lock_details)
            
            self._send_friendly_notification(f"✅ Document '{document.get('document_id')}' generated successfully.")
            return json.dumps({"success": True, "data": document})

        except json.JSONDecodeError as e:
            return json.dumps({"success": False, "error": f"Invalid JSON format: {e}"})
        except Exception as e:
            console_error(f"Error generating document: {str(e)}", self.agent_name)
            self._send_friendly_notification(f"❌ An error occurred while generating the document.")
            return json.dumps({"success": False, "error": str(e)})

    async def close(self):
        """Clean up resources."""
        try:
            await document_operations.close()
            console_info("Document Plugin resources cleaned up.", self.agent_name)
        except Exception as e:
            console_error(f"Error during Document Plugin cleanup: {e}", self.agent_name)
