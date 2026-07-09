#!/bin/bash

# gogrepoc AppImage Build Script (Miniconda Edition)
# This script uses Miniconda to create a completely portable Python environment
# for packaging gogrepoc into a standalone AppImage
# Supports cross-compilation for different architectures

set -e

# Configuration
APPIMAGE_NAME="gogrepoc"
BUILD_DIR="$(pwd)/build-miniconda"
APPDIR="$BUILD_DIR/AppDir"
SCRIPT_URL="https://raw.githubusercontent.com/Kalanyr/gogrepoc/refs/heads/main/gogrepoc.py"

# Get latest commit ID for versioning
get_version() {
    log_info "Getting latest commit version..."
    COMMIT_ID=$(curl -s https://api.github.com/repos/Kalanyr/gogrepoc/commits | grep '"sha"' | head -n 1 | cut -d '"' -f 4 | cut -c1-7)
    if [ -z "$COMMIT_ID" ]; then
        log_warning "Could not fetch commit ID, using 'unknown'"
        COMMIT_ID="unknown"
    else
        log_info "Latest commit: $COMMIT_ID"
    fi
    VERSION="$COMMIT_ID"
    
    # Set global AppImage filename
    APPIMAGE_FILENAME="${APPIMAGE_NAME}-${VERSION}-miniconda-${TARGET_ARCH}.AppImage"
    log_info "AppImage filename: $APPIMAGE_FILENAME"
}

# Extract version from gogrepoc.py script
get_script_version() {
    log_info "Extracting version from gogrepoc.py..."
    if [ -f "$APPDIR/usr/bin/gogrepoc.py" ]; then
        SCRIPT_VERSION=$(grep "^__version__" "$APPDIR/usr/bin/gogrepoc.py" | cut -d "'" -f 2)
        if [ -z "$SCRIPT_VERSION" ]; then
            log_warning "Could not extract script version, using '1.0.0'"
            SCRIPT_VERSION="1.0.0"
        else
            log_info "Script version: $SCRIPT_VERSION"
        fi
    else
        log_warning "gogrepoc.py not found, using version '1.0.0'"
        SCRIPT_VERSION="1.0.0"
    fi
}

# Miniconda configuration
MINICONDA_VERSION="latest"
PYTHON_VERSION="3.13"

# Allow override of target architecture
TARGET_ARCH="${TARGET_ARCH:-$(uname -m)}"
HOST_ARCH=$(uname -m)

# Map architecture names for Miniconda
case "$TARGET_ARCH" in
    x86_64|amd64)
        MINICONDA_ARCH="x86_64"
        TARGET_ARCH="x86_64"  # Normalize amd64 to x86_64
        ;;
    aarch64|arm64)
        MINICONDA_ARCH="aarch64"
        TARGET_ARCH="aarch64"  # Normalize arm64 to aarch64
        ;;
    *)
        echo "Unsupported target architecture: $TARGET_ARCH"
        echo "Supported: x86_64, aarch64"
        exit 1
        ;;
esac

MINICONDA_INSTALLER="Miniconda3-${MINICONDA_VERSION}-Linux-${MINICONDA_ARCH}.sh"
MINICONDA_URL="https://repo.anaconda.com/miniconda/${MINICONDA_INSTALLER}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Check basic dependencies
check_deps() {
    log_info "Checking dependencies..."
    
    for cmd in wget bash curl; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "$cmd not found"
            exit 1
        fi
    done
    
    # Get version info
    get_version
    
    # Warn about cross-compilation
    if [ "$TARGET_ARCH" != "$HOST_ARCH" ]; then
        log_warning "Cross-compiling from $HOST_ARCH to $TARGET_ARCH"
        log_warning "Testing will be skipped for cross-compiled AppImage"
    fi
    
    log_success "Dependencies OK"
}

# Download and install Miniconda
install_miniconda() {
    log_info "Setting up Miniconda Python environment..."
    
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
    cd "$BUILD_DIR"
    
    # Download Miniconda installer
    if [ ! -f "$MINICONDA_INSTALLER" ]; then
        log_info "Downloading Miniconda installer..."
        wget -q "$MINICONDA_URL" || {
            log_error "Failed to download Miniconda"
            exit 1
        }
    fi
    
    # Install Miniconda to a local directory
    log_info "Installing Miniconda..."
    bash "$MINICONDA_INSTALLER" -b -p "$BUILD_DIR/miniconda" || {
        log_error "Failed to install Miniconda"
        exit 1
    }
    
    # Initialize conda
    source "$BUILD_DIR/miniconda/etc/profile.d/conda.sh"
    conda config --set always_yes yes --set changeps1 no
    
    # Update conda
    log_info "Updating conda..."
    conda update -q conda
    
    log_success "Miniconda installed"
}

