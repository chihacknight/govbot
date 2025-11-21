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
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"
  case "${os}-${arch}" in
    "Darwin-x86_64")
      ASSET="govbot-macos-x86_64"
      ;;
    "Darwin-arm64")
      ASSET="govbot-macos-arm64"
      ;;
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
  local url temp_file
  url="https://github.com/${REPO}/releases/download/${LATEST_TAG}/${ASSET}"
  temp_file="$(mktemp)"
  
  if [[ "${ASSET}" == *.exe ]]; then
    if [[ -f "${INSTALL_PATH}.exe" ]]; then
      log "Overwriting existing binary at ${INSTALL_PATH}.exe"
    fi
    log "Downloading ${url}"
    curl -fsSL "${url}" -o "${temp_file}"
    mv -f "${temp_file}" "${INSTALL_PATH}.exe"
    chmod +x "${INSTALL_PATH}.exe"
    INSTALLED_PATH="${INSTALL_PATH}.exe"
  else
    if [[ -f "${INSTALL_PATH}" ]]; then
      log "Overwriting existing binary at ${INSTALL_PATH}"
    fi
    log "Downloading ${url}"
    curl -fsSL "${url}" -o "${temp_file}"
    mv -f "${temp_file}" "${INSTALL_PATH}"
    chmod +x "${INSTALL_PATH}"
    INSTALLED_PATH="${INSTALL_PATH}"
  fi
}

ensure_path_entry() {
  if [[ ":${PATH}:" == *":${INSTALL_DIR}:"* ]]; then
    log "PATH already contains ${INSTALL_DIR}"
    return
  fi

  local profile added=false
  for profile in "${PROFILE_CANDIDATES[@]}"; do
    if [[ -f "${profile}" ]]; then
      if grep -Fq "${INSTALL_DIR}" "${profile}"; then
        log "${profile} already exports ${INSTALL_DIR}"
        added=true
        break
      else
        printf '\n# Added by govbot installer\nexport PATH="%s:$PATH"\n' "${INSTALL_DIR}" >> "${profile}"
        log "Appended PATH update to ${profile}"
        added=true
        break
      fi
    fi
  done

  if [[ "${added}" = false ]]; then
    profile="${PROFILE_CANDIDATES[-1]}"
    printf '#!/usr/bin/env bash\n' > "${profile}"
    printf '# Added by govbot installer\nexport PATH="%s:$PATH"\n' "${INSTALL_DIR}" >> "${profile}"
    log "Created ${profile} with PATH update"
  fi

  log "Reload your shell or run: source <profile>"
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

If this is your first install, restart your shell or run:
  source <your-shell-profile>

Run 'govbot --help' to get started.
EOF
}

main "$@"

