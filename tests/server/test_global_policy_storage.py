"""Unit тесты для GlobalPolicyStorage."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from codelab.server.exceptions import StorageError
from codelab.server.storage import GlobalPolicyStorage


class TestGlobalPolicyStorageInit:
    """Тесты инициализации."""

    @pytest.mark.asyncio
    async def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Создание ~/.acp/ если не существует."""
        policy_path = tmp_path / ".acp" / "global_permissions.json"
        storage = GlobalPolicyStorage(policy_path)

        # Директория не создана до первой операции
        assert not policy_path.parent.exists()

        # Создаётся при load
        await storage._ensure_directory()
        assert policy_path.parent.exists()

    @pytest.mark.asyncio
    async def test_init_with_custom_path(self, tmp_path: Path) -> None:
        """Инициализация с custom path."""
        custom_path = tmp_path / "custom" / "policies.json"
        storage = GlobalPolicyStorage(custom_path)

        assert storage._storage_path == custom_path

    @pytest.mark.asyncio
    async def test_init_with_default_path(self) -> None:
        """Инициализация с default path."""
        storage = GlobalPolicyStorage()

        expected = Path.home() / ".codelab" / "data" / "policies" / "global_permissions.json"
        assert storage._storage_path == expected


class TestGlobalPolicyStorageLoad:
    """Тесты загрузки policies."""

    @pytest.mark.asyncio
    async def test_load_empty_file(self, tmp_path: Path) -> None:
        """Загрузка пустого файла возвращает {}."""
        policy_path = tmp_path / "policies.json"
        policy_path.write_text("")

        storage = GlobalPolicyStorage(policy_path)
        policies = await storage.load()

        assert policies == {}

    @pytest.mark.asyncio
    async def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Несуществующий файл возвращает {}."""
        policy_path = tmp_path / "nonexistent.json"

        storage = GlobalPolicyStorage(policy_path)
        policies = await storage.load()

        assert policies == {}

    @pytest.mark.asyncio
    async def test_load_valid_file(self, tmp_path: Path) -> None:
        """Загрузка валидного файла с policies."""
        policy_path = tmp_path / "policies.json"
        test_data = {
            "version": 1,
            "policies": {"execute": "allow_always", "read": "reject_always"},
            "metadata": {"updated_at": "2026-04-16T14:30:00Z", "updated_by": "user"},
        }
        policy_path.write_text(json.dumps(test_data))

        storage = GlobalPolicyStorage(policy_path)
        policies = await storage.load()

        assert policies == {"execute": "allow_always", "read": "reject_always"}

    @pytest.mark.asyncio
    async def test_load_caches_result(self, tmp_path: Path) -> None:
        """Load кэширует результат в _cache."""
        policy_path = tmp_path / "policies.json"
        test_data = {
            "version": 1,
            "policies": {"execute": "allow_always"},
            "metadata": {},
        }
        policy_path.write_text(json.dumps(test_data))

        storage = GlobalPolicyStorage(policy_path)
        policies1 = await storage.load()

        # Кэш должен быть установлен
        assert storage._cache == {"execute": "allow_always"}
        assert policies1 == {"execute": "allow_always"}

    @pytest.mark.asyncio
    async def test_load_corrupted_json_raises_error(self, tmp_path: Path) -> None:
        """Поврежденный JSON вызывает StorageError."""
        policy_path = tmp_path / "policies.json"
        policy_path.write_text("{invalid json}")

        storage = GlobalPolicyStorage(policy_path)

        with pytest.raises(StorageError, match="Corrupted JSON"):
            await storage.load()


class TestGlobalPolicyStorageSave:
    """Тесты сохранения policies."""

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path: Path) -> None:
        """Сохранение и загрузка policies."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        test_policies = {"execute": "allow_always", "read": "reject_always"}
        await storage.save(test_policies)

        # Загрузить и проверить
        loaded = await storage.load()
        assert loaded == test_policies

    @pytest.mark.asyncio
    async def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Save создаёт директорию если не существует."""
        policy_path = tmp_path / "subdir" / "subdir2" / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        assert not policy_path.parent.exists()

        await storage.save({"execute": "allow_always"})

        assert policy_path.exists()
        assert policy_path.parent.exists()

    @pytest.mark.asyncio
    async def test_save_includes_metadata(self, tmp_path: Path) -> None:
        """Save включает metadata с timestamp."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.save({"execute": "allow_always"})

        # Прочитать напрямую из файла
        with open(policy_path) as f:
            data = json.load(f)

        assert "metadata" in data
        assert "updated_at" in data["metadata"]
        assert "updated_by" in data["metadata"]

    @pytest.mark.asyncio
    async def test_save_atomic_write(self, tmp_path: Path) -> None:
        """Save использует atomic write (temp file -> rename)."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        # Сохранить
        await storage.save({"execute": "allow_always"})

        # Проверить что нет .tmp файла
        temp_path = policy_path.with_suffix(".json.tmp")
        assert not temp_path.exists()
        assert policy_path.exists()

    @pytest.mark.asyncio
    async def test_save_updates_cache(self, tmp_path: Path) -> None:
        """Save обновляет кэш."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        test_policies = {"execute": "allow_always"}
        await storage.save(test_policies)

        assert storage._cache == test_policies


