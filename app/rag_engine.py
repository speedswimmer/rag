"""RAG pipeline — refactored from rag_demo.py into a reusable class."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_anthropic import ChatAnthropic
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_classic.chains import RetrievalQA
from langchain_text_splitters import RecursiveCharacterTextSplitter

if TYPE_CHECKING:
    from app.config import Config

logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self, config: "Config"):
        self.config = config
        self._embeddings: HuggingFaceEmbeddings | None = None
        self._vectorstore: Chroma | None = None
        self._qa_chain: RetrievalQA | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Load embedding model and open existing ChromaDB (if available)."""
        logger.info("Loading embedding model: %s", self.config.embedding_model)
        self._embeddings = HuggingFaceEmbeddings(
            model_name=self.config.embedding_model,
            model_kwargs={"device": "cpu"},
        )

        chroma_dir = str(self.config.chroma_dir)
        # Check if a persisted collection already exists
        import chromadb
        client = chromadb.PersistentClient(path=chroma_dir)
        collections = client.list_collections()

        if collections:
            logger.info("Opening existing ChromaDB at %s", chroma_dir)
            self._vectorstore = Chroma(
                persist_directory=chroma_dir,
                embedding_function=self._embeddings,
            )
            self._build_chain()
        else:
            logger.info("No existing ChromaDB found — index will be built on first request")

    def rebuild_index(self) -> None:
        """Load all documents, chunk, embed, and persist to ChromaDB."""
        logger.info("Starting full index rebuild …")
        docs = self._load_documents()
        if not docs:
            logger.warning("No documents found in %s — index not built", self.config.docs_dir)
            return

        chunks = self._split_documents(docs)
        logger.info("Created %d chunks from %d document pages", len(chunks), len(docs))

        self._vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=self._embeddings,
            persist_directory=str(self.config.chroma_dir),
        )
        logger.info("ChromaDB rebuilt with %d chunks", len(chunks))
        self._build_chain()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def ask(self, question: str) -> dict:
        """Run question through RetrievalQA chain.

        Returns:
            {"answer": str, "sources": [{"source": str, "page": int|str}]}
        """
        if self._qa_chain is None:
            return {
                "answer": "Das System ist noch nicht bereit. Bitte lade zuerst Dokumente hoch.",
                "sources": [],
            }

        result = self._qa_chain.invoke({"query": question})
        sources = []
        for doc in result.get("source_documents", []):
            sources.append({
                "source": Path(doc.metadata.get("source", "unbekannt")).name,
                "page": doc.metadata.get("page", "?"),
            })

        return {"answer": result["result"], "sources": sources}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_documents(self) -> list:
        docs = []
        docs_dir = str(self.config.docs_dir)

        try:
            pdf_loader = DirectoryLoader(
                docs_dir, glob="**/*.pdf", loader_cls=PyPDFLoader, show_progress=False
            )
            pdf_docs = pdf_loader.load()
            docs.extend(pdf_docs)
            logger.info("Loaded %d PDF pages", len(pdf_docs))
        except Exception as exc:
            logger.warning("PDF loading error: %s", exc)

        try:
            txt_loader = DirectoryLoader(
                docs_dir,
                glob="**/*.txt",
                loader_cls=TextLoader,
                show_progress=False,
                loader_kwargs={"autodetect_encoding": True},
            )
            txt_docs = txt_loader.load()
            docs.extend(txt_docs)
            logger.info("Loaded %d TXT documents", len(txt_docs))
        except Exception as exc:
            logger.warning("TXT loading error: %s", exc)

        return docs

    def _split_documents(self, docs: list) -> list:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            length_function=len,
        )
        return splitter.split_documents(docs)

    def _build_chain(self) -> None:
        llm = ChatAnthropic(
            model=self.config.llm_model,
            max_tokens=self.config.llm_max_tokens,
            temperature=self.config.llm_temperature,
        )
        self._qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self._vectorstore.as_retriever(
                search_kwargs={"k": self.config.retrieval_k}
            ),
            return_source_documents=True,
        )
        logger.info("RetrievalQA chain built")
