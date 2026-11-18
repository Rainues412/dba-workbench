"""Validation and thumbnail generation for local account profiles."""

import base64
import binascii
import json
import unicodedata
from io import BytesIO
from typing import Annotated

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
AVATAR_SIZE = (192, 192)
PROFILE_COLUMNS = "display_name, avatar_png, profile_revision, work_role, specialties, bio"
AVATAR_FORMATS = {
    "data:image/png;base64": "PNG",
    "data:image/jpeg;base64": "JPEG",
    "data:image/webp;base64": "WEBP",
}


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    avatar: str | None = Field(max_length=4 * ((MAX_AVATAR_BYTES + 2) // 3) + 32)
    work_role: str | None = Field(default=None, max_length=40)
    specialties: list[Annotated[str, Field(max_length=30)]] | None = Field(default=None, max_length=12)
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("work_role", "bio", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("specialties")
    @classmethod
    def unique_specialties(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        items: dict[str, str] = {}
        for value in values:
            name = value.strip()
            if name:
                items.setdefault(name.casefold(), name)
        return list(items.values())


def normalize_display_name(value: str) -> str:
    name = value.strip()
    if len(name) > 40 or any(unicodedata.category(char) in {"Cc", "Cs"} for char in name):
        raise HTTPException(422, "显示名称最多 40 个字符，且不能包含控制字符。")
    return name


def avatar_thumbnail(value: str | None) -> bytes | None:
    if value is None:
        return None

    header, _, encoded = value.partition(",")
    image_format = AVATAR_FORMATS.get(header)
    if not image_format:
        raise HTTPException(422, "请选择 PNG、JPG 或 WebP 图片。")
    try:
        source = base64.b64decode(encoded, validate=True)
        if len(source) > MAX_AVATAR_BYTES:
            raise HTTPException(422, "头像图片不能超过 5 MB。")
        with Image.open(BytesIO(source), formats=[image_format]) as image:
            if image.width * image.height > MAX_AVATAR_PIXELS:
                raise HTTPException(422, "头像图片不能超过 2000 万像素。")
            thumbnail = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGBA"), AVATAR_SIZE)
            thumbnail.info.clear()
            with BytesIO() as output:
                thumbnail.save(output, format="PNG")
                return output.getvalue()
    except (binascii.Error, UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as error:
        raise HTTPException(422, "无法读取这张图片，请换一张图片。") from error


def profile_payload(row) -> dict:
    avatar_png = row["avatar_png"]
    avatar = "data:image/png;base64," + base64.b64encode(avatar_png).decode("ascii") if avatar_png else None
    return {
        "display_name": row["display_name"],
        "avatar": avatar,
        "revision": row["profile_revision"],
        "work_role": row["work_role"],
        "specialties": json.loads(row["specialties"]),
        "bio": row["bio"],
    }
