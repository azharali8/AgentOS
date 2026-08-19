from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app.db.models import LearningExperienceModel


class ExperienceRepository:
    """Repository for learning experience persistence."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, experience: LearningExperienceModel) -> LearningExperienceModel:
        self.session.add(experience)
        self.session.commit()
        self.session.refresh(experience)
        return experience

    def update(self, experience: LearningExperienceModel) -> LearningExperienceModel:
        self.session.commit()
        self.session.refresh(experience)
        return experience

    def get_by_id(self, experience_id: str) -> Optional[LearningExperienceModel]:
        return (
            self.session.query(LearningExperienceModel)
            .filter(LearningExperienceModel.experience_id == experience_id)
            .first()
        )

    def get_latest_by_task_id(self, task_id: str) -> Optional[LearningExperienceModel]:
        return (
            self.session.query(LearningExperienceModel)
            .filter(LearningExperienceModel.task_id == task_id)
            .order_by(LearningExperienceModel.timestamp.desc())
            .first()
        )

    def list_experiences(
        self,
        limit: int = 50,
        offset: int = 0,
        task_type: Optional[str] = None,
        task_complexity: Optional[str] = None,
        selected_strategy: Optional[str] = None,
        success: Optional[bool] = None,
        project_type: Optional[str] = None,
        framework: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> List[LearningExperienceModel]:
        query = self.session.query(LearningExperienceModel)
        if task_type:
            query = query.filter(LearningExperienceModel.task_type == task_type)
        if task_complexity:
            query = query.filter(LearningExperienceModel.task_complexity == task_complexity)
        if selected_strategy:
            query = query.filter(LearningExperienceModel.selected_strategy == selected_strategy)
        if success is not None:
            query = query.filter(LearningExperienceModel.success == success)
        if project_type:
            query = query.filter(LearningExperienceModel.project_type == project_type)
        if framework:
            query = query.filter(LearningExperienceModel.framework == framework)
        if task_id:
            query = query.filter(LearningExperienceModel.task_id == task_id)
        return (
            query.order_by(LearningExperienceModel.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_older_than(self, cutoff: datetime) -> List[LearningExperienceModel]:
        return (
            self.session.query(LearningExperienceModel)
            .filter(LearningExperienceModel.timestamp < cutoff)
            .order_by(LearningExperienceModel.timestamp.asc())
            .all()
        )

    def count(self) -> int:
        return self.session.query(LearningExperienceModel).count()

    def delete(self, experience: LearningExperienceModel) -> None:
        self.session.delete(experience)
        self.session.commit()

