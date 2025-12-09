# Main.py

import sys

from PySide6.QtCore import (Q_ARG, Q_RETURN_ARG, QByteArray, QMetaObject,
                            QObject, QPoint, QPropertyAnimation, QRectF,
                            QRunnable, QSize, Qt, QThreadPool, QTimer, Signal,
                            SignalInstance, QParallelAnimationGroup, QPointF)
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QMouseEvent, QPainter, QPainterPath, QResizeEvent, QAction
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget, QSystemTrayIcon, QMenu, QMessageBox

from Utils import *
from Widgets import *

VERSION = "0.0.1"
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
    Expand_width = 13

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContentsMargins(0, 0, 0, 0)

        self.taskScheduler = TaskScheduler(parent=self, max_workers=2, use_async_loop=True)
        self.taskScheduler.emitter.finished.connect(self._on_dynamic_worker_finished)

        self.trayIcon = QSystemTrayIcon()
        self.trayIcon.setIcon(GlobalResourceLoader.loadPixmapFromSVG("dynamic_island.svg", QSize(64, 64)))
        self.trayMenu = QMenu()
        self.trayAction_About = QAction("About")
        self.trayAction_About.triggered.connect(self.about)
        self.trayAction_Exit = QAction("Exit")
        self.trayAction_Exit.triggered.connect(self.exitApp)
        self.trayMenu.addAction(self.trayAction_About)
        self.trayMenu.addAction(self.trayAction_Exit)
        self.trayIcon.setContextMenu(self.trayMenu)
        self.trayIcon.setToolTip("Dynamic Island")
        self.trayIcon.show()
        
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

        self.panelProgressBars: dict[str, tuple[float, float]] = {} # curent, max, maximum=0 -> no bar, maximum<0 -> indeterminate
        self.panelProgressBarRendering: tuple[float, float] = (0, 0) # from width %, to %, using QPointF(x, y) to represent
        self.panelProgressBarAnimation: QVariantAnimation = QVariantAnimation(self)
        self.panelProgressBarAnimation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.panelProgressBarAnimation.setDuration(500)
        self.panelProgressBarAnimation.valueChanged.connect(self.rerenderProgressBar)

        self.mouseHoverAnimation = QVariantAnimation(self)
        self.mouseHoverAnimation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.mouseHoverAnimation.valueChanged.connect(self.update)
        self.mouseHoverAnimation.setStartValue(0)
        self.mouseHoverAnimation.setEndValue(-1)
        self.mouseHoverAnimation.setDuration(300)

        self.defaultPosition = QRect()
        self.currentScreenState = acquireScreenState()
        self.initialize()

        self.mouseCheckTimer = QTimer(self)
        self.mouseCheckTimer.timeout.connect(self.checkMouse)
        self.mouseCheckTimer.setSingleShot(False)
        self.mouseCheckTimer.setInterval(100)
        self.mouseCheckTimer.start()

        self.extensionManager = ExtensionManager(self)
        self.extensionThread = ExtensionThread(self.extensionManager)
        self.loadExtension()

    def onTestTimer(self):
        self.checkMouse()

    def exitApp(self):
        self.hide()
        # TODO: fix thread terminate issues
        sys.exit()

    def about(self):
        QMessageBox.about(self, "About Dynamic Island",
            f"Dynamic Island by Perplexity\nv{VERSION}\n"
        )

    def focusModeOn(self):
        # self.frameworkAnimation.
        print("Focus mode on.")
        Hide_height = 2
        Hide_width = 40
        pos = QPoint((acquireScreenState().geometry.width() - Hide_width) // 2, -Hide_height-1)
        endRect = QRect(pos.x() - self.Expand_width, pos.y(), Hide_width + self.Expand_width * 2, Hide_height)

        self.frameworkAnimation.start(self.geometry(), endRect, duration=920, center_on_width=True)

    def focusModeOff(self):
        print("Focus mode off.")
        self.animateToPanel()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        print("Mouse press received")
        return super().mousePressEvent(event)
    
    def panelClicked(self):
        ...

    def loadExtension(self):
        mainPanel: MainPanel = self.panels["DynamicIsland.MainPanel"] # type: ignore
        mainPanel.PanelSizeHint = QSize(400, 30)
        mainPanel.rightLabel.setText("- Loading Extensions")
        self.animateToPanel()

        self.extensionManager.loadingProgress.connect(
            lambda cur, tot: self.panels[self.currentPanelID].requestProgressBarUpdate.emit(cur, tot*2)
        )
        
        def finishedLoading():
            mainPanel.rightLabel.transitionToText("- Loading Panels")
            for x in self.extensionManager.extensionPanelTypes:
                self.registerPanel(x, self.extensionManager.extensionPanelTypes[x][0](), self.extensionManager.extensionPanelTypes[x][1])
            
            tryDisconnect(self.extensionManager.loadingProgress)
            tryDisconnect(self.extensionManager.finishedLoading)
            self.extensionManager.loadingProgress.connect(
                lambda cur, tot: self.panels[self.currentPanelID].requestProgressBarUpdate.emit(cur + tot, tot*2)
            )

            def finishedLoading2():
                tryDisconnect(self.extensionManager.loadingProgress)
                tryDisconnect(self.extensionManager.finishedLoading)
                mainPanel.startUpdate()
                self.panel_priorities[self.currentPanelID] = 0
                self.panels[self.currentPanelID].requestProgressBarUpdate.emit(0, 0)
                mainPanel.PanelSizeHint = QSize(300, 30)
                self.checkPanelLayers()
                self.panels["DynamicIsland.FocusPanel"].fullscreenTimer.start() # type: ignore

            self.extensionManager.finishedLoading.connect(finishedLoading2)
            self.extensionThread.start()
            
        self.extensionManager.finishedLoading.connect(finishedLoading)
        self.extensionThread.start()         

    def checkMouse(self):
        """实时获取鼠标位置"""
        mouseIn = self.geometry().contains(QCursor.pos())
        if mouseIn and self.mouseHoverAnimation.endValue() != self.Expand_width:
            self.mouseHoverAnimation.stop()
            self.mouseHoverAnimation.setStartValue(self.mouseHoverAnimation.currentValue())
            self.mouseHoverAnimation.setEndValue(self.Expand_width)
            self.mouseHoverAnimation.start()

        elif not mouseIn and self.mouseHoverAnimation.endValue() != 0:
            self.mouseHoverAnimation.stop()
            self.mouseHoverAnimation.setStartValue(self.mouseHoverAnimation.currentValue())
            self.mouseHoverAnimation.setEndValue(0)
            self.mouseHoverAnimation.start()

    @Slot(float, float)
    def requestProgressBarUpdate(self, current: float, maximum: float, useTransition: bool = True):
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
        rect = QRectF(self.rect().marginsRemoved(
            QMargins(self.Expand_width - self.mouseHoverAnimation.currentValue(), 0, 
                     self.Expand_width - self.mouseHoverAnimation.currentValue(), 0)
        ))
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
        print("Registered:", panel_id, priority)
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
        self.registerPanel("DynamicIsland.MainPanel", MainPanel(), 1000000)
        self.registerPanel("DynamicIsland.MediaPanel", MediaPanel(), 1)

        focusPanel = FocusPanel()
        focusPanel.focusStarted.connect(self.focusModeOn)
        focusPanel.focusEnded.connect(self.focusModeOff)
        self.registerPanel("DynamicIsland.FocusPanel", focusPanel, 999999)

        screenState = acquireScreenState()
        InitialSize = QSize(100, 0)
        InitialPos = QPoint(int((screenState.geometry.width() - InitialSize.width()) / 2), -15)
        self.setGeometry(QRect(InitialPos, InitialSize))

        self.panels["DynamicIsland.MainPanel"].PanelSizeHint = QSize(400, 30)
        self.switchToPanel("DynamicIsland.MainPanel")

    def panelShowRequested(self):
        panel: Panel = self.sender() # type: ignore
        print(panel.panelID, "is requesting to show")
        if panel.panelID != self.currentPanelID:
            if panel.panelID not in self.panel_layers:
                self.panel_layers.append(panel.panelID)
            self.checkPanelLayers()

    def panelHideRequested(self):
        panel: Panel = self.sender() # type: ignore
        print(panel.panelID, "is requesting to hide")
        if len(self.panel_layers) == 1:
            return
        
        try:
            self.panel_layers.remove(panel.panelID)
        finally:
            self.checkPanelLayers()

    def checkPanelLayers(self):
        self.panel_layers.sort(key=lambda x: self.panel_priorities[x])
        if self.panel_layers[-1] != self.currentPanelID:
            self.switchToPanel(self.panel_layers[-1])

    def animateToPanel(self, panel_id: str | None = None):
        if not panel_id:
            panel_id = self.currentPanelID
            if not panel_id:
                return

        screenState = acquireScreenState()
        self.currentScreenState = screenState

        panel = self.panels[panel_id]
        pos = QPoint((screenState.geometry.width() - panel.PanelSizeHint.width()) // 2, panel.Top_space)
        endRect = QRect(pos.x() - self.Expand_width, pos.y(), panel.PanelSizeHint.width() + self.Expand_width * 2, panel.PanelSizeHint.height())

        self.frameworkAnimation.start(self.geometry(), endRect, duration=920, center_on_width=True)
        self.show()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.placePanel()
        return super().resizeEvent(event)
    
    def placePanel(self):
        if not self.currentPanel:
            return
        
        self.currentPanel.setGeometry(QRect(self.Expand_width, 0, self.width() - 2*self.Expand_width, self.height()))

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
    app.setApplicationName("DynamicIsland")
    app.setWindowIcon(GlobalResourceLoader.loadPixmapFromSVG("dynamic_island.svg", QSize(64, 64)))
    app.setStyleSheet(
'''
QLabel {
    color: white;
}
'''
    )
    island = DynamicIsland()
    app.exec()