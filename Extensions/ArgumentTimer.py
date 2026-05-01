from Extension import *
from typing import Any, Callable
from PySide6.QtCore import QTimer, QObject, QSize, Qt
from PySide6.QtWidgets import QMessageBox, QFileDialog, QGridLayout, QLabel, QPushButton, QLineEdit, QHBoxLayout, QVBoxLayout, QLayout
from PySide6.QtMultimedia import QAudio
import os
import datetime
import dataclasses
import json

from Utils import Callable

import json
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit,
    QHBoxLayout, QVBoxLayout, QFileDialog
)
from PySide6.QtWidgets import QStyle
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QUrl


class ArgumentTimerPanel(BarPanel):
    """
    Assumptions about BarPanel:
      - self.mainLayout:  主视图内容应放入这里
      - self.leftLayout:   横栏左侧内容应放入这里
      - self.rightLayout:  横栏右侧内容应放入这里
      - self.mainWidget:   主视图容器，切换时 show/hide
      - self.leftWidget:   横栏左侧容器，切换时 show/hide
      - self.rightWidget:  横栏右侧容器，切换时 show/hide
      - self.requestResize / self.requestShow / self.requestHide /
        self.requestProgressBarUpdate: 你的信号
    """

    def __init__(self):
        super().__init__()

        self.PanelSizeHint = QSize(550, 300)

        self.snoozed = False
        self.showing = False

        self.themeText = "Enter theme..."
        self.stages: list[dict[str, Any]] = []
        self.currentStageIndex = 0
        self.currentSide = "affirmative"  # affirmative / negative / joint
        self.remainingSeconds = 0
        self.running = False

        self.countdownTimer = QTimer(self)
        self.countdownTimer.setInterval(1000)
        self.countdownTimer.timeout.connect(self._tick)

        self.player = QMediaPlayer()
        self.hintSound = QAudioOutput()
        self.player.setAudioOutput(self.hintSound)

        self.player.setSource(QUrl.fromLocalFile(r"C:\Windows\Media\Alarm03.wav"))
        self.hintSound.setVolume(0.6)

        # self.indeterminateBarTimer = QTimer(self)
        # self.indeterminateBarTimer.setInterval(500)
        # self.indeterminateBarTimer.timeout.connect(
        #     lambda: self.requestProgressBarUpdate.emit(-1, -1)
        # )
        # self.indeterminateBarTimer.start()

        self.setupUI()
        self.loadConfig()
        self._applyStateToUI()

    # ----------------------------
    # UI
    # ----------------------------
    def setupUI(self):
        # 先清空父类现有布局中的旧内容，避免重复堆叠
        self._clearLayout(self.mainLayout)
        self._clearLayout(self.leftLayout)
        self._clearLayout(self.rightLayout)

        self.playIcon = QIcon(ExtensionRoot + "/play.svg")
        self.pauseIcon = QIcon(ExtensionRoot + "/pause.svg")
        self.expandIcon = QIcon(ExtensionRoot + "/maximise.svg")
        self.collapseIcon = QIcon(ExtensionRoot + "/maximise.svg")

        # ===== 主视图 =====
        self.themeInput = QLineEdit()
        self.themeInput.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.themeInput.setPlaceholderText("Enter theme...")
        self.themeInput.setText(self.themeText)
        self.themeInput.setFrame(False)
        self.themeInput.setStyleSheet("""
QLineEdit {
    font-size: 28px;
    padding: 6px 8px;
    border: none;
    background: transparent;
    color: white;
}
QLineEdit:focus {
    border: none;
    outline: none;
}
QLineEdit::placeholder {
    color: rgba(255, 255, 255, 0.45);
}
""")
        self.themeInput.editingFinished.connect(self._syncThemeFromInput)

        self.stageLabel = QLabel()
        self.stageLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stageLabel.setStyleSheet(
            "font-family: Microsoft Yahei UI; font-size: 22px; font-weight: bold;"
        )

        self.sideLabel = QLabel()
        self.sideLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sideLabel.setStyleSheet("font-size: 20px; font-weight: 600;")

        self.timeLabel = QLabel()
        self.timeLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timeLabel.setStyleSheet("font-size: 48px; font-weight: bold;")

        self.pauseButton = QPushButton("Start")
        self.pauseButton.setStyleSheet("font-size: 14px; padding: 8px;")
        self.pauseButton.clicked.connect(self.toggleStartPause)

        self.nextPhaseButton = QPushButton("Next Phase")
        self.nextPhaseButton.setStyleSheet("font-size: 14px; padding: 8px;")
        self.nextPhaseButton.clicked.connect(self.nextPhase)

        self.snoozeButton = QPushButton("Collapse")
        self.snoozeButton.setStyleSheet("font-size: 14px; padding: 8px;")
        self.snoozeButton.clicked.connect(self.switchSnooze)

        buttonLayout = QHBoxLayout()
        buttonLayout.addStretch(1)
        buttonLayout.addWidget(self.pauseButton)
        buttonLayout.addWidget(self.nextPhaseButton)
        buttonLayout.addWidget(self.snoozeButton)
        buttonLayout.addStretch(1)

        mainVLayout = QVBoxLayout()
        mainVLayout.addWidget(self.themeInput)
        mainVLayout.addWidget(self.stageLabel)
        mainVLayout.addWidget(self.sideLabel)
        mainVLayout.addWidget(self.timeLabel)
        mainVLayout.addLayout(buttonLayout)
        mainVLayout.setSpacing(14)
        mainVLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.mainLayout.addLayout(mainVLayout)

        # ===== 横栏视图 =====
        self.compactThemeLabel = QLabel()
        self.compactThemeLabel.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.compactThemeLabel.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.compactThemeLabel.setWordWrap(True)

        self.compactStageLabel = QLabel()
        self.compactStageLabel.setStyleSheet("font-size: 13px;")
        self.compactStageLabel.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )

        self.compactTimeLabel = QLabel()
        self.compactTimeLabel.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.compactTimeLabel.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )

        self.compactSideLabel = QLabel()
        self.compactSideLabel.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.compactSideLabel.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )

        self.compactSnoozeButton = QPushButton("Expand")
        self.compactSnoozeButton.setStyleSheet("font-size: 12px; padding: 4px 8px;")
        self.compactSnoozeButton.clicked.connect(self.switchSnooze)
        self.compactSnoozeButton.setIcon(self.collapseIcon)
        self.compactSnoozeButton.setText("")
        self.compactSnoozeButton.setFixedSize(28, 28)

        self.compactPauseButton = QPushButton("Start")
        self.compactPauseButton.setStyleSheet("font-size: 12px; padding: 4px 8px;")
        self.compactPauseButton.clicked.connect(self.toggleStartPause)
        self.compactPauseButton.setIcon(self.playIcon)
        self.compactPauseButton.setText("")
        self.compactPauseButton.setFixedSize(28, 28)

        self.leftLayout.addWidget(self.compactThemeLabel)

        rightInfo = QVBoxLayout()
        rightInfo.addWidget(self.compactStageLabel)
        rightInfo.addWidget(self.compactSideLabel)
        # rightInfo.addWidget(self.compactTimeLabel)
        rightInfo.setSpacing(0)
        rightInfo.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        rightButtons = QHBoxLayout()
        rightButtons.addWidget(self.compactSnoozeButton)
        rightButtons.addWidget(self.compactPauseButton)
        rightButtons.setSpacing(6)
        rightButtons.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        rightBox = QHBoxLayout()
        rightBox.addLayout(rightInfo)
        rightBox.addLayout(rightButtons)
        rightBox.setSpacing(2)
        rightBox.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )

        self.rightLayout.addLayout(rightBox)

        self.mainWidget.setVisible(True)
        self.leftWidget.setVisible(False)
        self.rightWidget.setVisible(False)

        self.setStyleSheet("""
* {
    font-family: "Microsoft YaHei UI";
}
""")

    # ----------------------------
    # Config
    # ----------------------------
    def loadConfig(self, path: str | None = ExtensionRoot + "ArgumentConfig.json") -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                None,
                "Choose a config file",
                ".",
                "Argument timer config (*.json)",
            )
            if not path:
                return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.exception("Failed to load config: %s", e)
            return

        self.themeText = str(data.get("theme", "Enter theme..."))

        rawStages = data.get("stages", [])
        stages: list[dict[str, Any]] = []

        for item in rawStages:
            try:
                stages.append(
                    {
                        "name": str(item.get("name", "Phase")),
                        "duration": max(1, int(item.get("duration", 60))),
                        "mode": "split"
                        if str(item.get("mode", "split")).lower() == "split"
                        else "joint",
                    }
                )
            except Exception:
                continue

        if not stages:
            stages = [
                {"name": "Phase 1", "duration": 180, "mode": "split"},
            ]

        self.stages = stages
        self.currentStageIndex = 0
        self.currentSide = "affirmative"
        self.running = False

        self.requestProgressBarUpdate.emit(1, 1)
        self.themeInput.setText(self.themeText)
        self._resetCurrentStage()
        self._applyStateToUI()

    # ----------------------------
    # State helpers
    # ----------------------------
    def _currentStage(self) -> dict[str, Any]:
        return self.stages[self.currentStageIndex]

    def _isSplitStage(self) -> bool:
        return self._currentStage().get("mode", "split") == "split"

    def _stageName(self) -> str:
        return self._currentStage().get("name", "Phase")

    def _sideText(self) -> str:
        if not self._isSplitStage():
            return "共同辩论 Joint Debate"
        return "正方 Affirmative" if self.currentSide == "affirmative" else "反方 Negative"

    def _sideColor(self) -> str:
        if not self._isSplitStage():
            return "rgba(255,255,255,0.88)"
        if self.currentSide == "affirmative":
            return "rgba(90, 150, 235, 0.88)"
        return "rgba(235, 105, 105, 0.88)"

    def _resetCurrentStage(self) -> None:
        if not self.stages:
            self.remainingSeconds = 0
            return

        self.remainingSeconds = int(self._currentStage()["duration"])
        if self._isSplitStage():
            self.currentSide = "affirmative"
        else:
            self.currentSide = "joint"

    def _formatTime(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    def _syncThemeFromInput(self) -> None:
        self.themeText = self.themeInput.text().strip() or "Enter theme..."
        self._applyStateToUI()

    def _applyStateToUI(self) -> None:
        if not hasattr(self, "stageLabel"):
            return

        if not self.stages:
            self.stageLabel.setText("No config loaded")
            self.sideLabel.setText("")
            self.timeLabel.setText("00:00")

            self.compactThemeLabel.setText(self.themeText)
            self.compactStageLabel.setText("No config")
            self.compactSideLabel.setText("")
            self.compactTimeLabel.setText("00:00")
            return

        stageText = f"{self.currentStageIndex + 1}. {self._stageName()}"
        timeText = self._formatTime(self.remainingSeconds)
        sideText = self._sideText()
        sideColor = self._sideColor()

        # if not self.themeInput.hasFocus():
            # self.themeInput.setText(self.themeText)
        
        self.stageLabel.setText(stageText)
        self.sideLabel.setText(sideText)
        self.timeLabel.setText(timeText)
        self.sideLabel.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {sideColor};"
        )
        self.timeLabel.setStyleSheet(
            f"font-size: 48px; font-weight: bold; color: {sideColor};"
        )

        self.compactThemeLabel.setText(self.themeText)
        self.compactStageLabel.setText(stageText)
        self.compactSideLabel.setText(sideText + " " + timeText)
        # self.compactTimeLabel.setText(timeText)
        self.compactSideLabel.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {sideColor};"
        )
        self.compactTimeLabel.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {sideColor};"
        )

        btnText = "Pause" if self.running else "Start"
        self.pauseButton.setText(btnText)
        self.snoozeButton.setText("Expand" if self.snoozed else "Collapse")

        if self.running:
            self.compactPauseButton.setIcon(self.pauseIcon)
        else:
            self.compactPauseButton.setIcon(self.playIcon)

        if self.remainingSeconds == 0 and self.currentSide != "affirmative":
            if self.currentStageIndex == len(self.stages) - 1:
                self.stageLabel.setText("辩论结束. Debate Ended.")
                self.compactStageLabel.setText("辩论结束. Debate Ended.")
            else:
                self.stageLabel.setText("Next: " + self.stages[self.currentStageIndex+1]["name"])
                self.compactStageLabel.setText("Next: " + self.stages[self.currentStageIndex+1]["name"])

        self.requestProgressBarUpdate.emit(
            self.remainingSeconds,
            int(self._currentStage()["duration"]),
        )

    # ----------------------------
    # Timer control
    # ----------------------------
    def toggleStartPause(self):
        if not self.stages:
            return

        if self.running:
            self.pause()
        else:
            self.start()

    def start(self):
        if not self.stages:
            return

        if self.remainingSeconds <= 0:
            self.nextPhase()

        self.running = True
        self.countdownTimer.start()
        self._applyStateToUI()

    def pause(self):
        self.running = False
        self.countdownTimer.stop()
        self._applyStateToUI()

    def _tick(self):
        if not self.running or not self.stages:
            return

        self.remainingSeconds -= 1

        if self.remainingSeconds <= 0:
            self.remainingSeconds = 0
            
            self.pause()
            self.player.play()
            return

        self.requestProgressBarUpdate.emit(self.remainingSeconds, self.stages[self.currentStageIndex]["duration"])
        self._applyStateToUI()

    def nextPhase(self):
        if not self.stages:
            return

        self.pause()

        if self._isSplitStage() and self.currentSide == "affirmative":
            # 还没到反方发言，则切到反方
            self.currentSide = "negative"
            self.remainingSeconds = int(self._currentStage()["duration"])
        else:
            # 否则直接进入下一阶段
            self.currentStageIndex += 1
            if self.currentStageIndex >= len(self.stages):
                self.currentStageIndex = len(self.stages) - 1
                self.remainingSeconds = 0
                self.running = False
                self.countdownTimer.stop()
                self._applyStateToUI()
                return

            self._resetCurrentStage()

        self.running = False
        self.countdownTimer.stop()
        self._applyStateToUI()

    # ----------------------------
    # Snooze / collapse
    # ----------------------------
    def switchSnooze(self):
        self.snoozed = not self.snoozed

        self.mainWidget.setVisible(not self.snoozed)
        self.leftWidget.setVisible(self.snoozed)
        self.rightWidget.setVisible(self.snoozed)

        self.reLayout()
        self._applyStateToUI()

    def reLayout(self):
        self.PanelSizeHint = QSize(600, 50) if self.snoozed else QSize(550, 300)
        self.requestResize.emit()

    # ----------------------------
    # Utilities
    # ----------------------------
    def _clearLayout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child = item.layout()

            if widget is not None:
                widget.setParent(None)
            elif child is not None:
                self._clearLayout(child)

    # ----------------------------
    # Framework hooks
    # ----------------------------
    def postInitialize(self) -> None:
        logger.info("Initialized.")

    def sysTrayItems(self) -> dict[str, Callable[..., Any]]:
        return {
            "Switch Argument Timer": self.switchCountdown,
            "Load New Config": lambda: self.loadConfig(None),
            "Start": self.start,
            "Pause": self.pause,
            "Next Phase": self.nextPhase,
        }

    def switchCountdown(self):
        if self.showing:
            self.requestHide.emit()
        else:
            self.requestShow.emit()
        self.showing = not self.showing

DI_setExtensionName("Argument Timer")
DI_setExtensionNamespace("ArgumentTimer")
DI_registerPanel("ArgumentTimerPanel", ArgumentTimerPanel, 8)
