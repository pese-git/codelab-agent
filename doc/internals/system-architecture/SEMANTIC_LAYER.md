# Semantic Layer — Семантический уровень

> Компоненты для семантического поиска: векторные индексы, RAG, семантический поиск

## Оглавление

- [Обзор](#обзор)
- [VectorIndex](#vectorindex)
- [RAGProvider](#ragprovider)
- [SemanticSearch](#semanticsearch)
- [Интеграция с ContextManager](#интеграция-с-contextmanager)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Semantic Layer отвечает за **семантическое понимание кода**: векторные индексы, retrieval-augmented generation, семантический поиск.

**Компоненты:**
- `VectorIndex` — векторный индекс кода
- `RAGProvider` — провайдер RAG (retrieval-augmented generation)
- `SemanticSearch` — семантический поиск

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ VectorIndex      ← Semantic Layer                        │
│  └─ RAGProvider      ← Semantic Layer                        │
│  └─ SemanticSearch   ← Semantic Layer                        │
└─────────────────────────────────────────────────────────────┘
```

---

## VectorIndex

### Назначение

Векторный индекс кода: преобразование кода в векторы для семантического поиска.

### Интерфейс

```python
@dataclass
class CodeChunk:
    """Фрагмент кода."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    embedding: list[float] | None = None

class VectorIndex:
    """Векторный индекс кода."""
    
    def __init__(
        self,
        embedding_model: str = "openai/text-embedding-3-small",
        llm: LLMProvider | None = None,
    ):
        self.embedding_model = embedding_model
        self.llm = llm
        self.chunks: list[CodeChunk] = []
        self.index: Any | None = None  # FAISS, Chroma, etc.
    
    async def build_index(self, cwd: str) -> None:
        """
        Построить векторный индекс.
        
        Pipeline:
        1. Разбить код на чанки
        2. Преобразовать каждый чанк в вектор
        3. Построить индекс
        """
        # Получить все файлы
        files = await self._get_all_files(cwd)
        
        # Разбить на чанки
        for file_path in files:
            content = await self._read_file(file_path)
            chunks = self._split_into_chunks(content, file_path)
            self.chunks.extend(chunks)
        
        # Преобразовать в векторы
        await self._generate_embeddings()
        
        # Построить индекс
        await self._build_faiss_index()
    
    def _split_into_chunks(
        self,
        content: str,
        file_path: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[CodeChunk]:
        """Разбить код на чанки."""
        lines = content.split('\n')
        chunks = []
        
        for i in range(0, len(lines), chunk_size - overlap):
            chunk_lines = lines[i:i + chunk_size]
            chunks.append(CodeChunk(
                file_path=file_path,
                start_line=i + 1,
                end_line=i + len(chunk_lines),
                content='\n'.join(chunk_lines)
            ))
        
        return chunks
    
    async def _generate_embeddings(self) -> None:
        """Сгенерировать эмбеддинги для всех чанков."""
        if not self.llm:
            return
        
        for chunk in self.chunks:
            embedding = await self.llm.generate_embedding(
                chunk.content,
                model=self.embedding_model
            )
            chunk.embedding = embedding
    
    async def _build_faiss_index(self) -> None:
        """Построить FAISS индекс."""
        try:
            import faiss
            import numpy as np
            
            # Собрать все эмбеддинги
            embeddings = [chunk.embedding for chunk in self.chunks if chunk.embedding]
            
            if not embeddings:
                return
            
            # Создать индекс
            dimension = len(embeddings[0])
            self.index = faiss.IndexFlatL2(dimension)
            
            # Добавить векторы
            vectors = np.array(embeddings).astype('float32')
            self.index.add(vectors)
        except ImportError:
            # FAISS не установлен — использовать простой поиск
            pass
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[CodeChunk, float]]:
        """
        Семантический поиск.
        
        Args:
            query: Поисковый запрос
            top_k: Количество результатов
        
        Returns:
            Список (chunk, score)
        """
        if not self.index:
            return []
        
        # Преобразовать запрос в вектор
        query_embedding = await self.llm.generate_embedding(
            query,
            model=self.embedding_model
        )
        
        # Поиск
        import numpy as np
        query_vector = np.array([query_embedding]).astype('float32')
        distances, indices = self.index.search(query_vector, top_k)
        
        # Вернуть результаты
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.chunks):
                chunk = self.chunks[idx]
                score = 1.0 / (1.0 + distances[0][i])  # Преобразовать distance в similarity
                results.append((chunk, score))
        
        return results
```

---

## RAGProvider

### Назначение

Провайдер RAG: retrieval-augmented generation для получения релевантного контекста.

### Интерфейс

```python
class RAGProvider:
    """Провайдер RAG."""
    
    def __init__(
        self,
        vector_index: VectorIndex,
        llm: LLMProvider,
    ):
        self.vector_index = vector_index
        self.llm = llm
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[CodeChunk]:
        """
        Получить релевантные фрагменты кода.
        
        Args:
            query: Запрос
            top_k: Количество результатов
        
        Returns:
            Список релевантных фрагментов
        """
        results = await self.vector_index.search(query, top_k)
        return [chunk for chunk, _ in results]
    
    async def augment_context(
        self,
        query: str,
        base_context: str,
    ) -> str:
        """
        Дополнить контекст релевантными фрагментами.
        
        Args:
            query: Запрос
            base_context: Базовый контекст
        
        Returns:
            Дополненный контекст
        """
        # Получить релевантные фрагменты
        chunks = await self.retrieve(query, top_k=5)
        
        if not chunks:
            return base_context
        
        # Сформировать дополненный контекст
        augmented = base_context + "\n\n## Relevant Code Snippets\n"
        
        for i, chunk in enumerate(chunks, 1):
            augmented += f"\n### Snippet {i}: {chunk.file_path}:{chunk.start_line}-{chunk.end_line}\n"
            augmented += f"```\n{chunk.content}\n```\n"
        
        return augmented
    
    async def generate_with_rag(
        self,
        query: str,
        base_context: str,
    ) -> str:
        """
        Генерация с RAG.
        
        Args:
            query: Запрос
            base_context: Базовый контекст
        
        Returns:
            Ответ LLM с учётом RAG
        """
        # Дополнить контекст
        augmented_context = await self.augment_context(query, base_context)
        
        # Генерация
        response = await self.llm.create_completion(
            CompletionRequest(
                model="openai/gpt-4o",
                messages=[
                    LLMMessage(role="system", content=augmented_context),
                    LLMMessage(role="user", content=query)
                ],
                max_tokens=2000,
                temperature=0.0,
            )
        )
        
        return response.text
```

---

## SemanticSearch

### Назначение

Семантический поиск: поиск по смыслу, а не по точному совпадению.

### Интерфейс

```python
class SemanticSearch:
    """Семантический поиск."""
    
    def __init__(
        self,
        vector_index: VectorIndex,
        text_search: SearchEngine,
    ):
        self.vector_index = vector_index
        self.text_search = text_search
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """
        Семантический поиск.
        
        Комбинирует:
        1. Текстовый поиск (git grep)
        2. Семантический поиск (vector index)
        3. Ранжирование по релевантности
        """
        # Текстовый поиск
        text_results = await self.text_search.search(
            SearchQuery(terms=[query]),
            structure=await self._get_project_structure()
        )
        
        # Семантический поиск
        semantic_results = await self.vector_index.search(query, top_k=top_k)
        
        # Комбинировать результаты
        combined = self._combine_results(text_results, semantic_results)
        
        # Ранжировать
        ranked = self._rank_results(combined, query)
        
        return ranked[:top_k]
    
    def _combine_results(
        self,
        text_results: list[SearchResult],
        semantic_results: list[tuple[CodeChunk, float]],
    ) -> list[SearchResult]:
        """Комбинировать текстовые и семантические результаты."""
        combined = []
        
        # Добавить текстовые результаты
        for result in text_results:
            combined.append(result)
        
        # Добавить семантические результаты
        for chunk, score in semantic_results:
            combined.append(SearchResult(
                file_path=chunk.file_path,
                line_number=chunk.start_line,
                line_content=chunk.content.split('\n')[0],
                match_content=chunk.content,
                relevance_score=score
            ))
        
        return combined
    
    def _rank_results(
        self,
        results: list[SearchResult],
        query: str,
    ) -> list[SearchResult]:
        """Ранжировать результаты."""
        # Убрать дубликаты
        seen = set()
        unique = []
        
        for result in results:
            key = (result.file_path, result.line_number)
            if key not in seen:
                seen.add(key)
                unique.append(result)
        
        # Сортировать по релевантности
        unique.sort(key=lambda r: r.relevance_score, reverse=True)
        
        return unique
```

---

## Интеграция с ContextManager

```python
class ContextManager:
    def __init__(
        self,
        rag_provider: RAGProvider,
        semantic_search: SemanticSearch,
        ...
    ):
        self.rag_provider = rag_provider
        self.semantic_search = semantic_search
    
    async def build_context(self, session, task):
        # 1. Семантический поиск релевантного кода
        semantic_results = await self.semantic_search.search(task, top_k=10)
        
        # 2. RAG для дополнения контекста
        augmented_context = await self.rag_provider.augment_context(
            task,
            base_context=""
        )
        
        # 3. Добавить в контекст
        context = [augmented_context]
        
        return context + other_context
```

---

## Roadmap реализации

### Phase 5: Базовая реализация (4 недели)

**Задачи:**
- [ ] Реализовать `VectorIndex` с эмбеддингами
- [ ] Реализовать `RAGProvider` с retrieval
- [ ] Реализовать `SemanticSearch` с комбинированным поиском
- [ ] Unit tests

**Результат:** Базовый семантический поиск.

### Phase 5: Расширенная реализация (2 недели)

**Задачи:**
- [ ] Оптимизация производительности
- [ ] Интеграция с ContextManager
- [ ] Integration tests

**Результат:** Полноценный семантический поиск.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Code Understanding](./CODE_UNDERSTANDING.md) — понимание кодовой базы
