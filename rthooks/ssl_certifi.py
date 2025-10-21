# Runtime hook: ensure TLS cert bundle is available in frozen builds
import os
import sys

def _set_cert_env():
    try:
        import certifi
        cacert = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", cacert)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", cacert)
    except Exception:
        # Fallback to PyInstaller extraction dir, if certifi isn't importable
        try:
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidate = os.path.join(meipass, "certifi", "cacert.pem")
                if os.path.exists(candidate):
                    os.environ.setdefault("SSL_CERT_FILE", candidate)
                    os.environ.setdefault("REQUESTS_CA_BUNDLE", candidate)
        except Exception:
            pass

_set_cert_env()