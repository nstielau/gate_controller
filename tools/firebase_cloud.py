"""Configure Drawbridge with the signed-in gcloud account; never print secrets."""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

from env_config import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "drawbridge-45487"
ACCOUNT = "nick.stielau@gmail.com"
APP = "1:498911170567:web:67d0d78cf97be687c85aa2"
NUMBER = "498911170567"


class Cloud:
    def __init__(self):
        self.token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token", "--account", ACCOUNT], text=True
        ).strip()

    def call(self, url, method="GET", data=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
            "x-goog-user-project": PROJECT,
        })
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)

    def status(self):
        endpoints = {
            "Google sign-in": (f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/defaultSupportedIdpConfigs/google.com", lambda d: {"enabled": d.get("enabled", False)}),
            "Auth domains": (f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config", lambda d: {"domains": d.get("authorizedDomains", [])}),
            "Firestore": (f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases", lambda d: {"databases": [{"name": x["name"], "location": x.get("locationId")} for x in d.get("databases", [])]}),
            "App Check": (f"https://firebaseappcheck.googleapis.com/v1/projects/{NUMBER}/apps/{APP}/recaptchaEnterpriseConfig", lambda d: {"siteKey": d.get("siteKey")}),
        }
        for label, (url, summary) in endpoints.items():
            try:
                print(label + ": " + json.dumps(summary(self.call(url))))
            except urllib.error.HTTPError as error:
                print(f"{label}: HTTP {error.code} (not configured or unavailable)")

    def appcheck(self):
        url = f"https://recaptchaenterprise.googleapis.com/v1/projects/{PROJECT}/keys"
        keys = self.call(url).get("keys", [])
        key = next((k for k in keys if k.get("displayName") == "Drawbridge App Check"), None)
        if key is None:
            key = self.call(url, "POST", {"displayName": "Drawbridge App Check", "webSettings": {
                "allowedDomains": [f"{PROJECT}.web.app", f"{PROJECT}.firebaseapp.com"],
                "allowAllDomains": False, "integrationType": "SCORE",
            }})
        site_key = key["name"].rsplit("/", 1)[1]
        config = f"projects/{NUMBER}/apps/{APP}/recaptchaEnterpriseConfig"
        self.call(f"https://firebaseappcheck.googleapis.com/v1/{config}?updateMask=siteKey,tokenTtl", "PATCH", {
            "name": config, "siteKey": site_key, "tokenTtl": "3600s",
        })
        (ROOT / "web/app-check-config.js").write_text(
            "// Public reCAPTCHA Enterprise site key.\nexport const appCheckSiteKey = "
            + json.dumps(site_key) + ";\n"
        )
        print("App Check registered; public site key written to web/app-check-config.js")

    def secrets(self):
        env = load_dotenv(ROOT / ".env")
        values = {name: env.get(name, "") for name in ("MQTT_USERNAME", "MQTT_PASSWORD")}
        values["MQTT_CA_PEM"] = (ROOT / "emqxsl-ca.crt").read_text()
        if not all(values.values()) or "BEGIN CERTIFICATE" not in values["MQTT_CA_PEM"]:
            raise ValueError("Missing MQTT credentials or CA")
        for name, value in values.items():
            url = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/{name}"
            try:
                self.call(url)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                self.call(url.rsplit("/", 1)[0] + "?secretId=" + name, "POST", {"replication": {"automatic": {}}})
            try:
                latest = self.call(url + "/versions/latest:access")
                if base64.b64decode(latest["payload"]["data"]).decode() == value:
                    print(name + ": already current")
                    continue
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
            self.call(url + ":addVersion", "POST", {"payload": {"data": base64.b64encode(value.encode()).decode()}})
            print(name + ": uploaded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "appcheck", "secrets"])
    args = parser.parse_args()
    try:
        getattr(Cloud(), args.action)()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Google API returned HTTP {error.code}; check project services and account access.") from None


if __name__ == "__main__":
    main()
