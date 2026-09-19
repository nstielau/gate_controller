// Regenerate install icons from the existing castle artwork: node tools/export_castle_icons.mjs
import {chromium} from "@playwright/test";
import {mkdir, readFile, writeFile} from "node:fs/promises";
const source = new URL("../web/drawbridge-castle-128.png", import.meta.url);
const destination = new URL("../web/icons/", import.meta.url);
const data = "data:image/png;base64," + (await readFile(source)).toString("base64");
await mkdir(destination, {recursive: true});
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const icons = [
    {name: "castle-192.png", size: 192, padding: .04},
    {name: "castle-512.png", size: 512, padding: .04},
    {name: "castle-maskable-512.png", size: 512, padding: .22}
  ];
  for (const {name, size, padding} of icons) {
    const encoded = await page.evaluate(async ({data, size, padding}) => {
      const img = new Image();
      img.src = data;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = size;
      const context = canvas.getContext("2d");
      context.fillStyle = "#f3f4eb";
      context.fillRect(0, 0, size, size);
      context.imageSmoothingEnabled = false;
      // The artwork has its own transparent border. Use a small extra inset for
      // iOS/ordinary icons; only the separate maskable icon needs a safe circle.
      const inset = Math.round(size * padding);
      context.drawImage(img, inset, inset, size - 2 * inset, size - 2 * inset);
      return canvas.toDataURL("image/png").split(",")[1];
    }, {data, size, padding});
    await writeFile(new URL(name, destination), Buffer.from(encoded, "base64"));
  }
} finally { await browser.close(); }
console.log("Exported larger 192/512 pixel home-screen icons and a separate maskable icon.");
