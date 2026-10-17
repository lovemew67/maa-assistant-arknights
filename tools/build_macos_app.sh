#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OUTPUT_DIR="${REPO_ROOT}/dist"
APP_NAME="maa-zzh.app"
BUILD_TYPE="Release"
INSTALL_TO_APPLICATIONS=false
CLEAN=false

usage() {
    cat <<EOF
MAA macOS App Builder (Apple Silicon / M1-M4 Mac)

Usage: $(basename "$0") [options]

Options:
  --app-name <name>      Target App name (default: maa-zzh.app)
  --install              Automatically install to /Applications/<app-name>
  --clean                Clean prior build artifacts before building
  --output-dir <path>    Destination directory for App (default: ./dist)
  --build-type <type>    Build configuration: Release or Debug (default: Release)
  -h, --help             Show this help message

Prerequisites:
  - Xcode.app (installed from Mac App Store)
  - Homebrew packages: cmake, ninja
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --app-name)
            APP_NAME="$2"
            [[ "${APP_NAME}" != *".app" ]] && APP_NAME="${APP_NAME}.app"
            shift 2
            ;;
        --install)
            INSTALL_TO_APPLICATIONS=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --build-type)
            BUILD_TYPE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

cd "${REPO_ROOT}"

# 1. Check prerequisites
echo "==> [1/6] Checking build prerequisites..."

if ! command -v xcodebuild >/dev/null 2>&1; then
    echo "Error: xcodebuild not found. Please install Xcode from Mac App Store." >&2
    exit 1
fi

DEVELOPER_DIR="$(xcode-select -p 2>/dev/null || echo "")"
if [[ "${DEVELOPER_DIR}" == *"CommandLineTools"* ]]; then
    echo "Error: Active developer path is CommandLineTools: ${DEVELOPER_DIR}" >&2
    echo "Xcode.app is required to build MAA.app. Please run:" >&2
    echo "  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
    exit 1
fi

MISSING_DEPS=()
for tool in cmake ninja python3; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        MISSING_DEPS+=("${tool}")
    fi
done

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo "Error: Missing required tools: ${MISSING_DEPS[*]}" >&2
    echo "Please install them via Homebrew:" >&2
    echo "  brew install ${MISSING_DEPS[*]}" >&2
    exit 1
fi

TAG="$(git describe --tags --match "v*" HEAD 2>/dev/null || echo "v0.0.1-$(git rev-parse --short HEAD)")"
ARCH="$(uname -m)"

echo "Host Architecture: ${ARCH}"
echo "Release Tag:       ${TAG}"
echo "Build Type:        ${BUILD_TYPE}"
echo "Output Directory:  ${OUTPUT_DIR}"

# 2. Check and initialize submodules
echo "==> [2/6] Updating submodules..."
git submodule update --init --depth 1 src/MaaUtils src/MaaMacGui

if [[ "${CLEAN}" == "true" ]]; then
    echo "==> Cleaning prior build files..."
    rm -rf "build-${ARCH}" "install-${ARCH}" build src/MaaMacGui/MAA.xcarchive src/MaaMacGui/MAA.app
fi

mkdir -p "${OUTPUT_DIR}"

# 3. Download dependencies for macOS
echo "==> [3/6] Downloading MaaDeps for ${ARCH}-osx..."
python3 tools/maadeps-download.py --cache-asset "${ARCH}-osx"

# 4. Build MaaCore
echo "==> [4/6] Configuring and building MaaCore (${ARCH})..."
cmake -B "build-${ARCH}" \
    -GNinja \
    -DCMAKE_BUILD_TYPE="${BUILD_TYPE}" \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DCMAKE_OSX_ARCHITECTURES="${ARCH}" \
    -DMAA_HASH_VERSION="${TAG}"

cmake --build "build-${ARCH}" --parallel "$(sysctl -n hw.ncpu)"
cmake --install "build-${ARCH}" --prefix "install-${ARCH}"

