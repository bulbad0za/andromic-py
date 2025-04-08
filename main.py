import sys
import socket
import pyaudio
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QGroupBox, QDialog, QDialogButtonBox, 
    QComboBox, QFormLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize, QSettings
from PyQt5.QtGui import QIcon

# Параметры аудио
CHUNK = 64  
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
PORT = 5000

# Простой словарь переводов (здесь можно расширять)
translations = {
    "ru": {
        "app_title": "AndroMic",
        "header": "AndroMic",
        "connect_wifi": "Подключиться по Wi‑Fi",
        "connect_usb": "Подключиться по USB",
        "settings": "Настройки",
        "disconnect": "Разорвать",
        "status_not_connected": "Статус: Не подключено",
        "logs": "Логи",
        "vb_cable_settings": "Настройки VB-Cable",
        "select_vb_cable": "Выберите канал VB-Cable:",
        "select_language": "Выберите язык:",
        "ok": "ОК",
        "cancel": "Отмена",
        "local_ip": "Локальный IP: {}",
        "adb_success": "ADB Reverse успешно настроен",
        "adb_error": "Ошибка настройки ADB: {}",
        "adb_exec_error": "Ошибка при выполнении adb: {}",
        "mic_on": "Микрофон включен",
        "mic_off": "Микрофон отключен",
        "disconnected": "Соединение разорвано",
    },
    "en": {
        "app_title": "AndroMic",
        "header": "AndroMic",
        "connect_wifi": "Connect Wi‑Fi",
        "connect_usb": "Connect USB",
        "settings": "Settings",
        "disconnect": "Disconnect",
        "status_not_connected": "Status: Not connected",
        "logs": "Logs",
        "vb_cable_settings": "VB-Cable Settings",
        "select_vb_cable": "Select VB-Cable channel:",
        "select_language": "Select language:",
        "ok": "OK",
        "cancel": "Cancel",
        "local_ip": "Local IP: {}",
        "adb_success": "ADB Reverse successfully configured",
        "adb_error": "ADB configuration error: {}",
        "adb_exec_error": "Error executing adb: {}",
        "mic_on": "Microphone enabled",
        "mic_off": "Microphone muted",
        "disconnected": "Disconnected",
    }
}

# Класс потока для приёма аудио
class AudioReceiverWorker(QThread):
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    
    def __init__(self, mute_getter, device_index=None, parent=None):
        super().__init__(parent)
        self.mute_getter = mute_getter
        self.device_index = device_index
        self.running = True
        
    def run(self):
        p = pyaudio.PyAudio()
        stream_params = {
            "format": FORMAT,
            "channels": CHANNELS,
            "rate": RATE,
            "output": True,
            "frames_per_buffer": CHUNK,
        }
        if self.device_index is not None:
            stream_params["output_device_index"] = self.device_index
        try:
            stream = p.open(**stream_params)
        except Exception as e:
            self.error_signal.emit(f"Ошибка открытия аудиоустройства: {e}")
            return
        
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server_socket.bind(('0.0.0.0', PORT))
            server_socket.listen(1)
        except Exception as e:
            self.error_signal.emit(f"Ошибка открытия сокета: {e}")
            return
        
        self.status_signal.emit("Ожидание подключения от Android устройства...")
        try:
            conn, addr = server_socket.accept()
            self.status_signal.emit(f"Подключено: {addr}")
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            while self.running:
                data = conn.recv(CHUNK)
                if not data:
                    break
                # Если мьют включён – выводим тишину, иначе реальный звук
                if self.mute_getter():
                    stream.write(b'\x00' * len(data))
                else:
                    stream.write(data)
            self.status_signal.emit("Соединение закрыто")
        except Exception as e:
            self.error_signal.emit(f"Ошибка при приёме аудио: {e}")
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            p.terminate()
            try:
                conn.close()
            except Exception:
                pass
            server_socket.close()
    
    def stop(self):
        self.running = False
        self.quit()
        self.wait()

