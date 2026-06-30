# Ezthumb Modern (CustomTkinter Edition)

A desktop graphical user interface for the Ezthumb contact sheet generator, built with CustomTkinter.

## Requirements

Ensure the Python dependencies are installed:

```bash
pip install -r requirements.txt
```

In addition, the application requires:
- MediaInfo must be installed on the system for pymediainfo to access the shared libraries.
- The Ezthumb engine binaries (`ezthumb.exe`, `ffmpeg.exe`, `ffprobe.exe` and their associated DLLs) should be located in the `bin/` directory of the project, or installed globally at `C:\Program Files (x86)\Ezthumb`.

## Running the Application (Recommended)

To run the application directly from the source code without compilation (avoiding antivirus false positives):

```bash
python EzthumbWin_CTk.py
```

## Building the Standalone Executable (Optional)

To compile a standalone Windows executable, execute PyInstaller with the provided specification file:

```bash
pyinstaller --noconfirm EzthumbWin_CTk.spec
```

The compiled output will be generated inside the `dist/EzthumbWin_CTk/` directory.

Important: Since this is built in directory mode (`--onedir`), the executable `EzthumbWin_CTk.exe` requires the `_internal` directory to be present in the same folder. Do not move or copy the `.exe` file by itself.

## Project Structure

- EzthumbWin_CTk.py: The main application script.
- EzthumbWin_CTk.spec: PyInstaller configuration and build specification.
- favicon.ico: Application icon.
- requirements.txt: List of required Python dependencies.
- .gitignore: Configuration to exclude build and cache folders from Git.
