# Third-party notices

The Windows build uses Qt 6.12.0 and Qt for Python 6.12.0, including PySide6 Essentials and Shiboken6, under the GNU Lesser General Public License, version 3. The license texts are in the `licenses` directory.

Corresponding source and build information for the bundled Qt components are available from their upstream repositories.

- [Qt Base 6.12.0](https://github.com/qt/qtbase/tree/v6.12.0) supplies Qt Core, Gui, Widgets, Network, the Windows platform plugin, and their build files.
- [Qt SVG 6.12.0](https://github.com/qt/qtsvg/tree/v6.12.0) supplies Qt SVG and its image and icon plugins.
- [Qt for Python 6.12.0](https://github.com/qtproject/pyside-pyside-setup/tree/v6.12.0) supplies PySide6, Shiboken6, and their build files.
- [Qt's third-party component notices](https://doc.qt.io/qt-6/licenses-used-in-qt.html) and [Qt for Python's third-party component notices](https://doc.qt.io/qtforpython-6/licenses.html) identify additional notices for included components.

The app uses the upstream libraries without modification. They are separate files under `_internal` in the portable folder. Recipients can replace the Qt libraries, plugins, and Python bindings with ABI-compatible builds, or rebuild the application with their chosen versions using the instructions in the README. The release places no additional restrictions on modifying the libraries or debugging those modifications.

The portable build also includes CPython 3.12.10 and the PyInstaller 6.22.3 bootloader. Copies of the [CPython license](https://github.com/python/cpython/blob/v3.12.10/LICENSE) and [PyInstaller license and bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/COPYING.txt) are in the `licenses` directory.
