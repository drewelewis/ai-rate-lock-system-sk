"""
Loan Application Context Agent
Retrieves and verifies loan application data from the Loan Origination System (LOS).
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class LoanApplicationContextAgent:
    """
    Role: Retrieves and verifies loan application data.
    
    Tasks:
    - Pull borrower's loan file from LOS (Loan Origination System)
    - Check loan status (e.g., pre-approved, underwritten)
    - Confirm eligibility for rate lock
    """
    
    def __init__(self, los_service=None):
        self.los_service = los_service
        self.agent_name = "LoanApplicationContextAgent"
    
    async def retrieve_loan_context(self, loan_application_id: str) -> Dict[str, Any]:
        """Retrieve complete loan application context from LOS."""
        logger.info(f"{self.agent_name}: Retrieving context for loan {loan_application_id}")
        
        try:
            # Fetch loan application data
            loan_data = await self._fetch_loan_application(loan_application_id)
            
            if not loan_data:
                raise ValueError(f"Loan application {loan_application_id} not found")
            
            # Verify loan status
            loan_status = await self._check_loan_status(loan_application_id)
            
            # Check rate lock eligibility
            eligibility = await self._check_rate_lock_eligibility(loan_data, loan_status)
            
            # Build comprehensive context
            context = {
                "loan_application_id": loan_application_id,
                "borrower_info": loan_data.get('borrower'),
                "property_info": loan_data.get('property'),
                "loan_details": {
                    "loan_amount": loan_data.get('loan_amount'),
                    "loan_type": loan_data.get('loan_type'),
                    "loan_purpose": loan_data.get('loan_purpose'),
                    "rate_type": loan_data.get('rate_type', 'Fixed'),
                    "loan_term": loan_data.get('loan_term', 30)
                },
                "status_info": {
                    "current_status": loan_status,
                    "rate_lock_eligible": eligibility['eligible'],
                    "eligibility_reasons": eligibility['reasons']
                },
                "estimated_closing_date": loan_data.get('estimated_closing_date'),
                "loan_officer": loan_data.get('loan_officer'),
                "audit": {
                    "retrieved_by": self.agent_name,
                    "retrieved_at": datetime.utcnow().isoformat()
                }
            }
            
            logger.info(f"{self.agent_name}: Successfully retrieved context for loan {loan_application_id}")
            return context
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Error retrieving loan context - {str(e)}")
            raise
    
    async def _fetch_loan_application(self, loan_application_id: str) -> Optional[Dict[str, Any]]:
        """Fetch loan application data from LOS."""
        if not self.los_service:
            logger.warning("LOS service not configured")
            return None
        
        try:
            # TODO: Implement actual LOS integration (Encompass, Blend, etc.)
            loan_data = await self.los_service.get_loan_application(loan_application_id)
            return loan_data
            
        except Exception as e:
            logger.error(f"Error fetching loan application: {str(e)}")
            return None
    
    async def _check_loan_status(self, loan_application_id: str) -> str:
        """Check current loan processing status."""
        if not self.los_service:
            return "Unknown"
        
        try:
            status = await self.los_service.get_loan_status(loan_application_id)
            return status
            
        except Exception as e:
            logger.error(f"Error checking loan status: {str(e)}")
            return "Unknown"
    
    async def _check_rate_lock_eligibility(self, loan_data: Dict[str, Any], loan_status: str) -> Dict[str, Any]:
        """Determine if the loan is eligible for rate lock."""
        eligible = True
        reasons = []
        
        # Check loan status requirements
        valid_statuses = ["pre-approved", "underwritten", "conditionally_approved", "clear_to_close"]
        if loan_status.lower() not in valid_statuses:
            eligible = False
            reasons.append(f"Loan status '{loan_status}' not eligible for rate lock")
        
        # Check required documentation
        if not loan_data.get('income_verified'):
            eligible = False
            reasons.append("Income verification required")
        
        if not loan_data.get('assets_verified'):
            eligible = False
            reasons.append("Asset verification required")
        
        # Check property appraisal
        if not loan_data.get('appraisal_completed'):
            reasons.append("Appraisal pending - lock may be subject to value confirmation")
        
        # Check loan amount limits
        loan_amount = loan_data.get('loan_amount', 0)
        if loan_amount <= 0:
            eligible = False
            reasons.append("Invalid loan amount")
        
        # Check closing timeline
        closing_date = loan_data.get('estimated_closing_date')
        if not closing_date:
            reasons.append("Estimated closing date required for appropriate lock term")
        
        if eligible and not reasons:
            reasons.append("All eligibility requirements met")
        
        return {
            "eligible": eligible,
            "reasons": reasons
        }
    
    async def validate_borrower_identity(self, borrower_email: str, loan_application_id: str) -> bool:
        """Validate that the borrower email matches the loan application."""
        try:
            loan_data = await self._fetch_loan_application(loan_application_id)
            
            if not loan_data:
                return False
            
            borrower_info = loan_data.get('borrower', {})
            
            # Check primary borrower email
            if borrower_info.get('email', '').lower() == borrower_email.lower():
                return True
            
            # Check co-borrower email if exists
            co_borrower = loan_data.get('co_borrower', {})
            if co_borrower.get('email', '').lower() == borrower_email.lower():
                return True
            
            logger.warning(f"Borrower email {borrower_email} does not match loan {loan_application_id}")
            return False
            
        except Exception as e:
            logger.error(f"Error validating borrower identity: {str(e)}")
            return False
    
    async def get_loan_officer_info(self, loan_application_id: str) -> Optional[Dict[str, Any]]:
        """Get loan officer information for the application."""
        try:
            loan_data = await self._fetch_loan_application(loan_application_id)
            
            if not loan_data:
                return None
            
            loan_officer = loan_data.get('loan_officer', {})
            
            return {
                "name": loan_officer.get('name'),
                "email": loan_officer.get('email'),
                "phone": loan_officer.get('phone'),
                "nmls_id": loan_officer.get('nmls_id')
            }
            
        except Exception as e:
            logger.error(f"Error getting loan officer info: {str(e)}")
            return None
    
    async def update_loan_lock_request_status(self, loan_application_id: str, status: str) -> bool:
        """Update the rate lock request status in the LOS."""
        try:
            if not self.los_service:
                logger.warning("LOS service not configured")
                return False
            
            success = await self.los_service.update_rate_lock_status(
                loan_application_id,
                status
            )
            
            if success:
                logger.info(f"{self.agent_name}: Updated rate lock status to {status} for loan {loan_application_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating loan lock status: {str(e)}")
            return False
    
    async def close(self):
        """Clean up agent resources."""
        # Note: los_service cleanup would be handled by the service itself if needed
        logger.info(f"{self.agent_name}: Resources cleaned up.")