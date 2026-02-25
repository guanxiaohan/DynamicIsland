from Extension import * 

import os
import datetime
from PySide6.QtCore import QTimer, QObject, QSize, Qt
from PySide6.QtWidgets import QMessageBox, QFileDialog, QWidget, QLineEdit, QDateTimeEdit, QLabel, QPushButton, QDialog, QVBoxLayout, QHBoxLayout

class CountdownPanel(BarPanel):
    PanelSizeHint = QSize(400, 30)

    def __init__(self):
        super().__init__()

        self.leftLabel = BasicLabel()
        self.rightLabel = BasicLabel()

        self.leftLayout.addWidget(self.leftLabel)
        self.rightLayout.addWidget(self.rightLabel, alignment=Qt.AlignmentFlag.AlignRight)

        self.updateTimer = QTimer()
        self.updateTimer.timeout.connect(self.updateDisplay)
        self.updateTimer.setInterval(3000)
        self.updateTimer.start()

        self.showing = False
        self.time: datetime.datetime = datetime.datetime.now()
        self.eventName = "Upcoming Event"

        self.path = ExtensionRoot + "Countdown.txt"

    def postInitialize(self):
        self.loadSchedule()

    def loadSchedule(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                txt = f.readlines()
            self.time = datetime.datetime.fromtimestamp(float(txt[0].strip()))
            self.eventName = txt[1].strip()
        self.saveSchedule()

    def updateDisplay(self):
        def formatTimeToMins(secs: int):
            if secs < 60:
                return f"{secs}secs"
            if secs >= 86400:
                return f"{secs//86400}d {(secs%86400)//3600}h {(secs%3600)//60}min"
            if secs >= 3600:
                return f"{secs//3600}h {(secs%3600)//60}min"
            return f"{secs//60}min"
        
        seconds = (self.time - datetime.datetime.now()).seconds + (self.time - datetime.datetime.now()).days * 86400
        self.leftLabel.transitionToText(self.eventName)
        self.rightLabel.transitionToText(
            f"In {formatTimeToMins(abs(seconds))} | {getTimeString(None, False)}" if seconds >= 0 else
            f"{formatTimeToMins(abs(seconds))} ago | {getTimeString(None, False)}"
        )

    def saveSchedule(self):
        with open(self.path, "w") as f:
            f.write(str(self.time.timestamp()) + "\n" + self.eventName + "\n")

    def modifySchedule(self):
        dialog = QDialog()
        dateInput = QDateTimeEdit()
        label1 = QLabel("Time:")
        label2 = QLabel("Event Name:")
        nameInput = QLineEdit()
        okButton = QPushButton("OK")
        cancelButton = QPushButton("Cancel")

        layout = QVBoxLayout()
        layout.addWidget(label1)
        layout.addWidget(dateInput)
        layout.addWidget(label2)
        layout.addWidget(nameInput)

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)
        layout.addLayout(buttonLayout)

        dialog.setLayout(layout)
        okButton.clicked.connect(dialog.accept)
        cancelButton.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.eventName = nameInput.text()
            self.time = dateInput.dateTime().toPython() # type: ignore
            self.saveSchedule()

    def switchCountdown(self):
        if self.showing:
            self.requestHide.emit()
        else:
            self.requestShow.emit()
        self.showing = not self.showing

    def sysTrayItems(self):
        return {
            "Switch Panel": self.switchCountdown,
            "Modify Event": self.modifySchedule
        }

DI_setExtensionName("Countdown Display")
DI_setExtensionNamespace("CountdownPanel")
DI_registerPanel("SchedulePanel", CountdownPanel, 6)
