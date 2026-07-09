"""Unit тесты для ContextRegistry и ContextSource."""

import pytest

from codelab.server.agent.context.registry import (
    ContextRegistryImpl,
    FileContextSource,
    SkillCatalogSource,
    SkillContextSource,
)


class TestFileContextSource:
    """Тесты для FileContextSource."""

    @pytest.mark.asyncio
    async def test_source_id_is_path(self):
        """source_id должен быть путём к файлу."""
        source = FileContextSource("/path/to/file.py", "content")
        assert source.source_id == "/path/to/file.py"

    @pytest.mark.asyncio
    async def test_render_returns_content(self):
        """render() должен возвращать содержимое файла."""
        source = FileContextSource("/path/to/file.py", "def hello(): pass")
        content = await source.render()
        assert content == "def hello(): pass"

    @pytest.mark.asyncio
    async def test_fingerprint_deterministic(self):
        """fingerprint() должен быть детерминированным."""
        source = FileContextSource("/path/to/file.py", "content")
        fp1 = await source.fingerprint()
        fp2 = await source.fingerprint()
        assert fp1 == fp2

    @pytest.mark.asyncio
    async def test_fingerprint_changes_with_content(self):
        """fingerprint() должен меняться при изменении содержимого."""
        source1 = FileContextSource("/path/to/file.py", "content1")
        source2 = FileContextSource("/path/to/file.py", "content2")
        
        fp1 = await source1.fingerprint()
        fp2 = await source2.fingerprint()
        
        assert fp1 != fp2


class TestSkillContextSource:
    """Тесты для SkillContextSource."""

    @pytest.mark.asyncio
    async def test_source_id_has_prefix(self):
        """source_id должен иметь префикс 'skill:'."""
        source = SkillContextSource("python_basics", "skill content")
        assert source.source_id == "skill:python_basics"

    @pytest.mark.asyncio
    async def test_render_returns_content(self):
        """render() должен возвращать содержимое скилла."""
        source = SkillContextSource("python_basics", "Python is great")
        content = await source.render()
        assert content == "Python is great"

    @pytest.mark.asyncio
    async def test_fingerprint_deterministic(self):
        """fingerprint() должен быть детерминированным."""
        source = SkillContextSource("skill_id", "content")
        fp1 = await source.fingerprint()
        fp2 = await source.fingerprint()
        assert fp1 == fp2


