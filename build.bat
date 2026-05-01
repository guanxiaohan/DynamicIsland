C:\Users\13792\AppData\Local\Python\pythoncore-3.12-64\Scripts\pyinstaller.exe -w --noconfirm --name DynamicIsland -i ./Resources/Images/dynamic_island.ico ./Main.py

xcopy Resources\ dist\DynamicIsland\Resources /E /Y /EXCLUDE:build_copy_exclude.txt
xcopy Extensions\ dist\DynamicIsland\Extensions /E /Y
xcopy Extension.py dist\DynamicIsland\ /Y
