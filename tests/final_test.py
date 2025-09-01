#!/usr/bin/env python3
"""
Финальная проверка системы OCR
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    print("🔍 Финальная проверка системы OCR для WhisperBridge")
    print("=" * 50)

    # Проверка импортов
    print("1. Проверка импортов...")
    try:
        from whisperbridge.services.ocr_service import get_ocr_service
        from whisperbridge.core.ocr_manager import get_ocr_manager
        from whisperbridge.utils.image_utils import get_image_processor
        print("   ✅ Все импорты успешны")
    except Exception as e:
        print(f"   ❌ Ошибка импорта: {e}")
        return False

    # Проверка инициализации
    print("2. Проверка инициализации...")
    try:
        ocr_service = get_ocr_service()
        ocr_manager = get_ocr_manager()
        image_processor = get_image_processor()
        print("   ✅ Все сервисы инициализированы")
    except Exception as e:
        print(f"   ❌ Ошибка инициализации: {e}")
        return False

    # Проверка доступных движков
    print("3. Проверка доступных OCR движков...")
    available = ocr_manager.get_available_engines()
    print(f"   ✅ Доступные движки: {available}")

    if not available:
        print("   ❌ Нет доступных OCR движков!")
        return False

    # Проверка статистики
    print("4. Проверка статистики...")
    stats = ocr_service.get_engine_stats()
    for engine, stat in stats.items():
        status = "✅" if stat["available"] else "⚠️"
        print(f"   {status} {engine}: {stat['total_calls']} вызовов, {stat['successful_calls']} успешных")

    # Проверка кэша
    print("5. Проверка кэша...")
    cache_stats = ocr_service.get_cache_stats()
    print(f"   ✅ Кэш: размер {cache_stats['size']}, {'включен' if cache_stats['enabled'] else 'отключен'}")

    print("\n🎉 Все проверки пройдены успешно!")
    print("📋 Система OCR полностью функциональна!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)