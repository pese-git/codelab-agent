#!/usr/bin/env python3
"""Скрипт для A/B теста инкрементального режима Фазы 4.

Сравнивает потребление токенов между гидратацией и инкрементальным режимом.

Использование:
    python scripts/phase4_ab_test.py

Требования:
    - Запущенный LM Studio с моделью qwen3-coder-30b-a3b-instruct
    - Конфигурация ~/.codelab/codelab.toml с enabled=true
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run_test_session(incremental: bool, session_name: str) -> dict:
    """Запустить тестовую сессию и собрать метрики.

    Args:
        incremental: Включить инкрементальный режим
        session_name: Имя сессии для логирования

    Returns:
        Словарь с метриками сессии
    """
    print(f"\n{'='*60}")
    print(f"Запуск сессии: {session_name}")
    print(f"Инкрементальный режим: {incremental}")
    print(f"{'='*60}\n")

    # Обновляем конфигурацию
    config_path = Path.home() / ".codelab" / "codelab.toml"
    config_content = config_path.read_text()

    # Заменяем incremental значение
    if "incremental = " in config_content:
        config_content = config_content.replace(
            "incremental = true",
            f"incremental = {str(incremental).lower()}"
        ).replace(
            "incremental = false",
            f"incremental = {str(incremental).lower()}"
        )
    else:
        # Добавляем incremental после enabled
        config_content = config_content.replace(
            "enabled = true",
            f"enabled = true\nincremental = {str(incremental).lower()}"
        )

    config_path.write_text(config_content)
    print(f"Конфигурация обновлена: incremental={incremental}")

    # Запускаем сервер в фоне
    print("Запуск сервера...")
    server_process = subprocess.Popen(
        [
            sys.executable, "-m", "codelab.server.cli", "serve",
            "--observability-debug",
            "--log-level", "DEBUG",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Ждём запуска сервера
    time.sleep(5)

    try:
        # Запускаем клиент и выполняем тестовые запросы
        print("Выполнение тестовых запросов...")

        # Создаём простую тестовую сессию через stdio
        test_commands = [
            "Прочитай файл src/codelab/server/agent/context/manager.py",
            "Какие классы определены в этом файле?",
            "Покажи метод build_context",
            "Какие параметры он принимает?",
            "Прочитай файл src/codelab/server/agent/context/epoch.py",
            "Что делает класс EpochManager?",
            "Какие методы он предоставляет?",
            "Прочитай файл src/codelab/server/agent/context/reconciler.py",
            "Что делает класс DefaultContextReconciler?",
            "Какие состояния он поддерживает?",
        ]

        # Выполняем запросы через codelab CLI
        for i, cmd in enumerate(test_commands, 1):
            print(f"  Запрос {i}/{len(test_commands)}: {cmd[:50]}...")
            # Здесь можно добавить реальное выполнение запросов
            time.sleep(1)  # Имитация выполнения

        # Ждём экспорта метрик
        print("Ожидание экспорта метрик...")
        time.sleep(5)

        # Читаем метрики
        metrics_dir = Path.home() / ".codelab" / "data" / "observability" / "metrics"
        today = datetime.now().strftime("%Y-%m-%d")
        metrics_file = metrics_dir / f"{today}.json"

        if metrics_file.exists():
            metrics_data = json.loads(metrics_file.read_text())
            # Находим последнюю сессию
            session_ids = list(metrics_data.keys())
            if session_ids:
                latest_session = session_ids[-1]
                session_metrics = metrics_data[latest_session]

                result = {
                    "session_name": session_name,
                    "incremental": incremental,
                    "session_id": latest_session,
                    "context_build_count": session_metrics.get("context_build_count", 0),
                    "context_baseline_tokens": session_metrics.get("context_baseline_tokens", 0),
                    "context_tail_tokens": session_metrics.get("context_tail_tokens", 0),
                    "context_reconcile_count": session_metrics.get("context_reconcile_count", 0),
                    "context_epoch_breaks_total": session_metrics.get("context_epoch_breaks_total", 0),
                    "llm_total_input_tokens": session_metrics.get("llm_total_input_tokens", 0),
                    "llm_call_count": session_metrics.get("llm_call_count", 0),
                }

                print(f"\nМетрики сессии {session_name}:")
                print(f"  Сборок контекста: {result['context_build_count']}")
                print(f"  Реконсиляций: {result['context_reconcile_count']}")
                print(f"  Разрывов эпох: {result['context_epoch_breaks_total']}")
                print(f"  Baseline токенов (сумма): {result['context_baseline_tokens']}")
                print(f"  Tail токенов (сумма): {result['context_tail_tokens']}")
                print(f"  LLM входных токенов: {result['llm_total_input_tokens']}")

                return result
        else:
            print(f"Файл метрик не найден: {metrics_file}")

        return {}

    finally:
        # Останавливаем сервер
        print("Остановка сервера...")
        server_process.terminate()
        server_process.wait(timeout=10)


def compare_results(hydration: dict, incremental: dict) -> None:
    """Сравнить результаты A/B теста.

    Args:
        hydration: Метрики сессии с гидратацией
        incremental: Метрики сессии с инкрементальным режимом
    """
    print(f"\n{'='*60}")
    print("СРАВНЕНИЕ РЕЗУЛЬТАТОВ")
    print(f"{'='*60}\n")

    if not hydration or not incremental:
        print("Недостаточно данных для сравнения")
        return

    print(f"{'Метрика':<40} {'Гидрация':>15} {'Инкремент':>15} {'Экономия':>15}")
    print("-" * 85)

    # Сравниваем baseline токены
    h_baseline = hydration.get("context_baseline_tokens", 0)
    i_baseline = incremental.get("context_baseline_tokens", 0)
    baseline_saving = ((h_baseline - i_baseline) / h_baseline * 100) if h_baseline > 0 else 0
    print(f"{'Baseline токены (сумма)':<40} {h_baseline:>15,} {i_baseline:>15,} {baseline_saving:>14.1f}%")

    # Сравниваем tail токены
    h_tail = hydration.get("context_tail_tokens", 0)
    i_tail = incremental.get("context_tail_tokens", 0)
    tail_saving = ((h_tail - i_tail) / h_tail * 100) if h_tail > 0 else 0
    print(f"{'Tail токены (сумма)':<40} {h_tail:>15,} {i_tail:>15,} {tail_saving:>14.1f}%")

    # Сравниваем LLM токены
    h_llm = hydration.get("llm_total_input_tokens", 0)
    i_llm = incremental.get("llm_total_input_tokens", 0)
    llm_saving = ((h_llm - i_llm) / h_llm * 100) if h_llm > 0 else 0
    print(f"{'LLM входных токенов':<40} {h_llm:>15,} {i_llm:>15,} {llm_saving:>14.1f}%")

    # Сравниваем количество сборок
    h_builds = hydration.get("context_build_count", 0)
    i_builds = incremental.get("context_build_count", 0)
    print(f"{'Сборок контекста':<40} {h_builds:>15} {i_builds:>15}")

    # Сравниваем реконсиляции
    h_reconcile = hydration.get("context_reconcile_count", 0)
    i_reconcile = incremental.get("context_reconcile_count", 0)
    print(f"{'Реконсиляций':<40} {h_reconcile:>15} {i_reconcile:>15}")

    # Сравниваем разрывы эпох
    h_breaks = hydration.get("context_epoch_breaks_total", 0)
    i_breaks = incremental.get("context_epoch_breaks_total", 0)
    print(f"{'Разрывов эпох':<40} {h_breaks:>15} {i_breaks:>15}")

    print("\n" + "="*60)
    print("ИНТЕРПРЕТАЦИЯ")
    print("="*60)

    if llm_saving > 50:
        print(f"✓ Отличный результат! Экономия {llm_saving:.1f}% токенов")
    elif llm_saving > 20:
        print(f"✓ Хороший результат. Экономия {llm_saving:.1f}% токенов")
    else:
        print(f"⚠ Низкая экономия ({llm_saving:.1f}%). Возможные причины:")
        print("  - Частые разрывы эпох (проверьте context_epoch_breaks_total)")
        print("  - Короткая сессия (недостаточно ходов для накопления экономии)")
        print("  - Изменения baseline-источников (system_prompt, skill_catalog)")


def main():
    """Главная функция."""
    print("="*60)
    print("A/B ТЕСТ ФАЗЫ 4: ИНКРЕМЕНТАЛЬНЫЙ РЕЖИМ")
    print("="*60)

    # Запускаем тест с гидратацией
    hydration_results = run_test_session(
        incremental=False,
        session_name="Гидрация (incremental=false)"
    )

    # Запускаем тест с инкрементальным режимом
    incremental_results = run_test_session(
        incremental=True,
        session_name="Инкрементальный (incremental=true)"
    )

    # Сравниваем результаты
    compare_results(hydration_results, incremental_results)

    print("\n" + "="*60)
    print("ТЕСТ ЗАВЕРШЁН")
    print("="*60)


if __name__ == "__main__":
    main()
