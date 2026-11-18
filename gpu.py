"""Visible OpenGL compatibility workload through Windows system libraries."""
import ctypes as c
import math
import time
from ctypes import wintypes as w


class PixelFormat(c.Structure):
    _fields_ = ([("size", w.WORD), ("version", w.WORD), ("flags", w.DWORD)]
                + [(name, c.c_ubyte) for name in
                   "pixel_type color red red_shift green green_shift blue blue_shift alpha alpha_shift accum accum_red accum_green accum_blue accum_alpha depth stencil aux layer reserved".split()]
                + [(name, w.DWORD) for name in ("layer_mask", "visible", "damage")])


def run():
    user, gdi, gl = [c.WinDLL(n, use_last_error=True) for n in
                     ("user32", "gdi32", "opengl32")]
    ptr, uint, integer, real = c.c_void_p, c.c_uint, c.c_int, c.c_float

    def bind(dll, name, result, *args):
        fn = getattr(dll, name)
        fn.restype, fn.argtypes = result, args
        return fn

    window = bind(user, "CreateWindowExW", ptr, uint, w.LPCWSTR, w.LPCWSTR,
                  uint, integer, integer, integer, integer, ptr, ptr, ptr, ptr)
    get_dc = bind(user, "GetDC", ptr, ptr)
    release_dc = bind(user, "ReleaseDC", integer, ptr, ptr)
    destroy = bind(user, "DestroyWindow", integer, ptr)
    peek = bind(user, "PeekMessageW", integer, c.POINTER(w.MSG), ptr, uint, uint, uint)
    dispatch = bind(user, "DispatchMessageW", c.c_ssize_t, c.POINTER(w.MSG))
    escape = bind(user, "GetAsyncKeyState", c.c_short, integer)
    choose = bind(gdi, "ChoosePixelFormat", integer, ptr, c.POINTER(PixelFormat))
    set_format = bind(gdi, "SetPixelFormat", integer, ptr, integer, c.POINTER(PixelFormat))
    swap = bind(gdi, "SwapBuffers", integer, ptr)
    context = bind(gl, "wglCreateContext", ptr, ptr)
    current = bind(gl, "wglMakeCurrent", integer, ptr, ptr)
    delete = bind(gl, "wglDeleteContext", integer, ptr)
    for name, result, args in [
        ("glGetString", c.c_char_p, [uint]), ("glNewList", None, [uint, uint]),
        ("glEndList", None, []), ("glBegin", None, [uint]), ("glEnd", None, []),
        ("glVertex3f", None, [real]*3), ("glColor3f", None, [real]*3),
        ("glClearColor", None, [real]*4), ("glClear", None, [uint]),
        ("glEnable", None, [uint]), ("glDisable", None, [uint]),
        ("glViewport", None, [integer]*4), ("glLoadIdentity", None, []),
        ("glRotatef", None, [real]*4), ("glCallList", None, [uint]),
        ("glScissor", None, [integer]*4), ("glGetError", uint, []),
        ("glReadPixels", None, [integer]*4+[uint,uint,ptr])]:
        bind(gl, name, result, *args)
    hwnd = window(0, "STATIC", "PC-Check GPU", 0x90000000, 80, 80,
                  480, 480, None, None, None, None)
    dc = rc = None
    try:
        if not hwnd:
            raise OSError("Windows не открыла окно теста")
        dc = get_dc(hwnd)
        fmt = PixelFormat(size=c.sizeof(PixelFormat), version=1, flags=0x25,
                          color=24, depth=16)
        index = choose(dc, c.byref(fmt))
        if not index or not set_format(dc, index, c.byref(fmt)):
            raise OSError("Недоступен формат окна OpenGL")
        rc = context(dc)
        if not rc or not current(dc, rc):
            raise OSError("Не удалось запустить OpenGL")
        renderer = (gl.glGetString(0x1F01) or b"unknown").decode(errors="replace")
        print("Активный рендерер:", renderer, flush=True)
        if any(s in renderer.lower() for s in ("gdi generic","llvmpipe","softpipe","swiftshader","software","unknown")):
            return f"Тест пропущен: программный или неизвестный рендерер ({renderer})."
        gl.glViewport(0, 0, 480, 480)
        gl.glEnable(0x0B71)  # depth test
        gl.glNewList(1, 0x1300)
        for i in range(128):
            gl.glBegin(0x0005)  # triangle strip
            for j in range(65):
                v = math.tau*j/64
                for k in (i, i+1):
                    u = math.tau*k/128
                    r = .58 + .24*math.cos(v)
                    gl.glColor3f(.45+.4*math.cos(u), .55+.4*math.sin(v), .85)
                    gl.glVertex3f(r*math.cos(u), r*math.sin(u), .24*math.sin(v))
            gl.glEnd()
        gl.glEndList()
        start = time.monotonic()
        frames = 0
        pixel = (c.c_ubyte*4)()
        msg = w.MSG()
        while time.monotonic()-start < 20:
            while peek(c.byref(msg), hwnd, 0, 0, 1):
                if msg.message in (0x10, 0x12) or (msg.message == 0x104 and msg.wParam == 0x73):
                    return f"{renderer}: остановлено пользователем."
                dispatch(c.byref(msg))
            if escape(27) & 0x8000:
                return f"{renderer}: остановлено пользователем."
            gl.glClearColor(.04, .06, .10, 1)
            gl.glClear(0x4100)
            gl.glLoadIdentity()
            gl.glRotatef((time.monotonic()-start)*90, .7, 1, .3)
            gl.glCallList(1)
            # Verify a changing corner marker before swapping the back buffer.
            gl.glEnable(0x0C11)
            gl.glScissor(0, 0, 4, 4)
            red = frames % 2
            gl.glClearColor(red, 1-red, 0, 1)
            gl.glClear(0x4000)
            gl.glDisable(0x0C11)
            gl.glReadPixels(1, 1, 1, 1, 0x1908, 0x1401, pixel)
            if gl.glGetError() or tuple(pixel[:3]) != (255*red, 255*(1-red), 0):
                return f"{renderer}: ошибка OpenGL или несовпадение контрольного пикселя."
            if not swap(dc):
                raise OSError("Сбой вывода кадра")
            frames += 1
        return (f"{renderer}: {frames} кадров, {frames/(time.monotonic()-start):.1f} кадр/с. "
                "Контрольный пиксель совпал во всех кадрах.")
    finally:
        if rc:
            current(None, None)
            delete(rc)
        if dc:
            release_dc(hwnd, dc)
        if hwnd:
            destroy(hwnd)