# Окно настроек для выбора канала VB-Cable и языка
class SettingsDialog(QDialog):
    def __init__(self, current_device_index=None, current_language="ru", parent=None):
        super().__init__(parent)
        self.setWindowTitle(translations[current_language]["vb_cable_settings"])
        self.setFixedSize(300, 200)
        self.selected_device_index = current_device_index
        self.selected_language = current_language
        self.current_language = current_language
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.device_combo = QComboBox()
        self.populate_audio_devices()
        if self.selected_device_index is not None:
            index = self.device_combo.findData(self.selected_device_index)
            if index != -1:
                self.device_combo.setCurrentIndex(index)
        form_layout.addRow(translations[self.current_language]["select_vb_cable"], self.device_combo)
        self.language_combo = QComboBox()
        self.language_combo.addItem("Русский", "ru")
        self.language_combo.addItem("English", "en")
        index = self.language_combo.findData(self.selected_language)
        if index != -1:
            self.language_combo.setCurrentIndex(index)
        form_layout.addRow(translations[self.current_language]["select_language"], self.language_combo)
        layout.addLayout(form_layout)
        button_box = QDialogButtonBox()
        ok_button = button_box.addButton(translations[self.current_language]["ok"], QDialogButtonBox.AcceptRole)
        cancel_button = button_box.addButton(translations[self.current_language]["cancel"], QDialogButtonBox.RejectRole)
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(button_box)
        
    def populate_audio_devices(self):
        p = pyaudio.PyAudio()
        self.device_combo.clear()
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev.get("maxOutputChannels", 0) > 0:
                self.device_combo.addItem(f"{i}: {dev['name']}", i)
        p.terminate()
        
    def get_selected_device(self):
        return self.device_combo.currentData()
    
    def get_selected_language(self):
        return self.language_combo.currentData()

