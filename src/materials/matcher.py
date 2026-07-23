from __future__ import annotations

from difflib import SequenceMatcher

from materials.models import Candidate, MaterialQuery, MaterialRecord
from materials.normalization import normalize_spec, normalize_text, split_material_names


class MaterialMatcher:
    def __init__(self, materials: list[MaterialRecord]):
        self.materials = materials

    def search(self, query: MaterialQuery, limit: int = 20) -> list[Candidate]:
        query_name = normalize_text(query.name)
        expanded_names = split_material_names(query.name)
        query_names = {normalize_text(name) for name in expanded_names} or {query_name}
        query_spec = normalize_spec(query.specification)
        candidates: list[Candidate] = []

        for material in self.materials:
            material_name = normalize_text(material.name)
            material_spec = normalize_spec(material.specification)
            name_equal = bool(query_name and material_name and query_name == material_name)
            spec_equal = bool(query_spec and material_spec and query_spec == material_spec)
            name_score = SequenceMatcher(None, query_name, material_name).ratio() if query_name else 0
            spec_score = SequenceMatcher(None, query_spec, material_spec).ratio() if query_spec else 0

            alias_name_equal = any(name and material_name and name == material_name for name in query_names)
            alias_name_contained = any(
                name and material_name and (name in material_name or material_name in name) for name in query_names
            )

            if (name_equal or alias_name_equal) and (spec_equal or not query_spec or not material_spec):
                match_type = "synonym" if normalize_text(query.name) != normalize_text(material.name) else "exact"
                score = 1.0 if spec_equal else 0.9
                confidence = "high" if spec_equal or (not query_spec and not material_spec) else "medium"
                reason = "名称或同义词一致，规格一致" if spec_equal else "名称或同义词一致，但规格信息不完整"
            elif (name_equal or alias_name_equal) and query_spec and material_spec:
                match_type = "keyword"
                score = 0.75
                confidence = "medium"
                reason = "名称或同义词一致，但规格存在冲突，请人工确认"
            elif alias_name_contained and not query_spec:
                match_type = "synonym"
                score = 0.86
                confidence = "medium"
                reason = "名称包含别名或形态词（例如番茄/西红柿），请人工核对具体物料形态"
            elif name_score >= 0.78 and (not query_spec or spec_score >= 0.75):
                match_type = "semantic"
                score = round((name_score + spec_score) / (2 if query_spec else 1), 4)
                confidence = "medium" if score >= 0.82 else "low"
                reason = "名称语义接近，需人工核对规格"
            elif query_spec and spec_equal:
                match_type = "keyword"
                score = 0.82
                confidence = "medium"
                reason = "规格一致，但名称不同"
            else:
                continue

            candidates.append(Candidate(material=material, match_type=match_type, confidence=confidence, score=score, reason=reason))

        return sorted(candidates, key=lambda item: item.score, reverse=True)[:limit]
