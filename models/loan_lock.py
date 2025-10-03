# JSON model for a LoanLock entity
class LoanLock:
    def __init__(self, loan_id, status):
        self.loan_id = loan_id
        self.status = status
