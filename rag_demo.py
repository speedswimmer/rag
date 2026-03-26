#!/usr/bin/env python3
"""
RAG Demo - Retrieval Augmented Generation
Raspberry Pi 5 + ChromaDB + Claude API
"""

import os
import sys
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain_classic.chains import RetrievalQA

# Konfiguration
DOCS_DIR = "./dokumente"
CHROMA_DIR = "./chroma_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL = "claude-sonnet-4-20250514"

def check_api_key():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("FEHLER: ANTHROPIC_API_KEY ist nicht gesetzt!")
        print("Fuehre aus: export ANTHROPIC_API_KEY='dein-key'")
        sys.exit(1)

def load_documents():
    docs = []

    try:
        pdf_loader = DirectoryLoader(
            DOCS_DIR,
            glob="**/*.pdf",
            loader_cls=PyPDFLoader,
            show_progress=True
        )
        pdf_docs = pdf_loader.load()
        docs.extend(pdf_docs)
        print(f"  {len(pdf_docs)} PDF-Seiten geladen")
    except Exception as e:
        print(f"  Keine PDFs gefunden oder Fehler: {e}")

    try:
        txt_loader = DirectoryLoader(
            DOCS_DIR,
            glob="**/*.txt",
            loader_cls=TextLoader,
            show_progress=True
        )
        txt_docs = txt_loader.load()
        docs.extend(txt_docs)
        print(f"  {len(txt_docs)} Textdateien geladen")
    except Exception as e:
        print(f"  Keine Textdateien gefunden oder Fehler: {e}")

    return docs

def create_vectorstore(chunks, embeddings):
    print("\nErstelle Vektordatenbank...")
    print("(Beim ersten Mal wird das Embedding-Modell heruntergeladen, ca. 80MB)")

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR
    )
    print(f"Vektordatenbank erstellt mit {len(chunks)} Chunks")
    return vectorstore

def main():
    print("=" * 50)
    print("RAG System - Raspberry Pi 5")
    print("=" * 50)

    check_api_key()

    docs_path = Path(DOCS_DIR)
    if not docs_path.exists():
        docs_path.mkdir(parents=True)

    doc_files = list(docs_path.glob("**/*.pdf")) + list(docs_path.glob("**/*.txt"))
    if not doc_files:
        print(f"\nKeine Dokumente im Ordner '{DOCS_DIR}' gefunden!")
        print("Kopiere PDF- oder TXT-Dateien in den Ordner und starte erneut.")
        print(f"\nBeispiel:")
        print(f"  cp mein-dokument.pdf {DOCS_DIR}/")
        sys.exit(1)

    print(f"\n{len(doc_files)} Dateien gefunden in '{DOCS_DIR}'")

    print("\nLade Dokumente...")
    docs = load_documents()

    if not docs:
        print("Keine Dokumente konnten geladen werden!")
        sys.exit(1)

    print("\nTeile Texte in Chunks auf...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    chunks = splitter.split_documents(docs)
    print(f"{len(chunks)} Chunks erstellt")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"}
    )

    vectorstore = create_vectorstore(chunks, embeddings)

    llm = ChatAnthropic(
        model=LLM_MODEL,
        max_tokens=1024,
        temperature=0.3
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectorstore.as_retriever(
            search_kwargs={"k": 3}
        ),
        return_source_documents=True
    )

    print("\n" + "=" * 50)
    print("RAG System bereit!")
    print("Stelle Fragen zu deinen Dokumenten.")
    print("Eingabe 'exit' zum Beenden.")
    print("=" * 50)

    while True:
        try:
            frage = input("\nDeine Frage: ").strip()

            if not frage:
                continue

            if frage.lower() in ['exit', 'quit', 'q']:
                print("\nAuf Wiedersehen!")
                break

            print("\nSuche relevante Passagen und generiere Antwort...")
            result = qa_chain.invoke({"query": frage})

            print(f"\n{'─' * 40}")
            print(f"Antwort:\n{result['result']}")
            print(f"\n{'─' * 40}")
            print(f"Quellen ({len(result['source_documents'])} Dokumente):")
            for i, doc in enumerate(result['source_documents'], 1):
                source = doc.metadata.get('source', 'unbekannt')
                page = doc.metadata.get('page', '?')
                print(f"  {i}. {source} (Seite {page})")

        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            break
        except Exception as e:
            print(f"\nFehler: {e}")

if __name__ == "__main__":
    main()