# Create conda environment with required packages
create_conda_env() {
    log_info "Creating conda environment with required packages..."
    
    source "$BUILD_DIR/miniconda/etc/profile.d/conda.sh"
    
    # Create environment with Python and required packages
    log_info "Installing packages..."
    conda create -n gogrepoc python=$PYTHON_VERSION \
        requests \
        html5lib \
        psutil \
        python-dateutil \
        pytz \
        -c conda-forge
    
    # Activate environment and install packages not available in conda
    conda activate gogrepoc
    
    # Install html2text via pip (not available in conda-forge)
    pip install html2text
    
    # Try to install optional packages
    log_info "Installing optional packages..."
    conda install pyqt -c conda-forge || log_warning "PyQt installation failed (optional)"
    
    conda deactivate
    log_success "Conda environment created"
}

# Build AppDir from conda environment
build_appdir() {
    log_info "Building AppDir from conda environment..."
    
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/lib"
    mkdir -p "$APPDIR/usr/share/applications"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
    
    # Copy the entire conda environment
    log_info "Copying conda environment..."
    cp -r "$BUILD_DIR/miniconda/envs/gogrepoc"/* "$APPDIR/usr/"
    
    # Ensure python3 is in the right place and executable
    if [ ! -f "$APPDIR/usr/bin/python3" ]; then
        ln -s python "$APPDIR/usr/bin/python3"
    fi
    chmod +x "$APPDIR/usr/bin/python"*
    
    # For cross-compilation, skip ldd analysis since it won't work
    if [ "$TARGET_ARCH" = "$HOST_ARCH" ]; then
        # Copy essential shared libraries (native compilation only)
        log_info "Copying shared libraries..."
        
        PYTHON_LIBS=$(ldd "$APPDIR/usr/bin/python" 2>/dev/null | grep -E "lib(python|ssl|crypto|ffi|z|bz2|lzma|sqlite3)" | awk '{print $3}' | sort | uniq || true)
        
        for lib in $PYTHON_LIBS; do
            if [ -f "$lib" ] && [ ! -f "$APPDIR/usr/lib/$(basename "$lib")" ]; then
                cp "$lib" "$APPDIR/usr/lib/" 2>/dev/null || true
                log_info "Copied $(basename "$lib")"
            fi
        done
    else
        log_info "Skipping ldd analysis for cross-compilation (libraries included in conda environment)"
    fi
    
    log_success "AppDir built from conda environment"
}

# Download gogrepoc script
install_gogrepoc() {
    log_info "Downloading gogrepoc script..."
    
    wget -O "$APPDIR/usr/bin/gogrepoc.py" "$SCRIPT_URL"
    chmod +x "$APPDIR/usr/bin/gogrepoc.py"
    
    log_success "gogrepoc script installed"
}

# Create AppRun script
create_apprun() {
    log_info "Creating AppRun script..."
    
    cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash

# Get the directory containing this AppImage
HERE="$(dirname "$(readlink -f "${0}")")"

# Set up conda environment
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:$LD_LIBRARY_PATH"
export PYTHONHOME="$HERE/usr"
export CONDA_PREFIX="$HERE/usr"
export CONDA_PYTHON_EXE="$HERE/usr/bin/python"

# Ensure we don't use system packages
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1

# Change to the directory where AppImage was called from
cd "${APPIMAGE_WORKDIR:-$PWD}"

# Execute gogrepoc with the bundled Python
exec "$HERE/usr/bin/python" "$HERE/usr/bin/gogrepoc.py" "$@"
EOF
    
    chmod +x "$APPDIR/AppRun"
    log_success "AppRun created"
}

# Create desktop integration files
create_desktop() {
    log_info "Creating desktop integration..."
    
    # Get the script version for display purposes
    get_script_version
    
    # Main desktop file
    cat > "$APPDIR/gogrepoc.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=GOGRepo (${VERSION})
Comment=GOG Repository Manager v${SCRIPT_VERSION} (Commit ${VERSION})
Exec=gogrepoc
Icon=gogrepoc
Categories=Game;
Terminal=true
StartupNotify=false
EOF
    
    # Icon (simple SVG)
    cat > "$APPDIR/gogrepoc.svg" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <rect width="256" height="256" fill="#43B02A" rx="32"/>
  <circle cx="128" cy="100" r="40" fill="#FFF"/>
  <rect x="88" y="140" width="80" height="16" fill="#FFF" rx="8"/>
  <rect x="104" y="170" width="48" height="12" fill="#FFF" rx="6"/>
      <text x="128" y="220" font-family="monospace" font-size="16" font-weight="bold" text-anchor="middle" fill="#FFF">${VERSION}</text>
</svg>
EOF
    
    # Copy files to standard locations
    cp "$APPDIR/gogrepoc.desktop" "$APPDIR/usr/share/applications/"
    cp "$APPDIR/gogrepoc.svg" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"
    
    log_success "Desktop integration created"
}

# Optimize the AppDir
optimize_appdir() {
    log_info "Optimizing AppDir..."
    
    # Remove conda package cache
    rm -rf "$APPDIR/usr/pkgs"
    
    # Remove conda environment metadata that we don't need
    rm -rf "$APPDIR/usr/conda-meta"
    
    # Remove bytecode files
    find "$APPDIR" -name "*.pyc" -delete
    find "$APPDIR" -name "*.pyo" -delete
    find "$APPDIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Remove unnecessary files
    rm -rf "$APPDIR/usr/lib/python"*/test
    rm -rf "$APPDIR/usr/lib/python"*/unittest
    rm -rf "$APPDIR/usr/lib/python"*/tkinter
    rm -rf "$APPDIR/usr/lib/python"*/turtle*
    rm -rf "$APPDIR/usr/lib/python"*/venv
    rm -rf "$APPDIR/usr/lib/python"*/ensurepip
    rm -rf "$APPDIR/usr/lib/python"*/distutils
    
    # Remove development headers and static libraries
    rm -rf "$APPDIR/usr/include"
    rm -rf "$APPDIR/usr/share/man"
    rm -rf "$APPDIR/usr/share/doc"
    find "$APPDIR" -name "*.a" -delete 2>/dev/null || true
    find "$APPDIR" -name "*.h" -delete 2>/dev/null || true
    
    # Remove large optional packages if present
    rm -rf "$APPDIR/usr/lib/python"*/site-packages/numpy/tests
    rm -rf "$APPDIR/usr/lib/python"*/site-packages/scipy/tests
    rm -rf "$APPDIR/usr/lib/python"*/site-packages/matplotlib/tests
    
    # Strip binaries
    find "$APPDIR" -type f -executable -exec strip --strip-unneeded {} + 2>/dev/null || true
    
    log_success "AppDir optimized"
}

