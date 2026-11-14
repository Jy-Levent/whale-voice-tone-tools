# -*- coding: utf-8 -*-
"""语音预设管理：列出 / 切换 / 校验。

用法（在 WhaleGirl 根目录执行）：
    python bridge/voice_preset.py list          列出所有预设
    python bridge/voice_preset.py show          看当前用的是哪套
    python bridge/voice_preset.py use irritable 切换预设

切换会同时做两件事：
  1. 把 data/voice-presets.json 的 active 改成该预设（标签规则，Python 侧读）
  2. 把该预设的 instructions 写进 data/voice-send.json（语气指令，启动器读）

写 voice-send.json 时按启动器的习惯做 ASCII 转义（非 ASCII 转成 \\uXXXX），
否则它可能读不进来 —— 这是实测踩过的坑。
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESET_PATH = os.path.join(ROOT, "data", "voice-presets.json")
SEND_PATH = os.path.join(ROOT, "data", "voice-send.json")


def read_json(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def escape_non_ascii(text):
    """模拟 .NET 序列化：非 ASCII 转成 \\uXXXX。"""
    return "".join(
        char if ord(char) < 0x80 else "\\u%04x" % ord(char)
        for char in text
    )


def cmd_list():
    data = read_json(PRESET_PATH)
    active = str(data.get("active") or "")
    for key, preset in (data.get("presets") or {}).items():
        mark = "*" if key == active else " "
        print("%s %-12s %-6s %s" % (mark, key, preset.get("name", ""), preset.get("desc", "")))
    print("\n* 表示当前生效")


def cmd_show():
    data = read_json(PRESET_PATH)
    active = str(data.get("active") or "")
    preset = (data.get("presets") or {}).get(active) or {}
    print("当前预设:", active, "|", preset.get("name", ""))
    print("说明:", preset.get("desc", ""))
    print("标签规则数:", len(preset.get("tags") or []))
    print()
    print("语气指令:", preset.get("instructions", ""))


def cmd_use(name):
    data = read_json(PRESET_PATH)
    presets = data.get("presets") or {}
    preset = presets.get(name)
    if not isinstance(preset, dict):
        print("没有这个预设:", name)
        print("可用:", ", ".join(presets.keys()))
        return 1

    # 1) 切 active
    data["active"] = name
    with open(PRESET_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    print("已切换标签规则 ->", name, "（重启 WhaleGirl 生效）")

    # 2) 同步语气指令到 voice-send.json
    instructions = str(preset.get("instructions") or "").strip()
    if not instructions:
        print("这套预设没写 instructions，只改了标签规则")
        return 0
    try:
        send = read_json(SEND_PATH)
    except (OSError, ValueError) as exc:
        print("读不到 voice-send.json，跳过语气指令同步:", exc)
        return 0
    send["Instructions"] = instructions
    profile = (send.get("Profiles") or {}).get(str(send.get("Provider") or "breezeblue"))
    if isinstance(profile, dict):
        profile["Instructions"] = instructions
    with open(SEND_PATH, "w", encoding="ascii") as handle:
        handle.write(escape_non_ascii(json.dumps(send, ensure_ascii=False)))
    print("已写入语气指令 -> voice-send.json（%d 字符）" % len(instructions))
    return 0


def cmd_test(text, preset_name=None):
    """试一句话，看会不会插标签、插哪个、被哪条规则命中。改完规则用它验证。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import voice_reply

    data = read_json(PRESET_PATH)
    active = preset_name or str(data.get("active") or "")
    preset = (data.get("presets") or {}).get(active) or {}
    if preset_name and not preset:
        print("没有这个预设:", preset_name)
        print("可用:", ", ".join((data.get("presets") or {}).keys()))
        return 1

    result = voice_reply.add_audio_tags(text, root=ROOT)
    print("预设:", active, "|", preset.get("name", ""))
    print("原句:", text)
    print("结果:", result if result != text else text + "   ← 没有匹配，原样输出")

    # 找出是哪条规则命中的，方便对规则表
    for item in preset.get("tags") or []:
        compiled = voice_reply._compile_rule(item)
        if not compiled:
            continue
        pattern, tag = compiled
        match = pattern.search(text)
        if match:
            print()
            print("命中规则:", item.get("when", "(未命名)"))
            print("  标签:", tag)
            print("  匹配到:", repr(match.group(0)))
            print("  规则原文:", item.get("pattern") or item.get("words"))
            return 0
    print()
    print("没有任何规则命中 —— 想让它有反应，就在对应预设的 tags 里加这个词")
    return 0