# Главное окно приложения
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "AndroMic")
        self.language = self.settings.value("language", "ru")
        self.output_device_index = self.settings.value("output_device_index", None, type=int)
        self.is_muted = False
        self.connected = False
        self.audio_worker = None
        self.initUI()
        
    def initUI(self):
        self.setFixedSize(400, 300)
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QVBoxLayout(self.central)
        self.header_label = QLabel()
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.main_layout.addWidget(self.header_label)
        # Ряд кнопок подключения
        btn_layout = QHBoxLayout()
        self.wifi_button = QPushButton()
        self.usb_button = QPushButton()
        self.wifi_button.setIcon(QIcon("icons/wifi.svg"))
        self.wifi_button.setIconSize(QSize(24, 24))
        self.usb_button.setIcon(QIcon("icons/usb.svg"))
        self.usb_button.setIconSize(QSize(24, 24))
        btn_layout.addWidget(self.wifi_button)
        btn_layout.addWidget(self.usb_button)
        self.main_layout.addLayout(btn_layout)
        # Кнопка мьюта (только иконка, квадратная)
        self.mute_button = QPushButton()
        self.mute_button.setFixedSize(60, 60)
        self.mute_button.setIconSize(QSize(40, 40))
        self.main_layout.addWidget(self.mute_button, alignment=Qt.AlignCenter)
        # Статус и IP
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.status_label)
        self.ip_label = QLabel()
        self.ip_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.ip_label)
        # Область логов (сворачиваемая)
        self.log_group = QGroupBox()
        self.log_group.setCheckable(True)
        self.log_group.setChecked(False)
        self.log_group.toggled.connect(self.toggle_logs)
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setVisible(False)
        log_layout.addWidget(self.log_text)
        self.log_group.setLayout(log_layout)
        self.main_layout.addWidget(self.log_group)
        # Кнопки настроек и разрыва соединения
        btn_bottom_layout = QHBoxLayout()
        self.settings_button = QPushButton()
        self.settings_button.setText(translations[self.language]["settings"])
        self.settings_button.setIcon(QIcon("icons/settings.svg"))
        self.settings_button.setIconSize(QSize(24, 24))
        self.settings_button.setFixedSize(100, 40)
        btn_bottom_layout.addWidget(self.settings_button)
        self.disconnect_button = QPushButton()
        self.disconnect_button.setText(translations[self.language]["disconnect"])
        self.disconnect_button.setIcon(QIcon("icons/disconnect.svg"))
        self.disconnect_button.setIconSize(QSize(24, 24))
        self.disconnect_button.setFixedSize(100, 40)
        self.disconnect_button.setEnabled(False)
        btn_bottom_layout.addWidget(self.disconnect_button)
        self.main_layout.addLayout(btn_bottom_layout)
        # Подключаем сигналы
        self.wifi_button.clicked.connect(self.connect_wifi)
        self.usb_button.clicked.connect(self.connect_usb)
        self.settings_button.clicked.connect(self.open_settings)
        self.disconnect_button.clicked.connect(self.disconnect_connection)
        self.mute_button.clicked.connect(self.toggle_mute)
        self.update_ui_texts()
        
    def update_ui_texts(self):
        t = translations[self.language]
        self.setWindowTitle(t["app_title"])
        self.header_label.setText(t["header"])
        self.wifi_button.setText(t["connect_wifi"])
        self.usb_button.setText(t["connect_usb"])
        self.settings_button.setText(t["settings"])
        self.disconnect_button.setText(t["disconnect"])
        self.status_label.setText(t["status_not_connected"])
        self.log_group.setTitle(t["logs"])
        if self.is_muted:
            self.mute_button.setIcon(QIcon("icons/mic_off.svg"))
        else:
            self.mute_button.setIcon(QIcon("icons/mic.svg"))
        self.ip_label.setText("")
        
    def log(self, msg):
        self.log_text.append(msg)
        self.status_label.setText(msg)
        
    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip
        
    def connect_wifi(self):
        t = translations[self.language]
        local_ip = self.get_local_ip()
        self.ip_label.setText(t["local_ip"].format(local_ip))
        self.log(t["local_ip"].format(local_ip))
        self.start_audio_receiver()
        
    def connect_usb(self):
        t = translations[self.language]
        try:
            result1 = subprocess.run(
                ["adb", "reverse", "tcp:5000", "tcp:5000"],
                capture_output=True, text=True
            )
            # Для USB здесь не требуется пробрасывать управляющий порт, так как синхронный мьют не используется
            if result1.returncode == 0:
                self.log(t["adb_success"])
            else:
                self.log(t["adb_error"].format(result1.stderr))
        except Exception as e:
            self.log(t["adb_exec_error"].format(e))
        self.start_audio_receiver()
        
    def open_settings(self):
        dialog = SettingsDialog(current_device_index=self.output_device_index, current_language=self.language, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.output_device_index = dialog.get_selected_device()
            self.language = dialog.get_selected_language()
            self.settings.setValue("language", self.language)
            self.settings.setValue("output_device_index", self.output_device_index)
            self.log(f"Выбран VB-Cable: {self.output_device_index}; Язык: {self.language}")
            self.update_ui_texts()
        else:
            self.log("Настройки не изменены")
            
    def disconnect_connection(self):
        if self.audio_worker is not None and self.audio_worker.isRunning():
            self.audio_worker.stop()
            self.audio_worker = None
            self.connected = False
            self.disconnect_button.setEnabled(False)
            t = translations[self.language]
            self.log(t["disconnected"])
            self.status_label.setText(t["status_not_connected"])
        else:
            self.log("Нет активного соединения для разрыва")
            
    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self.update_ui_texts()
        t = translations[self.language]
        self.log(t["mic_off"] if self.is_muted else t["mic_on"])
        
    def toggle_logs(self, checked):
        self.log_text.setVisible(checked)
        if checked:
            self.setFixedHeight(500)
        else:
            self.setFixedHeight(300)
            
    def start_audio_receiver(self):
        if self.audio_worker is None or not self.audio_worker.isRunning():
            self.audio_worker = AudioReceiverWorker(lambda: self.is_muted, device_index=self.output_device_index)
            self.audio_worker.status_signal.connect(self.log)
            self.audio_worker.error_signal.connect(self.log)
            self.audio_worker.start()
            self.connected = True
            self.disconnect_button.setEnabled(True)
        else:
            self.log("Аудиопоток уже запущен")
            
    def closeEvent(self, event):
        if self.audio_worker is not None:
            self.audio_worker.stop()
        event.accept()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
