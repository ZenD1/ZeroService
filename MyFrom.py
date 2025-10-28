from PyQt5 import QtWidgets, uic, QtGui, QtCore
from PyQt5.QtWidgets import QFileDialog
import sys, os, base64, re
from dotenv import load_dotenv
from groq import Groq
from Pattern import patterns
from openai import OpenAI
import os


load_dotenv()
print("DEBUG: .env path =", os.path.abspath(".env"))
print("DEBUG: OPENAI_API_KEY =", os.getenv("OPENAI_API_KEY"))
print("DEBUG: GROQ_API_KEY =", os.getenv("GROQ_API_KEY"))


load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("❌ В .env нет GROQ_API_KEY")

client = Groq(api_key=api_key)

gpt_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class MyApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi("App.ui", self)

        self.patterns = patterns
        self.loaded_chart_path = None
        self.loaded_volume_path = None
        self.forecast_text = ""

        self.chart_scene = QtWidgets.QGraphicsScene(self)
        self.volume_scene = QtWidgets.QGraphicsScene(self)

        # === Проверяем UI элементы ===
        required = [
            "patternList", "patternImage", "patternDescription",
            "chatOutput", "chatInput", "sendButton",
            "pushButton", "pushButton_2",  # 👈 кнопки для графика и объёмов
            "graphicsView", "graphicsView_3"  # 👈 отображение картинок
        ]
        for name in required:
            if not hasattr(self, name):
                raise AttributeError(f"❌ Нет элемента {name} в App.ui")

        # === События ===
        self.patternList.currentRowChanged.connect(self.show_pattern)
        self.sendButton.clicked.connect(self.on_send)
        self.pushButton.clicked.connect(self.load_chart_image)
        self.pushButton_2.clicked.connect(self.load_volume_image)
        self.pushButton_3.clicked.connect(self.generate_future_chart)
        self.pushButton_4.clicked.connect(self.generate_forecast_image)

        # === Заполняем паттерны при запуске ===
        self.show_all_patterns()

    # === Загрузка графика ===
    def load_chart_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение графика", "", "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self.loaded_chart_path = path
        pixmap = QtGui.QPixmap(path)
        if pixmap.isNull():
            self.chatOutput.append("⚠️ Не удалось загрузить изображение графика")
            return
        scaled = pixmap.scaled(self.graphicsView.width(), self.graphicsView.height(), QtCore.Qt.KeepAspectRatio)
        self.chart_scene.clear()
        self.chart_scene.addPixmap(scaled)
        self.graphicsView.setScene(self.chart_scene)
        self.chatOutput.append("📊 График успешно загружен.")

    def generate_forecast_image(self):
        if not self.forecast_text:
            self.chatOutput.append("⚠️ Нет текста прогноза для визуализации.")
            return

        try:
            self.chatOutput.append("🧠 Генерация изображения прогноза...")
            prompt = (
                "Создай изображение прогноза движения цены на основе следующего описания:\n\n"
                f"{self.forecast_text}\n\n"
                "Покажи уровни поддержки, сопротивления, стрелки направления (вверх/вниз/флэт). "
                "Используй стиль свечного графика, нейтральные цвета."
            )

            result = gpt_client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024"
            )

            img_b64 = result.data[0].b64_json
            img_bytes = base64.b64decode(img_b64)
            out_path = "forecast_chart.png"
            with open(out_path, "wb") as f:
                f.write(img_bytes)

            pixmap = QtGui.QPixmap(out_path)
            pixmap = pixmap.scaled(self.graphicsView.width(), self.graphicsView.height(), QtCore.Qt.KeepAspectRatio)
            self.chart_scene.addPixmap(pixmap)
            self.graphicsView.setScene(self.chart_scene)

            self.chatOutput.append("✅ Прогноз визуализирован и добавлен в окно графика.")
        except Exception as e:
            self.chatOutput.append(f"⚠️ Ошибка при генерации изображения: {e}")

    # === Загрузка объёмов ===
    def load_volume_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение объёмов", "", "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self.loaded_volume_path = path
        pixmap = QtGui.QPixmap(path)
        if pixmap.isNull():
            self.chatOutput.append("⚠️ Не удалось загрузить изображение объёмов")
            return
        scaled = pixmap.scaled(self.graphicsView_3.width(), self.graphicsView_3.height(), QtCore.Qt.KeepAspectRatio)
        self.volume_scene.clear()
        self.volume_scene.addPixmap(scaled)
        self.graphicsView_3.setScene(self.volume_scene)
        self.chatOutput.append("📈 Объёмы успешно загружены.")

        # === Если обе картинки есть — запускаем анализ ===
        if self.loaded_chart_path and self.loaded_volume_path:
            self.chatOutput.append("<b>🧠 Анализ графика и объёмов...</b>")
            result = self.analyze_chart_with_volume(self.loaded_chart_path, self.loaded_volume_path)
            self.chatOutput.append(f"<b>Результат анализа:</b> {result}")

            detected = self.extract_pattern_names(result)
            self.show_detected_patterns(detected)

    # === Кодек для base64 ===
    def encode_image(self, path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    # === Анализ графика + объёмов ===
    def analyze_chart_with_volume(self, chart_path, volume_path):
        try:
            b64_chart = self.encode_image(chart_path)
            b64_volume = self.encode_image(volume_path)

            pattern_summary = "\n".join([f"- {p.name}: {p.description}" for p in patterns])

            completion = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты эксперт по техническому анализу. "
                            "Перед тобой два изображения: первое — график цены, второе — объёмы. "
                            "Ты должен рассматривать их совместно.\n\n"
                            "Вот список известных паттернов:\n"
                            f"{pattern_summary}\n\n"
                            "1️⃣ Определи все паттерны на графике и отметь их как %%имя%%.\n"
                            "2️⃣ Затем оцени направление будущего движения графика: "
                            "**Вверх**, **Вниз** или **Боковое движение (флэт)**.\n"
                            "3️⃣ Укажи это направление отдельной строкой, в формате:\n"
                            "**Прогноз: Вверх** (или **Вниз**, или **Горизонтально**)."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text",
                             "text": "Проанализируй график и объёмы, выдели все паттерны и дай прогноз."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_chart}"}},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_volume}"}}
                        ]
                    }
                ],
            )

            result = completion.choices[0].message.content or "❌ Нет ответа от модели"

            # === Извлекаем прогноз ===
            forecast_match = re.search(r"\*\*Прогноз:(.*?)\*\*", result)
            if forecast_match:
                forecast_text = forecast_match.group(0)
                self.resultChatgrahik.setHtml(f"<b style='color:#2E86C1;font-size:16px'>{forecast_text}</b>")
            else:
                self.resultChatgrahik.setHtml("<b>❌ Прогноз не найден.</b>")

            return result

        except Exception as e:
            return f"⚠️ Ошибка анализа: {e}"

    # === Вспомогательные методы ===
    def extract_pattern_names(self, text):
        if not text:
            return [], []

        all_found = re.findall(r"%%(.*?)%%", text)
        detected, new_patterns = [], []
        known_names = [p.name.lower() for p in patterns]

        for name in all_found:
            clean = name.strip().lower()
            if clean.endswith("(новый)"):
                clean = clean.replace("(новый)", "").strip()
                new_patterns.append(clean)
            elif any(clean in k or k in clean for k in known_names):
                detected.append(clean)
            else:
                new_patterns.append(clean)
        return detected, new_patterns

    def show_detected_patterns(self, result):
        detected, new_patterns = result
        self.patternList.clear()

        if not detected and not new_patterns:
            self.patternList.addItem("❌ Паттерны не распознаны")
            self.patternDescription.setText("Модель не нашла совпадений.")
            return

        found = []
        for p in patterns:
            pname = p.name.lower()
            for d in detected:
                if d in pname or pname in d:
                    found.append(p)
                    break

        if found:
            self.patterns = found
            self.patternList.addItem("✅ Распознанные паттерны:")
            for p in found:
                self.patternList.addItem(p.name)

        if new_patterns:
            self.patternList.addItem("")
            self.patternList.addItem("🆕 Новые паттерны:")
            for n in new_patterns:
                self.patternList.addItem(f"🧩 {n}")

    def show_all_patterns(self):
        self.patternList.clear()
        for p in self.patterns:
            self.patternList.addItem(p.name)

    def show_pattern(self, index):
        if index < 0 or index >= len(self.patterns):
            return
        p = self.patterns[index]
        self.patternDescription.setText(p.description)
        if os.path.exists(p.image_path):
            pixmap = QtGui.QPixmap(p.image_path)
            pixmap = pixmap.scaled(self.patternImage.width(), self.patternImage.height(), QtCore.Qt.KeepAspectRatio)
            self.patternImage.setPixmap(pixmap)
        else:
            self.patternImage.setText("Нет изображения")

    # === Генерация прогноза графика ===
    def generate_future_chart(self):
        if not self.loaded_chart_path:
            self.chatOutput.append("⚠️ Сначала загрузите график для анализа.")
            return

        try:
            self.chatOutput.append("🧩 Генерация прогноза графика...")

            b64_chart = self.encode_image(self.loaded_chart_path)

            # Модель: используем визуальную с поддержкой изображения
            completion = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — эксперт по техническому анализу и визуализации графиков. "
                            "На основе данного графика построй прогноз: покажи, "
                            "куда, вероятно, пойдёт цена, нарисуй стрелки направления, "
                            "обозначь уровни поддержки и сопротивления. "
                            "Сохрани стиль графика, не изменяй прошлые данные."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text",
                             "text": "Продолжи график на несколько свечей вперёд с указанием направлений."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_chart}"}}
                        ]
                    }
                ]
            )

            result_text = completion.choices[0].message.content

            # Попробуем извлечь визуальное описание
            self.forecast_text = result_text
            self.resultChatgrahik.setHtml(f"<b>📊 Прогноз получен:</b><br>{result_text}")
        except Exception as e:
            self.chatOutput.append(f"⚠️ Ошибка при создании прогноза: {e}")

    def on_send(self):
        text = self.chatInput.text().strip()
        if not text:
            return
        self.chatOutput.append(f"<b>Вы:</b> {text}")
        self.chatInput.clear()
        reply = self.ask_groq(text)
        self.chatOutput.append(f"<b>ZeroService:</b> {reply}")

    def ask_groq(self, text):
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Ты помощник ZeroService."},
                    {"role": "user", "content": text}
                ]
            )
            return completion.choices[0].message.content
        except Exception as e:
            return f"⚠️ Ошибка Groq API: {e}"


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = MyApp()
    win.show()
    sys.exit(app.exec_())
