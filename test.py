import sys
from PyQt6.QtWidgets import QApplication, QLabel


app = QApplication(sys.argv)
label = QLabel("PyQt6 已正常安装！")
label.show()
sys.exit(app.exec())