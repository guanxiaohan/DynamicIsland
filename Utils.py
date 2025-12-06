# Utils.py

import time
from dataclasses import dataclass
from time import localtime, strftime

from PySide6.QtCore import (Q_ARG, Q_RETURN_ARG, QByteArray, QEasingCurve,
                            QMetaObject, QObject, QPoint, QPropertyAnimation,
                            QRect, QRectF, QRunnable, QSize, Qt, QThreadPool,
                            QTimer, Signal, SignalInstance, QAbstractAnimation,
                            QVariantAnimation)
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QSizePolicy,
                               QWidget)
from typing import Callable, Any


@dataclass
class screenState:
    geometry: QRect
    logicalDPI: float

def acquireScreenState():
    screen = QGuiApplication.primaryScreen()
    return screenState(
        screen.geometry(),
        screen.logicalDotsPerInch()
    )

def generateEasingCurve():
    import math

    def spring_ease(x, zeta=0.6, omega0=10.0):
        t = max(0.0, min(1.0, x))
        if zeta < 1.0:
            wd = omega0 * math.sqrt(1 - zeta*zeta)
            expo = math.exp(-zeta*omega0*t)
            return 1 - expo*(math.cos(wd*t) + (zeta/math.sqrt(1-zeta*zeta))*math.sin(wd*t))
        else:
            # 临界或过阻尼的数值近似（避免除零）
            expo = math.exp(-omega0*t)
            return 1 - expo*(1 + omega0*t)
        
    easingCurve = QEasingCurve()
    easingCurve.setCustomType(spring_ease)
    return easingCurve, spring_ease

def getTimeString(t: float | int | None = None, second: bool = True):
    if t:
        return strftime("%H:%M:%S" if second else "%H:%M", time.localtime(t))
    else:
        return strftime("%H:%M:%S" if second else "%H:%M", time.localtime())

def tryDisconnect(signal: SignalInstance, slot: Callable | None = None):
    try:
        signal.disconnect(slot) if slot else signal.disconnect()
    except:
        pass

class Fonts:
    def __init__(self) -> None:
        ...

    @staticmethod
    def default() -> QFont:
        DefaultFont = QFont("Calibri", pointSize=12)
        DefaultFont.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return DefaultFont

class Pens:
    cameraPen = QPen()
    cameraPen.setWidth(5)
    cameraPen.setColor(QColor(20, 20, 20, 255))

    progressPen = QPen(QColor(95, 95, 95, 255))
    progressPen.setCapStyle(Qt.PenCapStyle.RoundCap)

class Brushes:
    backgroundBrush = QColor(30, 30, 30, 240)
    cameraBrush = QColor(80, 80, 80, 255)

@dataclass
class DynamicProperty:
    enabled: bool = True
    max_interval: int = 1000  # milliseconds
    asynchronous: bool = False
    updating: bool = False

