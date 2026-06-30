# Ezthumb Modern (CustomTkinter Edition)

A desktop graphical user interface for the Ezthumb contact sheet generator, rebuilt using CustomTkinter.

## Features

- Modern Dark Mode Interface: A unified dark user interface leveraging CustomTkinter widgets and custom styling.
- Native Drag and Drop: Integrated drag and drop capability using the tkinterdnd2 library to prevent GIL locks and support administrator execution.
- Metadata Integration: Advanced media track detection via the pymediainfo library. Displays video resolutions, display aspect ratios (DAR), frame rates, precise audio stream bitrates, and descriptive subtitle track titles.
- Adjustable Grid Layout: Responsive 2-column thumbnail editing grid that fits within the default 917x617 window size.
- Smart Frame Randomizer: Generates random frame timestamps while maintaining chronological order to prevent overlap.
- Profile Management: Save and load configuration settings dynamically.

## Requirements

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Additional requirements:
- MediaInfo must be installed on the system for pymediainfo to access the shared libraries.

## Building the Executable

To compile a standalone Windows executable, run PyInstaller with the provided specification file:

```bash
pyinstaller --noconfirm EzthumbWin_CTk.spec
```

Note: Ensure that ezthumb.exe, ffmpeg.exe, and ffprobe.exe are located in "C:\Program Files (x86)\Ezthumb" for correct packaging.

## Project Structure

- EzthumbWin_CTk.py: The main application script.
- EzthumbWin_CTk.spec: PyInstaller configuration and build specification.
- favicon.ico: Application icon.
- requirements.txt: List of required Python dependencies.
- .gitignore: Standard configuration to exclude build and cache folders from Git.
