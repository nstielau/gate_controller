// Raster previews from the exact SVGs in a staged fabrication release.
import {chromium} from "@playwright/test";
import {readFile} from "node:fs/promises";
import {join} from "node:path";

const directory = process.argv[2];
if (!directory) throw new Error("Usage: node tools/render_featherwing.mjs RELEASE_DIR");
const browser = await chromium.launch();
try {
  for (const [stem, width] of [["drawbridge-silkscreen", 840], ["schematic", 1600]]) {
    const page = await browser.newPage();
    await page.setContent(await readFile(join(directory, `${stem}.svg`), "utf8"));
    await page.locator("svg").evaluate((svg, width) => {
      const {width: w, height: h} = svg.viewBox.baseVal;
      svg.setAttribute("width", width);
      svg.setAttribute("height", Math.round(width * h / w));
    }, width);
    // White paper makes the black single-color mark readable in file previews.
    await page.locator("svg").screenshot({path: join(directory, `${stem}.png`)});
    await page.close();
  }
} finally {
  await browser.close();
}
