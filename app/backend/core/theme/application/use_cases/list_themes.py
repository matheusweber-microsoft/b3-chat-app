from dataclasses import dataclass
from uuid import UUID
from typing import Dict, Any
from core.theme.domain.theme import SubTheme
from core.theme.domain.theme_repository import ThemeRepository
from core.log import Logger


@dataclass
class ThemeOutput:
    themeId: UUID
    themeName: str
    language: str
    active: bool
    subthemes: list[SubTheme]
    assistantConfig: Dict[str, Any]

    def to_dict(self):
        return {
            "themeId": str(self.themeId),
            "themeName": self.themeName,
            "language": self.language,
            "subThemes": [subtheme.to_dict() for subtheme in self.subthemes],
            "active": self.active,
            "assistantConfig": self.assistantConfig
        }


class ListTheme:
    def __init__(self, repository: ThemeRepository):
        self.logging = Logger()
        self.repository = repository

    @dataclass
    class Input:
        pass

    @dataclass
    class Output:
        data: list[ThemeOutput]

    def execute(self) -> Output:
        self.logging.info("Starting to execute ListTheme use case")

        try:
            themes = self.repository.list()
            data = [
                ThemeOutput(
                    themeId=theme.themeId,
                    themeName=theme.themeName,
                    language=theme.language,
                    active=theme.active,
                    subthemes=list(theme.subThemes),
                    assistantConfig=theme.assistantConfig

                )
                for theme in themes
            ]
            self.logging.info(f"Successfully listed {len(data)} themes")
            return self.Output(data=data)
        except Exception as e:
            self.logging.error("Failed to list themes", exc_info=True)
            raise RuntimeError("An error occurred while listing themes") from e
