from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.db.models import EventModel

class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, event: EventModel) -> EventModel:
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list_by_task(self, task_id: str, limit: int = 100, offset: int = 0) -> List[EventModel]:
        return self.session.query(EventModel).filter(EventModel.task_id == task_id).order_by(EventModel.timestamp.asc()).offset(offset).limit(limit).all()

    def count_by_task(self, task_id: str) -> int:
        from sqlalchemy import func
        return self.session.query(func.count(EventModel.event_id)).filter(EventModel.task_id == task_id).scalar()
