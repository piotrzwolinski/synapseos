"""Embedding generation using Gemini's embedding model."""

import os
from google import genai
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 3072


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for a single text using Gemini embedding model.

    Args:
        text: The text to embed

    Returns:
        A list of floats representing the embedding vector
    """
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return list(result.embeddings[0].values)


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a batch.

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    # Process each text individually since batch API varies
    embeddings = []
    for text in texts:
        embedding = generate_embedding(text)
        embeddings.append(embedding)

    return embeddings
