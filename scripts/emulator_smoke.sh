#!/usr/bin/env bash
set -euo pipefail
trap 'adb logcat -d > emulator-final-logcat.txt' EXIT
adb shell getprop ro.product.cpu.abilist | tee emulator-abis.txt
adb install -r AndroidLLM.apk | tee emulator-install.txt
adb logcat -c
adb shell am start -W -n com.johndsdev.androidllm/.MainActivity | tee emulator-launch.txt
for attempt in $(seq 1 30); do
  adb logcat -d > emulator-logcat.txt
  if grep -q 'Native library loaded! System info' emulator-logcat.txt; then break; fi
  sleep 1
done
grep -q 'Native library loaded! System info' emulator-logcat.txt
! grep -qE 'FATAL EXCEPTION|Fatal signal|UnsatisfiedLinkError' emulator-logcat.txt
adb shell pidof com.johndsdev.androidllm
adb shell uiautomator dump /sdcard/window.xml
adb pull /sdcard/window.xml emulator-window.xml
adb exec-out screencap -p > emulator-screen.png

adb install -r AndroidLLM-test.apk
# Exercise UI using the exact ARM delivery APK first.
adb shell am instrument -w -r -e class com.johndsdev.androidllm.SearchAndScrollTest com.johndsdev.androidllm.test/androidx.test.runner.AndroidJUnitRunner | tee emulator-ui-test.txt
grep -q 'OK (3 tests)' emulator-ui-test.txt
# Google's ARM translator lacks LSE atomics. Test native inference with an x86
# sibling built from identical binding/core sources, not translated ARM code.
adb install -r AndroidLLM-emulator.apk
adb logcat -c
adb shell am instrument -w -r -e class com.johndsdev.androidllm.InferenceSmokeTest com.johndsdev.androidllm.test/androidx.test.runner.AndroidJUnitRunner | tee emulator-inference-test.txt
grep -q 'OK (1 test)' emulator-inference-test.txt
adb logcat -d > emulator-inference-logcat.txt
! grep -qE 'FATAL EXCEPTION|Fatal signal|UnsatisfiedLinkError' emulator-inference-logcat.txt
grep -q 'AndroidLLM persistent CPU pool:' emulator-inference-logcat.txt
