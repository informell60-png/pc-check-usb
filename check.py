import base64
from datetime import datetime
import hashlib
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
MIB = 1024**2


def inventory():
    commands = [
        ("Процессор", "Win32_Processor", "Name,NumberOfCores,NumberOfLogicalProcessors"),
        ("Видеокарты", "Win32_VideoController", "Name,DriverVersion,VideoProcessor"),
        ("Память по планкам", "Win32_PhysicalMemory", "Manufacturer,PartNumber,@{n='GiB';e={$_.Capacity/1GB}},ConfiguredClockSpeed"),
        ("Материнская плата", "Win32_BaseBoard", "Manufacturer,Product"),
        ("Накопители", "Win32_DiskDrive", "Model,@{n='GB';e={[math]::Round($_.Size/1e9,1)}}"),
        ("Windows", "Win32_OperatingSystem", "Caption,Version,BuildNumber")]
    script = ["[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)"]
    for title, cls, fields in commands:
        script.append(f"'{title}'; try {{ Get-CimInstance {cls} -ErrorAction Stop | "
                      f"Select-Object {fields} | Format-List | Out-String -Width 180 "
                      "| ForEach-Object {$_.Trim()} } catch { 'Данные недоступны' }; ''")
    encoded = base64.b64encode("\n".join(script).encode("utf-16le")).decode()
    shell = Path(os.environ["SystemRoot"])/"System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            capture_output=True, timeout=50)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("Windows не вернула сведения CIM.")
    return result.stdout.decode("utf-8-sig", errors="replace").strip()


def cpu():
    block = b"a"*1_000_000
    expected = "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"
    start = time.monotonic()
    rounds = 0
    while time.monotonic()-start < 10:
        if hashlib.sha256(block).hexdigest() != expected:
            return "Ошибка: SHA-256 не совпал с эталоном."
        rounds += 1
    return f"Один поток: {rounds} вычислений SHA-256 за 10 с. Все совпали с эталоном."


def memory():
    size = 128*MIB
    buf = bytearray(size)
    for pattern in (b'\x55', b'\xaa', b'\x00', b'\xff'):
        reference = pattern*MIB
        for offset in range(0, size, MIB):
            buf[offset:offset+MIB] = reference
        for offset in range(0, size, MIB):
            if buf[offset:offset+MIB] != reference:
                return f"Несовпадение в блоке со смещением {offset}."
    return "128 МиБ памяти процесса: четыре шаблона записаны и прочитаны без расхождений."


def gpu():
    import gpu as renderer
    print("20 секунд. Осмотри вращающееся кольцо: есть ли мигание или полосы? Esc — остановить.")
    return renderer.run()


def save(history):
    folder = ROOT/"reports"
    folder.mkdir(exist_ok=True)
    path = folder/f"PC-Check_{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
    path.write_text("PC-Check USB 0.1\n\n"+"\n\n".join(history), encoding="utf-8-sig")
    return path


def main():
    tests = {"1": ("Характеристики ПК", inventory), "2": ("Видеокарта · 20 с", gpu),
             "3": ("Процессор · 10 с", cpu), "4": ("Оперативная память · 128 МиБ", memory)}
    history = []
    while True:
        print("\n  PC-CHECK USB   /   0.1\n  ──────────────────────────────────")
        for key, (name, _) in tests.items():
            print(f"  {key}   {name}")
        print("  5   Сохранить отчёт на флешку\n  0   Выход")
        key = input("\nВыбери номер › ").strip()
        if key == "0":
            break
        if key == "5":
            if not history:
                print("Сначала выбери проверку.")
                continue
            try:
                print("Сохранено:", save(history))
            except OSError as error:
                print("Не удалось записать отчёт:", error)
            continue
        if key not in tests:
            print("Введи цифру от 0 до 5.")
            continue
        name, action = tests[key]
        print("\n"+name+"…", flush=True)
        try:
            result = action()
        except KeyboardInterrupt:
            result = "Остановлено пользователем."
        except Exception as error:
            result = f"Проверка не завершена: {type(error).__name__}: {error}"
        print(result)
        history.append(f"{datetime.now():%d.%m.%Y %H:%M:%S} | {name}\n{result}")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        pass