class SpringAnimation(QObject):
    """
    永久存在的几何动画器（封装 QVariantAnimation）。
    - parent: 通常传入 DynamicIsland 实例（用于 setGeometry）
    - easing_func: 接受 0..1 返回 progress 的函数（例如 spring_ease）
    - duration: 毫秒
    - min_size: 宽/高的最小值，避免设为 0 导致 Windows 层问题
    """
    def __init__(self, parent: QWidget, easing_func: Callable | None = None, duration: int = 920, min_size: int = 1):
        super().__init__(parent)
        self._parent = parent
        self._screen_width = acquireScreenState().geometry.width()
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(duration)
        self._anim.valueChanged.connect(self._on_value_changed)
        self._anim.finished.connect(self._on_finished)

        self.easing = easing_func or (lambda t: t)
        self._start_rect = QRect()
        self._end_rect = QRect()
        self._animate_width = True
        self._animate_height = True
        self._animate_x = True
        self._animate_y = True
        self._center_on_width = True
        self._min_size = max(1, int(min_size))
        self._running = False

    def start(self, start_rect: QRect, end_rect: QRect, *,
              duration: int | None = None,
              center_on_width: bool = True):
        try:
            self._screen_width = acquireScreenState().geometry.width()
        except Exception:
            self._screen_width = 1920  # 回退值

        # copy rects (避免外部引用被改动)
        self._start_rect = QRect(start_rect)
        self._end_rect = QRect(end_rect)

        # 判定哪些方向需要动画（等于则忽略）
        self._animate_width = (self._start_rect.width() != self._end_rect.width())
        self._animate_height = (self._start_rect.height() != self._end_rect.height())
        # x 动画：如果居中策略启用且宽度会变动，我们会根据每帧宽度重新计算 x（所以就不插值原有 x）
        self._center_on_width = bool(center_on_width)
        if self._center_on_width and self._animate_width:
            # 当宽度随动画变化时，x 由每帧居中计算（不插值 start_x->end_x）
            self._animate_x = False
        else:
            self._animate_x = (self._start_rect.x() != self._end_rect.x())

        self._animate_y = (self._start_rect.y() != self._end_rect.y())

        # 如果完全相同，直接设置并返回
        if self._start_rect == self._end_rect:
            self._parent.setGeometry(self._end_rect)
            return

        if duration is not None:
            self._anim.setDuration(int(duration))

        # 停掉已有动画（安全）
        if self._anim.state() == QAbstractAnimation.State.Running:
            self._anim.stop()

        # 启动
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._running = True

    def stop(self, jump_to_end: bool = False):
        if self._anim.state() == QAbstractAnimation.State.Running:
            self._anim.stop()
        if jump_to_end:
            self._parent.setGeometry(self._end_rect)
        self._running = False

    def _on_value_changed(self, v):
        # v 是 0.0..1.0
        t = float(v)
        try:
            p = float(self.easing(t))
        except Exception:
            p = t  # 回退
        # 计算当前宽高
        if self._animate_width:
            cur_w = int(round(self._start_rect.width() + (self._end_rect.width() - self._start_rect.width()) * p))
        else:
            cur_w = self._start_rect.width()

        if self._animate_height:
            cur_h = int(round(self._start_rect.height() + (self._end_rect.height() - self._start_rect.height()) * p))
        else:
            cur_h = self._start_rect.height()

        # 最小值保护（避免 0 或负）
        if cur_w < self._min_size:
            cur_w = self._min_size
        if cur_h < self._min_size:
            cur_h = self._min_size

        # 计算位置：如果启用 center_on_width 且宽度在变，则每帧居中（使用屏幕宽度）
        if self._center_on_width and self._animate_width:
            # screenState = acquireScreenState()
            cur_x = int((self._screen_width - cur_w) // 2)
        else:
            if self._animate_x:
                cur_x = int(round(self._start_rect.x() + (self._end_rect.x() - self._start_rect.x()) * p))
            else:
                cur_x = self._start_rect.x()

        if self._animate_y:
            cur_y = int(round(self._start_rect.y() + (self._end_rect.y() - self._start_rect.y()) * p))
        else:
            cur_y = self._start_rect.y()

        # 最终一次性设置完整矩形 —— 保证原子性
        self._parent.setGeometry(cur_x, cur_y, cur_w, cur_h)

    def _on_finished(self):
        # 确保最后帧精确到目标状态（修正浮点误差）
        self._parent.setGeometry(self._end_rect)
        self._running = False
    
def addRoundCornerToPixmap(pixmap: QPixmap, radius: int, color: QColor = QColor(0, 0, 0, 0)) -> QPixmap:
    """
    Return a new QPixmap that is the original pixmap clipped to rounded corners.
    Outside the rounded rect will be filled with `color` (default transparent).

    Args:
        pixmap: source QPixmap (may be null).
        radius: corner radius in pixels.
        color: background color to fill the corners (default fully transparent).

    Returns:
        QPixmap: new pixmap with rounded corners.
    """
    if pixmap is None or pixmap.isNull():
        return QPixmap()

    # Preserve device pixel ratio for HiDPI
    dpr = pixmap.devicePixelRatio()
    size = pixmap.size()
    w, h = size.width(), size.height()

    # Clamp radius to valid range
    r = max(0, int(radius))
    r = min(r, min(w, h) // 2)

    # Prepare the target pixmap and fill with background color (may be transparent)
    result = QPixmap(size)
    result.fill(color)
    result.setDevicePixelRatio(dpr)

    # Create rounded path
    path = QPainterPath()
    path.addRoundedRect(QRectF(0.0, 0.0, float(w), float(h)), float(r), float(r))

    # Paint the source pixmap into the rounded area of the result (atomic per-frame friendly)
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Clip to the rounded path so only the rounded region gets the source pixmap drawn
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
    finally:
        painter.end()

    return result