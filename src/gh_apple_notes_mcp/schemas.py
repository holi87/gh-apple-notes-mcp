"""Pydantic models for MCP tool inputs and outputs."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---- Tool inputs ----

class ListNotesInput(BaseModel):
    folder: Optional[str] = None
    since: Optional[str] = None
    limit: int = Field(50, gt=0, le=1000)
    include_trashed: bool = False


class GetNoteInput(BaseModel):
    id: str
    include_html: bool = False


class GetByTitleInput(BaseModel):
    title: str
    folder: Optional[str] = None


class CreateNoteInput(BaseModel):
    title: str
    body: str
    folder: str = "Notes"


class AppendTagInput(BaseModel):
    id: str
    tag: str

    @field_validator("tag")
    @classmethod
    def reject_hash_prefix(cls, v: str) -> str:
        if v.startswith("#"):
            raise ValueError("tag must not start with '#'")
        return v


class UpdateBodyInput(BaseModel):
    id: str
    new_body: str


class DeleteNoteInput(BaseModel):
    id: str
    confirm: bool


# ---- Tool outputs ----

class NoteSummary(BaseModel):
    id: str
    title: str
    folder: str
    created: str
    modified: str
    tags: list[str] = Field(default_factory=list)
    snippet: str = ""


class NoteDetail(BaseModel):
    id: str
    title: str
    body: str
    folder: str
    created: str
    modified: str
    tags: list[str] = Field(default_factory=list)
    has_attachments: bool = False
    html: Optional[str] = None


class FolderInfo(BaseModel):
    name: str
    note_count: int
    is_smart_folder: bool = False


class AppendTagResult(BaseModel):
    success: bool
    already_present: bool
    new_body: str


class OperationResult(BaseModel):
    success: bool


class CreateNoteResult(BaseModel):
    id: str


# ---- Semantic stubs (F3) ----

class SemanticSearchInput(BaseModel):
    query: str
    top_k: int = Field(5, gt=0, le=100)
    filter_folder: Optional[str] = None
    mode: Literal["candidates", "auto"] = "candidates"


class SemanticReindexInput(BaseModel):
    full: bool = False
