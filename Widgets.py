# Widgets.py

from PySide6.QtGui import QPaintEvent, QPixmap, QFontMetrics
from PySide6.QtCore import QEasingCurve, Slot, Property
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget, QGraphicsOpacityEffect

from TaskScheduler import TaskScheduler
from Utils import *
import asyncio
import datetime

class AbstractWidget:
    _task_id: str = ""
    dynamicProperty: DynamicProperty | None = None

    def updateRetrieval(self) -> object | None:
        '''An abstract method for updating label content.'''
        ...

    @Slot(object)
    def updateReceived(self, data: object | None):
        '''Update the widget content with the retrieved data.'''
        ...

AppearDuration = 230
VanishDuration = 230

class Panel(QWidget):
    vanished = Signal()
    appeared = Signal()
    requestResize = Signal()
    requestShow = Signal()
    requestHide = Signal()
    requestProgressBarUpdate = Signal(int, int) # current, max

    PanelSizeHint = QSize(300, 30)
    Top_space = 0
    Center_space = 26
    Spacing = 6
    Left_margin = 9
    Right_margin = 9
    Top_margin = 2
    Bottom_margin = 2

    SpringCurve, SpringCurve_Reference = generateEasingCurve()

    def __init__(self):
        super().__init__()
        self.panelID: str = ""

        self.taskScheduler = TaskScheduler(parent=self, max_workers=2, use_async_loop=True)
        self.taskScheduler.emitter.finished.connect(self._on_dynamic_worker_finished)
        self.dynamicUpdateQueue: list[AbstractWidget] = []
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self.opacityAnimation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self.opacityAnimation.setEasingCurve(QEasingCurve.Type.Linear)

        self.setContentsMargins(self.Left_margin, self.Top_margin, self.Right_margin, self.Bottom_margin)
        self.mainLayout = QHBoxLayout()
        self.mainLayout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(self.mainLayout)

    def _on_dynamic_worker_finished(self, task_id: str, widget: AbstractWidget, data, exc):
        try:
            widget.updateReceived(data)
        except Exception:
            import traceback
            traceback.print_exc()

    def registerDynamicWidget(self, widget: AbstractWidget):
        self.dynamicUpdateQueue.append(widget)
        dp = getattr(widget, "dynamicProperty", None)
        if dp and dp.enabled:
            # 如果方法本身是协程函数，则按协程执行
            is_coro_func = asyncio.iscoroutinefunction(getattr(widget, "updateRetrieval", None))
            # prefer real detection; you can still override by dp.asynchronous if you want:
            is_coroutine = True if is_coro_func else False

            if is_coroutine:
                # for coroutine tasks pass a callable that returns a coroutine, and owner=widget
                task_id = self.taskScheduler.schedulePeriodic(
                    lambda: widget.updateRetrieval(),  # factory that returns coroutine
                    dp.max_interval,
                    is_coroutine=True,
                    owner=widget
                )
            else:
                task_id = self.taskScheduler.schedulePeriodic(
                    widget.updateRetrieval,
                    dp.max_interval,
                    is_coroutine=False,
                    owner=widget
                )
            widget._task_id = task_id

    def vanish(self):
        tryDisconnect(self.opacityAnimation.finished)
        self.opacityAnimation.stop()
        self.opacityAnimation.setDuration(VanishDuration)
        self.opacityAnimation.setStartValue(1.0)
        self.opacityAnimation.setEndValue(0.0)
        self.opacityAnimation.finished.connect(self.onVanishFinished)
        self.opacityAnimation.start()

    def onVanishFinished(self):
        self.vanished.emit()
        self.hide()
        # # cancel widget tasks
        # for w in self.dynamicUpdateQueue:
        #     tid = getattr(w, "_task_id", None)
        #     if tid:
        #         self.taskScheduler.cancel(tid)
        #         delattr(w, "_task_id")
        tryDisconnect(self.opacityAnimation.finished)
        tryDisconnect(self.vanished)

    def appear(self):
        self.show()
        tryDisconnect(self.opacityAnimation.finished)
        self.opacityAnimation.stop()
        self.opacityAnimation.setDuration(AppearDuration)
        self.opacityAnimation.setStartValue(0.0)
        self.opacityAnimation.setEndValue(1.0)
        self.opacityAnimation.finished.connect(self.onAppearFinished)
        self.opacityAnimation.start()

    def onAppearFinished(self):
        self.appeared.emit()
        tryDisconnect(self.opacityAnimation.finished)
        tryDisconnect(self.appeared)

    @Slot(int, str)
    def notificationReceived(self, priority: int, content: str):
        '''Global notification event'''
        ...

