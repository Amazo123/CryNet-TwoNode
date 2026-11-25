# build-job failure diagnostics
run 45679335026, commit e5208c26ae8a720bc1467ea2a9178f97d7ff0125

## pio.log (last 200 lines)
```
Collecting platformio==6.2.0
  Downloading platformio-6.2.0-py3-none-any.whl.metadata (7.2 kB)
Requirement already satisfied: pip in /opt/hostedtoolcache/Python/3.11.18/x64/lib/python3.11/site-packages (from platformio==6.2.0) (26.3)
Collecting bottle==0.13.* (from platformio==6.2.0)
  Downloading bottle-0.13.4-py2.py3-none-any.whl.metadata (1.6 kB)
Collecting click!=8.3,<8.6,>=8.0.4 (from platformio==6.2.0)
  Downloading click-8.5.1-py3-none-any.whl.metadata (2.6 kB)
Collecting colorama (from platformio==6.2.0)
  Downloading colorama-0.4.6-py2.py3-none-any.whl.metadata (17 kB)
Collecting marshmallow<5,>=3 (from platformio==6.2.0)
  Downloading marshmallow-4.4.0-py3-none-any.whl.metadata (6.8 kB)
Collecting pyelftools<1,>=0.27 (from platformio==6.2.0)
  Downloading pyelftools-0.33-py3-none-any.whl.metadata (1.0 kB)
Collecting pyserial==3.5.* (from platformio==6.2.0)
  Downloading pyserial-3.5-py2.py3-none-any.whl.metadata (1.6 kB)
Collecting requests==2.* (from platformio==6.2.0)
  Downloading requests-2.34.2-py3-none-any.whl.metadata (4.8 kB)
Collecting semantic_version==2.10.* (from platformio==6.2.0)
  Downloading semantic_version-2.10.0-py2.py3-none-any.whl.metadata (9.7 kB)
Collecting tabulate==0.* (from platformio==6.2.0)
  Downloading tabulate-0.10.0-py3-none-any.whl.metadata (40 kB)
Collecting ajsonrpc==1.2.* (from platformio==6.2.0)
  Downloading ajsonrpc-1.2.0-py3-none-any.whl.metadata (6.9 kB)
Collecting starlette<2 (from platformio==6.2.0)
  Downloading starlette-1.10.0-py3-none-any.whl.metadata (6.6 kB)
Collecting uvicorn<1 (from platformio==6.2.0)
  Downloading uvicorn-0.54.0-py3-none-any.whl.metadata (6.6 kB)
Collecting wsproto==1.* (from platformio==6.2.0)
  Downloading wsproto-1.3.2-py3-none-any.whl.metadata (5.2 kB)
Collecting charset_normalizer<4,>=2 (from requests==2.*->platformio==6.2.0)
  Downloading charset_normalizer-3.5.3-cp311-cp311-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (43 kB)
Collecting idna<4,>=2.5 (from requests==2.*->platformio==6.2.0)
  Downloading idna-3.20-py3-none-any.whl.metadata (7.2 kB)
Collecting urllib3<3,>=1.26 (from requests==2.*->platformio==6.2.0)
  Downloading urllib3-2.8.0-py3-none-any.whl.metadata (7.4 kB)
Collecting certifi>=2023.5.7 (from requests==2.*->platformio==6.2.0)
  Downloading certifi-2026.11.20-py3-none-any.whl.metadata (2.5 kB)
Collecting anyio<5,>=4.0.0 (from starlette<2->platformio==6.2.0)
  Downloading anyio-4.16.0-py3-none-any.whl.metadata (4.7 kB)
Collecting typing-extensions>=4.10.0 (from starlette<2->platformio==6.2.0)
  Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
Collecting h11>=0.8 (from uvicorn<1->platformio==6.2.0)
  Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
Downloading platformio-6.2.0-py3-none-any.whl (418 kB)
Downloading ajsonrpc-1.2.0-py3-none-any.whl (22 kB)
Downloading bottle-0.13.4-py2.py3-none-any.whl (103 kB)
Downloading click-8.5.1-py3-none-any.whl (126 kB)
Downloading marshmallow-4.4.0-py3-none-any.whl (53 kB)
Downloading pyelftools-0.33-py3-none-any.whl (201 kB)
Downloading pyserial-3.5-py2.py3-none-any.whl (90 kB)
Downloading requests-2.34.2-py3-none-any.whl (73 kB)
Downloading charset_normalizer-3.5.3-cp311-cp311-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (263 kB)
Downloading idna-3.20-py3-none-any.whl (69 kB)
Downloading semantic_version-2.10.0-py2.py3-none-any.whl (15 kB)
Downloading starlette-1.10.0-py3-none-any.whl (80 kB)
Downloading anyio-4.16.0-py3-none-any.whl (134 kB)
Downloading tabulate-0.10.0-py3-none-any.whl (39 kB)
Downloading urllib3-2.8.0-py3-none-any.whl (135 kB)
Downloading uvicorn-0.54.0-py3-none-any.whl (87 kB)
Downloading wsproto-1.3.2-py3-none-any.whl (24 kB)
Downloading h11-0.16.0-py3-none-any.whl (37 kB)
Downloading certifi-2026.11.20-py3-none-any.whl (127 kB)
Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Downloading colorama-0.4.6-py2.py3-none-any.whl (25 kB)
Installing collected packages: pyserial, bottle, urllib3, typing-extensions, tabulate, semantic_version, pyelftools, marshmallow, idna, h11, colorama, click, charset_normalizer, certifi, ajsonrpc, wsproto, uvicorn, requests, anyio, starlette, platformio

Successfully installed ajsonrpc-1.2.0 anyio-4.16.0 bottle-0.13.4 certifi-2026.11.20 charset_normalizer-3.5.3 click-8.5.1 colorama-0.4.6 h11-0.16.0 idna-3.20 marshmallow-4.4.0 platformio-6.2.0 pyelftools-0.33 pyserial-3.5 requests-2.34.2 semantic_version-2.10.0 starlette-1.10.0 tabulate-0.10.0 typing-extensions-4.16.0 urllib3-2.8.0 uvicorn-0.54.0 wsproto-1.3.2
```
## arduino.log (last 200 lines)
```
Installing in /usr/local/bin
ARCH=64bit
OS=Linux
Using curl as download tool
Downloading https://downloads.arduino.cc/arduino-cli/arduino-cli_1.6.0_Linux_64bit.tar.gz
arduino-cli  Version: 1.6.0 Commit: 50a0e80da Date: 2026-11-10T15:30:50Z installed successfully in /usr/local/bin
Downloading index: library_index.tar.bz2 0 B / 4.53 MiB    0.00%Downloading index: library_index.tar.bz2 downloaded
Downloading index: package_index.tar.bz2 0 B / 112.61 KiB    0.00%Downloading index: package_index.tar.bz2 downloaded
Downloading index: package_esp32_index.json 0 B / 720.12 KiB    0.00%Downloading index: package_esp32_index.json downloaded
Downloading missing tool builtin:ctags@5.8-arduino12...
builtin:ctags@5.8-arduino12 0 B / 555.43 KiB    0.00%builtin:ctags@5.8-arduino12 downloaded
Installing builtin:ctags@5.8-arduino12...
Skipping tool configuration....
builtin:ctags@5.8-arduino12 installed
Downloading missing tool builtin:dfu-discovery@0.1.2...
builtin:dfu-discovery@0.1.2 0 B / 1.65 MiB    0.00%builtin:dfu-discovery@0.1.2 downloaded
Installing builtin:dfu-discovery@0.1.2...
Skipping tool configuration....
builtin:dfu-discovery@0.1.2 installed
Downloading missing tool builtin:mdns-discovery@1.1.0...
builtin:mdns-discovery@1.1.0 0 B / 3.07 MiB    0.00%builtin:mdns-discovery@1.1.0 downloaded
Installing builtin:mdns-discovery@1.1.0...
Skipping tool configuration....
builtin:mdns-discovery@1.1.0 installed
Downloading missing tool builtin:serial-discovery@1.5.2...
builtin:serial-discovery@1.5.2 0 B / 2.06 MiB    0.00%builtin:serial-discovery@1.5.2 downloaded
Installing builtin:serial-discovery@1.5.2...
Skipping tool configuration....
builtin:serial-discovery@1.5.2 installed
Downloading missing tool builtin:serial-monitor@0.15.0...
builtin:serial-monitor@0.15.0 0 B / 2.33 MiB    0.00%builtin:serial-monitor@0.15.0 downloaded
Installing builtin:serial-monitor@0.15.0...
Skipping tool configuration....
builtin:serial-monitor@0.15.0 installed
Downloading index: package_index.tar.bz2 0 B / 112.61 KiB    0.00%Downloading index: package_index.tar.bz2 downloaded
Downloading index: package_esp32_index.json 0 B / 720.12 KiB    0.00%Downloading index: package_esp32_index.json downloaded
Downloading packages...
esp32:esp-x32@2601 0 B / 318.78 MiB    0.00%esp32:esp-x32@2601 0 B / 318.78 MiB    0.00%esp32:esp-x32@2601 40.55 MiB / 318.78 MiB   12.72% 00m02sesp32:esp-x32@2601 100.19 MiB / 318.78 MiB   31.43% 00m01sesp32:esp-x32@2601 152.76 MiB / 318.78 MiB   47.92%esp32:esp-x32@2601 210.27 MiB / 318.78 MiB   65.96%esp32:esp-x32@2601 210.27 MiB / 318.78 MiB   65.96%esp32:esp-x32@2601 273.89 MiB / 318.78 MiB   85.92%esp32:esp-x32@2601 downloaded
esp32:xtensa-esp-elf-gdb@17.1_20260402 0 B / 40.68 MiB    0.00%esp32:xtensa-esp-elf-gdb@17.1_20260402 0 B / 40.68 MiB    0.00%esp32:xtensa-esp-elf-gdb@17.1_20260402 downloaded
esp32:esp-rv32@2601 0 B / 563.25 MiB    0.00%esp32:esp-rv32@2601 0 B / 563.25 MiB    0.00%esp32:esp-rv32@2601 67.23 MiB / 563.25 MiB   11.94% 00m02sesp32:esp-rv32@2601 100.00 MiB / 563.25 MiB   17.75% 00m02sesp32:esp-rv32@2601 164.12 MiB / 563.25 MiB   29.14% 00m01sesp32:esp-rv32@2601 225.58 MiB / 563.25 MiB   40.05% 00m01sesp32:esp-rv32@2601 225.58 MiB / 563.25 MiB   40.05% 00m01sesp32:esp-rv32@2601 287.85 MiB / 563.25 MiB   51.10% 00m01sesp32:esp-rv32@2601 313.44 MiB / 563.25 MiB   55.65% 00m01sesp32:esp-rv32@2601 361.88 MiB / 563.25 MiB   64.25%esp32:esp-rv32@2601 421.74 MiB / 563.25 MiB   74.88%esp32:esp-rv32@2601 421.74 MiB / 563.25 MiB   74.88%esp32:esp-rv32@2601 466.69 MiB / 563.25 MiB   82.86%esp32:esp-rv32@2601 529.10 MiB / 563.25 MiB   93.94%esp32:esp-rv32@2601 downloaded
esp32:riscv32-esp-elf-gdb@17.1_20260402 0 B / 41.05 MiB    0.00%esp32:riscv32-esp-elf-gdb@17.1_20260402 0 B / 41.05 MiB    0.00%esp32:riscv32-esp-elf-gdb@17.1_20260402 downloaded
esp32:openocd-esp32@v0.12.0-esp32-20260424 0 B / 2.51 MiB    0.00%esp32:openocd-esp32@v0.12.0-esp32-20260424 downloaded
esp32:esptool_py@5.3.1 0 B / 79.71 MiB    0.00%esp32:esptool_py@5.3.1 0 B / 79.71 MiB    0.00%esp32:esptool_py@5.3.1 39.94 MiB / 79.71 MiB   50.11%esp32:esptool_py@5.3.1 downloaded
esp32:mkspiffs@0.2.3 0 B / 49.46 KiB    0.00%esp32:mkspiffs@0.2.3 downloaded
esp32:mklittlefs@4.0.2-db0513a 0 B / 52.73 KiB    0.00%esp32:mklittlefs@4.0.2-db0513a downloaded
arduino:dfu-util@0.11.0-arduino5 0 B / 2.18 MiB    0.00%arduino:dfu-util@0.11.0-arduino5 downloaded
esp32:esp32-libs@3.3.12 0 B / 45.80 MiB    0.00%esp32:esp32-libs@3.3.12 0 B / 45.80 MiB    0.00%esp32:esp32-libs@3.3.12 downloaded
esp32:esp32c3-libs@3.3.12 0 B / 58.01 MiB    0.00%esp32:esp32c3-libs@3.3.12 0 B / 58.01 MiB    0.00%esp32:esp32c3-libs@3.3.12 downloaded
esp32:esp32c5-libs@3.3.12 0 B / 75.61 MiB    0.00%esp32:esp32c5-libs@3.3.12 0 B / 75.61 MiB    0.00%esp32:esp32c5-libs@3.3.12 downloaded
esp32:esp32c6-libs@3.3.12 0 B / 66.34 MiB    0.00%esp32:esp32c6-libs@3.3.12 0 B / 66.34 MiB    0.00%esp32:esp32c6-libs@3.3.12 downloaded
esp32:esp32h2-libs@3.3.12 0 B / 62.40 MiB    0.00%esp32:esp32h2-libs@3.3.12 0 B / 62.40 MiB    0.00%esp32:esp32h2-libs@3.3.12 downloaded
esp32:esp32p4-libs@3.3.12 0 B / 96.49 MiB    0.00%esp32:esp32p4-libs@3.3.12 0 B / 96.49 MiB    0.00%esp32:esp32p4-libs@3.3.12 56.60 MiB / 96.49 MiB   58.66%esp32:esp32p4-libs@3.3.12 downloaded
esp32:esp32p4_es-libs@3.3.12 0 B / 96.08 MiB    0.00%esp32:esp32p4_es-libs@3.3.12 0 B / 96.08 MiB    0.00%esp32:esp32p4_es-libs@3.3.12 56.81 MiB / 96.08 MiB   59.13%esp32:esp32p4_es-libs@3.3.12 83.57 MiB / 96.08 MiB   86.99%esp32:esp32p4_es-libs@3.3.12 downloaded
esp32:esp32s2-libs@3.3.12 0 B / 43.82 MiB    0.00%esp32:esp32s2-libs@3.3.12 downloaded
esp32:esp32s3-libs@3.3.12 0 B / 87.46 MiB    0.00%esp32:esp32s3-libs@3.3.12 0 B / 87.46 MiB    0.00%esp32:esp32s3-libs@3.3.12 downloaded
esp32:esp32@3.3.12 0 B / 48.74 MiB    0.00%esp32:esp32@3.3.12 0 B / 48.74 MiB    0.00%esp32:esp32@3.3.12 downloaded
Installing esp32:esp-x32@2601...
Skipping tool configuration....
esp32:esp-x32@2601 installed
Installing esp32:xtensa-esp-elf-gdb@17.1_20260402...
Skipping tool configuration....
esp32:xtensa-esp-elf-gdb@17.1_20260402 installed
Installing esp32:esp-rv32@2601...
Skipping tool configuration....
esp32:esp-rv32@2601 installed
Installing esp32:riscv32-esp-elf-gdb@17.1_20260402...
Skipping tool configuration....
esp32:riscv32-esp-elf-gdb@17.1_20260402 installed
Installing esp32:openocd-esp32@v0.12.0-esp32-20260424...
Skipping tool configuration....
esp32:openocd-esp32@v0.12.0-esp32-20260424 installed
Installing esp32:esptool_py@5.3.1...
Skipping tool configuration....
esp32:esptool_py@5.3.1 installed
Installing esp32:mkspiffs@0.2.3...
Skipping tool configuration....
esp32:mkspiffs@0.2.3 installed
Installing esp32:mklittlefs@4.0.2-db0513a...
Skipping tool configuration....
esp32:mklittlefs@4.0.2-db0513a installed
Installing arduino:dfu-util@0.11.0-arduino5...
Skipping tool configuration....
arduino:dfu-util@0.11.0-arduino5 installed
Installing esp32:esp32-libs@3.3.12...
Skipping tool configuration....
esp32:esp32-libs@3.3.12 installed
Installing esp32:esp32c3-libs@3.3.12...
Skipping tool configuration....
esp32:esp32c3-libs@3.3.12 installed
Installing esp32:esp32c5-libs@3.3.12...
Skipping tool configuration....
esp32:esp32c5-libs@3.3.12 installed
Installing esp32:esp32c6-libs@3.3.12...
Skipping tool configuration....
esp32:esp32c6-libs@3.3.12 installed
Installing esp32:esp32h2-libs@3.3.12...
Skipping tool configuration....
esp32:esp32h2-libs@3.3.12 installed
Installing esp32:esp32p4-libs@3.3.12...
Skipping tool configuration....
esp32:esp32p4-libs@3.3.12 installed
Installing esp32:esp32p4_es-libs@3.3.12...
Skipping tool configuration....
esp32:esp32p4_es-libs@3.3.12 installed
Installing esp32:esp32s2-libs@3.3.12...
Skipping tool configuration....
esp32:esp32s2-libs@3.3.12 installed
Installing esp32:esp32s3-libs@3.3.12...
Skipping tool configuration....
esp32:esp32s3-libs@3.3.12 installed
Installing platform esp32:esp32@3.3.12...
Skipping platform configuration....
Platform esp32:esp32@3.3.12 installed
```
## deps.log (last 200 lines)
```
Cloning into 'firmware/hub_infer/components/esp-tflite-micro'...
From https://github.com/espressif/esp-tflite-micro
 * branch            dd4085950a119d9e33a6de1d7be1fc7fe29e0cfc -> FETCH_HEAD
Note: switching to 'dd4085950a119d9e33a6de1d7be1fc7fe29e0cfc'.

You are in 'detached HEAD' state. You can look around, make experimental
changes and commit them, and you can discard any commits you make in this
state without impacting any branches by switching back to a branch.

If you want to create a new branch to retain commits you create, you may
do so (now or later) by using -c with the switch command. Example:

  git switch -c <new-branch-name>

Or undo this operation with:

  git switch -

Turn off this advice by setting config variable advice.detachedHead to false

HEAD is now at dd40859 Merge branch 'feat/disable-esp-nn-flag' into 'master'
Cloning into 'firmware/hub_infer/components/esp-nn'...
From https://github.com/espressif/esp-nn
 * branch            744d48deae6aa4a4d7b93b6a80f548d5298813a4 -> FETCH_HEAD
Note: switching to '744d48deae6aa4a4d7b93b6a80f548d5298813a4'.

You are in 'detached HEAD' state. You can look around, make experimental
changes and commit them, and you can discard any commits you make in this
state without impacting any branches by switching back to a branch.

If you want to create a new branch to retain commits you create, you may
do so (now or later) by using -c with the switch command. Example:

  git switch -c <new-branch-name>

Or undo this operation with:

  git switch -

Turn off this advice by setting config variable advice.detachedHead to false

HEAD is now at 744d48d Merge branch 'fix/fc_batch_no_vla' into 'master'
patch_deps: esp-nn registry dependency removed from idf_component.yml
patch_deps: esp-nn added to the port's component requirements
```
## rebuild.log (last 200 lines)
```
Compiling .pio/build/esp32s3/bootloader/efuse/esp32s3/esp_efuse_table.c.o
Compiling .pio/build/esp32s3/bootloader/efuse/esp32s3/esp_efuse_fields.c.o
Compiling .pio/build/esp32s3/bootloader/efuse/esp32s3/esp_efuse_rtc_calib.c.o
Compiling .pio/build/esp32s3/bootloader/efuse/esp32s3/esp_efuse_utility.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/bootloader_support/libbootloader_support.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/bootloader_support/libbootloader_support.a
Compiling .pio/build/esp32s3/bootloader/efuse/src/esp_efuse_api.c.o
Compiling .pio/build/esp32s3/bootloader/efuse/src/esp_efuse_fields.c.o
Compiling .pio/build/esp32s3/bootloader/efuse/src/esp_efuse_utility.c.o
Compiling .pio/build/esp32s3/bootloader/efuse/src/efuse_controller/keys/with_key_purposes/esp_efuse_api_key.c.o
Compiling .pio/build/esp32s3/bootloader/esp_bootloader_format/esp_bootloader_desc.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_bootloader_format/libesp_bootloader_format.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_bootloader_format/libesp_bootloader_format.a
Compiling .pio/build/esp32s3/bootloader/esp_common/src/esp_err_to_name.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_ana_conv/esp32s3/adc_periph.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/efuse/libefuse.a
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_common/libesp_common.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/efuse/libefuse.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_common/libesp_common.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_ana_conv/adc_hal_common.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_ana_conv/adc_oneshot_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_ana_conv/adc_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_ana_conv/temperature_sensor_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_ana_conv/esp32s3/temperature_sensor_periph.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_clock/esp32s3/clk_tree_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_dma/gdma_hal_top.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_ana_conv/libesp_hal_ana_conv.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_ana_conv/libesp_hal_ana_conv.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_dma/esp32s3/gdma_periph.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_dma/gdma_hal_ahb_v1.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpio/gpio_hal.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_clock/libesp_hal_clock.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_clock/libesp_hal_clock.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpio/rtc_io_hal.c.o
NOTE: /home/runner/.platformio/packages/framework-espidf/components/bt/host/nimble/Kconfig.in:1428: BT_NIMBLE_MESH_PROVISIONER: 'default 0' is not a valid bool value (only 'y' and 'n' are allowed). Value is treated as 'n'.
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpio/esp32s3/rtc_io_periph.c.o
NOTE: /home/runner/.platformio/packages/framework-espidf/components/fatfs/Kconfig:240: FATFS_PRINT_LLI: 'default 0' is not a valid bool value (only 'y' and 'n' are allowed). Value is treated as 'n'.
NOTE: /home/runner/.platformio/packages/framework-espidf/components/fatfs/Kconfig:245: FATFS_PRINT_FLOAT: 'default 0' is not a valid bool value (only 'y' and 'n' are allowed). Value is treated as 'n'.
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_dma/libesp_hal_dma.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpio/esp32s3/dedic_gpio_periph.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpio/sdm_hal.c.o
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_dma/libesp_hal_dma.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpio/esp32s3/sdm_periph.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpspi/esp32s3/spi_periph.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpspi/spi_hal.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_gpio/libesp_hal_gpio.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_gpio/libesp_hal_gpio.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpspi/spi_hal_iram.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpspi/spi_slave_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpspi/spi_slave_hal_iram.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_gpspi/spi_slave_hd_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_mspi/esp32s3/mspi_periph.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_mspi/libesp_hal_mspi.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_mspi/libesp_hal_mspi.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_pmu/esp32s3/rtc_cntl_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_pmu/brownout_hal.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_gpspi/libesp_hal_gpspi.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_gpspi/libesp_hal_gpspi.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_security/mpu_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_systimer/systimer_hal.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_pmu/libesp_hal_pmu.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_pmu/libesp_hal_pmu.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_timg/timer_hal.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_security/libesp_hal_security.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_security/libesp_hal_security.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_timg/esp32s3/timer_periph.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_systimer/libesp_hal_systimer.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_systimer/libesp_hal_systimer.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_uart/uart_hal.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_timg/libesp_hal_timg.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_uart/uart_hal_iram.c.o
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_timg/libesp_hal_timg.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_uart/esp32s3/uart_periph.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_uart/uhci_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_usb/usb_dwc_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_usb/esp32s3/usb_dwc_periph.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_uart/libesp_hal_uart.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_uart/libesp_hal_uart.a
Compiling .pio/build/esp32s3/bootloader/esp_hal_usb/usb_wrap_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_usb/usb_serial_jtag_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_wdt/esp32s3/mwdt_periph.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_wdt/rom_patch.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hal_wdt/xt_wdt_hal.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/cpu.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_usb/libesp_hal_usb.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_usb/libesp_hal_usb.a
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hal_wdt/libesp_hal_wdt.a
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/esp_cpu_intr.c.o
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hal_wdt/libesp_hal_wdt.a
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/esp_memory_utils.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/cpu_region_protect.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/rtc_clk.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/rtc_clk_init.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/rtc_init.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/rtc_sleep.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/rtc_time.c.o
Compiling .pio/build/esp32s3/bootloader/esp_hw_support/port/esp32s3/chip_info.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_sys.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_print.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_crc.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_serial_output.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_hw_support/libesp_hw_support.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_hw_support/libesp_hw_support.a
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_spiflash.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_efuse.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_gpio.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_longjmp.S.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_cache_esp32s2_esp32s3.c.o
Compiling .pio/build/esp32s3/bootloader/esp_rom/patches/esp_rom_cache_writeback_esp32s3.S.o
Compiling .pio/build/esp32s3/bootloader/esp_security/src/esp_crypto_lock.c.o
Compiling .pio/build/esp32s3/bootloader/esp_security/src/esp_crypto_periph_clk.c.o
Compiling .pio/build/esp32s3/bootloader/esp_security/src/esp32s3/esp_crypto_clk.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_rom/libesp_rom.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_rom/libesp_rom.a
Compiling .pio/build/esp32s3/bootloader/esp_system/esp_err.c.o
Compiling .pio/build/esp32s3/bootloader/hal/hal_utils.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_security/libesp_security.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_security/libesp_security.a
Compiling .pio/build/esp32s3/bootloader/hal/efuse_hal.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/esp_system/libesp_system.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/esp_system/libesp_system.a
Compiling .pio/build/esp32s3/bootloader/hal/esp32s3/efuse_hal.c.o
Compiling .pio/build/esp32s3/bootloader/hal/mmu_hal.c.o
Compiling .pio/build/esp32s3/bootloader/hal/cache_hal.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/noos/log_timestamp.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/log_timestamp_common.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/noos/log_lock.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/hal/libhal.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/hal/libhal.a
Compiling .pio/build/esp32s3/bootloader/log/src/buffer/log_buffers.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/noos/util.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/util.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/log_format_text.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/log_print.c.o
Compiling .pio/build/esp32s3/bootloader/log/src/log.c.o
Compiling .pio/build/esp32s3/bootloader/bootloader/subproject/components/micro-ecc/uECC_verify_antifault.c.o
Compiling .pio/build/esp32s3/bootloader/soc/lldesc.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/log/liblog.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/log/liblog.a
Compiling .pio/build/esp32s3/bootloader/soc/dport_access_common.c.o
Compiling .pio/build/esp32s3/bootloader/soc/esp32s3/interrupts.c.o
Compiling .pio/build/esp32s3/bootloader/soc/esp32s3/gpio_periph.c.o
Compiling .pio/build/esp32s3/bootloader/soc/esp32s3/mpi_periph.c.o
Compiling .pio/build/esp32s3/bootloader/soc/esp32s3/power_supply_periph.c.o
Compiling .pio/build/esp32s3/bootloader/spi_flash/spi_flash_wrap.c.o
Archiving .pio/build/esp32s3/bootloader/esp-idf/soc/libsoc.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/soc/libsoc.a
Preprocessing linker script .pio/build/esp32s3/bootloader/ld/bootloader.memory.ld
Preprocessing linker script .pio/build/esp32s3/bootloader/ld/bootloader.sections.ld
Generating partitions .pio/build/esp32s3/partitions.bin
Archiving .pio/build/esp32s3/bootloader/esp-idf/spi_flash/libspi_flash.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/spi_flash/libspi_flash.a
Archiving .pio/build/esp32s3/bootloader/esp-idf/micro-ecc/libmicro-ecc.a
Indexing .pio/build/esp32s3/bootloader/esp-idf/micro-ecc/libmicro-ecc.a
Linking .pio/build/esp32s3/bootloader.elf
Building .pio/build/esp32s3/bootloader.bin
esptool v5.4.0
Creating ESP32-S3 image...
Merged 2 ELF sections.
Successfully created ESP32-S3 image.
Linking .pio/build/esp32s3/firmware.elf
Retrieving maximum program size .pio/build/esp32s3/firmware.elf
Checking size .pio/build/esp32s3/firmware.elf
Advanced Memory Usage is available via "PlatformIO Home > Project Inspect"
RAM:   [=         ]  14.3% (used 46820 bytes from 327680 bytes)
Flash: [========  ]  77.2% (used 1619863 bytes from 2097152 bytes)
Building .pio/build/esp32s3/firmware.bin
esptool v5.4.0
Creating ESP32-S3 image...
Merged 3 ELF sections.
Successfully created ESP32-S3 image.
======================== [SUCCESS] Took 332.89 seconds ========================
Sketch uses 983161 bytes (75%) of program storage space. Maximum is 1310720 bytes.
Global variables use 166404 bytes (50%) of dynamic memory, leaving 161276 bytes for local variables. Maximum is 327680 bytes.
/home/runner/work/CryNet-TwoNode/CryNet-TwoNode/firmware/wearable/wearable_crynet/wearable_crynet.ino:66:10: fatal error: Adafruit_GFX.h: No such file or directory
   66 | #include <Adafruit_GFX.h>
      |          ^~~~~~~~~~~~~~~~
compilation terminated.

[92mUsed library[0m [92mVersion[0m [90mPath[0m
[93mWire[0m         3.3.12  [90m/home/runner/.arduino15/packages/esp32/hardware/esp32/3.3.12/libraries/Wire[0m

[92mUsed platform[0m [92mVersion[0m [90mPath[0m
[93mesp32:esp32[0m   3.3.12  [90m/home/runner/.arduino15/packages/esp32/hardware/esp32/3.3.12[0m
Error during build: exit status 1
== hub ==
building the hub with PlatformIO (this takes a few minutes) ...
  bootloader.bin
  partitions.bin
  firmware.bin

== node ==
building the node with arduino-cli ...
  bootloader.bin
  partitions.bin
  boot_app0.bin
  app.bin

== wearable ==
building the wearable with arduino-cli ...
```
## compare.log -- never created
## final_check.log -- never created
## the tree after the run
```
 M firmware/prebuilt/hub/bootloader.bin
 M firmware/prebuilt/hub/firmware.bin
 M firmware/prebuilt/node/app.bin
?? arduino.log
?? deps.log
?? diag.md
?? pio.log
?? rebuild.log
 firmware/prebuilt/hub/bootloader.bin | Bin 22560 -> 22560 bytes
 firmware/prebuilt/hub/firmware.bin   | Bin 1620272 -> 1620288 bytes
 firmware/prebuilt/node/app.bin       | Bin 983328 -> 983312 bytes
 3 files changed, 0 insertions(+), 0 deletions(-)
```
