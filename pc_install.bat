@echo off
rem Cruller setup for Windows. Double-click me once.
>nul chcp 65001
where py >nul 2>nul && (set "PYRUN=py -3") || (set "PYRUN=python")
echo 1/2  Python libraries
%PYRUN% -m pip install --quiet numpy pillow opencv-python-headless pillow-heif
echo 2/2  checking the libraries
%PYRUN% -c "import numpy, PIL, cv2; print('     ready')"
echo.
echo Done. Drag a photo folder onto pc_crull.bat to analyse it.
pause
