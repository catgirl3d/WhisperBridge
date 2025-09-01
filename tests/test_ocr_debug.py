import sys
import os
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tempfile

# Добавить путь к модулям проекта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from whisperbridge.core.ocr_manager import OCREngineManager, OCREngine
from whisperbridge.services.ocr_service import OCRService, OCRRequest
from whisperbridge.core.config import settings


class OCRDebugTest:
    def __init__(self):
        self.manager = OCREngineManager()
        self.service = OCRService()
        self.test_results = []

    def create_test_image(self, text="Hello World", languages=["en"]):
        """Создать простое тестовое изображение с текстом."""
        # Создаем изображение 300x100 пикселей
        img = Image.new('RGB', (300, 100), color='white')
        draw = ImageDraw.Draw(img)

        # Пытаемся использовать системный шрифт, если не найдется - используем дефолтный
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            except:
                font = ImageFont.load_default()

        # Рисуем текст
        draw.text((10, 30), text, fill='black', font=font)
        return img

    def test_engine_initialization(self):
        """Тест инициализации движков."""
        print("\n=== Тест инициализации движков ===")

        # Тест EasyOCR
        easyocr_success = self.manager.initialize_engine(OCREngine.EASYOCR, ["en"])
        print(f"EasyOCR инициализация: {'УСПЕХ' if easyocr_success else 'ПРОВАЛ'}")

        # Проверка доступных движков
        available = self.manager.get_available_engines()
        print(f"Доступные движки: {[e.value for e in available]}")

        self.test_results.append({
            'test': 'engine_initialization',
            'easyocr': easyocr_success,
            'available': len(available)
        })

        return easyocr_success

    def test_basic_recognition(self):
        """Базовый тест распознавания."""
        print("\n=== Тест базового распознавания ===")

        # Создаем тестовое изображение
        test_text = "Hello World Test"
        img = self.create_test_image(test_text)

        # Создаем запрос
        request = OCRRequest(
            image=img,
            languages=["en"],
            preprocess=False,
            use_cache=False
        )

        # Обрабатываем через сервис
        start_time = time.time()
        response = self.service.process_image(request)
        processing_time = time.time() - start_time

        print(f"Распознанный текст: '{response.text}'")
        print(f"Уверенность: {response.confidence:.3f}")
        print(f"Движок: {response.engine_used.value}")
        print(f"Время обработки: {processing_time:.3f} сек")
        print(f"Успех: {response.success}")

        # Проверяем, содержит ли результат ожидаемый текст
        success = test_text.lower() in response.text.lower() and response.success

        self.test_results.append({
            'test': 'basic_recognition',
            'recognized_text': response.text,
            'confidence': response.confidence,
            'engine': response.engine_used.value,
            'processing_time': processing_time,
            'success': success
        })

        return success

    def test_multilingual_issue(self):
        """Тест проблемы с многоязычностью в PaddleOCR."""
        print("\n=== Тест многоязычности ===")

        # Создаем изображение с текстом на английском
        test_text = "Hello World"
        img = self.create_test_image(test_text)

        # Тестируем с несколькими языками
        languages = ["en", "ru", "fr"]

        print(f"Тестируем с языками: {languages}")


        # Тестируем EasyOCR с несколькими языками
        if self.manager.is_engine_available(OCREngine.EASYOCR):
            print("Тестируем EasyOCR с несколькими языками...")

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
                img.save(temp_path, 'PNG')

            try:
                result = self.manager.process_image(OCREngine.EASYOCR, temp_path, languages)
                print(f"EasyOCR результат: '{result.text}' (уверенность: {result.confidence:.3f})")

            finally:
                os.unlink(temp_path)

        self.test_results.append({
            'test': 'multilingual_issue',
            'languages_tested': languages,
            'easy_available': self.manager.is_engine_available(OCREngine.EASYOCR)
        })

        return True

    def test_performance_comparison(self):
        """Сравнение производительности с/без временных файлов."""
        print("\n=== Тест производительности ===")

        # Создаем тестовое изображение
        img = self.create_test_image("Performance Test")

        # Тест через сервис (с временным файлом)
        request = OCRRequest(
            image=img,
            languages=["en"],
            preprocess=False,
            use_cache=False
        )

        print("Тестируем через OCRService (с tempfile)...")
        start_time = time.time()
        for _ in range(3):  # Несколько итераций для усреднения
            response = self.service.process_image(request)
        service_time = (time.time() - start_time) / 3

        print(".3f")

        # Тест напрямую через manager (тоже с tempfile, так как код требует путь к файлу)
        print("Тестируем напрямую через OCREngineManager...")
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_path = temp_file.name
            img.save(temp_path, 'PNG')

        try:
            start_time = time.time()
            for _ in range(3):
                if self.manager.is_engine_available(OCREngine.EASYOCR):
                    result = self.manager.process_image(temp_path, ["en"])
            manager_time = (time.time() - start_time) / 3

            print(".3f")

            # Сравнение
            ratio = manager_time / service_time if service_time > 0 else 0
            print(".2f")

        finally:
            os.unlink(temp_path)

        self.test_results.append({
            'test': 'performance_comparison',
            'service_time': service_time,
            'manager_time': manager_time,
            'ratio': ratio
        })

        return True

    def test_error_handling(self):
        """Тест обработки ошибок."""
        print("\n=== Тест обработки ошибок ===")

        # Тест 1: None изображение
        print("Тест 1: None изображение")
        try:
            request = OCRRequest(
                image=None,  # type: ignore
                languages=["en"],
                preprocess=False,
                use_cache=False
            )
            response = self.service.process_image(request)
            print(f"Результат с None: success={response.success}, error='{response.error_message}'")
        except Exception as e:
            print(f"Исключение с None: {e}")

        # Тест 2: Пустое изображение
        print("Тест 2: Пустое изображение")
        empty_img = Image.new('RGB', (10, 10), color='white')
        request = OCRRequest(
            image=empty_img,
            languages=["en"],
            preprocess=False,
            use_cache=False
        )
        response = self.service.process_image(request)
        print(f"Результат с пустым изображением: success={response.success}, text='{response.text}'")

        # Тест 3: Неинициализированный движок
        print("Тест 3: Неинициализированный движок")
        # Создаем новый manager без инициализации
        test_manager = OCREngineManager()
        img = self.create_test_image("Test")
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_path = temp_file.name
            img.save(temp_path, 'PNG')

        try:
            result = test_manager.process_image(temp_path, ["en"])
            print(f"Результат с неинициализированным движком: success={result.success}, error='{result.error_message}'")
        finally:
            os.unlink(temp_path)

        self.test_results.append({
            'test': 'error_handling',
            'none_image_tested': True,
            'empty_image_tested': True,
            'uninitialized_engine_tested': True
        })

        return True

    def run_all_tests(self):
        """Запустить все тесты."""
        print("=== ЗАПУСК OCR DEBUG ТЕСТОВ ===")
        print(f"Текущее время: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Инициализируем сервис
        print("Инициализация OCR сервиса...")
        self.service.start_background_initialization()

        # Ждем инициализации
        timeout = 30
        start_wait = time.time()
        while not self.service.is_initialized and (time.time() - start_wait) < timeout:
            time.sleep(1)

        if not self.service.is_initialized:
            print("ВНИМАНИЕ: OCR сервис не инициализирован в течение 30 секунд")

        # Запускаем тесты
        tests = [
            self.test_engine_initialization,
            self.test_basic_recognition,
            self.test_multilingual_issue,
            self.test_performance_comparison,
            self.test_error_handling
        ]

        results = []
        for test in tests:
            try:
                result = test()
                results.append(result)
            except Exception as e:
                print(f"ОШИБКА в тесте {test.__name__}: {e}")
                results.append(False)

        # Итоги
        print("\n=== ИТОГИ ТЕСТИРОВАНИЯ ===")
        passed = sum(results)
        total = len(results)
        print(f"Пройдено тестов: {passed}/{total}")

        # Выводим результаты всех тестов
        print("\n=== ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ ===")
        for result in self.test_results:
            print(f"Тест: {result['test']}")
            for key, value in result.items():
                if key != 'test':
                    print(f"  {key}: {value}")
            print()

        # Выводим выявленные проблемы
        print("=== ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ ===")
        issues = []

        # Проблема 1: Сохранение во временный файл
        issues.append("- Все OCR движки требуют путь к файлу вместо прямой передачи numpy массива")
        issues.append("  Это снижает производительность из-за операций I/O")


        # Проблема 3: Агрегация через пробелы
        issues.append("- Текст из разных областей объединяется простым пробелом")
        issues.append("  Не учитывается структура документа и форматирование")

        # Проблема 4: Пороги уверенности
        issues.append("- Используются фиксированные пороги уверенности")
        issues.append("  Может приводить к потере текста с низкой уверенностью")

        for issue in issues:
            print(issue)

        print("\n=== РЕКОМЕНДАЦИИ ===")
        recommendations = [
            "1. Модифицировать OCR движки для работы с numpy массивами напрямую",
            "2. Улучшить агрегацию текста с учетом структуры",
            "3. Добавить адаптивные пороги уверенности",
            "4. Добавить больше логирования для отладки"
        ]

        for rec in recommendations:
            print(rec)

        return passed == total


if __name__ == "__main__":
    # Создаем и запускаем тесты
    tester = OCRDebugTest()
    success = tester.run_all_tests()

    print(f"\nОбщий результат: {'УСПЕХ' if success else 'ЕСТЬ ПРОБЛЕМЫ'}")
    sys.exit(0 if success else 1)