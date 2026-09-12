#!/usr/bin/env bash
set -euo pipefail
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
adb shell am instrument -w -r com.johndsdev.androidllm.test/androidx.test.runner.AndroidJUnitRunner | tee emulator-inference-test.txt
grep -qE 'OK \([0-9]+ tests?\)' emulator-inference-test.txt
adb logcat -d > emulator-inference-logcat.txt
! grep -qE 'FATAL EXCEPTION|Fatal signal|UnsatisfiedLinkError' emulator-inference-logcat.txt
grep -q 'AndroidLLM persistent CPU pool:' emulator-inference-logcat.txt
