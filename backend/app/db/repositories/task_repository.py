from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from backend.app.db.models import TaskModel

class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, task: TaskModel) -> TaskModel:
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get_by_id(self, task_id: str) -> Optional[TaskModel]:
        return self.session.query(TaskModel).filter(TaskModel.task_id == task_id).first()

    def update(self, task: TaskModel) -> TaskModel:
        self.session.commit()
        self.session.refresh(task)
        return task

    def list_tasks(self, limit: int = 20, offset: int = 0) -> List[TaskModel]:
        return self.session.query(TaskModel).order_by(TaskModel.created_at.desc()).offset(offset).limit(limit).all()

    def count_tasks(self) -> int:
        return self.session.query(func.count(TaskModel.task_id)).scalar()

    def get_incomplete_tasks(self) -> List[TaskModel]:
        return self.session.query(TaskModel).filter(
            TaskModel.status.in_(["PENDING", "PLANNING", "WAITING_APPROVAL", "EXECUTING", "REVIEWING"])
        ).all()
