const EXPOSE_PATCH = "return o?r?.[n(63)]?ce({so:o,c:r[n(63)]},t):o:null},t.token=ye,t}({});";
const EXPOSE_REPLACEMENT =
  "return o?r?.[n(63)]?ce({so:o,c:r[n(63)]},t):o:null},t.token=ye,t.__debug_n=_n,t.__debug_bindProof=D,t}({});";
const INSTANCE_PATCH = "var P=new _;";
const INSTANCE_REPLACEMENT = "var P=new _;globalThis.__debugP=P;";
const SDK_GLOBAL_PATCH = "var SentinelSDK=";
const SDK_GLOBAL_REPLACEMENT = "globalThis.SentinelSDK=";

function bytesToBase64(bytes) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out = "";
  let i = 0;
  while (i < bytes.length) {
    const b0 = bytes[i++] || 0;
    const b1 = bytes[i++] || 0;
    const b2 = bytes[i++] || 0;
    const n = (b0 << 16) | (b1 << 8) | b2;
    out += chars[(n >> 18) & 63];
    out += chars[(n >> 12) & 63];
    out += i - 2 < bytes.length ? chars[(n >> 6) & 63] : "=";
    out += i - 1 < bytes.length ? chars[n & 63] : "=";
  }
  return out;
}

function base64ToBytes(base64) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const clean = String(base64 || "").replace(/[^A-Za-z0-9+/=]/g, "");
  const bytes = [];
  for (let i = 0; i < clean.length; i += 4) {
    const c0 = chars.indexOf(clean[i]);
    const c1 = chars.indexOf(clean[i + 1]);
    const c2 = chars.indexOf(clean[i + 2]);
    const c3 = chars.indexOf(clean[i + 3]);
    const n = ((c0 & 63) << 18) | ((c1 & 63) << 12) | (((c2 < 0 ? 0 : c2) & 63) << 6) | ((c3 < 0 ? 0 : c3) & 63);
    bytes.push((n >> 16) & 255);
    if (clean[i + 2] !== "=") bytes.push((n >> 8) & 255);
    if (clean[i + 3] !== "=") bytes.push(n & 255);
  }
  return bytes;
}

function createStorage() {
  const map = new Map();
  return {
    get length() {
      return map.size;
    },
    clear() {
      map.clear();
    },
    getItem(key) {
      return map.has(String(key)) ? map.get(String(key)) : null;
    },
    setItem(key, value) {
      map.set(String(key), String(value));
    },
    removeItem(key) {
      map.delete(String(key));
    },
  };
}

function createElement(tagName) {
  const tag = String(tagName || "div").toLowerCase();
  return {
    nodeType: 1,
    tagName: tag.toUpperCase(),
    nodeName: tag.toUpperCase(),
    style: {},
    children: [],
    src: "",
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      this.children = this.children.filter((x) => x !== child);
      return child;
    },
    setAttribute() {},
    getAttribute() {
      return null;
    },
    addEventListener() {},
    removeEventListener() {},
    getBoundingClientRect() {
      return { x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 };
    },
  };
}

