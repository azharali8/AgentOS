from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.db.models import ApprovalModel

class ApprovalRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, approval: ApprovalModel) -> ApprovalModel:
        self.session.add(approval)
        self.session.commit()
        self.session.refresh(approval)
        return approval

    def get_by_id(self, approval_id: str) -> Optional[ApprovalModel]:
        return self.session.query(ApprovalModel).filter(ApprovalModel.approval_id == approval_id).first()

    def update(self, approval: ApprovalModel) -> ApprovalModel:
        self.session.commit()
        self.session.refresh(approval)
        return approval

    def list_approvals(self, limit: int = 20, offset: int = 0) -> List[ApprovalModel]:
        return self.session.query(ApprovalModel).order_by(ApprovalModel.created_at.desc()).offset(offset).limit(limit).all()

    def count_approvals(self) -> int:
        from sqlalchemy import func
        return self.session.query(func.count(ApprovalModel.approval_id)).scalar()
