from Extension import *
from typing import Self
from PySide6.QtCore import QTimer, QObject
import os
import datetime
import enum
import dataclasses
import json

class ExtensionPanel(BarPanel):

    @dataclasses.dataclass
    class SingleClassTime:

        @dataclasses.dataclass
        class TimeRule:
            class RepeatType(enum.Enum):
                Weekly = 0
                Daily = 1 # equivalent to Weekly, 7 days
                MultiWeekly = 2
        
            start_time: datetime.time
            end_time: datetime.time
            repeat_type: RepeatType
            weekdays: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7) # 1 for Monday, etc.

             # (the date marked for beginning week, weeks in one loop)
             # e.g. (2025/10/11, 4) means: regard the week where 2025/10/11 is contained as week #1,
             # 1 cycle takes 4 weeks.
            weeks: tuple[datetime.date, int] | None = None

            # ---------- JSON Dump ----------
            def to_dict(self) -> dict:
                return {
                    "start_time": self.start_time.isoformat(),
                    "end_time": self.end_time.isoformat(),
                    "repeat_type": self.repeat_type.name,
                    "weekdays": list(self.weekdays),
                    "weeks": (
                        [self.weeks[0].isoformat(), self.weeks[1]]
                        if self.weeks is not None
                        else None
                    ),
                }

            @classmethod
            def from_dict(cls, d: dict) -> Self:
                return cls(
                    start_time=datetime.time.fromisoformat(d["start_time"]),
                    end_time=datetime.time.fromisoformat(d["end_time"]),
                    repeat_type=cls.RepeatType[d["repeat_type"]],
                    weekdays=tuple(d["weekdays"]),
                    weeks=(
                        (datetime.date.fromisoformat(d["weeks"][0]), d["weeks"][1])
                        if d["weeks"] is not None
                        else None
                    )
                )

        time_rule: TimeRule
        class_id: int
        merged: bool = False
        display_name: str = "Class"
        notify_begin: int = 0
        notify_end: int = 0

        # ---------- JSON ----------
        def dumpToJsonStr(self) -> str:
            data = {
                "time_rule": self.time_rule.to_dict(),
                "class_id": self.class_id,
                "merged": self.merged,
                "display_name": self.display_name,
                "notify_begin": self.notify_begin,
                "notify_end": self.notify_end,
            }
            return json.dumps(data, ensure_ascii=False)

        @classmethod
        def loadFromJsonStr(cls, s: str) -> Self:
            d = json.loads(s)
            return cls(
                time_rule=cls.TimeRule.from_dict(d["time_rule"]),
                class_id=d["class_id"],
                merged=d["merged"],
                display_name=d["display_name"],
                notify_begin=d["notify_begin"],
                notify_end=d["notify_end"],
            )

    @dataclasses.dataclass
    class ClassInstance:
        class_name: str
        class_id: int
        class_day: tuple[int, int] # weekday, week in cycle

        # ---------- JSON ----------
        def dumpToJsonStr(self) -> str:
            d = dataclasses.asdict(self)
            d["class_day"] = list(self.class_day)
            return json.dumps(d, ensure_ascii=False)

        @classmethod
        def loadFromJsonStr(cls, s: str) -> Self:
            d = json.loads(s)
            d["class_day"] = tuple(d["class_day"])
            return cls(**d)

    class ClassSchedule:
        def __init__(self, timeTable: list['ExtensionPanel.SingleClassTime'], classFills: list['ExtensionPanel.ClassInstance'], exceptions: list['ExtensionPanel.ClassInstance']):
            self.timeTable = timeTable
            self.classes = classFills

        

    def __init__(self):
        super().__init__()

        self.testLabel = BasicLabel()
        self.leftLayout.addWidget(self.testLabel)
        
        self.timer = QTimer()
        self.timer.singleShot(4000, self.req)

    def postInitialize(self):
        self.loadSchedule()

    def loadSchedule(self):
        self.schedules = []
        path = ExtensionRoot + "ClassScheduler.TimeTable.json"
        if not os.path.exists(path):
            with open(path, "w") as f:
                return
        try:
            with open(path) as f:
                ...

        except:
            ...

    def req(self):
        self.requestShow.emit()
    
DI_registerPanel("ClassScheduler.SchedulePanel", ExtensionPanel, 0)
