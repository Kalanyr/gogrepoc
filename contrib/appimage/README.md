# GOGrepoc AppImage Build Script

A comprehensive build system for creating portable [gogrepoc](https://github.com/Kalanyr/gogrepoc) AppImages using Miniconda for complete Python environment isolation.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture Support](#architecture-support)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Deployment Method Comparison](#deployment-method-comparison)
- [Windows & WSL2 Usage](#windows--wsl2-usage)
- [Build Process](#build-process)
- [Output](#output)
- [Cross-Compilation Notes](#cross-compilation-notes)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)
- [Support](#support)

## Overview

This script creates standalone, portable AppImages of gogrepoc that run on any modern Linux distribution without requiring Python installation or system dependencies. The resulting AppImage includes Python 3.11, all required packages, and gogrepoc itself in a single executable file.

## Features

- **Complete Portability**: No system Python or package dependencies required
- **Cross-Compilation**: Build for different 64-bit architectures from any 64-bit host
- **Miniconda Integration**: Uses conda-forge packages for reliable dependency management
- **Automated Updates**: Pulls latest gogrepoc version from GitHub automatically
- **Size Optimization**: Removes unnecessary components for minimal AppImage size
- **Desktop Integration**: Includes .desktop file and icon for system integration

## Architecture Support

### Supported Architectures (64-bit only)

| Architecture | Description | Common Devices |
|--------------|-------------|----------------|
| **x86_64** | 64-bit Intel/AMD | Most desktops, servers, modern NAS devices |
| **aarch64** | 64-bit ARM | Apple M1/M2, modern ARM devices, newer NAS |

### 32-bit Architecture Notice

**32-bit architectures (i686, armv7l) are intentionally not supported.** This decision is based on:

#### Technical Challenges
- **Python Version Conflict**: gogrepoc requires Python 3.8+, but the last 32-bit Miniconda only provides Python 3.7.1
- **No Modern Package Ecosystem**: conda-forge and most Linux distributions have discontinued 32-bit support
- **Complex Workarounds Required**: Would need custom Python compilation or Docker-based cross-compilation

#### Market Reality (2025)
- **<3% of active systems** use 32-bit architectures
- **Most NAS devices** transitioned to 64-bit by 2018
- **Linux distributions** are phasing out 32-bit support (Ubuntu since 2019)
- **Container ecosystems** focus exclusively on 64-bit
- **Y2038 Problem**: 32-bit Unix timestamp overflow approaching in 2038

#### Development Effort vs. Benefit
32-bit support **IS technically possible** but would require:
- 6-8 hours additional development time
- Docker-based cross-compilation setup
- Custom Python compilation from source
- Nested AppImage approach with extraction overhead
- Extensive testing on legacy hardware

This effort would serve approximately 2-3% of potential users running outdated hardware that may not handle modern workloads effectively.

#### Alternatives for 32-bit Users
If you absolutely need 32-bit support:
1. **Upgrade to 64-bit hardware** (recommended)
2. **Compile gogrepoc manually** from source on your 32-bit system
3. **Use Docker** with 32-bit base images to create custom builds
4. **File an issue** if you represent a significant user base with legitimate 32-bit requirements

## Requirements

### Host System
- **64-bit Linux system** (x86_64 or aarch64)
- **Minimum 2GB RAM** (4GB recommended for cross-compilation)
- **500MB free disk space** for build artifacts
- **Internet connection** for downloading dependencies

### Required Tools
- `bash` (4.0+)
- `wget` or `curl`
- `git` (optional, for development)

The script automatically downloads and manages:
- Miniconda installer
- appimagetool
- All Python dependencies

## Quick Start

```bash
# Download the build script
wget https://raw.githubusercontent.com/your-repo/gogrepoc-appimage-build.sh
chmod +x gogrepoc-appimage-build.sh

# Build for current architecture
./gogrepoc-appimage-build.sh

# Cross-compile for ARM64
TARGET_ARCH=aarch64 ./gogrepoc-appimage-build.sh

# Build all supported architectures
for arch in x86_64 aarch64; do
    TARGET_ARCH=$arch ./gogrepoc-appimage-build.sh
done
```

## Usage

### Basic Build
```bash
./gogrepoc-appimage-build.sh
```
Creates an AppImage for your current system architecture.

### Cross-Compilation
```bash
# For ARM64 devices
TARGET_ARCH=aarch64 ./gogrepoc-appimage-build.sh

# Force x86_64 build
TARGET_ARCH=x86_64 ./gogrepoc-appimage-build.sh
```

### Advanced Options
```bash
# Keep build directory for inspection
./gogrepoc-appimage-build.sh --keep-build

# Clean previous builds
./gogrepoc-appimage-build.sh --clean

# Show help
./gogrepoc-appimage-build.sh --help
```

## Deployment Method Comparison

### When to Choose Each Method

**AppImage (This Script)** - Linux distribution, end-user simplicity, or mixed environments
```bash
./gogrepoc-appimage-build.sh
./gogrepoc-*.AppImage --help
```

**Native Script** - Development, testing, or when you control the target environment
```bash
git clone https://github.com/Kalanyr/gogrepoc
cd gogrepoc
python3 gogrepoc.py --help
```

**PyInstaller** - Cross-platform deployment or when AppImage isn't suitable
```bash
pip install pyinstaller
pyinstaller --onefile gogrepoc.py
```

**Docker** - Server deployments, complex environments, or when 32-bit support is required
```bash
docker run --rm -v $(pwd):/data gogrepoc:latest --help
```

| Method | Best For | Platform Support | Dependencies | Size |
|--------|----------|------------------|--------------|------|
| **AppImage** | Linux end-users, NAS deployment | Linux 64-bit, WSL2+ | None | ~150MB |
| **Native Script** | Development, controlled environments | Any with Python | Python + packages | ~50KB |
| **PyInstaller** | Cross-platform distribution | Windows/Linux/macOS | None | ~50-150MB |
| **Docker** | Servers, 32-bit support needed | Any Docker host | Docker daemon | ~300MB+ |

## Windows & WSL2 Usage

The AppImage can run on Windows through WSL2 (Windows Subsystem for Linux). This provides a Linux environment where the AppImage runs natively.

### WSL2 Setup (if not installed)

```powershell
# In PowerShell (Administrator)
wsl --install
# Reboot when prompted
```

### Running the AppImage

```bash
# Install FUSE support in WSL2
sudo apt update && sudo apt install fuse libfuse2

# Download and run the AppImage
wget https://github.com/gogrepoc/releases/latest/download/gogrepoc-latest-x86_64.AppImage
chmod +x gogrepoc-*.AppImage
./gogrepoc-*.AppImage --help
```

### File Path Examples

```bash
# Access Windows drives from WSL2
./gogrepoc-*.AppImage download "/mnt/c/Users/YourName/GOGLibrary"
./gogrepoc-*.AppImage download "/mnt/d/Games/GOG"

# Note: Use quotes for paths with spaces
./gogrepoc-*.AppImage download "/mnt/c/Program Files/GOG Galaxy/Games"
```

**Note:** For comprehensive gogrepoc usage instructions, refer to the [main gogrepoc documentation](https://github.com/Kalanyr/gogrepoc). This build script only covers AppImage creation and deployment.

## Build Process

1. **Dependency Check**: Verifies required tools are available
2. **Version Detection**: Fetches latest gogrepoc commit ID for versioning
3. **Miniconda Setup**: Downloads and installs Miniconda for target architecture
4. **Environment Creation**: Creates isolated conda environment with Python 3.11
5. **Package Installation**: Installs gogrepoc dependencies via conda-forge
6. **AppDir Assembly**: Builds AppImage directory structure
7. **Script Integration**: Downloads and integrates latest gogrepoc.py
8. **Optimization**: Removes unnecessary files to minimize size
9. **AppImage Creation**: Packages everything into a single executable
10. **Testing**: Validates the resulting AppImage (native builds only)

## Output

### Generated Files
- `gogrepoc-{commit}-miniconda-{arch}.AppImage` - The main executable
- Build artifacts are cleaned up automatically (unless `--keep-build` is used)

### AppImage Features
- **Size**: Typically 150-200MB (optimized)
- **Startup Time**: ~2-3 seconds on modern hardware
- **Python Version**: 3.13.x (latest available)
- **Dependencies**: All bundled, no external requirements

## Cross-Compilation Notes

- **Host Tools**: appimagetool runs on host architecture but produces target architecture AppImages
- **Library Analysis**: Skipped for cross-compilation (conda provides all necessary libraries)
- **Testing**: Disabled for cross-compiled AppImages (requires target hardware)
- **Compatibility**: Uses conda-forge pre-compiled packages for reliable cross-platform builds

## Troubleshooting

### Common Issues

**"Architecture not supported" error**
- Ensure you're using a supported 64-bit architecture
- Check `uname -m` output matches x86_64 or aarch64

**Download failures**
- Verify internet connection
- Some networks block GitHub releases - try different network
- Use `wget` instead of `curl` if available

**Build failures**
- Check available disk space (minimum 500MB)
- Ensure sufficient RAM (2GB minimum)
- For cross-compilation issues, try native build first

**AppImage won't run**
- Verify FUSE is installed: `sudo apt install fuse libfuse2`
- Check AppImage permissions: `chmod +x *.AppImage`
- Some systems require: `sudo modprobe fuse`

### Debug Mode
```bash
# Enable verbose output
set -x
./gogrepoc-appimage-build.sh
```

### File Locations
- **Build Directory**: `./build-miniconda/` (temporary)
- **Final AppImage**: Current directory
- **Logs**: Console output only

## Development

### Customizing the Build

**Python Version**
```bash
# Edit the script to change PYTHON_VERSION
PYTHON_VERSION="3.12"  # Change as needed
```

**Additional Packages**
Add packages to the conda create command:
```bash
conda create -n gogrepoc python=$PYTHON_VERSION \
    requests html5lib psutil python-dateutil pytz \
    your-additional-package \
    -c conda-forge
```

**Size Optimization**
The script already removes common unnecessary files. For further optimization:
- Remove additional test directories
- Strip more aggressively
- Remove unused shared libraries

### Contributing

1. Test changes on both supported architectures
2. Verify AppImages work on different distributions
3. Update documentation for any new features
4. Maintain compatibility with existing command-line interface

## License

This build script is provided under the same license as gogrepoc. The resulting AppImages contain:
- **gogrepoc**: Original license applies
- **Python**: PSF License
- **conda-forge packages**: Various open-source licenses
- **Miniconda**: Anaconda Terms of Service for distribution

## Support

### Issues with the Build Script
- Check this README and troubleshooting section
- Verify your system meets requirements
- Try a clean build: `./gogrepoc-appimage-build.sh --clean`

### Issues with gogrepoc Functionality  
- Report to the [gogrepoc repository](https://github.com/Kalanyr/gogrepoc)
- The AppImage version should behave identically to source installation

### 32-bit Support Requests
While 32-bit support is technically possible, it requires significant development effort for a very small user base. Consider:
- Hardware upgrade to 64-bit
- Manual compilation on 32-bit system
- Docker-based custom builds

If you represent a significant user base with legitimate 32-bit requirements, please file an issue with:
- Use case description
- Hardware constraints preventing 64-bit upgrade
- Number of affected users
- Willingness to contribute to development/testing

---

**Note**: This build system creates AppImages that are completely independent of system Python installations and should run on any Linux distribution with kernel 2.6+ and basic libraries.
