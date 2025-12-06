# Main.py

import sys

from PySide6.QtCore import (Q_ARG, Q_RETURN_ARG, QByteArray, QMetaObject,
                            QObject, QPoint, QPropertyAnimation, QRectF,
                            QRunnable, QSize, Qt, QThreadPool, QTimer, Signal,
                            SignalInstance, QParallelAnimationGroup, QPointF)
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QResizeEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

from Utils import *
from Widgets import *

BUILDING = True
if not BUILDING:
    import faulthandler
    faulthandler.enable()
if BUILDING:
    import warnings
    warnings.filterwarnings("ignore")

DEFAULTSIZE = QSize(300, 30)


class DynamicIsland(QWidget):
    notificationSignal = Signal(int, str) # Priority, content

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContentsMargins(0, 0, 0, 0)

        self.taskScheduler = TaskScheduler(parent=self, max_workers=2, use_async_loop=True)
        self.taskScheduler.emitter.finished.connect(self._on_dynamic_worker_finished)
        
        self.panels: dict[str, Panel] = {}
        self.panel_priorities: dict[str, int] = {}
        self.panel_layers: list[str] = []
        self.currentPanel: Panel | None = None
        self.currentUIPanelID: str = ""
        self.currentPanelID: str = ""
        
        curve, _curve_reference = generateEasingCurve()
        self.frameworkAnimationCurveFunc = _curve_reference
        self.frameworkAnimationCurve = curve
        self.frameworkAnimation = SpringAnimation(self, _curve_reference, duration=920)

        self.panelProgressBars: dict[str, tuple[int, int]] = {} # curent, max, maximum=0 -> no bar, maximum<0 -> indeterminate
        self.panelProgressBarRendering: tuple[float, float] = (0, 0) # from width %, to %, using QPointF(x, y) to represent
        self.panelProgressBarAnimation: QVariantAnimation = QVariantAnimation(self)
        self.panelProgressBarAnimation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.panelProgressBarAnimation.setDuration(500)
        self.panelProgressBarAnimation.valueChanged.connect(self.rerenderProgressBar)

        self.defaultPosition = QRect()
        self.currentScreenState = acquireScreenState()
        self.initialize()

        self.testTimer = QTimer(self)
        self.testTimer.timeout.connect(self.onTestTimer)
        self.testTimer.setSingleShot(True)
        self.testTimer.setInterval(9000)
        self.testTimer.start()

    def onTestTimer(self):
        self.broadcastNotification(1, "Test")
        # print("Sent")

    def requestProgressBarUpdate(self, current: int, maximum: int, useTransition: bool = True):
        panel: Panel = self.sender() # type: ignore
        if current < 0:
            current = 0
        if current > maximum:
            current = maximum

        self.panelProgressBars[panel.panelID] = (current, maximum)
        if self.sender() == self.panels[self.currentPanelID]:
            if not useTransition:
                self.panelProgressBarRendering = (0, current/maximum if maximum!=0 else 0)
                self.update()
            else:
                self.panelProgressBarAnimation.stop()
                self.panelProgressBarAnimation.setStartValue(QPointF(self.panelProgressBarRendering[0], self.panelProgressBarRendering[1]))
                self.panelProgressBarAnimation.setEndValue(QPointF(0, current/maximum if maximum!=0 else 0))
                self.panelProgressBarAnimation.setEasingCurve(QEasingCurve.Type.OutQuad)
                self.panelProgressBarAnimation.start()

    def rerenderProgressBar(self, val: float = -10000.0):
        self.panelProgressBarRendering = (self.panelProgressBarAnimation.currentValue().x(),
                                          self.panelProgressBarAnimation.currentValue().y())
        self.update()

    def _on_dynamic_worker_finished(self, task_id: str, owner, data, exc):
        if owner == self:
            self.updateRecieved(data)

    def updateRecieved(self, data):
        ...

    def broadcastNotification(self, priority: int, content: str):
        self.notificationSignal.emit(priority, content)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, DEFAULTSIZE.height()//2, DEFAULTSIZE.height()//2)

        gradient = Brushes.backgroundBrush
        painter.fillPath(path, gradient)
        painter.setClipPath(path)

        QWidget.paintEvent(self, event)

        # Draw a "Camera" on the top center
        camera_radius = 18
        center_point = self.mapFromGlobal(QPoint(
            self.currentScreenState.geometry.x() + self.currentScreenState.geometry.width() // 2,
            self.currentScreenState.geometry.y() + 
                (self.currentPanel.Top_space if self.currentPanel else 0) + 
                min(6, (self.currentPanel.PanelSizeHint if self.currentPanel else DEFAULTSIZE).height() // 2 - camera_radius // 2)
        ))
        camera_x, camera_y = center_point.x() - camera_radius // 2, center_point.y()
        painter.setPen(Pens.cameraPen)
        painter.setBrush(QColor(80, 80, 80, 255))
        painter.drawEllipse(camera_x, camera_y, camera_radius, camera_radius)

        # Paint progress bar
        progressHeight = 2
        Pens.progressPen.setWidth(progressHeight)
        painter.setPen(Pens.progressPen)
        roundCornerSpace = DEFAULTSIZE.height() // 4
        available_width = self.width() - DEFAULTSIZE.height() // 2
        painter.drawLine(QPoint(int(self.panelProgressBarRendering[0]*available_width + roundCornerSpace), self.height() - progressHeight + 1), 
                         QPoint(int(self.panelProgressBarRendering[1]*available_width + roundCornerSpace), self.height() - progressHeight + 1))

    def registerPanel(self, panel_id: str, panel: Panel, priority: int = 0):
        if panel_id in self.panels:
            print(f"Panel ID '{panel_id}' already registered. Overwriting.")
        self.panels[panel_id] = panel
        self.panel_priorities[panel_id] = priority
        panel.panelID = panel_id
        panel.requestResize.connect(self.animateToPanel)
        panel.requestShow.connect(self.panelShowRequested)
        panel.requestHide.connect(self.panelHideRequested)
        self.notificationSignal.connect(panel.notificationReceived)
        self.panelProgressBars[panel_id] = (0, 0)
        panel.requestProgressBarUpdate.connect(self.requestProgressBarUpdate)

    def switchToPanel(self, panel_id: str):
        if panel_id not in self.panels:
            print(f"Panel ID '{panel_id}' not found.")
            return
        self.currentPanelID = panel_id
        
        if self.currentPanel:
            self.currentPanel.vanish()
            self.currentPanel.vanished.connect(lambda p=panel_id: self.switchToPanel_Step2(p))
            self.animateToPanel(panel_id)

        else:
            self.switchToPanel_Step2(panel_id)

        if panel_id in self.panel_layers:
            self.panel_layers.remove(panel_id)
        self.panel_layers.append(panel_id)
        self.panels[self.currentPanelID].requestProgressBarUpdate.emit(*self.panelProgressBars[self.currentPanelID])

    def switchToPanel_Step2(self, panel_id: str):
        if not self.currentPanel:
            self.animateToPanel(panel_id)
        self.currentPanel = self.panels[panel_id]
        
        tryDisconnect(self.currentPanel.vanished)
        self.currentPanel.setParent(self)
        self.currentPanel.appear()

        self.currentUIPanelID = panel_id
        self.placePanel()

    def initialize(self):
        self.registerPanel("DynamicIsland.MainPanel", MainPanel(), 0)
        self.registerPanel("DynamicIsland.MediaPanel", MediaPanel(), 1)

        screenState = acquireScreenState()
        InitialSize = QSize(100, 0)
        InitialPos = QPoint(int((screenState.geometry.width() - InitialSize.width()) / 2), -15)
        self.setGeometry(QRect(InitialPos, InitialSize))

        self.switchToPanel("DynamicIsland.MainPanel")

    def panelShowRequested(self):
        panel: Panel = self.sender() # type: ignore
        if panel.panelID != self.currentPanelID and self.panel_priorities[panel.panelID] >= self.panel_priorities[self.currentPanelID]:
            self.switchToPanel(panel.panelID)

    def panelHideRequested(self):
        panel: Panel = self.sender() # type: ignore
        if len(self.panel_layers) == 1:
            return
        if panel.panelID == self.panel_layers[-1]:
            self.switchToPanel(self.panel_layers[-2])
        self.panel_layers.remove(panel.panelID)

    def animateToPanel(self, panel_id: str | None = None):
        if not panel_id:
            panel_id = self.currentPanelID
            if not panel_id:
                return

        screenState = acquireScreenState()
        self.currentScreenState = screenState

        panel = self.panels[panel_id]
        pos = QPoint((screenState.geometry.width() - panel.PanelSizeHint.width()) // 2, panel.Top_space)
        endRect = QRect(pos.x(), pos.y(), panel.PanelSizeHint.width(), panel.PanelSizeHint.height())

        self.frameworkAnimation.start(self.geometry(), endRect, duration=920, center_on_width=True)
        self.show()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.placePanel()
        return super().resizeEvent(event)
    
    def placePanel(self):
        if not self.currentPanel:
            return
        
        self.currentPanel.setGeometry(QRect(0, 0, self.width(), self.height()))

    # # Define BasePosX, BasePosY, BaseWidth, BaseHeight properties for animation
    # def getBasePosX(self):
    #     return self.geometry().x()
    # def setBasePosX(self, x):
    #     geom = self.geometry()
    #     geom.setX(x)
    #     self.setGeometry(geom)
    # BasePosX = Property(int, getBasePosX, setBasePosX)
    # def getBasePosY(self):
    #     return self.geometry().y()
    # def setBasePosY(self, y):
    #     geom = self.geometry()
    #     geom.setY(y)
    #     self.setGeometry(geom)
    # BasePosY = Property(int, getBasePosY, setBasePosY)
    # def getBaseWidth(self):
    #     return self.geometry().width()
    # def setBaseWidth(self, w):
    #     geom = self.geometry()
    #     geom.setWidth(w)
    #     self.setGeometry(geom)
    # BaseWidth = Property(int, getBaseWidth, setBaseWidth)
    # def getBaseHeight(self):
    #     return self.geometry().height()
    # def setBaseHeight(self, h):
    #     geom = self.geometry()
    #     geom.setHeight(h)
    #     self.setGeometry(geom)
    # BaseHeight = Property(int, getBaseHeight, setBaseHeight)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(
'''
QLabel {
    color: white;
}
'''
    )
    island = DynamicIsland()
    app.exec()