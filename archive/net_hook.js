const mod = Process.getModuleByName("GameAssembly.dll");
const BASE = mod.base;

console.log("[+] GameAssembly base =", BASE);

function addr(rva) {
    return BASE.add(ptr(rva));
}

function readIl2CppString(p) {
    if (p.isNull()) return null;
    try {
        const len = p.add(0x10).readS32();
        return p.add(0x14).readUtf16String(len);
    } catch (_) {
        return null;
    }
}

function readByteArrayAsUtf8(arr, maxLen = 1024 * 1024) {
    if (arr.isNull()) return null;
    try {
        const len = arr.add(0x18).readU32();
        if (len <= 0 || len > maxLen) return null;

        const data = arr.add(0x20);
        const bytes = data.readByteArray(len);
        return new TextDecoder("utf-8").decode(bytes);
    } catch (_) {
        return null;
    }
}

function hookRva(name, rva, cb) {
    const p = addr(rva);
    console.log("[+] hook", name, p);
    Interceptor.attach(p, cb);
}

function isJsonText(s) {
    if (!s) return false;
    s = s.trim();
    return s.startsWith("{") || s.startsWith("[");
}

function printPacket(tag, s) {
    if (!isJsonText(s)) return;
    console.log("\n== " + tag + " ==");
    console.log(s.trim());
}

function getFrameText(fr) {
    try {
        // WebSocketFrameReader.DataAsText offset = 0x18
        const textPtr = fr.add(0x18).readPointer();
        const text = readIl2CppString(textPtr);
        if (isJsonText(text)) return text;

        // fallback: WebSocketFrameReader.Data offset = 0x10
        const dataPtr = fr.add(0x10).readPointer();
        const dataText = readByteArrayAsUtf8(dataPtr);
        if (isJsonText(dataText)) return dataText;

        return null;
    } catch (_) {
        return null;
    }
}

// SEND: BestHTTP.WebSocket.WebSocket.Send(string)
// RVA: 0x88C280
hookRva("SEND WebSocket.Send(string)", 0x88C280, {
    onEnter(args) {
        printPacket("SEND", readIl2CppString(args[1]));
    }
});

// RECV: only after DecodeWithExtensions
// WebSocketFrameReader.DecodeWithExtensions(WebSocket webSocket)
// RVA: 0x8A5CC0
hookRva("RECV FrameReader.DecodeWithExtensions", 0x8A5CC0, {
    onEnter(args) {
        this.fr = args[0];
    },
    onLeave(_) {
        const s = getFrameText(this.fr);
        printPacket("RECV", s);
    }
});
