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
  for (const size of [192, 512]) {
    const encoded = await page.evaluate(async ({data, size}) => {
      const img = new Image();
      img.src = data;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = size;
      const context = canvas.getContext("2d");
      context.fillStyle = "#f3f4eb";
      context.fillRect(0, 0, size, size);
      context.imageSmoothingEnabled = false;
      // Keep the complete castle inside a maskable icon's central safe circle.
      const inset = Math.round(size * .22);
      context.drawImage(img, inset, inset, size - 2 * inset, size - 2 * inset);
      return canvas.toDataURL("image/png").split(",")[1];
    }, {data, size});
    await writeFile(new URL(`castle-${size}.png`, destination), Buffer.from(encoded, "base64"));
  }
} finally { await browser.close(); }
console.log("Exported castle home-screen icons at 192 and 512 pixels.");
