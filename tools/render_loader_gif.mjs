// Capture a complete, deterministically timed loop from the app's actual artwork.
import {chromium} from "@playwright/test";
import {mkdir, mkdtemp, readFile, rm, writeFile} from "node:fs/promises";
import {dirname, join} from "node:path";
import {tmpdir} from "node:os";
import {execFileSync} from "node:child_process";
import {duration} from "./build_loader_artwork.mjs";

const output = process.argv[2] || "artifacts/drawbridge-loader.gif";
await mkdir(dirname(output), {recursive: true});
const frames = await mkdtemp(join(tmpdir(), "drawbridge-loader-"));
const html = await readFile("web/index.html", "utf8");
const css = await readFile("web/styles.css", "utf8");
const loader = html.match(/<section id="loading-state"[\s\S]*?<\/section>/)?.[0];
if (!loader) throw new Error("Could not find the loading-state markup");
const artwork = await readFile("web/drawbridge-loader.svg", "utf8");
const preview = output.replace(/\.gif$/, ".html");
const previewHTML = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Drawbridge loading preview</title><style>${css}.drawbridge-loader svg{width:100%;height:100%}</style><main>${loader.replace(/<img[^>]+>/, artwork)}</main></html>`;
const captureFPS = 60;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({viewport: {width: 480, height: 600}, deviceScaleFactor: 1});
  await page.setContent(previewHTML);
  await page.evaluate(async () => {
    await Promise.all([...document.querySelectorAll("svg image")].map(async element => {
      const image = new Image(); image.src = element.getAttribute("href"); await image.decode();
    }));
    document.querySelector("svg").pauseAnimations();
    document.getAnimations().forEach(animation => animation.pause());
  });
  for (let frame = 0; frame < duration * captureFPS; frame += 1) {
    await page.evaluate(time => {
      document.querySelector("svg").setCurrentTime(time / 1000);
      document.getAnimations().forEach(animation => { animation.currentTime = time; });
    }, frame / captureFPS * 1000);
    await page.screenshot({path: join(frames, `frame-${String(frame).padStart(3, "0")}.png`)});
  }
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-framerate", String(captureFPS),
    "-i", join(frames, "frame-%03d.png"), "-filter_complex",
    "fps=50,split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=none", "-loop", "0", output]);
  await writeFile(preview, previewHTML);
  console.log(`Rendered full ${duration}-second up/down loop at 50 fps: ${output}; live SVG preview: ${preview}`);
} finally {
  await browser.close();
  await rm(frames, {recursive: true, force: true});
}
