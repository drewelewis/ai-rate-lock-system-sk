"""
Document Operations - MOCK IMPLEMENTATION
This module simulates generating documents.
"""

import asyncio
from typing import Dict, Any
from datetime import datetime
from utils.logger import console_info

class DocumentOperations:
    """
    A mock class that simulates generating documents.
    """
    
    def __init__(self):
        self.agent_name = "document_operations"

    async def generate_lock_confirmation_document(self, loan_data: Dict[str, Any], lock_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulates generating a rate lock confirmation document.
        
        Args:
            loan_data: A dictionary containing the loan context.
            lock_details: A dictionary containing the confirmed lock details.
            
        Returns:
            A dictionary representing the generated document.
        """
        loan_id = loan_data.get('loan_application_id', 'Unknown')
        console_info(f"Generating lock confirmation document for loan '{loan_id}'...", self.agent_name)
        
        # Simulate processing time
        await asyncio.sleep(0.5)
        
        document_id = f"DOC-LC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        content = f"""
        -----------------------------------------
        RATE LOCK CONFIRMATION
        -----------------------------------------
        Date: {datetime.utcnow().strftime('%Y-%m-%d')}
        
        Loan Application ID: {loan_id}
        Borrower: {loan_data.get('los_data', {}).get('borrower_info', {}).get('name', 'N/A')}
        
        Your rate has been successfully locked with the following terms:
        
        - Interest Rate: {lock_details.get('interest_rate')}%
        - Lock Period: {lock_details.get('lock_period_days')} days
        - Lock Expiration Date: {lock_details.get('lock_expiration_date')}
        - Product: {lock_details.get('product_description', 'N/A')}
        
        This confirmation is a legally binding agreement.
        
        Confirmation ID: {lock_details.get('confirmation_id')}
        Document ID: {document_id}
        -----------------------------------------
        """
        
        document = {
            "document_id": document_id,
            "document_type": "RateLockConfirmation",
            "content": content.strip(),
            "format": "text",
            "created_at": datetime.utcnow().isoformat()
        }
        
        console_info(f"Successfully generated document '{document_id}' for loan '{loan_id}'.", self.agent_name)
        return document

    async def close(self):
        """Clean up resources (no-op for mock)."""
        console_info("Document Operations resources closed (mock).", self.agent_name)
        await asyncio.sleep(0)

# Singleton instance
document_operations = DocumentOperations()
