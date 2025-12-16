#!/usr/bin/env bash
set -euo pipefail

REPO="windy-civi/toolkit"
BINARY_NAME="govbot"
INSTALL_DIR="${HOME}/.govbot/bin"
INSTALL_PATH="${INSTALL_DIR}/${BINARY_NAME}"
PROFILE_CANDIDATES=(
  "${HOME}/.zshrc"
  "${HOME}/.zprofile"
  "${HOME}/.bash_profile"
  "${HOME}/.bashrc"
  "${HOME}/.profile"
)

log() {
  printf '[govbot install] %s\n' "$*" >&2
}

ensure_curl() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to install govbot" >&2
    exit 1
  fi
}

detect_platform() {
  local os arch native_arch
  os="$(uname -s)"
  arch="$(uname -m)"

  # On macOS, detect native architecture (not Rosetta)
  if [[ "${os}" == "Darwin" ]]; then
    # Check if running under Rosetta on Apple Silicon
    if [[ "${arch}" == "x86_64" ]]; then
      # Check if native ARM64 is available
      if sysctl -n hw.optional.arm64 2>/dev/null | grep -q "1"; then
        native_arch="arm64"
        log "Detected native ARM64 architecture (running under Rosetta)"
      else
        native_arch="x86_64"
      fi
    else
      native_arch="${arch}"
    fi

    case "${native_arch}" in
      "arm64")
        ASSET="govbot-macos-arm64"
        ;;
      "x86_64")
        ASSET="govbot-macos-x86_64"
        ;;
      *)
        echo "Unsupported macOS architecture: ${native_arch}" >&2
        exit 1
        ;;
    esac
  else
    case "${os}-${arch}" in
      "Linux-x86_64"|"Linux-amd64")
        ASSET="govbot-linux-x86_64"
        ;;
      "MINGW64_NT-10.0-64"|"MSYS_NT-10.0-64")
        ASSET="govbot-windows-x86_64.exe"
        ;;
      *)
        echo "Unsupported platform: ${os}-${arch}" >&2
        exit 1
        ;;
    esac
  fi
}

latest_nightly_tag() {
  # Verify the nightly release exists
  if ! curl -fsSL "https://api.github.com/repos/${REPO}/releases/tags/nightly" >/dev/null 2>&1; then
    echo "Unable to find nightly release" >&2
    exit 1
  fi
  LATEST_TAG="nightly"
}

download_binary() {
  mkdir -p "${INSTALL_DIR}"
  local url temp_file fallback_asset

  # Determine fallback asset for macOS (if x86_64 requested but doesn't exist, try arm64)
  if [[ "${ASSET}" == "govbot-macos-x86_64" ]]; then
    fallback_asset="govbot-macos-arm64"
  elif [[ "${ASSET}" == "govbot-macos-arm64" ]]; then
    fallback_asset="govbot-macos-x86_64"
  else
    fallback_asset=""
  fi

  url="https://github.com/${REPO}/releases/download/${LATEST_TAG}/${ASSET}"
  temp_file="$(mktemp)"

  # Try to download the primary asset
  log "Downloading ${url}"
  if ! curl -fsSL "${url}" -o "${temp_file}" 2>/dev/null; then
    # If download failed and we have a fallback, try that
    if [[ -n "${fallback_asset}" ]]; then
      log "Primary asset ${ASSET} not found, trying fallback ${fallback_asset}"
      ASSET="${fallback_asset}"
      url="https://github.com/${REPO}/releases/download/${LATEST_TAG}/${ASSET}"
      if ! curl -fsSL "${url}" -o "${temp_file}" 2>/dev/null; then
        echo "Failed to download ${ASSET} from ${url}" >&2
        exit 1
      fi
    else
      echo "Failed to download ${ASSET} from ${url}" >&2
      exit 1
    fi
  fi

  if [[ "${ASSET}" == *.exe ]]; then
    if [[ -f "${INSTALL_PATH}.exe" ]]; then
      log "Overwriting existing binary at ${INSTALL_PATH}.exe"
    fi
    mv -f "${temp_file}" "${INSTALL_PATH}.exe"
    chmod +x "${INSTALL_PATH}.exe"
    INSTALLED_PATH="${INSTALL_PATH}.exe"
  else
    if [[ -f "${INSTALL_PATH}" ]]; then
      log "Overwriting existing binary at ${INSTALL_PATH}"
    fi
    mv -f "${temp_file}" "${INSTALL_PATH}"
    chmod +x "${INSTALL_PATH}"
    INSTALLED_PATH="${INSTALL_PATH}"
  fi
}

ensure_path_entry() {
  local already_in_path=false
  if [[ ":${PATH}:" == *":${INSTALL_DIR}:"* ]]; then
    log "PATH already contains ${INSTALL_DIR}"
    already_in_path=true
  fi

  local profile added=false sourced_profile=""
  for profile in "${PROFILE_CANDIDATES[@]}"; do
    if [[ -f "${profile}" ]]; then
      if grep -Fq "${INSTALL_DIR}" "${profile}"; then
        log "${profile} already exports ${INSTALL_DIR}"
        added=true
        sourced_profile="${profile}"
        break
      else
        printf '\n# Added by govbot installer\nexport PATH="%s:$PATH"\n' "${INSTALL_DIR}" >> "${profile}"
        log "Appended PATH update to ${profile}"
        added=true
        sourced_profile="${profile}"
        break
      fi
    fi
  done

  if [[ "${added}" = false ]]; then
    profile="${PROFILE_CANDIDATES[-1]}"
    printf '#!/usr/bin/env bash\n' > "${profile}"
    printf '# Added by govbot installer\nexport PATH="%s:$PATH"\n' "${INSTALL_DIR}" >> "${profile}"
    log "Created ${profile} with PATH update"
    sourced_profile="${profile}"
  fi

  # Auto-source the profile if PATH doesn't already contain the install dir
  if [[ "${already_in_path}" = false ]] && [[ -n "${sourced_profile}" ]]; then
    log "Sourcing ${sourced_profile} to update current session"
    # shellcheck disable=SC1090
    # Suppress errors from oh-my-zsh or other shell frameworks that might not be fully configured
    source "${sourced_profile}" 2>/dev/null || true
  fi
}

main() {
  ensure_curl
  detect_platform
  latest_nightly_tag
  download_binary
  ensure_path_entry

  cat <<EOF

govbot installed at: ${INSTALLED_PATH}
Latest nightly tag: ${LATEST_TAG}

Your shell profile has been updated and sourced.
Run 'govbot' to get started!
EOF
}

main "$@"

