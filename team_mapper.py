import json
import os
import logging

logger = logging.getLogger(__name__)

class TeamMapper:
    """Farklı kaynaklardaki takım isimlerini tekilleştirmek için eşleme sınıfı."""

    def __init__(self, mapping_file="data/team_mappings.json"):
        self.mapping_file = mapping_file
        self.mappings = {}
        self._load_mappings()

    def _load_mappings(self):
        """Eşleme dosyasını yükler."""
        if os.path.exists(self.mapping_file):
            try:
                with open(self.mapping_file, "r", encoding="utf-8") as f:
                    self.mappings = json.load(f)
            except Exception as e:
                logger.error(f"Eşleme dosyası yüklenemedi: {e}")
                self.mappings = {}
        else:
            # Varsayılan boş eşleme dosyası oluştur
            os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
            self._save_mappings()

    def _save_mappings(self):
        """Eşlemeleri dosyaya kaydeder."""
        try:
            with open(self.mapping_file, "w", encoding="utf-8") as f:
                json.dump(self.mappings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Eşleme dosyası kaydedilemedi: {e}")

    def normalize(self, team_name):
        """Takım ismini normalize eder (Varsa canonical isme çevirir)."""
        if not team_name:
            return ""
        
        name = team_name.strip()
        # Doğrudan eşleşme kontrolü (alias -> canonical)
        return self.mappings.get(name, name)

    def add_alias(self, alias, canonical_name):
        """Yeni bir takma ad ekler."""
        if alias and canonical_name and alias != canonical_name:
            self.mappings[alias] = canonical_name
            self._save_mappings()
            logger.info(f"Yeni eşleme eklendi: {alias} -> {canonical_name}")

    def auto_seed(self, db_teams):
        """Bilinen bazı varyasyonları otomatik ekler (Opsiyonel helper)."""
        # Örn: "Arsenal FC" -> "Arsenal"
        common_suffixes = [" FC", " AFC", " CF", " SD", " UD", " CD", " SC"]
        for team in db_teams:
            for suffix in common_suffixes:
                if team.endswith(suffix):
                    alias = team[:-len(suffix)].strip()
                    if alias not in self.mappings:
                        self.add_alias(alias, team)
                elif team.startswith(suffix.strip()):
                     # "FC Porto" -> "Porto"
                     pass
