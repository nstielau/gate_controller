# Firebase TLS trust roots

`google-roots.pem` contains the public GTS Root R1, R2, R3 and R4 certificates,
downloaded on 2026-09-14 from Google's HTTPS certificate repository:

- https://pki.goog/repo/certs/gtsr1.pem
- https://pki.goog/repo/certs/gtsr2.pem
- https://pki.goog/repo/certs/gtsr3.pem
- https://pki.goog/repo/certs/gtsr4.pem

The OTA HTTP client explicitly loads these roots and verifies the Firebase
hostname. The tested CircuitPython 10.3.0 built-in certificate bundle failed
Firebase validation; explicitly loading these roots succeeded. These are public
certificates, not credentials. Deploy and update them through USB, independently
of application releases. Never replace them with a server's short-lived leaf
certificate or disable TLS verification to work around a trust failure.

The separate MQTT CA is supplied from the ignored repository-root
`emqxsl-ca.crt`; it is not part of this public bundle.
