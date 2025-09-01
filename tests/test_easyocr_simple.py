import sys
import os
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Добавить путь к модулям проекта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from whisperbridge.core.ocr_manager import OCREngineManager, OCREngine
from whisperbridge.services.ocr_service import OCRService, OCRRequest


class EasyOCRSimpleTest:
    def __init__(self):
        self.manager = OCREngineManager()
        self.service = OCRService()
        self.test_images = {}

    def create_simple_test_image(self, text="Test Text", width=300, height=100, font_size=20):
        """Создать простое изображение с текстом."""
        # Создать белое изображение
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)

        try:
            # Попытаться использовать системный шрифт
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            # Использовать дефолтный шрифт если arial недоступен
            font = ImageFont.load_default()

        # Вычислить позицию текста для центрирования
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Нарисовать текст черным цветом
        draw.text((x, y), text, fill='black', font=font)

        return image

    def create_noisy_image(self, text="Noisy Text"):
        """Создать изображение с шумом."""
        image = self.create_simple_test_image(text)

        # Добавить случайный шум
        np_image = np.array(image)
        noise = np.random.randint(0, 50, np_image.shape, dtype=np.uint8)
        noisy_image = np.clip(np_image + noise, 0, 255).astype(np.uint8)

        return Image.fromarray(noisy_image)

    def create_multiline_image(self):
        """Создать многострочное изображение."""
        lines = ["First Line", "Second Line", "Third Line"]
        width, height = 300, 150
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()

        y_offset = 20
        for line in lines:
            draw.text((20, y_offset), line, fill='black', font=font)
            y_offset += 30

        return image

    def test_easyocr_initialization(self):
        """Тест инициализации только EasyOCR с новым API."""
        print("=== Testing EasyOCR Initialization ===")

        start_time = time.time()
        success = self.manager.initialize_engines(['en'])
        init_time = time.time() - start_time

        if success:
            print(f"✅ EasyOCR initialized successfully in {init_time:.3f} seconds")
        else:
            print("❌ EasyOCR initialization failed")

        return success, init_time

    def test_direct_easyocr_usage(self, image_path):
        """Прямое использование EasyOCR через OCREngineManager."""
        print("=== Testing Direct EasyOCR Usage ===")

        start_time = time.time()
        result = self.manager.process_image(image_path, ['en'])
        process_time = time.time() - start_time

        print(f"Direct OCR Result: '{result.text}'")
        print(f"Text processed in {process_time:.3f} seconds")
        return result, process_time

    def test_different_image_types(self):
        """Тест с разными типами изображений."""
        print("=== Testing Different Image Types ===")

        # Создать тестовые изображения
        simple_img = self.create_simple_test_image("Hello World")
        noisy_img = self.create_noisy_image("Noisy Text")
        multiline_img = self.create_multiline_image()

        images = {
            "simple": simple_img,
            "noisy": noisy_img,
            "multiline": multiline_img
        }

        results = {}

        for img_type, img in images.items():
            print(f"\n--- Testing {img_type} image ---")

            # Сохранить изображение во временный файл
            temp_path = f"temp_{img_type}.png"
            img.save(temp_path)

            try:
                result, process_time = self.test_direct_easyocr_usage(temp_path)
                results[img_type] = {
                    'result': result,
                    'time': process_time
                }
            finally:
                # Удалить временный файл
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        return results

    def test_numpy_array_processing(self):
        """Тест обработки numpy массивов."""
        print("=== Testing Numpy Array Processing ===")

        # Создать тестовое изображение
        test_img = self.create_simple_test_image("Numpy Test")
        image_array = np.array(test_img)

        # Инициализировать движок
        success = self.manager.initialize_engines(['en'])
        if not success:
            print("❌ Failed to initialize EasyOCR")
            return None

        # Тест обработки через process_image_array
        start_time = time.time()
        result = self.manager.process_image_array(image_array, ['en'])
        array_time = time.time() - start_time

        print(f"Numpy Array Result: '{result.text}'")
        print(f"Confidence: {result.confidence:.3f}")
        print(f"Processing time: {array_time:.3f} seconds")

        # Сравнение с обработкой файла
        temp_path = "temp_numpy_compare.png"
        test_img.save(temp_path)

        try:
            start_time = time.time()
            file_result = self.manager.process_image(temp_path, ['en'])
            file_time = time.time() - start_time

            print("\nComparison:")
            print(f"  Array processing: {array_time:.3f} seconds")
            print(f"  File processing: {file_time:.3f} seconds")
            print(f"  Performance difference: {file_time - array_time:.3f} seconds")

            return {
                'array_result': result,
                'file_result': file_result,
                'array_time': array_time,
                'file_time': file_time
            }

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_easyocr_performance(self):
        """Измерение производительности EasyOCR с файлами и массивами."""
        print("=== Testing EasyOCR Performance ===")

        # Создать тестовое изображение
        test_img = self.create_simple_test_image("Performance Test")
        temp_path = "temp_perf.png"
        test_img.save(temp_path)
        image_array = np.array(test_img)

        try:
            # Тест инициализации
            success, init_time = self.test_easyocr_initialization()

            if not success:
                return None

            # Тест обработки файла (несколько раз для усреднения)
            file_times = []
            for i in range(3):
                result, process_time = self.test_direct_easyocr_usage(temp_path)
                file_times.append(process_time)

            avg_file_time = sum(file_times) / len(file_times)

            # Тест обработки массива (несколько раз для усреднения)
            array_times = []
            for i in range(3):
                start_time = time.time()
                result = self.manager.process_image_array(image_array, ['en'])
                array_times.append(time.time() - start_time)

            avg_array_time = sum(array_times) / len(array_times)

            print("\n" + "=" * 20)
            print("Performance Results:")
            print(f"  - Initialization time: {init_time:.3f} seconds")
            print(f"  - Average file processing time: {avg_file_time:.3f} seconds")
            print(f"  - Average array processing time: {avg_array_time:.3f} seconds")
            print(f"  - Performance difference (file - array): {avg_file_time - avg_array_time:.3f} seconds")

            return {
                'init_time': init_time,
                'avg_file_time': avg_file_time,
                'avg_array_time': avg_array_time,
                'total_file_time': init_time + avg_file_time,
                'total_array_time': init_time + avg_array_time
            }

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_service_vs_direct(self):
        """Сравнение OCRService vs прямое использование."""
        print("=== Comparing OCRService vs Direct Usage ===")

        # Создать тестовое изображение
        test_img = self.create_simple_test_image("Comparison Test")

        # Инициализировать движки
        self.manager.initialize_engines(['en'])
        self.service.start_background_initialization()

        # Дать время на инициализацию
        time.sleep(2)

        # Тест через OCRService
        print("\n--- OCRService Test ---")
        request = OCRRequest(image=test_img, languages=['en'], use_cache=False)
        service_start = time.time()
        service_result = self.service.process_image(request)
        service_time = time.time() - service_start

        print(f"Service Result: '{service_result.text}'")
        print(f"Service processed in {service_time:.3f} seconds")
        # Тест прямого использования
        print("\n--- Direct Usage Test ---")
        temp_path = "temp_compare.png"
        test_img.save(temp_path)

        try:
            direct_result, direct_time = self.test_direct_easyocr_usage(temp_path)

            print("\n" + "=" * 20)
            print("Comparison Results:")
            print(f"  - OCRService time: {service_time:.3f} seconds")
            print(f"  - Direct usage time: {direct_time:.3f} seconds")
            return {
                'service': {
                    'result': service_result,
                    'time': service_time
                },
                'direct': {
                    'result': direct_result,
                    'time': direct_time
                }
            }

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_optimized_service(self):
        """Тест оптимизированного OCRService с numpy массивами."""
        print("=== Testing Optimized OCRService ===")

        # Создать тестовое изображение
        test_img = self.create_simple_test_image("Optimized Service Test")
        image_array = np.array(test_img)

        # Инициализировать сервис
        self.service.start_background_initialization()
        time.sleep(2)  # Дать время на инициализацию

        if not self.service.is_initialized:
            print("❌ OCRService failed to initialize")
            return None

        # Тест через OCRRequest с PIL изображением
        request = OCRRequest(image=test_img, languages=['en'], use_cache=False)
        start_time = time.time()
        response = self.service.process_image(request)
        service_time = time.time() - start_time

        print(f"Service Result: '{response.text}'")
        print(f"Confidence: {response.confidence:.3f}")
        print(f"Processing time: {service_time:.3f} seconds")
        print(f"Success: {response.success}")

        # Тест внутреннего метода _process_with_numpy_array
        start_time = time.time()
        internal_result = self.service._process_with_numpy_array(
            image_array, ['en'], timeout=10.0
        )
        internal_time = time.time() - start_time

        print("\nInternal method test:")
        print(f"Internal Result: '{internal_result.text}'")
        print(f"Confidence: {internal_result.confidence:.3f}")
        print(f"Processing time: {internal_time:.3f} seconds")

        return {
            'service_response': response,
            'internal_result': internal_result,
            'service_time': service_time,
            'internal_time': internal_time
        }

    def run_simple_tests(self):
        """Запуск всех простых тестов."""
        print("🚀 Starting EasyOCR Simple Tests")
        print("=" * 50)

        results = {}

        try:
            # Тест 1: Инициализация
            success, init_time = self.test_easyocr_initialization()
            results['initialization'] = {'success': success, 'time': init_time}

            if not success:
                print("❌ Cannot continue tests - EasyOCR initialization failed")
                return results

            # Тест 2: Разные типы изображений
            results['image_types'] = self.test_different_image_types()

            # Тест 3: Производительность
            results['performance'] = self.test_easyocr_performance()

            # Тест 4: Сравнение Service vs Direct
            results['comparison'] = self.test_service_vs_direct()

            # Тест 5: Numpy Array Processing
            results['numpy_processing'] = self.test_numpy_array_processing()

            # Тест 6: Optimized Service
            results['optimized_service'] = self.test_optimized_service()

            print("\n" + "=" * 50)
            print("✅ All tests completed successfully")

        except Exception as e:
            print(f"❌ Test execution failed: {e}")
            results['error'] = str(e)

        return results


if __name__ == "__main__":
    # Запуск простых тестов
    tester = EasyOCRSimpleTest()
    results = tester.run_simple_tests()

    print("\n📊 Test Summary:")
    print(f"Initialization: {'✅' if results.get('initialization', {}).get('success') else '❌'}")
    print(f"Image Types: {'✅' if 'image_types' in results else '❌'}")
    print(f"Performance: {'✅' if 'performance' in results else '❌'}")
    print(f"Comparison: {'✅' if 'comparison' in results else '❌'}")
    print(f"Numpy Processing: {'✅' if 'numpy_processing' in results else '❌'}")
    print(f"Optimized Service: {'✅' if 'optimized_service' in results else '❌'}")