def cmd_ui(start_port=8789):
    """起一个本机小服务，浏览器打开可视化编辑器。

    页面从 127.0.0.1 加载，所以读写文件由本进程代劳（浏览器不再需要授权目录）。
    只绑回环地址，不对外网开放；Ctrl+C 停止。
    """
    import http.server
    import json as _json
    import socket
    import threading
    import webbrowser

    editor = os.path.join(ROOT, "tools", "voice-preset-editor.html")
    if not os.path.exists(editor):
        print("找不到编辑器页面:", editor)
        print("请确认 tools/voice-preset-editor.html 已随补丁一起放好")
        return 1

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "WhaleVoicePreset/1.0"

        def log_message(self, fmt, *args):
            pass  # 不刷屏

        def _reply(self, code, payload, ctype="application/json; charset=utf-8"):
            body = payload.encode("utf-8") if isinstance(payload, str) else payload
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _fail(self, code, message):
            self._reply(code, _json.dumps({"error": str(message)}, ensure_ascii=False))

        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html", "/editor"):
                    with open(editor, encoding="utf-8") as handle:
                        self._reply(200, handle.read(), "text/html; charset=utf-8")
                elif path == "/api/presets":
                    self._reply(200, _json.dumps(read_json(PRESET_PATH), ensure_ascii=False))
                elif path == "/api/voice-send":
                    send = read_json(SEND_PATH)
                    self._reply(200, _json.dumps({
                        "instructions": send.get("Instructions") or "",
                        "model": send.get("Model") or "",
                        "voice": send.get("Voice") or "",
                        "enabled": send.get("Enabled") is True,
                    }, ensure_ascii=False))
                else:
                    self._fail(404, "not found")
            except (OSError, ValueError) as exc:
                self._fail(500, exc)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 2 * 1024 * 1024:
                self._fail(400, "bad body")
                return
            path = self.path.split("?")[0]
            try:
                payload = _json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                self._fail(400, "JSON 解析失败: %s" % exc)
                return
            try:
                if path == "/api/presets":
                    if not isinstance(payload, dict) or not isinstance(payload.get("presets"), dict):
                        self._fail(400, "缺少 presets 字段")
                        return
                    with open(PRESET_PATH, "w", encoding="utf-8") as handle:
                        _json.dump(payload, handle, ensure_ascii=False, indent=2)
                    self._reply(200, _json.dumps({"ok": True}, ensure_ascii=False))
                elif path == "/api/apply-instructions":
                    text = str(payload.get("instructions") or "").strip()
                    send = read_json(SEND_PATH)
                    send["Instructions"] = text
                    profile = (send.get("Profiles") or {}).get(str(send.get("Provider") or "breezeblue"))
                    if isinstance(profile, dict):
                        profile["Instructions"] = text
                    with open(SEND_PATH, "w", encoding="ascii") as handle:
                        handle.write(escape_non_ascii(_json.dumps(send, ensure_ascii=False)))
                    self._reply(200, _json.dumps({"ok": True, "length": len(text)}, ensure_ascii=False))
                else:
                    self._fail(404, "not found")
            except (OSError, ValueError) as exc:
                self._fail(500, exc)

    handler, port = None, 0
    for candidate in range(start_port, start_port + 20):
        try:
            handler = http.server.ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if handler is None:
        print("端口 %d~%d 都被占了，换个端口再试" % (start_port, start_port + 19))
        return 1

    url = "http://127.0.0.1:%d/" % port
    print("语音预设编辑器已启动：", url)
    print("关掉这个窗口（或按 Ctrl+C）就停止。")
    if os.environ.get("WHALE_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        handler.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        handler.server_close()
    return 0


def main(argv):
    if not os.path.exists(PRESET_PATH):
        print("找不到预设文件:", PRESET_PATH)
        return 1
    action = (argv[1] if len(argv) > 1 else "list").lower()
    try:
        if action == "list":
            cmd_list()
        elif action == "show":
            cmd_show()
        elif action == "use":
            if len(argv) < 3:
                print("用法: python bridge/voice_preset.py use <预设名>")
                return 1
            return cmd_use(argv[2])
        elif action == "test":
            if len(argv) < 3:
                print("用法: python bridge/voice_preset.py test \"一句话\" [预设名]")
                return 1
            return cmd_test(argv[2], argv[3] if len(argv) > 3 else None)
        elif action in ("ui", "editor", "web"):
            port = 8789
            if len(argv) > 2 and argv[2].isdigit():
                port = int(argv[2])
            return cmd_ui(port)
        else:
            print("用法: python bridge/voice_preset.py [list|show|use <name>|test \"一句话\"|ui]")
            return 1
    except (OSError, ValueError) as exc:
        print("预设文件有问题:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