# Download appimagetool and build AppImage
build_appimage() {
    log_info "Downloading appimagetool for target architecture..."
    
    cd "$BUILD_DIR"
    
    # Use host architecture for appimagetool (it runs on host but produces target arch AppImage)
    APPIMAGETOOL_NAME="appimagetool-${HOST_ARCH}"
    
    if [ ! -f "$APPIMAGETOOL_NAME" ]; then
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${HOST_ARCH}.AppImage"
        mv "appimagetool-${HOST_ARCH}.AppImage" "$APPIMAGETOOL_NAME"
        chmod +x "$APPIMAGETOOL_NAME"
    fi
    
    log_info "Building AppImage for $TARGET_ARCH..."
    
    # Build the AppImage with target architecture and version
    ARCH="$TARGET_ARCH" "./$APPIMAGETOOL_NAME" --no-appstream "$APPDIR" "$APPIMAGE_FILENAME"
    
    # Move to parent directory
    mv "$APPIMAGE_FILENAME" "../"
    
    local size=$(du -h "../$APPIMAGE_FILENAME" | cut -f1)
    log_success "AppImage built: $APPIMAGE_FILENAME (${size})"
}

# Test the AppImage
# Test the AppImage
test_appimage() {
    # Skip testing for cross-compiled AppImages
    if [ "$TARGET_ARCH" != "$HOST_ARCH" ]; then
        log_warning "Skipping tests for cross-compiled AppImage ($TARGET_ARCH)"
        return 0
    fi
    
    log_info "Testing the AppImage..."
    
    cd ..
    
    if [ -f "$APPIMAGE_FILENAME" ]; then
        log_info "Testing gogrepoc help..."
        "./$APPIMAGE_FILENAME" --help | head -5 > /dev/null || {
            log_error "Help test failed"
            return 1
        }
        
        log_success "AppImage tests passed!"
    else
        log_error "AppImage not found for testing: $APPIMAGE_FILENAME"
        log_info "Available files:"
        ls -la *.AppImage 2>/dev/null || echo "  No AppImage files found"
        return 1
    fi
}


