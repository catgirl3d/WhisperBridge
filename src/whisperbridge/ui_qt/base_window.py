from PySide6.QtCore import QEvent

class BaseWindow:
    """
    Mixin-класс для унифицированного сокрытия окон.
    """
    def dismiss(self):
        """
        Универсальный метод для сокрытия или закрытия окна.
        Переопределяется в дочерних классах.
        """
        self.hide()

    def closeEvent(self, event):
        """
        Стандартизованный обработчик события закрытия.
        Вызывает dismiss() для унифицированной логики.
        """
        self.dismiss()
        event.ignore()  # Игнорируем событие, чтобы не закрывать приложение