class TestGlobalPolicyStorageGetPolicy:
    """Тесты получения policy."""

    @pytest.mark.asyncio
    async def test_get_policy_existing(self, tmp_path: Path) -> None:
        """Получение существующей policy."""
        policy_path = tmp_path / "policies.json"
        test_data = {
            "version": 1,
            "policies": {"execute": "allow_always"},
            "metadata": {},
        }
        policy_path.write_text(json.dumps(test_data))

        storage = GlobalPolicyStorage(policy_path)
        result = await storage.get_policy("execute")

        assert result == "allow_always"

    @pytest.mark.asyncio
    async def test_get_policy_nonexistent(self, tmp_path: Path) -> None:
        """Получение несуществующей policy возвращает None."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        result = await storage.get_policy("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_policy_uses_cache(self, tmp_path: Path) -> None:
        """Get_policy использует кэш."""
        policy_path = tmp_path / "policies.json"
        test_data = {
            "version": 1,
            "policies": {"execute": "allow_always"},
            "metadata": {},
        }
        policy_path.write_text(json.dumps(test_data))

        storage = GlobalPolicyStorage(policy_path)

        # Загрузить для кэша
        await storage.load()

        # Удалить файл
        policy_path.unlink()

        # get_policy вернёт из кэша
        result = await storage.get_policy("execute")
        assert result == "allow_always"

    @pytest.mark.asyncio
    async def test_get_policy_loads_if_not_cached(self, tmp_path: Path) -> None:
        """Get_policy загружает если кэш не инициализирован."""
        policy_path = tmp_path / "policies.json"
        test_data = {
            "version": 1,
            "policies": {"read": "reject_always"},
            "metadata": {},
        }
        policy_path.write_text(json.dumps(test_data))

        storage = GlobalPolicyStorage(policy_path)

        # Без предварительного load
        result = await storage.get_policy("read")

        assert result == "reject_always"
        assert storage._cache is not None


class TestGlobalPolicyStorageSetPolicy:
    """Тесты установления policy."""

    @pytest.mark.asyncio
    async def test_set_policy(self, tmp_path: Path) -> None:
        """Установление policy."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")

        # Проверить что сохранилось
        loaded = await storage.load()
        assert loaded["execute"] == "allow_always"

    @pytest.mark.asyncio
    async def test_set_policy_multiple(self, tmp_path: Path) -> None:
        """Установление нескольких policies."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        await storage.set_policy("read", "reject_always")

        loaded = await storage.load()
        assert loaded == {"execute": "allow_always", "read": "reject_always"}

    @pytest.mark.asyncio
    async def test_set_policy_overwrite(self, tmp_path: Path) -> None:
        """Перезапись existing policy."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        await storage.set_policy("execute", "reject_always")

        loaded = await storage.load()
        assert loaded["execute"] == "reject_always"

    @pytest.mark.asyncio
    async def test_set_policy_invalid_decision(self, tmp_path: Path) -> None:
        """Невалидное решение вызывает ValueError."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        with pytest.raises(ValueError, match="Invalid decision"):
            await storage.set_policy("execute", "invalid")

    @pytest.mark.asyncio
    async def test_set_policy_updates_cache(self, tmp_path: Path) -> None:
        """Set_policy обновляет кэш."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")

        assert storage._cache == {"execute": "allow_always"}


class TestGlobalPolicyStorageDeletePolicy:
    """Тесты удаления policy."""

    @pytest.mark.asyncio
    async def test_delete_policy(self, tmp_path: Path) -> None:
        """Удаление policy."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        deleted = await storage.delete_policy("execute")

        assert deleted is True
        loaded = await storage.load()
        assert "execute" not in loaded

    @pytest.mark.asyncio
    async def test_delete_policy_nonexistent(self, tmp_path: Path) -> None:
        """Удаление несуществующей policy возвращает False."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        deleted = await storage.delete_policy("nonexistent")

        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_policy_preserves_others(self, tmp_path: Path) -> None:
        """Удаление сохраняет другие policies."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        await storage.set_policy("read", "reject_always")

        await storage.delete_policy("execute")

        loaded = await storage.load()
        assert loaded == {"read": "reject_always"}

    @pytest.mark.asyncio
    async def test_delete_policy_updates_cache(self, tmp_path: Path) -> None:
        """Delete_policy обновляет кэш."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        await storage.delete_policy("execute")

        assert storage._cache == {}


