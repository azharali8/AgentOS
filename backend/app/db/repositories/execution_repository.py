from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.db.models import ExecutionModel

class ExecutionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, execution: ExecutionModel) -> ExecutionModel:
        self.session.add(execution)
        self.session.commit()
        self.session.refresh(execution)
        return execution

    def get_by_id(self, execution_id: str) -> Optional[ExecutionModel]:
        return self.session.query(ExecutionModel).filter(ExecutionModel.execution_id == execution_id).first()

    def update(self, execution: ExecutionModel) -> ExecutionModel:
        self.session.commit()
        self.session.refresh(execution)
        return execution

    def list_by_task(self, task_id: str) -> List[ExecutionModel]:
        return self.session.query(ExecutionModel).filter(ExecutionModel.task_id == task_id).order_by(ExecutionModel.started_at.asc()).all()