# 5. Create XCFrameworks
echo "==> [5/6] Creating XCFrameworks in build/..."
rm -rf build/*.xcframework
mkdir -p build

xcodebuild -create-xcframework -library "install-${ARCH}/libMaaCore.dylib" -headers include -output build/MaaCore.xcframework
xcodebuild -create-xcframework -library "install-${ARCH}/libMaaUtils.dylib" -output build/MaaUtils.xcframework
xcodebuild -create-xcframework -library "install-${ARCH}/libfastdeploy_ppocr.dylib" -output build/fastdeploy_ppocr.xcframework

ONNX_LIB="$(ls install-${ARCH}/libonnxruntime*.dylib | head -n 1)"
xcodebuild -create-xcframework -library "${ONNX_LIB}" -output build/ONNXRuntime.xcframework

OPENCV_LIB="$(ls install-${ARCH}/libopencv*.dylib | head -n 1)"
xcodebuild -create-xcframework -library "${OPENCV_LIB}" -output build/OpenCV.xcframework

# 6. Build MaaMacGui
echo "==> [6/6] Building MaaMacGui via xcodebuild..."
echo "MARKETING_VERSION = ${TAG}" > src/MaaMacGui/Version.xcconfig
echo "CURRENT_PROJECT_VERSION = 1" >> src/MaaMacGui/Version.xcconfig

pushd src/MaaMacGui > /dev/null

if [[ -f "${REPO_ROOT}/patches/MaaMacGui.diff" ]]; then
    echo "==> Applying patch from patches/MaaMacGui.diff..."
    git apply "${REPO_ROOT}/patches/MaaMacGui.diff" 2>/dev/null || true
fi

rm -rf DerivedData MAA.xcarchive MAA.app
xcodebuild -skipMacroValidation CODE_SIGNING_ALLOWED=NO ARCHS="${ARCH}" ONLY_ACTIVE_ARCH=YES -derivedDataPath DerivedData -scheme MAA archive -archivePath MAA.xcarchive

echo "==> Extracting MAA.app from archive..."
cp -R MAA.xcarchive/Products/Applications/MAA.app .

echo "==> Applying Ad-Hoc code signature to MAA.app..."
codesign --force --deep --sign - MAA.app

TARGET_APP_PATH="${OUTPUT_DIR}/${APP_NAME}"
rm -rf "${TARGET_APP_PATH}"
cp -R MAA.app "${TARGET_APP_PATH}"

# Customize Bundle Name and Display Name
DISPLAY_NAME="${APP_NAME%.app}"
echo "==> Configuring app display name to '${DISPLAY_NAME}'..."
/usr/libexec/PlistBuddy -c "Set :CFBundleName ${DISPLAY_NAME}" "${TARGET_APP_PATH}/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleName string ${DISPLAY_NAME}" "${TARGET_APP_PATH}/Contents/Info.plist" 2>/dev/null || true

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName ${DISPLAY_NAME}" "${TARGET_APP_PATH}/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${DISPLAY_NAME}" "${TARGET_APP_PATH}/Contents/Info.plist" 2>/dev/null || true

echo "==> Applying Ad-Hoc code signature to ${APP_NAME}..."
codesign --force --deep --sign - "${TARGET_APP_PATH}"

# Clean up build artifacts inside submodule to keep git clean
rm -rf MAA.app MAA.xcarchive DerivedData
git checkout . 2>/dev/null || true

popd > /dev/null

if [[ "${INSTALL_TO_APPLICATIONS}" == "true" ]]; then
    echo "==> Installing ${APP_NAME} to /Applications..."
    rm -rf "/Applications/${APP_NAME}"
    cp -R "${TARGET_APP_PATH}" "/Applications/${APP_NAME}"
    xattr -cr "/Applications/${APP_NAME}" || true
    echo "==> Successfully installed to /Applications/${APP_NAME}"
fi

echo "=================================================="
echo "Build completed successfully!"
echo "Target App:  ${TARGET_APP_PATH}"
if [[ "${INSTALL_TO_APPLICATIONS}" == "true" ]]; then
    echo "Installed:   /Applications/${APP_NAME} (Ready to launch!)"
else
    echo "Tip: Run with --install to place directly in /Applications/${APP_NAME}"
fi
echo "=================================================="
