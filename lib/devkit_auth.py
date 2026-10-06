"""Access tokens with roles. Only SHA-256 hashes are stored; a token's plaintext is shown once, at creation."""
import hashlib, hmac, json, os, secrets, threading, time

ROLES = ("viewer", "operator", "admin")  # each role includes everything the previous one may do
TOKEN_PREFIX = "dk_"
TOUCH_INTERVAL = 60  # seconds between persisted last_used updates per token
OWNER = {"id": "owner", "name": "Owner", "role": "admin"}


def allows(role, needed):
    return ROLES.index(role) >= ROLES.index(needed)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class TokenStore:
    def __init__(self, path, owner_token):
        self.path, self.owner_digest, self.lock = path, digest(owner_token), threading.Lock()
        self.tokens = self._load()

    def _load(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def _save(self):
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self.tokens, f, indent=1)
        os.replace(tmp, self.path)

    def verify(self, token):
        """Returns {id, name, role} for a valid token, else None. Constant-time comparison per candidate."""
        if not token:
            return None
        d = digest(token)
        if hmac.compare_digest(d, self.owner_digest):
            return dict(OWNER)
        with self.lock:
            for t in self.tokens:
                if hmac.compare_digest(d, t["hash"]):
                    if time.time() - t.get("last_used", 0) > TOUCH_INTERVAL:
                        t["last_used"] = time.time()
                        self._save()
                    return {"id": t["id"], "name": t["name"], "role": t["role"]}
        return None

    def create(self, name, role, created_by):
        name = (name or "").strip()[:60]
        if not name:
            raise ValueError("a token needs a name")
        if role not in ROLES:
            raise ValueError("role must be one of: " + ", ".join(ROLES))
        plain = TOKEN_PREFIX + secrets.token_urlsafe(32)
        rec = {"id": secrets.token_hex(6), "name": name, "role": role, "hash": digest(plain), "created": time.time(),
               "created_by": created_by, "last_used": 0}
        with self.lock:
            self.tokens.append(rec)
            self._save()
        return self.public(rec), plain

    def revoke(self, token_id):
        with self.lock:
            before = len(self.tokens)
            self.tokens = [t for t in self.tokens if t["id"] != token_id]
            if len(self.tokens) == before:
                raise ValueError("no such token")
            self._save()

    @staticmethod
    def public(t):
        return {k: t.get(k) for k in ("id", "name", "role", "created", "created_by", "last_used")}

    def list(self):
        with self.lock:
            return [dict(OWNER, created=None, created_by=None, last_used=None, builtin=True)] + [self.public(t) for t in self.tokens]
