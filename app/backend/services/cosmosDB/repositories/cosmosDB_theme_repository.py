from core.log import Logger
from typing import List
from core.theme.domain.theme import SubTheme, Theme
from services.cosmosDB.cosmosRepository import CosmosRepository



class ThemeRepository:
    collection_name = "themes"

    def __init__(self, repository: CosmosRepository):
        self.repository = repository
        self.logging = Logger()

    def list(self) -> List[Theme]:
        self.logging.info("Listing themes")
        try:
            documents = self.repository.list_all(self.collection_name, {"active": True}, {
                "_id": 1, "id": 1, "themeName": 1, "themeId": 1, "language": 1, "active": 1, "subThemes": 1, "assistantConfig": 1, 
            })
            list_of_themes = [Theme.from_dict(theme) for theme in documents]
            self.logging.info(f"Found {len(list_of_themes)} active themes")
            return list_of_themes
        except Exception as e:
            self.logging.error("Failed to list themes")
            raise RuntimeError(
                "Failed to retrieve themes from the database") from e
