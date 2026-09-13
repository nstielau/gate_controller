# Drawbridge loader artwork

The loader reuses `web/drawbridge-castle-128.png` without repainting the castle.
The original bridge is clipped from that image and animated using an affine
projection about its fixed hinge. Chain endpoints follow the moving edge.
Only a small masked area behind the original bridge/chains uses new pixels,
from `web/drawbridge-loader-background.png`. The rest stays the original image.

The background patch was prepared using the built-in image generation/editing
tool, then resized to the original 128-pixel canvas for use in the SVG. The
generated image's outer background is never used. The original icon remains
unchanged, and reduced-motion mode shows that unmodified original.

Final image-edit prompt:

> Use case: precise-object-edit. Edit target is the attached 128x128 pixel-art castle app icon. Create a clean background layer for animating its existing wooden drawbridge. REMOVE ONLY the movable brown wooden drawbridge across the center doorway, and its two diagonal suspension chains. Fill the tiny exposed region with the existing stone threshold/doorway behind it and blue moat beneath it. Keep the fixed arched doorway and inner vertical wooden door. Preserve EVERYTHING else exactly: original pixel clusters, low-resolution detail, original proportions, original 128x128 coordinate framing, tower silhouettes and positions, wall textures, grass, ground, water, light, palette, camera and margins. This must look like the same literal source icon with only bridge and suspension chains erased and inpainted. Do not upscale into new detail or redesign the castle. Output a single square image with original transparent margins if possible. No grid or checkerboard pattern. No text. Intended output is a background patch used only behind the original moving bridge; matching source pixel coordinate alignment is essential.

Rebuild the SVG with `node tools/build_loader_artwork.mjs` (also runs during
`make web-build`). Rebuild the GIF preview with `node tools/render_loader_gif.mjs`.
The renderer embeds the same SVG used by the app and samples a full cycle at
fixed timestamps. It captures at 60 fps and exports a four-second GIF at 50 fps
(an exact 20 ms frame interval), with a generated palette to preserve the colors.
It also writes a live SVG HTML preview beside the GIF for native browser playback.

The deck uses an explicit scale/shear animation in coordinates aligned to the
hinge. This avoids CSS matrix decomposition flips when the deck passes edge-on.
The 120 animation intervals follow a cosine motion profile, slowing smoothly
at both endpoints. Only the moving deck texture is filtered for subpixel motion;
the fixed castle retains its original pixel rendering.