function installRuntime(payload) {
  const screen = {
    width: Number(payload.screen_width || 1366),
    height: Number(payload.screen_height || 768),
    availWidth: Number(payload.screen_width || 1366),
    availHeight: Number(payload.screen_height || 768),
    colorDepth: 24,
    pixelDepth: 24,
  };
  const scripts = [];
  const documentElement = createElement("html");
  documentElement.clientWidth = screen.width;
  documentElement.clientHeight = screen.height;
  const document = {
    readyState: "complete",
    hidden: false,
    visibilityState: "visible",
    referrer: "https://auth.openai.com/",
    URL: "https://auth.openai.com/",
    cookie: `oai-did=${encodeURIComponent(payload.device_id || "")}`,
    scripts,
    currentScript: { src: "https://sentinel.openai.com/sentinel/sdk.js", getAttribute() { return null; } },
    documentElement,
    body: createElement("body"),
    head: createElement("head"),
    createElement(tag) {
      const el = createElement(tag);
      if (String(tag).toLowerCase() === "script") scripts.push(el);
      return el;
    },
    createElementNS(_ns, tag) {
      return this.createElement(tag);
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    getElementById() {
      return null;
    },
    getElementsByTagName() {
      return [];
    },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return true;
    },
  };

  const performance = {
    now: () => Number(payload.performance_now || 12345.67),
    timeOrigin: Number(payload.time_origin || 1710000000000),
    memory: { jsHeapSizeLimit: Number(payload.js_heap_size_limit || 4294967296) },
  };

  class TextEncoderPoly {
    encode(text) {
      const str = String(text || "");
      const out = new Uint8Array(str.length);
      for (let i = 0; i < str.length; i += 1) out[i] = str.charCodeAt(i) & 255;
      return out;
    }
  }

  class TextDecoderPoly {
    decode(input) {
      if (!input) return "";
      let out = "";
      for (let i = 0; i < input.length; i += 1) {
        out += String.fromCharCode(input[i]);
      }
      return out;
    }
  }

  class URLSearchParamsPoly {
    constructor(search) {
      this._pairs = [];
      const s = String(search || "").replace(/^\?/, "");
      if (!s) return;
      const parts = s.split("&");
      for (const p of parts) {
        if (!p) continue;
        const i = p.indexOf("=");
        if (i < 0) {
          this._pairs.push([decodeURIComponent(p), ""]);
        } else {
          this._pairs.push([
            decodeURIComponent(p.slice(0, i)),
            decodeURIComponent(p.slice(i + 1)),
          ]);
        }
      }
    }
    keys() {
      return this._pairs.map((x) => x[0])[Symbol.iterator]();
    }
  }

  class URLPoly {
    constructor(input, base) {
      const raw = String(input || "");
      if (/^https?:\/\//i.test(raw)) {
        this.href = raw;
      } else {
        const b = String(base || "https://auth.openai.com/").replace(/\/$/, "");
        this.href = `${b}/${raw.replace(/^\//, "")}`;
      }
      const m = this.href.match(/^(https?:)\/\/([^\/]+)(\/[^?#]*)?(\?[^#]*)?(#.*)?$/i);
      this.protocol = m ? m[1] : "https:";
      this.host = m ? m[2] : "auth.openai.com";
      this.hostname = this.host;
      this.pathname = m && m[3] ? m[3] : "/";
      this.search = m && m[4] ? m[4] : "";
      this.hash = m && m[5] ? m[5] : "";
      this.origin = `${this.protocol}//${this.host}`;
    }
    toString() {
      return this.href;
    }
  }

  globalThis.window = globalThis;
  globalThis.self = globalThis;
  globalThis.top = globalThis;
  globalThis.parent = globalThis;
  globalThis.document = document;
  globalThis.navigator = {
    userAgent: String(payload.user_agent || "Mozilla/5.0"),
    language: String(payload.language || "zh-CN"),
    languages: Array.isArray(payload.languages) ? payload.languages : ["zh-CN", "zh"],
    hardwareConcurrency: Number(payload.hardware_concurrency || 12),
    platform: "Win32",
    vendor: "Google Inc.",
    webdriver: false,
  };
  globalThis.location = {
    href: "https://auth.openai.com/",
    origin: "https://auth.openai.com",
    pathname: "/",
    search: "",
  };
  globalThis.screen = screen;
  globalThis.performance = performance;
  globalThis.localStorage = createStorage();
  globalThis.sessionStorage = createStorage();
  globalThis.__sentinel_init_pending = [];
  globalThis.__sentinel_token_pending = [];

  globalThis.setTimeout = (cb) => {
    if (typeof cb === "function") cb();
    return 1;
  };
  globalThis.clearTimeout = () => {};
  globalThis.setInterval = () => 1;
  globalThis.clearInterval = () => {};
  globalThis.requestIdleCallback = (cb) => {
    if (typeof cb === "function") cb({ didTimeout: false, timeRemaining: () => 50 });
    return 1;
  };
  globalThis.cancelIdleCallback = () => {};
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  globalThis.dispatchEvent = () => true;
  globalThis.postMessage = () => {};

  globalThis.atob = (input) => String.fromCharCode(...base64ToBytes(input));
  globalThis.btoa = (input) => {
    const str = String(input || "");
    const bytes = [];
    for (let i = 0; i < str.length; i += 1) bytes.push(str.charCodeAt(i) & 255);
    return bytesToBase64(bytes);
  };
  globalThis.TextEncoder = globalThis.TextEncoder || TextEncoderPoly;
  globalThis.TextDecoder = globalThis.TextDecoder || TextDecoderPoly;
  globalThis.URL = globalThis.URL || URLPoly;
  globalThis.URLSearchParams = globalThis.URLSearchParams || URLSearchParamsPoly;
  globalThis.Event =
    globalThis.Event ||
    class Event {
      constructor(type) {
        this.type = type;
      }
    };
  globalThis.CustomEvent =
    globalThis.CustomEvent ||
    class CustomEvent extends globalThis.Event {
      constructor(type, init) {
        super(type);
        this.detail = init && Object.prototype.hasOwnProperty.call(init, "detail") ? init.detail : null;
      }
    };
  globalThis.MessageChannel =
    globalThis.MessageChannel ||
    class MessageChannel {
      constructor() {
        this.port1 = { postMessage() {}, addEventListener() {}, removeEventListener() {}, start() {}, close() {} };
        this.port2 = { postMessage() {}, addEventListener() {}, removeEventListener() {}, start() {}, close() {} };
      }
    };
  globalThis.matchMedia =
    globalThis.matchMedia ||
    ((query) => ({
      media: String(query || ""),
      matches: false,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent() {
        return false;
      },
    }));
  globalThis.getComputedStyle =
    globalThis.getComputedStyle ||
    (() => ({
      getPropertyValue() {
        return "";
      },
    }));
  globalThis.history = globalThis.history || { length: 1, state: null, back() {}, forward() {}, go() {}, pushState() {}, replaceState() {} };
  globalThis.chrome = globalThis.chrome || { runtime: {}, app: {} };
  globalThis.CSS = globalThis.CSS || { supports() { return true; } };
  globalThis.indexedDB =
    globalThis.indexedDB ||
    {
      open() {
        return { onerror: null, onsuccess: null, onupgradeneeded: null, result: {}, error: null };
      },
      deleteDatabase() {
        return {};
      },
    };
  globalThis.fetch = async () => {
    throw new Error("fetch should not be called");
  };

  const randomFill = (arr) => {
    for (let i = 0; i < arr.length; i += 1) {
      arr[i] = Math.floor(Math.random() * 256);
    }
    return arr;
  };
  globalThis.crypto = {
    randomUUID: globalThis.crypto && typeof globalThis.crypto.randomUUID === "function"
      ? globalThis.crypto.randomUUID.bind(globalThis.crypto)
      : undefined,
    getRandomValues: randomFill,
  };
}

function loadPatchedSdk(sdkSource) {
  let sdk = String(sdkSource || "");
  sdk = sdk.replace(SDK_GLOBAL_PATCH, SDK_GLOBAL_REPLACEMENT);
  sdk = sdk.replace(INSTANCE_PATCH, INSTANCE_REPLACEMENT);
  sdk = sdk.replace(EXPOSE_PATCH, EXPOSE_REPLACEMENT);
  eval(sdk);
}

async function run(payload, sdkSource) {
  installRuntime(payload);
  loadPatchedSdk(sdkSource);

  if (payload.action === "requirements") {
    const requestP = await globalThis.__debugP.getRequirementsToken();
    return { request_p: requestP };
  }

  if (payload.action === "solve") {
    const challenge = payload.challenge || {};
    const requestP = String(payload.request_p || "").trim();
    if (!requestP) throw new Error("missing request_p");
    const finalP = await globalThis.__debugP.getEnforcementToken(challenge);
    globalThis.SentinelSDK.__debug_bindProof(challenge, requestP);
    const dx = challenge && challenge.turnstile ? challenge.turnstile.dx : null;
    const tValue = dx ? await globalThis.SentinelSDK.__debug_n(challenge, dx) : null;
    return { final_p: finalP, t: tValue };
  }

  throw new Error(`unsupported action: ${payload.action}`);
}

(async () => {
  try {
    const payload = JSON.parse(String(globalThis.__payload_json || "{}"));
    const sdkSource = String(globalThis.__sdk_source || "");
    const result = await run(payload, sdkSource);
    globalThis.__vm_output_json = JSON.stringify(result);
  } catch (error) {
    const detail = {
      name: error && error.name ? String(error.name) : "Error",
      message: error && error.message ? String(error.message) : String(error),
      stack: error && error.stack ? String(error.stack) : String(error),
    };
    const message = `${detail.name}: ${detail.message}\n${detail.stack}`;
    globalThis.__vm_error = message;
  } finally {
    globalThis.__vm_done = true;
  }
})();
