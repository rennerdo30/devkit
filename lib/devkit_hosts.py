"""Other devkit servers this one can reach. Requests are forwarded at most one hop (no relaying through peers)."""
import json, sys, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

PLATFORM = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
TARGET_PLATFORM = {"ios": "macos", "ios-sim": "macos", "macos": "macos", "windows": "windows", "linux": "linux"}
HOP_HEADER = "X-Devkit-Hop"
STATUS_TTL = 3
PING_TIMEOUT = 3
CALL_TIMEOUT = 60
MAX_PEERS = 32


class PeerError(Exception):
    pass


class Peers:
    def __init__(self, read_config, write_config, self_name):
        self.read_config, self.write_config, self.self_name = read_config, write_config, self_name
        self.lock, self.cache = threading.Lock(), (0, [])
        self.pool = ThreadPoolExecutor(max_workers=8)

    def all(self):
        return list(self.read_config().get("peers") or [])

    def get(self, name):
        for p in self.all():
            if p["name"] == name:
                return p
        raise PeerError("no such host: %s" % name)

    def call(self, peer, method, path, body=None, query=None, timeout=CALL_TIMEOUT, client="devkit"):
        """Forward one request; returns (status, content_type, bytes)."""
        try:
            with self.open(peer, method, path, body, query, timeout, client) as r:
                return r.status, r.headers.get("Content-Type", "application/json"), r.read()
        except (urllib.error.URLError, OSError) as e:
            raise PeerError("%s is not reachable: %s" % (peer["name"], getattr(e, "reason", e)))

    def open(self, peer, method, path, body=None, query=None, timeout=CALL_TIMEOUT, client="devkit", range_header=None):
        """Forward one request; caller closes the response."""
        url = peer["url"].rstrip("/") + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + peer["token"], "Content-Type": "application/json", HOP_HEADER: "1",
            "X-Devkit-Client": client})
        if range_header is not None:
            req.add_header("Range", range_header)
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            return e
        except (urllib.error.URLError, OSError) as e:
            raise PeerError("%s is not reachable: %s" % (peer["name"], getattr(e, "reason", e)))

    def call_json(self, peer, method, path, body=None, query=None, client="devkit"):
        status, _, data = self.call(peer, method, path, body, query, client=client)
        out = json.loads(data or b"{}")
        if status >= 400:
            raise PeerError("%s: %s" % (peer["name"], out.get("error", status)))
        return out

    def ping(self, url, token):
        try:
            return self.call_json({"name": url, "url": url, "token": token}, "GET", "/api/ping")
        except (PeerError, ValueError) as e:
            raise PeerError(str(e))

    def add(self, url, token):
        url = url.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        info = self.ping(url, token)
        name = info.get("name") or info.get("host")
        if name == self.self_name:
            raise PeerError("that is this server")
        cfg = self.read_config()
        peers = [p for p in cfg.get("peers") or [] if p["name"] != name and p["url"] != url]
        if len(peers) >= MAX_PEERS:
            raise PeerError("too many hosts")
        peers.append({"name": name, "url": url, "token": token, "added": time.time()})
        cfg["peers"] = peers
        self.write_config(cfg)
        self.cache = (0, [])
        return {"name": name, "url": url, "platform": info.get("platform")}

    def remove(self, name):
        cfg = self.read_config()
        peers = [p for p in cfg.get("peers") or [] if p["name"] != name]
        if len(peers) == len(cfg.get("peers") or []):
            raise PeerError("no such host: %s" % name)
        cfg["peers"] = peers
        self.write_config(cfg)
        self.cache = (0, [])

    def status(self):
        """Live state of every peer (cached for a few seconds)."""
        with self.lock:
            if time.time() - self.cache[0] < STATUS_TTL:
                return self.cache[1]
        def one(p):
            base = {"name": p["name"], "url": p["url"], "self": False}
            try:
                info = self.call_json(p, "GET", "/api/ping")
                return dict(base, online=True, **{k: info.get(k) for k in ("platform", "host", "macos", "chip", "xcode", "queue_len", "running", "kinds", "targets", "version")})
            except (PeerError, ValueError) as e:
                return dict(base, online=False, error=str(e))
        out = list(self.pool.map(one, self.all()))
        with self.lock:
            self.cache = (time.time(), out)
        return out

    def route(self, target, self_info):
        """Pick a host for a job: matching platform, shortest queue, this host on ties. Returns None for this host."""
        want = TARGET_PLATFORM.get(target or "", PLATFORM)
        cands = [dict(self_info, self=True, online=True)] + [h for h in self.status() if h.get("online")]
        cands = [h for h in cands if h.get("platform") == want]
        if not cands:
            raise PeerError("no online host runs %s jobs" % want)
        best = min(cands, key=lambda h: (h.get("queue_len") or 0, not h["self"]))
        return None if best["self"] else best["name"]
