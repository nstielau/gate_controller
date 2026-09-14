// Local IAM administration; never deployed as a browser API.
const {execFileSync} = require("node:child_process");
const {readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync} = require("node:fs");
const {resolve, join} = require("node:path");
const {tmpdir} = require("node:os");
const {randomBytes} = require("node:crypto");
const {Firestore} = require("../firebase/functions/node_modules/@google-cloud/firestore");
const {OAuth2Client} = require("../firebase/functions/node_modules/google-auth-library");
const {Storage} = require("../firebase/functions/node_modules/@google-cloud/storage");
const {hash, OWNER, validateManifest} = require("../firebase/functions/administration.cjs");
const ROOT = resolve(__dirname, ".."), PROJECT = "drawbridge-45487", BUCKET = PROJECT + "-firmware";
const [action, argument] = process.argv.slice(2);
if (!["seed-admin", "enroll", "import-release", "bucket-setup"].includes(action)) throw new Error("Usage: firmware_admin.cjs seed-admin | bucket-setup | enroll DEVICE_ID | import-release VERSION");
if (process.env.FIRESTORE_EMULATOR_HOST || process.env.FIREBASE_AUTH_EMULATOR_HOST || process.env.STORAGE_EMULATOR_HOST) throw new Error("Unset emulators before administering production.");
const cli = (command, args) => execFileSync(command, args, {cwd: ROOT, encoding: "utf8"});
async function main() {
  if (action === "bucket-setup") {
    // Fail if the name exists elsewhere; never adopt another project's bucket.
    try {
      const bucket = JSON.parse(cli("gcloud", ["storage", "buckets", "describe", "gs://" + BUCKET, "--format=json", "--account=" + OWNER]));
      const number = cli("gcloud", ["projects", "describe", PROJECT, "--format=value(projectNumber)", "--account=" + OWNER]).trim();
      if (String(bucket.projectNumber || bucket.project_number) !== number) throw new Error("Wrong bucket project");
    } catch (error) {
      if (!error.status) throw error;
      cli("gcloud", ["storage", "buckets", "create", "gs://" + BUCKET, "--project=" + PROJECT, "--location=us-east1", "--uniform-bucket-level-access", "--public-access-prevention", "--account=" + OWNER]);
    }
    cli("gcloud", ["storage", "buckets", "add-iam-policy-binding", "gs://" + BUCKET,
      "--member=serviceAccount:drawbridge-functions@" + PROJECT + ".iam.gserviceaccount.com", "--role=roles/storage.objectViewer", "--account=" + OWNER]);
    console.log("Private firmware bucket configured."); return;
  }
  const accessToken = cli("gcloud", ["auth", "print-access-token", "--account", OWNER]).trim();
  const authClient = new OAuth2Client(); authClient.setCredentials({access_token: accessToken});
  authClient.quotaProjectId = PROJECT;
  const db = new Firestore({projectId: PROJECT, authClient});
  try {
    if (action === "seed-admin") {
      await db.doc("admins/" + hash(OWNER)).set({email: OWNER, grantedBy: "project-iam", grantedAtMs: Date.now()});
      console.log("Nick is an administrator.");
    }
    if (action === "enroll") {
      if (!/^[a-z0-9-]{1,64}$/.test(argument || "")) throw new Error("Invalid device ID");
      const ref = db.doc("devices/" + argument);
      if (!(await ref.get()).exists) throw new Error("Create the device before enrollment.");
      const folder = join(ROOT, "artifacts/ota"); mkdirSync(folder, {recursive: true, mode: 0o700});
      const output = join(folder, argument + ".env"), token = randomBytes(32).toString("hex");
      // Exclusive creation avoids silently rotating a provisioned device.
      writeFileSync(output, `DEVICE_ID=${argument}\nOTA_TOKEN=${token}\n`, {flag: "wx", mode: 0o600});
      await db.runTransaction(async tx => {
        const device = (await tx.get(ref)).data();
        if (!device || device.otaCredentialHash) throw new Error("Already enrolled or device missing; explicit IAM revocation is required before rotation.");
        tx.update(ref, {otaCredentialHash: hash(token), firmwareTarget: {enabled: false, version: null, sequence: (device.firmwareTarget?.sequence || 0) + 1}});
      });
      console.log("Enrollment saved to ignored " + output + "; no target assigned. Provision over USB with make ota-provision.");
    }
    if (action === "import-release") {
      if (!/^\d+\.\d+\.\d+$/.test(argument || "")) throw new Error("Invalid version");
      const tag = "firmware-v" + argument;
      const release = JSON.parse(cli("gh", ["release", "view", tag, "--repo", "nstielau/gate_controller", "--json", "isDraft,isPrerelease,tagName"]));
      if (release.isDraft || release.isPrerelease || release.tagName !== tag) throw new Error("A published non-prerelease is required.");
      const commit = JSON.parse(cli("gh", ["api", "repos/nstielau/gate_controller/commits/" + tag])).sha;
      const temp = mkdtempSync(join(tmpdir(), "drawbridge-release-"));
      try {
        cli("gh", ["release", "download", tag, "--repo", "nstielau/gate_controller", "--dir", temp, "--pattern", "drawbridge.py", "--pattern", "manifest.json"]);
        const m = validateManifest(JSON.parse(readFileSync(join(temp, "manifest.json"), "utf8")));
        const bytes = readFileSync(join(temp, "drawbridge.py"));
        if (m.git_commit !== commit || m.app_version !== argument || m.size !== bytes.length || m.sha256 !== hash(bytes)) throw new Error("Release integrity mismatch");
        const source = JSON.parse(cli("gh", ["api", "repos/nstielau/gate_controller/contents/circuitpython/drawbridge.py?ref=" + commit]));
        if (source.encoding !== "base64" || !bytes.equals(Buffer.from(source.content, "base64"))) throw new Error("Release differs from tagged source");
        const storage = new Storage({projectId: PROJECT, authClient}), file = storage.bucket(BUCKET).file(m.artifact_object);
        try { await file.save(bytes, {resumable: false, validation: "crc32c", preconditionOpts: {ifGenerationMatch: 0}, metadata: {contentType: "text/plain", cacheControl: "private,max-age=31536000,immutable"}}); }
        catch (error) {
          if (error.code !== 412) throw error;
          if (hash((await file.download())[0]) !== m.sha256) throw new Error("Existing object mismatch");
        }
        const ref = db.doc("firmwareReleases/" + argument);
        await db.runTransaction(async tx => {
          const previous = await tx.get(ref);
          if (previous.exists) {
            if (JSON.stringify(validateManifest(previous.data())) !== JSON.stringify(m)) throw new Error("Release version is immutable");
          } else tx.create(ref, {...m, approved: true, importedAtMs: Date.now()});
        });
        console.log("Approved release " + argument + "; assign it from Administration after bench validation.");
      } finally { rmSync(temp, {recursive: true, force: true}); }
    }
  } finally { await db.terminate(); }
}
main().catch(() => { console.error("Firmware administration failed. Check IAM, arguments, and local enrollment/release files; credentials are not logged."); process.exitCode = 1; });
