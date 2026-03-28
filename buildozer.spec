[app]
title = AndroidReader
package.name = androidreader
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy
orientation = landscape
fullscreen = 0

[buildozer]
log_level = 2

[app:android]
android.api = 24
android.sdk_path = D:/android-sdk
android.ndk_path = D:/android-ndk-r16-beta1
android.buildtools = 21.1.2
android.use_aapt2 = True
android.arch = armeabi-v7a
android.ndk_api = 19
android.allow_backup = True