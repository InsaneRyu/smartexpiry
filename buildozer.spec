[app]
title = SmartExpiry Pro
package.name = smartexpiry
package.domain = org.smartexpiry
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,ttf,db
version = 0.1
android.numeric_version = 1

# Se elimina libzbar y el fix rígido de python3
requirements = python3,kivy==2.3.0,pillow,certifi

p4a.branch = v2024.01.21
services = alertas:service.py:foreground
orientation = portrait, landscape
fullscreen = 0

# Android SDK / NDK / API Setup
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

# Permisos requeridos para API 33
android.permissions = INTERNET,CAMERA,FOREGROUND_SERVICE,POST_NOTIFICATIONS

[buildozer]
log_level = 2
warn_on_root = 1
