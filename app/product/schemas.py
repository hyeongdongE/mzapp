from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Category, FeedbackType, NotificationMode


class InterestsInput(BaseModel):
    categories: list[Category] = Field(min_length=1)


class SettingsInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    categories: list[Category] = Field(min_length=1)
    notification_mode: NotificationMode = Field(alias="notificationMode")


class FeedbackInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    feedback_type: FeedbackType = Field(alias="feedbackType")
