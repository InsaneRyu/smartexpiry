[app]
title = SmartExpiry Pro
package.name = smartexpiry
package.domain = org.smartexpiry
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 0.1
android.numeric_version = 1
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,pillow,libzbar,pyzbar
p4a.branch = v2024.01.21
orientation = portrait, landscape
fullscreen = 0

# Android
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.permissions = INTERNET,CAMERA

[buildozer]
log_level = 2
warn_on_root = 1
