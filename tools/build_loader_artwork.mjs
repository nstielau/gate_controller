// Reuse the actual icon pixels. Only the bridge and suspension chains move.
import {readFile, writeFile} from "node:fs/promises";

const original = (await readFile("web/drawbridge-castle-128.png")).toString("base64");
const background = (await readFile("web/drawbridge-loader-background.png")).toString("base64");
const hinge = [54, 77];
export const duration = 4;
const intervals = 120;
// Isometric projection: hinge axis (20,8) stays fixed; the free edge lifts.
const poses = Array.from({length: intervals + 1}, (_, index) => {
  const angle = (1 - Math.cos(index / intervals * 2 * Math.PI)) * Math.PI / 4;
  const vx = -20 * Math.cos(angle), vy = 16 * Math.cos(angle) - 28 * Math.sin(angle);
  const a = (340 + 8 * vx) / 260, b = (136 + 8 * vy) / 260;
  const c = -(200 + 20 * vx) / 260, d = -(80 + 20 * vy) / 260;
  return [a, b, c, d, hinge[0] - a * hinge[0] - c * hinge[1], hinge[1] - b * hinge[0] - d * hinge[1]];
});
const fixed = value => Number(value.toFixed(4));
// Animate explicit scale/shear in the hinge basis. Interpolating CSS matrices
// decomposes them into rotations and can flip abruptly as the deck goes edge-on.
const keyframes = poses.map(([a,b,c,d],index) => {
  const vx = -10*a -17*c, vy = -10*b -17*d;
  const shear = (-17*vx +10*vy)/-260;
  const scale = (20*vy -8*vx)/-260;
  return `${fixed(index/intervals*100)}% {transform:scaleY(${fixed(scale)}) skewX(${fixed(Math.atan(shear)*180/Math.PI)}deg)}`;
}).join("\n");
const coordinate = (point, axis) => poses.map(([a,b,c,d,e,f]) => fixed(axis === 0 ? a*point[0]+c*point[1]+e : b*point[0]+d*point[1]+f)).join(";");
const chain = (anchor, tip) => `<g>
  ${["stroke='#332e39' stroke-width='1.6'", "stroke='#aaa098' stroke-width='.65' stroke-dasharray='1 1'"].map(style => `<line x1='${anchor[0]}' y1='${anchor[1]}' ${style}>
    <animate attributeName='x2' values='${coordinate(tip,0)}' dur='${duration}s' repeatCount='indefinite'/>
    <animate attributeName='y2' values='${coordinate(tip,1)}' dur='${duration}s' repeatCount='indefinite'/>
  </line>`).join("")}</g>`;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <title>Drawbridge loading</title>
  <style>image { image-rendering:pixelated } .bridge image { image-rendering:auto } .bridge { animation:lift ${duration}s linear infinite; transform-origin:0 0 } @keyframes lift { ${keyframes} } @media(prefers-reduced-motion:reduce) { .motion { display:none } }</style>
  <defs>
    <image id="original" width="128" height="128" href="data:image/png;base64,${original}"/>
    <clipPath id="bridge"><path d="M43 59L67 69L75 84L73 87L53 79L43 63Z"/></clipPath>
    <clipPath id="revealed"><path d="M42 58L66 67L76 82L76 88L52 80L42 64Z M42 59L46 62L60 38L55 37Z M65 69L70 74L82 47L77 45Z"/></clipPath>
  </defs>
  <use href="#original"/>
  <g class="motion">
    <image width="128" height="128" href="data:image/png;base64,${background}" clip-path="url(#revealed)"/>
    <g transform="translate(54 77) matrix(20 8 -10 -17 0 0)">
      <g class="bridge">
        <g id="bridge-texture" transform="matrix(${[17/260,8/260,-10/260,-20/260,0,0].join(' ')}) translate(-54 -77)">
          <image width="128" height="128" href="data:image/png;base64,${original}" clip-path="url(#bridge)"/>
        </g>
      </g>
    </g>
    ${chain([57,40],[44,60])}
    ${chain([79,48],[67,70])}
  </g>
</svg>`;
await writeFile("web/drawbridge-loader.svg", svg);
console.log("Built loader SVG with original castle/bridge pixels and a masked background patch.");
