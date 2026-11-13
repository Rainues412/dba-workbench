"""The editable customer directory profile and its legacy read projection."""
from pydantic import BaseModel, Field, field_validator

# A saved profile replaces the legacy project field. Both search routes use the
# same project source, so a renamed or removed project cannot surface as a hit.
CUSTOMER_PROJECT_ROWS = """json_each(
    CASE WHEN c.project_profile IS NULL
         THEN json_array(json_object('name', c.project_name))
         ELSE json_extract(c.project_profile, '$.projects')
    END
) AS project"""
CUSTOMER_PROJECT_NAME = "json_extract(project.value, '$.name')"


class Owner(BaseModel):
    name: str
    label: str = ""

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required")
        return value


class GroupChat(BaseModel):
    name: str = ""
    platform: str = ""


class Project(BaseModel):
    name: str
    chat: GroupChat = Field(default_factory=GroupChat)
    owners: list[Owner] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Project name is required")
        return value


class ProjectProfile(BaseModel):
    chat: GroupChat = Field(default_factory=GroupChat)
    owners: list[Owner] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)


def customer_record(row) -> dict:
    record = dict(row)
    stored = record["project_profile"]
    if stored is not None:
        profile = ProjectProfile.model_validate_json(stored)
    else:
        # A named legacy project owns the chat and owner. Without a project name
        # the saved group and owner remain directly accessible on the customer.
        project = record["project_name"] or ""
        person = record["wb_person"] or ""
        owners = [Owner(name=person)] if person.strip() else []
        chat = GroupChat(name=record["group_name"] or "", platform=record["wb_contact"] or "")
        if project.strip():
            profile = ProjectProfile(projects=[Project(name=project, chat=chat, owners=owners)])
        else:
            profile = ProjectProfile(chat=chat, owners=owners)
    record["project_profile"] = profile.model_dump()
    return record