class BarPanel(Panel):
    # Implement a base class for those panels which only have a bar-layout
    # Which have left and right parts divided by a center space ("Camera" drew on main class)

    Width_rightIcon = 15
    Color_Notification = QColor(0, 124, 215)

    def __init__(self):
        super().__init__()

        self.setContentsMargins(0, 0, 0, 0)
        self.leftWidget = QWidget(self)  # Used for left side layout
        self.leftLayout = QHBoxLayout()
        self.leftLayout.setContentsMargins(self.Left_margin, self.Top_margin, self.Spacing, self.Bottom_margin)
        self.leftWidget.setLayout(self.leftLayout)
        self.rightWidget = QWidget(self)  # Used for right side layout
        self.rightLayout = QHBoxLayout()
        self.rightLayout.setContentsMargins(self.Spacing, self.Top_margin, self.Right_margin, self.Bottom_margin)
        self.rightWidget.setLayout(self.rightLayout)

        # schedulePeriodic should call detectMicCam periodically (you already had this)
        # self.taskScheduler.schedulePeriodic(lambda: self.detectMicCam(), 2000,
        #                                     is_coroutine=True, owner=self)

        # animation state (0.0..1.0)
        self.animation_RightIcon: float = 0.0

        # property animation drives the Property "Animation_RightIcon"
        self.rightIconAnimation = QPropertyAnimation(self, b"Animation_RightIcon")
        self.rightIconAnimation.setDuration(650)
        self.rightIconAnimation.setEasingCurve(QEasingCurve.Type.Linear)

        self._icon_before_state: tuple[QColor | None, float] = (None, 0.0)
        self._icon_after_state: tuple[QColor | None, float] = (None, 0.0)
        
    # async def detectMicCam(self):
    #     from Windows import check_device_usage  # your module
    #     return await check_device_usage()

    def updateReceived(self, data):
        """
        Panel.taskScheduler -> this will be called with detection result.
        Data expected to be: (mic_using: bool, cam_using: bool)
        """
        # be tolerant: if data is (mic, cam) tuple or dict with keys
        if data is None:
            return
        
        # route to state-changed handler
        self.iconStateChanged(data["color"])

    def reposition(self):
        total_width = self.width()
        center_space = self.Center_space
        left_width = (total_width - center_space) // 2
        right_width = (total_width - center_space) // 2 - self.calculateRightIconWidth()

        self.leftWidget.setGeometry(0, 0, left_width, self.height())
        self.rightWidget.setGeometry(self.width() - right_width - self.calculateRightIconWidth(), 0, right_width, self.height())

    def resizeEvent(self, event):
        self.reposition()
        return super().resizeEvent(event)

    def calculateRightIconWidth(self) -> int:
        # actual width of one icon (animated)
        return int(round(self.Width_rightIcon * self.SpringCurve.valueForProgress(self.animation_RightIcon)))

    def iconStateChanged(self, color: QColor | None):
        """Handle detection result and animate icon area in/out accordingly."""
        self._icon_before_state = (self._icon_after_state[0], float(self.animation_RightIcon))
        self.rightIconAnimation.stop()
        self.rightIconAnimation.setStartValue(float(self.animation_RightIcon))

        # if any device is currently used, animate to 1.0 (show), otherwise to 0.0 (hide)
        target = 1.0 if color else 0.0
        # short-circuit if already at target
        if abs(self.animation_RightIcon - target) < 1e-3:
            # nothing to animate, but ensure repainted
            self.update()
            return

        self.rightIconAnimation.setEndValue(target)
        self._icon_after_state = (color, target)
        self.rightIconAnimation.start()

    def animation_getRightIconProgress(self) -> float:
        return float(self.animation_RightIcon)

    def animation_setRightIconProgress(self, progress: float) -> None:
        p = float(progress)
        self.animation_RightIcon = p
        # any change in animation should force repaint
        self.reposition()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        try:
            mix = (lambda c1, c2, c2_prop: c2*min(c2_prop, 1) + c1*max(1-c2_prop, 0)) if self._icon_after_state[0] is not None else (lambda c1, c2, c2_prop: c1*min(c2_prop, 1) + c2*max(1-c2_prop, 0))
            color0 = self._icon_before_state[0] or QColor(0, 0, 0, 0)
            color1 = self._icon_after_state[0] or QColor(0, 0, 0, 0)
            progress = self.animation_getRightIconProgress() * 1.2
            color = QColor(mix(color0.red(), color1.red(), progress),
                           mix(color0.green(), color1.green(), progress),
                           mix(color0.blue(), color1.blue(), progress),
                           mix(color0.alpha(), color1.alpha(), progress))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            radius = 6
            posX = self.width() - self.calculateRightIconWidth()//2 - radius//2 - self.Right_margin + 3
            posY = self.height()//2 - radius//2

            pen = QPen(color)
            painter.setPen(pen)
            brush = QBrush(color)
            painter.setBrush(brush)
            painter.drawEllipse(posX, posY, radius, radius)

        finally:
            painter.end()

    Animation_RightIcon = Property(float, animation_getRightIconProgress, animation_setRightIconProgress)

    def leftAvailableWidth(self, newWidth: int | None = None) -> int:
        return (newWidth or self.PanelSizeHint.width()) // 2 - self.Center_space // 2 - self.Left_margin - self.Spacing

    def rightAvailableWidth(self, newWidth: int | None = None) -> int:
        extra = self.Width_rightIcon
        return (newWidth or self.PanelSizeHint.width()) // 2 - self.Center_space // 2 - self.Right_margin - extra - self.Spacing
    
    def notificationReceived(self, priority: int, content: str):
        self.iconStateChanged(self.Color_Notification)

