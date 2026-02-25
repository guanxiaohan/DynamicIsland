# Extension.py
# Header file for DynamicIsland extensions
# Must write "from Extension import *"" at the beginning of the script.

from Widgets import (Panel, BasicLabel, AbstractWidget, AlternatingLabel, BarPanel)
import Widgets
from Utils import (Pens, Brushes, Fonts, acquireScreenState, generateEasingCurve, 
                   tryDisconnect, getTimeString, GlobalResourceLoader,
                   DynamicProperty, SpringAnimation, logger)
import Utils

import Windows

from TaskScheduler import (TaskScheduler, ScheduledTask)
import TaskScheduler

import typing
import time

# def DI_registerPanel(panel_id: str, panel: Panel, priority: int = 0):
#     print(1)
ExtensionRoot = "./Extensions/"
DI_setExtensionName: typing.Callable[[str], None]
DI_setExtensionNamespace: typing.Callable[[str], None]
DI_registerPanel: typing.Callable[[str, type[Panel], int], None]
