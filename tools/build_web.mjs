import {build} from "esbuild";
import {readFile, writeFile, mkdir, rm, copyFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import {gzipSync} from "node:zlib";
const test = process.argv.includes("--test");
const out = test ? ".artifacts/web-test" : "web/dist";
if (!test) {
  for (const file of ["web/firebase-config.js", "web/app-check-config.js"]) {
    const text = await readFile(file, "utf8");
    if (text.includes("replace-me")) throw new Error("Configure " + file + " before building");
  }
}
await rm(out, {recursive: true, force: true});
await mkdir(out + "/assets", {recursive: true});
const result = await build({
  entryPoints: ["web/app.js", "web/styles.css"], outdir: out + "/assets",
  entryNames: "[name]-[hash]", bundle: true, minify: true, format: "esm",
  target: ["safari16", "chrome100"], metafile: true,
  ...(test ? {plugins: [{name: "test-gateway", setup(build) {
    build.onResolve({filter: /^\.\/gateway\.js$/}, () => ({path: "/gateway.js", external: true}));
  }}]} : {})
});
const outputs = Object.keys(result.metafile.outputs);
const js = "/" + outputs.find(p => p.endsWith(".js")).slice(out.length + 1);
const css = "/" + outputs.find(p => p.endsWith(".css")).slice(out.length + 1);
const html = (await readFile("web/index.html", "utf8")).replace("/app.js", js).replace("/styles.css", css);
await writeFile(out + "/index.html", html);
await copyFile("web/manifest.webmanifest", out + "/manifest.webmanifest");
await copyFile("web/drawbridge-castle-128.png", out + "/assets/drawbridge-castle.png");
for (const size of [192, 512]) await copyFile(`web/icons/castle-${size}.png`, `${out}/castle-${size}.png`);
if (test) await copyFile("web/test/gateway.js", out + "/gateway.js");
const assets = ["/", "/index.html", js, css, "/assets/drawbridge-castle.png", "/castle-192.png", "/castle-512.png", "/manifest.webmanifest", ...(test ? ["/gateway.js"] : [])];
const sw = await readFile("web/service-worker.js", "utf8");
const digest = createHash("sha256").update(sw);
for (const path of assets.filter(p => p !== "/")) digest.update(await readFile(out + path));
const release = digest.digest("hex").slice(0, 16);
await writeFile(out + "/service-worker.js", sw.replace("__RELEASE__", release).replace("__ASSETS__", JSON.stringify(assets)));
const bundle = await readFile(out + js);
console.log("Built " + out + "; JavaScript " + Math.round(bundle.length / 1024) + " KiB (" + Math.round(gzipSync(bundle).length / 1024) + " KiB gzip), release " + release);
