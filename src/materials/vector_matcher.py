from materials.models import Candidate, MaterialQuery, MaterialRecord
from materials.normalization import normalize_text, split_material_names


class VectorMaterialMatcher:
    def __init__(self, vector_store):
        self.vector_store = vector_store
        self._index_version = "pgvector"

    def search(self, query: MaterialQuery, limit: int = 20) -> list[Candidate]:
        names = split_material_names(query.name)
        names = list(dict.fromkeys(name for name in names if name.strip())) or [query.name]
        result_by_code = {}
        for name in names:
            query_text = " ".join(part.strip() for part in (name, query.specification) if part.strip())
            results = self.vector_store.similarity_search_with_score(query_text, k=limit)
            for document, distance in results:
                code = str(document.metadata.get("code", ""))
                if code not in result_by_code or float(distance) < result_by_code[code][1]:
                    result_by_code[code] = (document, float(distance), name)

        candidates = []
        for document, distance, matched_name in sorted(result_by_code.values(), key=lambda item: item[1])[:limit]:
            metadata = document.metadata
            self._index_version = str(metadata.get("index_version", self._index_version))
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            confidence = "high" if similarity >= 0.9 else "medium" if similarity >= 0.75 else "low"
            matched_name_normalized = normalize_text(matched_name)
            material_name_normalized = normalize_text(metadata.get("name", ""))
            shape_variant = (
                matched_name_normalized != material_name_normalized
                and matched_name_normalized in material_name_normalized
            )
            if shape_variant:
                confidence = "medium"
                similarity = min(similarity, 0.89)
            candidates.append(
                Candidate(
                    material=_material_from_metadata(metadata),
                    match_type="synonym" if normalize_text(matched_name) != normalize_text(query.name) else "semantic",
                    confidence=confidence,
                    score=round(similarity, 4),
                    reason=(
                        "由别名扩展后通过 LangChain PGVector 召回，请核对具体物料形态"
                        if normalize_text(matched_name) != normalize_text(query.name)
                        else "由 LangChain PGVector 语义检索召回，请结合名称和规格人工核对"
                    ),
                )
            )
        return candidates

    def index_version(self) -> str:
        return self._index_version


def _material_from_metadata(metadata: dict) -> MaterialRecord:
    return MaterialRecord(
        code=str(metadata.get("code", "")),
        name=str(metadata.get("name", "")),
        specification=str(metadata.get("specification", "")),
        short_name=str(metadata.get("short_name", "")),
        english_name=str(metadata.get("english_name", "")),
        description=str(metadata.get("description", "")),
        status=str(metadata.get("status", "disabled")),
    )