class TestContextRegistryImpl:
    """Тесты для ContextRegistryImpl."""

    @pytest.mark.asyncio
    async def test_register_source(self):
        """register() должен добавлять источник в реестр."""
        registry = ContextRegistryImpl()
        source = FileContextSource("/file.py", "content")
        
        registry.register(source)
        
        assert "/file.py" in registry.list_sources()

    @pytest.mark.asyncio
    async def test_unregister_source(self):
        """unregister() должен удалять источник из реестра."""
        registry = ContextRegistryImpl()
        source = FileContextSource("/file.py", "content")
        
        registry.register(source)
        registry.unregister("/file.py")
        
        assert "/file.py" not in registry.list_sources()

    @pytest.mark.asyncio
    async def test_get_source(self):
        """get_source() должен возвращать источник по ID."""
        registry = ContextRegistryImpl()
        source = FileContextSource("/file.py", "content")
        
        registry.register(source)
        retrieved = registry.get_source("/file.py")
        
        assert retrieved is source

    @pytest.mark.asyncio
    async def test_get_source_not_found(self):
        """get_source() должен возвращать None для несуществующего ID."""
        registry = ContextRegistryImpl()
        retrieved = registry.get_source("/nonexistent.py")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_render_baseline_combines_all_sources(self):
        """render_baseline() должен объединять все источники."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("/file1.py", "content1"))
        registry.register(FileContextSource("/file2.py", "content2"))
        
        baseline = await registry.render_baseline()
        
        assert "content1" in baseline
        assert "content2" in baseline

    @pytest.mark.asyncio
    async def test_render_baseline_empty_registry(self):
        """render_baseline() должен возвращать пустую строку для пустого реестра."""
        registry = ContextRegistryImpl()
        baseline = await registry.render_baseline()
        assert baseline == ""

    @pytest.mark.asyncio
    async def test_render_updates_only_changed(self):
        """render_updates() должен рендерить только изменённые источники."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("/file1.py", "content1"))
        registry.register(FileContextSource("/file2.py", "content2"))
        
        updates = await registry.render_updates(["/file1.py"])
        
        assert "content1" in updates
        assert "content2" not in updates

    @pytest.mark.asyncio
    async def test_detect_changes_first_time(self):
        """detect_changes() должен возвращать все источники при первом вызове."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("/file1.py", "content1"))
        registry.register(FileContextSource("/file2.py", "content2"))
        
        changes = await registry.detect_changes()
        
        assert len(changes) == 2
        assert "/file1.py" in changes
        assert "/file2.py" in changes

    @pytest.mark.asyncio
    async def test_detect_changes_no_changes(self):
        """detect_changes() не должен возвращать изменения если ничего не изменилось."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("/file1.py", "content1"))
        
        # Первый вызов фиксирует fingerprint
        await registry.detect_changes()
        
        # Второй вызов не должен обнаружить изменений
        changes = await registry.detect_changes()
        assert len(changes) == 0

    @pytest.mark.asyncio
    async def test_snapshot_returns_fingerprints(self):
        """snapshot() должен возвращать словарь fingerprint'ов."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("/file1.py", "content1"))
        registry.register(FileContextSource("/file2.py", "content2"))
        
        snapshot = await registry.snapshot()
        
        assert len(snapshot) == 2
        assert "/file1.py" in snapshot
        assert "/file2.py" in snapshot
        assert len(snapshot["/file1.py"]) == 16  # SHA256 truncated to 16 chars

    @pytest.mark.asyncio
    async def test_list_sources(self):
        """list_sources() должен возвращать список ID источников."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("/file1.py", "content1"))
        registry.register(SkillContextSource("skill1", "skill content"))
        
        sources = registry.list_sources()
        
        assert len(sources) == 2
        assert "/file1.py" in sources
        assert "skill:skill1" in sources

    @pytest.mark.asyncio
    async def test_multiple_sources_same_render(self):
        """Несколько источников должны корректно рендериться вместе."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("/main.py", "def main(): pass"))
        registry.register(FileContextSource("/utils.py", "def helper(): pass"))
        registry.register(SkillContextSource("python", "Python tips"))
        
        baseline = await registry.render_baseline()
        
        assert "def main(): pass" in baseline
        assert "def helper(): pass" in baseline
        assert "Python tips" in baseline


class TestSkillCatalogSource:
    """Тесты для SkillCatalogSource."""

    @pytest.mark.asyncio
    async def test_source_id_is_skill_catalog(self):
        """source_id должен быть 'skill_catalog'."""
        source = SkillCatalogSource([])
        assert source.source_id == "skill_catalog"

    @pytest.mark.asyncio
    async def test_render_empty_skills(self):
        """render() должен возвращать пустую строку для пустого списка."""
        source = SkillCatalogSource([])
        content = await source.render()
        assert content == ""

    @pytest.mark.asyncio
    async def test_render_with_skills(self):
        """render() должен рендерить каталог скиллов."""
        skills = [
            {"name": "python", "description": "Python tips"},
            {"name": "testing", "description": "Testing best practices"},
        ]
        source = SkillCatalogSource(skills)
        content = await source.render()
        
        assert "<available_skills>" in content
        assert "</available_skills>" in content
        assert "python" in content
        assert "testing" in content
        assert "Python tips" in content

    @pytest.mark.asyncio
    async def test_fingerprint_deterministic(self):
        """fingerprint() должен быть детерминированным."""
        skills = [{"name": "python", "description": "Python tips"}]
        source = SkillCatalogSource(skills)
        fp1 = await source.fingerprint()
        fp2 = await source.fingerprint()
        assert fp1 == fp2

    @pytest.mark.asyncio
    async def test_fingerprint_changes_with_skills(self):
        """fingerprint() должен меняться при изменении набора скиллов."""
        source1 = SkillCatalogSource([{"name": "python", "description": "Python tips"}])
        source2 = SkillCatalogSource([
            {"name": "python", "description": "Python tips"},
            {"name": "testing", "description": "Testing practices"},
        ])
        
        fp1 = await source1.fingerprint()
        fp2 = await source2.fingerprint()
        
        assert fp1 != fp2

    @pytest.mark.asyncio
    async def test_render_sorted_by_name(self):
        """render() должен сортировать скиллы по имени."""
        skills = [
            {"name": "zebra", "description": "Z"},
            {"name": "alpha", "description": "A"},
        ]
        source = SkillCatalogSource(skills)
        content = await source.render()
        
        # alpha должен быть перед zebra
        alpha_pos = content.find("alpha")
        zebra_pos = content.find("zebra")
        assert alpha_pos < zebra_pos
