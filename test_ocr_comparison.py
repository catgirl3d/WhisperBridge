import sys
import os
import time
import psutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

# Добавить путь к модулям проекта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from whisperbridge.core.ocr_manager import OCREngineManager, OCREngine
from whisperbridge.services.ocr_service import OCRService, OCRRequest


@dataclass
class ComparisonResult:
    """Результат сравнения OCR движков."""
    engine: str
    text: str
    confidence: float
    processing_time: float
    memory_usage: float
    success: bool
    error: Optional[str] = None
    image_type: str = "unknown"
    languages: List[str] = None

    def __post_init__(self):
        if self.languages is None:
            self.languages = []


@dataclass
class TestScenario:
    """Тестовый сценарий."""
    name: str
    image: Image.Image
    expected_text: str
    languages: List[str]
    description: str


class OCRComparisonTest:
    """Комплексный тест сравнения OCR движков."""

    def __init__(self):
        """Инициализация теста."""
        self.manager = OCREngineManager()
        self.service = OCRService()
        self.results: List[ComparisonResult] = []
        self.scenarios: List[TestScenario] = []
        self.performance_data: Dict[str, Any] = {}

    def create_test_scenarios(self) -> List[TestScenario]:
        """Создать разнообразные тестовые сценарии."""
        scenarios = []

        # Сценарий 1: Простой английский текст
        simple_img = self._create_simple_text_image("Hello World Test", "en")
        scenarios.append(TestScenario(
            name="simple_english",
            image=simple_img,
            expected_text="Hello World Test",
            languages=["en"],
            description="Simple English text on white background"
        ))

        # Сценарий 2: Многострочный текст
        multiline_img = self._create_multiline_image()
        scenarios.append(TestScenario(
            name="multiline_text",
            image=multiline_img,
            expected_text="First Line Second Line Third Line",
            languages=["en"],
            description="Multi-line text with structure"
        ))

        # Сценарий 3: Зашумленный текст
        noisy_img = self._create_noisy_image("Noisy Text Recognition")
        scenarios.append(TestScenario(
            name="noisy_text",
            image=noisy_img,
            expected_text="Noisy Text Recognition",
            languages=["en"],
            description="Text with random noise"
        ))

        # Сценарий 4: Многоязычный текст (английский + русский)
        mixed_img = self._create_mixed_language_image()
        scenarios.append(TestScenario(
            name="multilingual",
            image=mixed_img,
            expected_text="Hello Привет Test Тест",
            languages=["en", "ru"],
            description="Mixed English and Russian text"
        ))

        # Сценарий 5: Маленький шрифт
        small_font_img = self._create_simple_text_image("Small Font Test", "en", font_size=12)
        scenarios.append(TestScenario(
            name="small_font",
            image=small_font_img,
            expected_text="Small Font Test",
            languages=["en"],
            description="Text with small font size"
        ))

        # Сценарий 6: Размытый текст
        blurred_img = self._create_blurred_image("Blurred Text Test")
        scenarios.append(TestScenario(
            name="blurred_text",
            image=blurred_img,
            expected_text="Blurred Text Test",
            languages=["en"],
            description="Blurred text for quality testing"
        ))

        self.scenarios = scenarios
        return scenarios

    def _create_simple_text_image(self, text: str, lang: str, font_size: int = 20) -> Image.Image:
        """Создать простое изображение с текстом."""
        width, height = 400, 100
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)

        try:
            if lang == "ru":
                # Для русского текста использовать другой шрифт если возможно
                font = ImageFont.truetype("arial.ttf", font_size)
            else:
                font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        # Центрировать текст
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        draw.text((x, y), text, fill='black', font=font)
        return image

    def _create_multiline_image(self) -> Image.Image:
        """Создать многострочное изображение."""
        lines = ["First Line", "Second Line", "Third Line"]
        width, height = 300, 120
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

    def _create_noisy_image(self, text: str) -> Image.Image:
        """Создать изображение с шумом."""
        image = self._create_simple_text_image(text, "en")

        # Добавить случайный шум
        np_image = np.array(image)
        noise = np.random.randint(0, 30, np_image.shape, dtype=np.uint8)
        noisy_image = np.clip(np_image + noise, 0, 255).astype(np.uint8)

        return Image.fromarray(noisy_image)

    def _create_mixed_language_image(self) -> Image.Image:
        """Создать изображение с смешанными языками."""
        text = "Hello Привет Test Тест"
        width, height = 500, 100
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except:
            font = ImageFont.load_default()

        # Центрировать текст
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        draw.text((x, y), text, fill='black', font=font)
        return image

    def _create_blurred_image(self, text: str) -> Image.Image:
        """Создать размытое изображение."""
        image = self._create_simple_text_image(text, "en")

        # Применить размытие
        from PIL import ImageFilter
        return image.filter(ImageFilter.GaussianBlur(radius=1))

    def measure_performance(self, image_path: str,
                           languages: List[str], iterations: int = 3) -> Dict[str, Any]:
        """Измерить производительность EasyOCR."""
        engine = OCREngine.EASYOCR
        if not self.manager.is_engine_available(engine):
            return {
                'engine': engine.value,
                'available': False,
                'error': f'Engine {engine.value} not available'
            }

        process_times = []
        memory_usages = []
        results = []

        # Получить начальное использование памяти
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        for i in range(iterations):
            # Измерить использование памяти перед обработкой
            mem_before = process.memory_info().rss / 1024 / 1024

            start_time = time.time()
            result = self.manager.process_image(image_path, languages)
            end_time = time.time()

            # Измерить использование памяти после обработки
            mem_after = process.memory_info().rss / 1024 / 1024

            process_times.append(end_time - start_time)
            memory_usages.append(mem_after - mem_before)
            results.append(result)

            # Небольшая задержка между итерациями
            time.sleep(0.05)

        avg_time = sum(process_times) / len(process_times)
        avg_memory = sum(memory_usages) / len(memory_usages)

        successful_results = [r for r in results if r.success]
        avg_confidence = sum(r.confidence for r in successful_results) / len(successful_results) if successful_results else 0.0

        return {
            'engine': engine.value,
            'available': True,
            'avg_processing_time': avg_time,
            'avg_memory_usage': avg_memory,
            'avg_confidence': avg_confidence,
            'success_rate': len(successful_results) / len(results),
            'iterations': iterations
        }

    def compare_engines(self) -> Dict[str, Any]:
        """Сравнить оба движка на всех сценариях."""
        print("🚀 Starting OCR Engine Comparison")
        print("=" * 60)

        comparison_results = {
            'scenarios': [],
            'performance': {},
            'issues': [],
            'recommendations': []
        }

        # Инициализация движков
        print("📋 Initializing OCR engines...")
        engines_initialized = []

        # Initialize EasyOCR engine
        start_time = time.time()
        success = self.manager.initialize_engine(OCREngine.EASYOCR, ["en", "ru"])
        init_time = time.time() - start_time

        if success:
            engines_initialized.append(OCREngine.EASYOCR)
            print(".3f")
        else:
            print("❌ EASYOCR initialization failed"

        if not engines_initialized:
            comparison_results['issues'].append("No OCR engines could be initialized")
            return comparison_results

        # Создать тестовые сценарии
        scenarios = self.create_test_scenarios()
        print(f"📸 Created {len(scenarios)} test scenarios")

        # Тестировать каждый сценарий
        for scenario in scenarios:
            print(f"\n🔍 Testing scenario: {scenario.name}")
            print(f"   Description: {scenario.description}")

            scenario_results = {
                'name': scenario.name,
                'description': scenario.description,
                'expected_text': scenario.expected_text,
                'engines': {}
            }

            # Сохранить изображение во временный файл
            temp_path = None
            try:
                # Создать временный файл
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                    temp_path = temp_file.name
                    scenario.image.save(temp_path, 'PNG')

                # Небольшая задержка для освобождения файла
                time.sleep(0.1)

                # Тестировать каждый доступный движок
                for engine in engines_initialized:
                    print(f"   Testing {engine.value.upper()}...")

                    perf_data = self.measure_performance(
                        temp_path, scenario.languages
                    )

                    if perf_data['available']:
                        # Создать результат сравнения
                        result = ComparisonResult(
                            engine=engine.value,
                            text="",  # Будет заполнено из perf_data если нужно
                            confidence=perf_data['avg_confidence'],
                            processing_time=perf_data['avg_processing_time'],
                            memory_usage=perf_data['avg_memory_usage'],
                            success=perf_data['success_rate'] > 0,
                            image_type=scenario.name,
                            languages=scenario.languages
                        )

                        scenario_results['engines'][engine.value] = {
                            'performance': perf_data,
                            'result': result
                        }

                        print(f"     Time: {perf_data['avg_processing_time']:.3f}s, "
                              f"Confidence: {perf_data['avg_confidence']:.1f}, "
                              f"Success: {perf_data['success_rate']:.3f}")

                        self.results.append(result)
                    else:
                        print(f"   ❌ {engine.value.upper()} not available")

            except Exception as e:
                print(f"   ❌ Error testing scenario {scenario.name}: {e}")
                scenario_results['error'] = str(e)
            finally:
                # Удалить временный файл с повторными попытками
                if temp_path and os.path.exists(temp_path):
                    for attempt in range(5):
                        try:
                            os.unlink(temp_path)
                            break
                        except OSError:
                            if attempt < 4:
                                time.sleep(0.2)  # Подождать перед следующей попыткой
                            else:
                                print(f"   ⚠️  Could not delete temp file: {temp_path}")

            comparison_results['scenarios'].append(scenario_results)

        # Анализ проблем
        comparison_results['issues'] = self._analyze_issues(comparison_results)

        # Генерация рекомендаций
        comparison_results['recommendations'] = self._generate_recommendations(comparison_results)

        return comparison_results

    def _analyze_issues(self, comparison_results: Dict[str, Any]) -> List[str]:
        """Анализировать выявленные проблемы."""
        issues = []

        # Проверить доступность движков
        available_engines = [e.value for e in self.manager.get_available_engines()]
        if len(available_engines) < 2:
            issues.append(f"Only {len(available_engines)} OCR engines available: {available_engines}")

        # Проверить производительность
        for scenario in comparison_results['scenarios']:
            for engine_name, engine_data in scenario['engines'].items():
                perf = engine_data['performance']

                if perf['avg_processing_time'] > 2.0:
                    issues.append(f"Slow processing in {scenario['name']} for {engine_name}: {perf['avg_processing_time']:.3f}s")

                if perf['success_rate'] < 0.5:
                    issues.append(f"Low success rate in {scenario['name']} for {engine_name}: {perf['success_rate']:.1%}")


        return issues

    def _generate_recommendations(self, comparison_results: Dict[str, Any]) -> List[str]:
        """Сгенерировать рекомендации по улучшению."""
        recommendations = []

        available_engines = [e.value for e in self.manager.get_available_engines()]

        # Рекомендации по движкам
        if len(available_engines) == 0:
            recommendations.append("Install EasyOCR engine")
        elif len(available_engines) == 1:
            recommendations.append("EasyOCR engine is available and working")

        # Рекомендации по производительности
        slow_scenarios = []
        for scenario in comparison_results['scenarios']:
            for engine_name, engine_data in scenario['engines'].items():
                if engine_data['performance']['avg_processing_time'] > 1.0:
                    slow_scenarios.append(f"{scenario['name']} ({engine_name})")

        if slow_scenarios:
            recommendations.append(f"Optimize performance for slow scenarios: {', '.join(slow_scenarios[:3])}")

        # Рекомендации по качеству
        low_quality_scenarios = []
        for scenario in comparison_results['scenarios']:
            for engine_name, engine_data in scenario['engines'].items():
                if engine_data['performance']['success_rate'] < 0.7:
                    low_quality_scenarios.append(f"{scenario['name']} ({engine_name})")

        if low_quality_scenarios:
            recommendations.append(f"Improve OCR quality for: {', '.join(low_quality_scenarios[:3])}")

        # Технические рекомендации
        recommendations.extend([
            "Consider implementing direct numpy array processing to avoid temporary files",
            "Add better error handling for edge cases (empty images, corrupted files)",
            "Implement adaptive confidence thresholds based on image quality",
            "Consider caching frequently used OCR results",
            "Add image preprocessing options (contrast enhancement, noise reduction)"
        ])

        return recommendations

    def generate_report(self, comparison_results: Dict[str, Any]) -> str:
        """Создать итоговый отчет."""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("OCR ENGINE COMPARISON REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")

        # Общая информация
        report_lines.append("📊 OVERVIEW")
        report_lines.append("-" * 40)

        available_engines = [e.value for e in self.manager.get_available_engines()]
        report_lines.append(f"Available engines: {', '.join(available_engines) if available_engines else 'None'}")
        report_lines.append(f"Test scenarios: {len(comparison_results['scenarios'])}")
        report_lines.append("")

        # Результаты по сценариям
        report_lines.append("🔍 SCENARIO RESULTS")
        report_lines.append("-" * 40)

        for scenario in comparison_results['scenarios']:
            report_lines.append(f"\nScenario: {scenario['name']}")
            report_lines.append(f"Description: {scenario['description']}")
            report_lines.append(f"Expected: {scenario['expected_text']}")

            for engine_name, engine_data in scenario['engines'].items():
                perf = engine_data['performance']
                report_lines.append(f"  {engine_name.upper()}:")
                report_lines.append(f"    - Processing time: {perf['avg_processing_time']:.3f}s")
                report_lines.append(f"    - Confidence: {perf['avg_confidence']:.3f}")
                report_lines.append(f"    - Success rate: {perf['success_rate']:.1%}")
                report_lines.append(f"    - Memory usage: {perf['avg_memory_usage']:.1f}MB")

        # Выявленные проблемы
        if comparison_results['issues']:
            report_lines.append("\n⚠️  IDENTIFIED ISSUES")
            report_lines.append("-" * 40)
            for i, issue in enumerate(comparison_results['issues'], 1):
                report_lines.append(f"{i}. {issue}")

        # Рекомендации
        if comparison_results['recommendations']:
            report_lines.append("\n💡 RECOMMENDATIONS")
            report_lines.append("-" * 40)
            for i, rec in enumerate(comparison_results['recommendations'], 1):
                report_lines.append(f"{i}. {rec}")

        report_lines.append("\n" + "=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)

        return "\n".join(report_lines)

    def run_comparison(self) -> Dict[str, Any]:
        """Запустить полное сравнение."""
        print("🎯 Starting Comprehensive OCR Comparison Test")
        print("=" * 60)

        try:
            # Запустить сравнение
            comparison_results = self.compare_engines()

            # Сгенерировать отчет
            report = self.generate_report(comparison_results)

            # Сохранить отчет в файл
            report_path = "ocr_comparison_report.txt"
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)

            print(f"\n📄 Report saved to: {report_path}")

            # Вывести краткий отчет в консоль
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)

            available_engines = [e.value for e in self.manager.get_available_engines()]
            print(f"✅ Available engines: {len(available_engines)}")
            print(f"✅ Test scenarios completed: {len(comparison_results['scenarios'])}")
            print(f"⚠️  Issues identified: {len(comparison_results['issues'])}")
            print(f"💡 Recommendations: {len(comparison_results['recommendations'])}")

            if comparison_results['issues']:
                print("\nTop issues:")
                for i, issue in enumerate(comparison_results['issues'][:3], 1):
                    print(f"  {i}. {issue}")

            return {
                'success': True,
                'results': comparison_results,
                'report': report,
                'report_path': report_path
            }

        except Exception as e:
            error_msg = f"Comparison test failed: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }


def main():
    """Главная функция для запуска теста."""
    print("🔬 OCR Test Suite")
    print("Testing EasyOCR performance and accuracy")
    print("=" * 60)

    # Создать и запустить тест
    tester = OCRComparisonTest()
    result = tester.run_comparison()

    if result['success']:
        print("\n✅ Test completed successfully!")
        print(f"📄 Detailed report saved to: {result['report_path']}")
    else:
        print(f"\n❌ Test failed: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()