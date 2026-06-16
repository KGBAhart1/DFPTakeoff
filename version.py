APP_NAME     = "DFP TakeoffPro"
APP_VERSION  = "1.0.6"          # <-- bump this for every release
APP_COMPANY  = "Defense Fire Protection"

# Auto-update flow:
#   1. Bump APP_VERSION here
#   2. Update version.json in repo root (version + download_url + notes)
#   3. Rebuild exe:        python -m PyInstaller DFP_TakeoffPro.spec
#   4. Build installer:    "C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss
#                          (also bump MyAppVersion in installer.iss to match)
#   5. Commit & push to GitHub (main branch)
#   6. Create GitHub Release — tag must NOT have a "v" prefix (e.g. "1.0.6" not "v1.0.6")
#      Upload installer_output\DFP_TakeoffPro_Setup_X.X.X.exe as the release asset
#
# Repo: https://github.com/KGBAhart1/DFPTakeoff  (public — required for raw URL access)
# version.json is fetched on every app launch to check for updates.
# download_url in version.json must match the exact GitHub release tag and filename.
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/KGBAhart1/DFPTakeoff/main/version.json"