# Cleanup
cleanup() {
    if [ "$1" != "keep" ]; then
        log_info "Cleaning up build directory..."
        rm -rf "$BUILD_DIR"
    fi
}

# Main function
main() {
    log_info "Starting gogrepoc AppImage build (Miniconda edition)..."
    
    check_deps
    install_miniconda
    create_conda_env
    build_appdir
    install_gogrepoc
    create_apprun
    create_desktop
    optimize_appdir
    build_appimage
    test_appimage
    
    if [ "$1" != "--keep-build" ]; then
        cleanup
    fi
    
    log_success "Build completed successfully!"
    log_info "Usage: ./$APPIMAGE_FILENAME [command] [options]"
    log_info "Example: ./$APPIMAGE_FILENAME login"
    
    # Show size comparison info
    local appimage="./$APPIMAGE_FILENAME"
    if [ -f "$appimage" ]; then
        local size_bytes=$(stat -c%s "$appimage")
        local size_mb=$((size_bytes / 1024 / 1024))
        log_info "Final AppImage size: ${size_mb}MB"
        log_info "Version: $VERSION (commit: $COMMIT_ID)"
        
        if [ "$TARGET_ARCH" != "$HOST_ARCH" ]; then
            log_warning "Cross-compiled AppImage created for $TARGET_ARCH"
            log_warning "Test on target architecture before distributing"
        fi
    fi
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        cat << EOF
gogrepoc AppImage Build Script (Miniconda Edition)

Creates a standalone AppImage for gogrepoc using Miniconda for a completely
portable Python environment that doesn't depend on system Python.

Usage: $0 [OPTIONS]
       TARGET_ARCH=aarch64 $0    # Cross-compile for ARM64

Options:
  --help, -h         Show this help
  --keep-build       Don't remove build directory after completion
  --clean            Remove build directory before starting

Environment Variables:
  TARGET_ARCH        Target architecture (x86_64, i686, aarch64, armv7l)
                     Defaults to current system architecture

Supported Architectures:
  x86_64             64-bit Intel/AMD (most desktops, servers)
  i686               32-bit Intel/AMD (older systems, some embedded)
  aarch64            64-bit ARM (modern ARM devices, Apple M1, newer NAS)
  armv7l             32-bit ARM (Raspberry Pi, older NAS, embedded)

Examples:
  $0                           # Build for current architecture
  TARGET_ARCH=aarch64 $0       # Cross-compile for ARM64 (modern ARM)
  TARGET_ARCH=armv7l $0        # Cross-compile for ARM32 (Raspberry Pi, older ARM)
  TARGET_ARCH=i686 $0          # Cross-compile for 32-bit Intel
  TARGET_ARCH=x86_64 $0        # Force 64-bit Intel

Build All Architectures:
  for arch in x86_64 i686 aarch64 armv7l; do
    TARGET_ARCH=\$arch $0
  done

Requirements:
  - wget
  - bash
  - curl

This script downloads Miniconda and creates a completely self-contained
Python environment with all required packages, then bundles it into a
portable AppImage. The resulting AppImage should work on any Linux
distribution without requiring any Python installation.

Cross-compilation notes:
  - Uses Miniconda's pre-compiled packages for target architecture
  - Skips ldd analysis when cross-compiling (not needed with conda)
  - Testing is skipped for cross-compiled AppImages
  - appimagetool runs on host but produces target architecture AppImage

Advantages over system Python approach:
  - No dependency on system Python version
  - Consistent across all Linux distributions  
  - Includes all required packages and dependencies
  - Completely portable and self-contained
  - Supports cross-compilation for different architectures
EOF
        exit 0
        ;;
    --clean)
        cleanup
        shift
        ;;
esac

# Run main function
main "$@"