class MainPanel(BarPanel):
    def __init__(self):
        super().__init__()
        
        self.leftLabel = BasicLabel("Dynamic Island")
        self.rightLabel = BasicLabel("- Perplexity")

        self.taskScheduler.schedulePeriodic(lambda: getTimeString(None, False), 3000, owner = self)

        self.leftLayout.addWidget(self.leftLabel)
        self.rightLayout.addWidget(self.rightLabel, alignment=Qt.AlignmentFlag.AlignRight)

    def updateReceived(self, data):
        currentTime = time.localtime()
        txt = "Good Morning." if 3 <= currentTime.tm_hour < 12 else \
              "Good Afternoon." if 12 <= currentTime.tm_hour < 18 else \
              "Good Evening."
        self.rightLabel.setText(data)
        self.leftLabel.transitionToText(txt)

class MediaPanel(BarPanel):
    PanelSizeHint = (QSize(400, 30))
    Max_width = 560
    Min_width = 300
    Cover_size = 22
    Spacing = 6

    def __init__(self):
        super().__init__()
        
        self.leftLabel = CurrentMediaLabel()
        self.rightLabel = AlternatingLabel(
            texts={"Time": "", "Artist": ""}, switch_interval=3000, init_id="Time"
        )
        self.albumCoverLabel = QLabel()
        self.registerDynamicWidget(self.leftLabel)

        self.currentThumbnail: bytes | None = None
        self.currentTitle: str | None = None
        self.currentArtist: str | None = None
        self.currentStartTime: float = 0
        self.currentDuration: float = 0

        self.progressBarTimer = QTimer(self)
        self.progressBarTimer.setInterval(1000)
        self.progressBarTimer.timeout.connect(lambda: self.requestProgressBarUpdate.emit(time.time() - self.currentStartTime, self.currentDuration))
        self.progressBarTimer.start()

        self.albumCoverLabel.setFixedSize(self.Cover_size, self.Cover_size)
        self.leftLabel.songRetrieved.connect(self.onSongRetrieved)
        self.albumCoverLabel.hide()
        self.leftLayout.addWidget(self.albumCoverLabel)
        self.leftLayout.addWidget(self.leftLabel)
        self.rightLayout.addWidget(self.rightLabel, alignment=Qt.AlignmentFlag.AlignRight)

    def updateRightLabel(self, artist: str | None):
        self.rightLabel.setTextItem("Time", getTimeString(second=False), False)
        self.rightLabel.setTextItem("Artist", artist, True)

    @Slot(object)
    def onSongRetrieved(self, data: dict | None):
        def isSongChanged(title: str | None, artist: str | None, thumbnail: bytes | None):
            return (title != self.currentTitle) or (artist != self.currentArtist) or (thumbnail != self.currentThumbnail)
        
        if data is not None:
            title = data.get("title", "Unknown Title")
            artist = data.get("artist", "Unknown Artist")
            thumbnail = data.get("thumbnail", None)
            self.currentStartTime, self.currentDuration = (time.time() - (data or {}).get("position_seconds", 0), (data or {}).get("duration_seconds", 0))
        
            if not data["is_playing"] and self.progressBarTimer.isActive():
                self.progressBarTimer.stop()
            elif data["is_playing"] and not self.progressBarTimer.isActive():
                self.progressBarTimer.start()
        else:
            title = None
            artist = None
            thumbnail = None
            self.currentStartTime = 0
            self.currentDuration = 0
            self.progressBarTimer.stop()

        if not isSongChanged(title, artist, thumbnail):
            self.requestProgressBarUpdate.emit(time.time() - self.currentStartTime, self.currentDuration)
            return
        
        self.currentTitle = title
        self.currentArtist = artist
        self.currentThumbnail = thumbnail

        # 先计算要显示的左右文本（但不最终截断——calculateSongTextDivision 会负责半区截断）
        if data:
            left_text, right_artist_text = self.calculateSongTextDivision(title or "Unknown Title", artist or "Unknown Artist",
                                                                       cover_visible=bool(self.currentThumbnail))
        else:
            left_text, right_artist_text = "Not Playing", None

        # 更新显示
        self.leftLabel.transitionToText(left_text)
        self.updateRightLabel(right_artist_text)

        # 处理封面图
        if self.currentThumbnail:
            pixmap = QPixmap()
            pixmap.loadFromData(self.currentThumbnail)  # 直接用 bytes
            self.albumCoverLabel.setPixmap(
                addRoundCornerToPixmap(pixmap.scaled(self.albumCoverLabel.size(),
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation),
                              self.Cover_size//2-1)
            )
            self.albumCoverLabel.show()
            cover_visible = True
        else:
            self.albumCoverLabel.clear()
            self.albumCoverLabel.hide()
            cover_visible = False

        # 4) 使用将要显示的文本计算像素宽度（**不要使用 widget.text()**）
        fm_left = QFontMetrics(self.leftLabel.font())
        fm_right = QFontMetrics(self.rightLabel.font())

        left_w = fm_left.horizontalAdvance(left_text)
        # 右侧的实际显示会在 Time/Artist 之间切换——为避免抖动，使用两者中较宽的作为预期宽度
        time_text = getTimeString(second=False)
        artist_text_for_right = right_artist_text or ""
        right_expected_w = max(fm_right.horizontalAdvance(time_text), fm_right.horizontalAdvance(artist_text_for_right))

        left_margin = self.Left_margin
        right_margin = self.Right_margin
        cover_extra = (self.Cover_size + self.Spacing) if cover_visible else 0

        left_total = left_w + left_margin + self.Spacing + cover_extra
        right_total = right_expected_w + right_margin + self.Spacing
        raw_total = max(left_total, right_total)*2 + self.Center_space
        total_width = int(max(self.Min_width, min(self.Max_width, raw_total)))

        new_size_hint = QSize(total_width, self.PanelSizeHint.height())
        if self.currentTitle != None:
            self.requestShow.emit()
        else:
            self.requestHide.emit()

        if new_size_hint.width() != self.PanelSizeHint.width():
            self.PanelSizeHint = new_size_hint
            self.requestResize.emit()

        self.requestProgressBarUpdate.emit(time.time() - self.currentStartTime, self.currentDuration)

        # 5) 最后把文本应用到 widget（可触发动画）
        self.leftLabel.transitionToText(left_text)
        print("Updated Media Label:", self.currentTitle, self.currentArtist)

    def calculateSongTextDivision(self, title: str, artist: str, cover_visible: bool) -> tuple[str, str | None]:
        """
        策略：
        1) 若 "artist - title" 可以完整放在左半区 => 返回 (artist - title, "")
        2) 否则：尽量把 title 放在左半区（完整或 elide），把 artist 放到右半区（完整或 elide）
        返回 (left_text_to_display, right_artist_text_for_rightLabel)。
        """
        fm_left = QFontMetrics(self.leftLabel.font())
        fm_right = QFontMetrics(self.rightLabel.font())
        cover_extra = (self.Cover_size + self.Spacing) if cover_visible else 0

        # 右侧预估宽：Time 与 Artist 之间取较宽者（用于 tentative_total 估算）
        time_text = getTimeString(second=False)
        time_w = fm_right.horizontalAdvance(time_text)
        artist_raw = artist or ""
        title_raw = title or ""
        # artist_w = fm_left.horizontalAdvance(artist_raw)
        title_w = fm_left.horizontalAdvance(title_raw)
        # sep_w = fm_left.horizontalAdvance(" - ")
        full_left = f"{artist_raw} - {title_raw}"
        full_left_w = fm_left.horizontalAdvance(full_left)

        left_half_avail = int(max(0, self.leftAvailableWidth(self.Max_width) - cover_extra))
        right_half_avail = int(max(0, self.rightAvailableWidth(self.Max_width)))

        # 1) 如果整个 "artist - title" 能放下，直接做左侧完整显示（右侧留空，显示 time）
        if full_left_w <= left_half_avail:
            return full_left, None

        # 2) 否则：左侧优先 title（尽量完整，否则 elide），右侧放 artist（尽量完整，否则 elide）
        # 左侧 title（完整或 elide）
        if title_w <= left_half_avail:
            left_text = title_raw
        else:
            left_text = fm_left.elidedText(title_raw, Qt.TextElideMode.ElideRight, max(0, left_half_avail))

        # 右侧 artist（完整或 elide）
        if fm_right.horizontalAdvance(artist_raw) <= right_half_avail:
            right_text = artist_raw
        else:
            right_text = fm_right.elidedText(artist_raw, Qt.TextElideMode.ElideRight, max(0, right_half_avail))

        return left_text, right_text

class WeatherPanel(Panel):
    PanelSizeHint = QSize(400, 100)

    def __init__(self):
        super().__init__()

        # self.taskScheduler.scheduleOnce()

    def updateReceived(self, weatherData: dict):
        ...

class SchedulePanel(QWidget):
    class Schedule:
        ...
    def __init__(self):
        super().__init__()

    

class BasicLabel(QLabel, AbstractWidget):
    def __init__(self, text: str = "", dynamicProperty: DynamicProperty | None = None):
        super().__init__()
        self.dynamicProperty = dynamicProperty
        self.setFont(Fonts.default())
        self.setContentsMargins(0, 0, 0, 0)
        self.setMargin(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        self._opacity = 1.0

        self.animation = QPropertyAnimation(self, b"opacity")
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.setText(text)

    def paintEvent(self, arg__1):
        painter = QPainter(self)
        pen = painter.pen()
        color = pen.color()
        color.setAlphaF(self._opacity)
        pen.setColor(color)
        painter.setPen(pen)
        painter.drawText(self.rect(), self.alignment(), self.text())
        
    def updateReceived(self, data: Any):
        if data is not None:
            self.setText(str(data))
        print("Updated Label - " + self.text())

    def transitionToText(self, new_text: str, duration: int = 420):
        if new_text == self.text():
            return
        
        self.animation.stop()
        self.animation.setDuration(duration // 2)
        self.animation.setStartValue(self._opacity)
        self.animation.setEndValue(0.0)

        def on_fade_out():
            self.setText(new_text)
            tryDisconnect(self.animation.finished)
            self.animation.stop()
            self.animation.setDuration(duration // 2)
            self.animation.setStartValue(self._opacity)
            self.animation.setEndValue(1.0)
            self.animation.start()

        # unique connection
        tryDisconnect(self.animation.finished)
        self.animation.finished.connect(on_fade_out)
        self.animation.start()

    def getOpacity(self):
        return self._opacity

    def setOpacity(self, v: float):
        self._opacity = v
        self.update()

    def calculateSizeHint(self, text: str) -> QSize:
        fm = QFontMetrics(self.font())
        rect = fm.boundingRect(text)
        return QSize(rect.width() + self.margin()*2, rect.height() + self.margin()*2)

    opacity = Property(float, getOpacity, setOpacity)

class AlternatingLabel(BasicLabel):
    def __init__(self, texts: dict[str, str], init_id: str, switch_interval: int = 3000):
        super().__init__(texts[init_id])
        self.texts = texts
        self.current_id = init_id

        self.switchTimer = QTimer(self)
        self.switchTimer.timeout.connect(self.switchLabel)
        if switch_interval > 0:
            self.switchTimer.setInterval(switch_interval)
            self.switchTimer.setSingleShot(False)
            self.switchTimer.start()

    def switchLabel(self, new_id: str | None = None):
        if new_id and new_id in self.texts:
            self.current_id = new_id
            new_text = self.texts[new_id]
            self.transitionToText(new_text)
            return
        
        elif self.current_id not in self.texts:
            self.current_id = self.texts.keys().__iter__().__next__()
            next_id = self.current_id
            new_text = self.texts[next_id]
            self.transitionToText(new_text)
            return
        
        ids = list(self.texts.keys())
        current_index = ids.index(self.current_id)
        next_index = (current_index + 1) % len(ids)
        next_id = ids[next_index]
        self.current_id = next_id
        new_text = self.texts[next_id]
        self.transitionToText(new_text)

    def setTextItem(self, text_id: str, new_text: str | None, useTransition: bool = True):
        if new_text is None:
            # Remove this text item
            if text_id in self.texts:
                del self.texts[text_id]
                # If it was the current text, switch to another
            if text_id == self.current_id:
                self.switchLabel()
            return
        
        if text_id not in self.texts:
            self.texts[text_id] = new_text

        self.texts[text_id] = new_text
        if text_id == self.current_id:
            self.transitionToText(new_text) if useTransition else super().setText(new_text)

    def removeTextItem(self, text_id: str):
        self.setTextItem(text_id, None)

    def transitionToText(self, new_text: str, duration: int = 420):
        return super().transitionToText(new_text, duration)
    
class CurrentTimeLabel(BasicLabel):
    def __init__(self, showSecond: bool = True):
        super().__init__("", DynamicProperty(enabled=True, max_interval=5000, asynchronous=True))
        self.showSecond = showSecond
        self.setText(getTimeString(second=self.showSecond))

    def updateRetrieval(self) -> str:
        return getTimeString(second=self.showSecond)
    
class CurrentMediaLabel(BasicLabel):
    songRetrieved = Signal(object)

    def __init__(self):
        super().__init__("", DynamicProperty(enabled=True, max_interval=3000, asynchronous=False))
        self.setText("Acquiring Media Info...")

    async def updateRetrieval(self):
        from Windows import get_media_info
        return await get_media_info()

    def updateReceived(self, data: dict | None):
        self.songRetrieved.emit(data)
        
