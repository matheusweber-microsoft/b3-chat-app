from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any
from uuid import UUID
import os


@dataclass
class SubTheme:
    subthemeName: str
    subthemeId: str
    allowedForGroups: List[str]

    @classmethod
    def from_dict(cls, subtheme: dict):
        return cls(
            subthemeName=subtheme["subthemeName"],
            subthemeId=subtheme["subthemeId"],
            allowedForGroups=subtheme["allowedForGroups"]
        )

    def to_dict(self):
        return {
            "subthemeId": self.subthemeId,
            "subthemeName": self.subthemeName,
            "allowedForGroups": self.allowedForGroups
        }


@dataclass
class Theme:
    themeName: str
    themeId: str
    language: str
    active: bool
    subThemes: List[SubTheme]
    assistantConfig: Dict[str, Any]

    @classmethod
    def from_dict(cls, theme: dict):
        return cls(
            themeName=theme["themeName"],
            themeId=theme["themeId"],
            language=theme["language"],
            active=theme["active"],
            subThemes=[SubTheme.from_dict(subtheme)
                       for subtheme in theme["subThemes"]],
            assistantConfig=theme["assistantConfig"]
        )

    def to_dict(self):
        return {
            "themeId": self.themeId,
            "themeName": self.themeName,
            "language": self.language,
            "active": self.active,
            "subThemes": [subtheme.to_dict() for subtheme in self.subThemes],
            "assistantConfig": self.assistantConfig
        }
