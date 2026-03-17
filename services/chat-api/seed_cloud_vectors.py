import pathlib

from app.services.ingestion import ingest_document

BASE_PATH = pathlib.Path("knowledge_base")
MODE_FOLDERS = {
    "relationship": BASE_PATH / "relationship",
    "coaching": BASE_PATH / "coaching",
    "personal_growth": BASE_PATH / "personal_growth",
}


def main():
    total_chunks = 0
    for mode, folder in MODE_FOLDERS.items():
        if not folder.exists():
            print(f"Skip {mode}: folder not found -> {folder}")
            continue
        for file_path in folder.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".txt", ".pdf", ".docx"}:
                continue
            result = ingest_document(
                mode=mode,
                filename=file_path.name,
                content=file_path.read_bytes(),
                source=str(file_path),
                user_id="seed",
                session_id=None,
            )
            total_chunks += result["chunks_indexed"]
            print(f"Indexed {file_path.name} ({mode}) -> {result['chunks_indexed']} chunks")
    print(f"Done. Total chunks indexed: {total_chunks}")


if __name__ == "__main__":
    main()
