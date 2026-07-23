from langchain_postgres import PGVector

from config import Settings
from indexing.embedding import E5Embeddings


COLLECTION_NAME = "erp_materials"


def create_vector_store(settings: Settings, embeddings: E5Embeddings) -> PGVector:
    return PGVector(
        embeddings=embeddings,
        connection=settings.postgres_url,
        embedding_length=settings.embedding_dimension,
        collection_name=COLLECTION_NAME,
        use_jsonb=True,
        create_extension=True,
    )