class TestGlobalPolicyStorageListPolicies:
    """Тесты списка policies."""

    @pytest.mark.asyncio
    async def test_list_policies_empty(self, tmp_path: Path) -> None:
        """Список пустых policies."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        policies = await storage.list_policies()

        assert policies == {}

    @pytest.mark.asyncio
    async def test_list_policies(self, tmp_path: Path) -> None:
        """Список всех policies."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        await storage.set_policy("read", "reject_always")

        policies = await storage.list_policies()

        assert policies == {"execute": "allow_always", "read": "reject_always"}

    @pytest.mark.asyncio
    async def test_list_policies_returns_copy(self, tmp_path: Path) -> None:
        """List_policies возвращает копию."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")

        policies1 = await storage.list_policies()
        policies2 = await storage.list_policies()

        # Модификация первого не влияет на второе
        policies1["new"] = "value"

        assert "new" not in policies2


class TestGlobalPolicyStorageClearAll:
    """Тесты очистки всех policies."""

    @pytest.mark.asyncio
    async def test_clear_all(self, tmp_path: Path) -> None:
        """Очистка всех policies."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        await storage.set_policy("read", "reject_always")

        await storage.clear_all()

        loaded = await storage.load()
        assert loaded == {}

    @pytest.mark.asyncio
    async def test_clear_all_updates_cache(self, tmp_path: Path) -> None:
        """Clear_all обновляет кэш."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")
        await storage.clear_all()

        assert storage._cache == {}


class TestGlobalPolicyStorageConcurrency:
    """Тесты конкурентности."""

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, tmp_path: Path) -> None:
        """Конкурентные async операции безопасны."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        # Запустить несколько операций параллельно
        async def set_and_get(tool_kind: str, decision: str) -> tuple[None, str | None]:
            await storage.set_policy(tool_kind, decision)
            result = await storage.get_policy(tool_kind)
            return result

        results = await asyncio.gather(
            set_and_get("execute", "allow_always"),
            set_and_get("read", "reject_always"),
            set_and_get("write", "allow_always"),
        )

        assert "allow_always" in results
        assert "reject_always" in results

    @pytest.mark.asyncio
    async def test_concurrent_set_operations(self, tmp_path: Path) -> None:
        """Конкурентные set операции."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        # Устанавливать policies одновременно
        await asyncio.gather(
            *(storage.set_policy(f"tool_{i}", "allow_always") for i in range(5))
        )

        # Все должны быть сохранены
        policies = await storage.list_policies()
        assert len(policies) == 5


class TestGlobalPolicyStorageEdgeCases:
    """Тесты граничных случаев."""

    @pytest.mark.asyncio
    async def test_policy_kind_with_special_chars(self, tmp_path: Path) -> None:
        """Tool kind со спецсимволами."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        tool_kind = "tool/with:special.chars"
        await storage.set_policy(tool_kind, "allow_always")

        result = await storage.get_policy(tool_kind)
        assert result == "allow_always"

    @pytest.mark.asyncio
    async def test_large_number_of_policies(self, tmp_path: Path) -> None:
        """Большое количество policies."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        # Установить 100 policies
        for i in range(100):
            decision = "allow_always" if i % 2 == 0 else "reject_always"
            await storage.set_policy(f"tool_{i}", decision)

        policies = await storage.list_policies()
        assert len(policies) == 100

    @pytest.mark.asyncio
    async def test_empty_string_tool_kind(self, tmp_path: Path) -> None:
        """Empty string как tool_kind."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("", "allow_always")

        result = await storage.get_policy("")
        assert result == "allow_always"

    @pytest.mark.asyncio
    async def test_multiple_loads_same_instance(self, tmp_path: Path) -> None:
        """Несколько load вызовов на одном экземпляре."""
        policy_path = tmp_path / "policies.json"
        storage = GlobalPolicyStorage(policy_path)

        await storage.set_policy("execute", "allow_always")

        # Первый load
        policies1 = await storage.load()

        # Изменить файл напрямую
        test_data = {
            "version": 1,
            "policies": {"read": "reject_always"},
            "metadata": {},
        }
        policy_path.write_text(json.dumps(test_data))

        # Второй load (должен перезагрузить)
        policies2 = await storage.load()

        assert policies1 == {"execute": "allow_always"}
        assert policies2 == {"read": "reject_always"}
